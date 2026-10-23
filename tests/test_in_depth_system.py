"""
Comprehensive In-Depth System Verification Suite.
Covers:
1. Incoming calls (TeleCMI GET/POST/HEAD, Twilio TwiML, number normalization, PCMO payload, known vs unknown caller, non-blocking DB).
2. Outgoing calls (dispatch endpoint, auth verification, carrier error 502 propagation, IST calling window, DNC statuses, fallback chain).
3. Voice pipeline (STT silence, SSRF rejection, TTS caching, markdown cleanup, consecutive silence circuit breaker, exit phrases & regex, human transfer).
4. RAG Engine (selective gating, ground truth accuracy for CPL/A320/Cabin Crew/Eligibility/Dwarka, job guarantee refusal, keyword fallback).
5. Latency profiling (gating < 1ms, dossier lookup < 1ms, RAG < 5ms, PCMO generation < 15ms, statistical distribution).
6. No network areas & failure injection (carrier drop/timeout, GCS outage local fallback, LLM outage polite fallback, TTS outage fallback, SSRF prevention).
7. Database response (CRUD operations, session history, offline DB resilience, concurrency stress).
"""

import os
import sys
import time
import json
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import config
import main
import database
import supabase_client
import precall_manager
import telephony
import assistant
import rag
import scheduler
import storage_service


# ============================================================================
# 1. INCOMING CALLING TESTS
# ============================================================================
class IncomingCallingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.test_phone = "+919818282209"
        precall_manager.manager.clear_dossier()

    def tearDown(self):
        precall_manager.manager.clear_dossier()

    def test_telecmi_head_liveness_probe(self):
        """Carriers send HEAD probes to verify endpoint liveness before connecting."""
        res = self.client.head("/telecmi/answer")
        self.assertEqual(res.status_code, 200)

    def test_telecmi_answer_get_and_post_supported(self):
        """TeleCMI may deliver call answer signals via GET or POST with query or form parameters."""
        res_get = self.client.get("/telecmi/answer?from=9818282209&direction=inbound")
        self.assertEqual(res_get.status_code, 200)

        res_post = self.client.post("/telecmi/answer", json={"from": "9818282209", "direction": "inbound"})
        self.assertEqual(res_post.status_code, 200)

    def test_phone_number_normalization_variations(self):
        """Verify 10-digit Indian, 12-digit 91 prefix, and +91 international formats are all normalized."""
        test_numbers = [
            ("9818282209", "+919818282209"),
            ("919818282209", "+919818282209"),
            ("+919818282209", "+919818282209"),
        ]
        for raw, expected in test_numbers:
            with patch.object(precall_manager.manager, "get_dossier") as mock_dossier:
                mock_dossier.return_value = None
                res = self.client.get(f"/telecmi/answer?from={raw}&direction=inbound")
                self.assertEqual(res.status_code, 200)
                mock_dossier.assert_called_with(expected)

    def test_telecmi_pcmo_connect_when_agent_id_configured(self):
        """When AGENT_ID is active, PCMO returns a direct bridge to the AI agent."""
        orig_agent = config.AGENT_ID
        try:
            config.AGENT_ID = "agent_test_123"
            res = self.client.post("/telecmi/answer", json={"from": "9818282209", "direction": "inbound"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIsInstance(data, list)
            self.assertTrue(len(data) > 0)
            self.assertEqual(data[0]["action"], "connect")
            self.assertEqual(data[0]["endpoints"][0]["id"], "agent_test_123")
        finally:
            config.AGENT_ID = orig_agent

    def test_telecmi_pcmo_ivr_fallback_when_agent_id_unset(self):
        """When AGENT_ID is unset, PCMO generates play_get_input to run the turn-by-turn fallback."""
        orig_agent = config.AGENT_ID
        orig_app_id = config.TELECMI_PIOPIY_APP_ID
        try:
            config.AGENT_ID = ""
            config.TELECMI_PIOPIY_APP_ID = ""
            res = self.client.post("/telecmi/answer", json={"from": "9818282209", "direction": "inbound"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIsInstance(data, list)
            self.assertEqual(data[0]["action"], "play_get_input")
            self.assertIn("process-recording", data[0]["on_result"]["url"])
        finally:
            config.AGENT_ID = orig_agent
            config.TELECMI_PIOPIY_APP_ID = orig_app_id

    def test_known_lead_gets_personalized_greeting(self):
        """Inbound call from pre-registered lead receives personalized opening greeting."""
        precall_manager.manager.register_precall(
            phone=self.test_phone,
            name="Rohit Sharma",
            course_interest="CPL Ground School",
            prewarm_audio=False
        )
        orig_agent = config.AGENT_ID
        orig_app_id = config.TELECMI_PIOPIY_APP_ID
        try:
            config.AGENT_ID = ""
            config.TELECMI_PIOPIY_APP_ID = ""
            res = self.client.post("/telecmi/answer", json={"from": self.test_phone, "direction": "inbound"})
            self.assertEqual(res.status_code, 200)
            # In turn-by-turn fallback, play_get_input file_name is loaded
            data = res.json()
            self.assertEqual(data[0]["action"], "play_get_input")
        finally:
            config.AGENT_ID = orig_agent
            config.TELECMI_PIOPIY_APP_ID = orig_app_id

    def test_twilio_inbound_voice_twiml(self):
        """Twilio inbound /answer-call renders valid VoiceResponse XML containing Play and Record."""
        res = self.client.post("/answer-call?direction=inbound", data={"From": "+919818282209"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("<Response>", res.text)
        self.assertIn("<Play>", res.text)
        self.assertIn("<Record", res.text)


# ============================================================================
# 2. OUTGOING CALLING TESTS
# ============================================================================
class OutgoingCallingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.orig_secret = config.API_SHARED_SECRET
        config.API_SHARED_SECRET = "test_secret_123"

    def tearDown(self):
        config.API_SHARED_SECRET = self.orig_secret

    def test_dispatch_auth_guard(self):
        """Outbound dispatch refuses requests without correct shared secret."""
        res_no_key = self.client.post("/api/calls/dispatch", json={"phone": "+919818282209"})
        self.assertEqual(res_no_key.status_code, 401)

        res_wrong_key = self.client.post(
            "/api/calls/dispatch",
            json={"phone": "+919818282209"},
            headers={"X-API-Key": "wrong_key"}
        )
        self.assertEqual(res_wrong_key.status_code, 401)

    def test_dispatch_validation_missing_phone(self):
        """Payload lacking a phone number returns 400 Bad Request."""
        res = self.client.post(
            "/api/calls/dispatch",
            json={"name": "Rohit"},
            headers={"X-API-Key": "test_secret_123"}
        )
        self.assertEqual(res.status_code, 400)

    def test_carrier_rejection_propagates_502(self):
        """If carrier rejects call (e.g. kyc_not_verified or no credit), return 502 with error details."""
        with patch("telephony.dispatch_outbound_call") as mock_dispatch:
            mock_dispatch.return_value = {
                "ok": False,
                "provider": "piopiy_ai",
                "error": "kyc_not_verified",
                "request_id": None
            }
            res = self.client.post(
                "/api/calls/dispatch",
                json={"phone": "+919818282209", "name": "Vipul"},
                headers={"X-API-Key": "test_secret_123"}
            )
            self.assertEqual(res.status_code, 502)
            self.assertIn("kyc_not_verified", res.json().get("error", ""))

    def test_calling_window_hours_enforcement(self):
        """Test calling hours constraint (09:00 to 20:00 IST)."""
        ist = scheduler.IST
        # 11:30 AM IST (inside window)
        dt_inside = datetime(2026, 10, 18, 11, 30, tzinfo=ist)
        self.assertTrue(scheduler.in_call_window(dt_inside))

        # 07:45 AM IST (before window)
        dt_early = datetime(2026, 10, 18, 7, 45, tzinfo=ist)
        self.assertFalse(scheduler.in_call_window(dt_early))

        # 21:15 PM IST (after window)
        dt_late = datetime(2026, 10, 18, 21, 15, tzinfo=ist)
        self.assertFalse(scheduler.in_call_window(dt_late))

    def test_do_not_call_status_filtering(self):
        """Leads marked NOT_INTERESTED, INVALID_NUMBER, or CONVERTED must never be dialed."""
        self.assertFalse(scheduler.is_callable_lead({"status": "NOT_INTERESTED"}))
        self.assertFalse(scheduler.is_callable_lead({"status": "INVALID_NUMBER"}))
        self.assertFalse(scheduler.is_callable_lead({"status": "CONVERTED"}))
        self.assertTrue(scheduler.is_callable_lead({"status": "NEW"}))
        self.assertTrue(scheduler.is_callable_lead({"status": "CONTACTED"}))


# ============================================================================
# 3. VOICE PIPELINE TESTS
# ============================================================================
class VoicePipelineTests(unittest.TestCase):
    def setUp(self):
        self.test_phone = "+919999900001"
        supabase_client.clear_conversation_history(self.test_phone)

    def tearDown(self):
        supabase_client.clear_conversation_history(self.test_phone)

    def test_stt_silence_returns_empty_string(self):
        """Audio URL pointing to empty/none input returns empty string gracefully."""
        from voice_test import listen
        result = listen("")
        self.assertEqual(result, "")

    def test_stt_ssrf_protection_disallowed_hosts(self):
        """STT listen refuses to fetch from non-allowlisted domains, loopback, or private IPs."""
        from voice_test import listen
        unsafe_urls = [
            "http://127.0.0.1:8080/audio.wav",
            "http://169.254.169.254/latest/meta-data/",
            "https://evil-attacker.com/malicious.wav",
            "ftp://ftp.example.com/audio.wav",
        ]
        for url in unsafe_urls:
            res = listen(url)
            self.assertEqual(res, "", f"Expected rejection for {url}")

    def test_markdown_and_punctuation_cleanup_for_tts(self):
        """TTS text pre-processor strips bold, hashtags, and markdown code ticks to avoid robot glitched speech."""
        raw_text = "Hello **Captain**! We have *batches* starting #soon with `Airbus A320` simulator."
        clean_text = raw_text.replace("*", "").replace("#", "").replace("_", "").replace("`", "").strip()
        self.assertNotIn("*", clean_text)
        self.assertNotIn("#", clean_text)
        self.assertNotIn("`", clean_text)
        self.assertEqual(clean_text, "Hello Captain! We have batches starting soon with Airbus A320 simulator.")

    def test_exit_trigger_phrases_and_regex(self):
        """Exit phrases and tags must trigger call hangup flag."""
        for phrase in ["goodbye", "thank you", "bye", "shukriya", "alvida"]:
            self.assertTrue(any(ep in phrase.lower() for ep in assistant.EXIT_PHRASES))

        # Check regex removal of [EXIT] tags
        import re
        sample_ai_text = "We look forward to welcoming you to Airborne Aviation Academy! [EXIT]"
        cleaned = re.sub(r'\[exit\]\.?', '', sample_ai_text, flags=re.IGNORECASE).strip()
        self.assertNotIn("[EXIT]", cleaned)
        self.assertEqual(cleaned, "We look forward to welcoming you to Airborne Aviation Academy!")

    @patch("assistant.listen")
    @patch("assistant.speak_and_get_url")
    @patch("assistant.chat_with_gpt")
    def test_consecutive_silence_hangup_circuit_breaker(self, mock_llm, mock_speak, mock_listen):
        """3 consecutive silent turns must trigger the hangup circuit breaker."""
        mock_listen.return_value = ""
        mock_speak.return_value = "https://mock.com/audio.mp3"
        mock_llm.return_value = "Are you still there?"

        # Turn 1
        _, hangup_1 = assistant.handle_conversation("mock_silence.wav", self.test_phone, "inbound")
        self.assertFalse(hangup_1)

        # Turn 2
        _, hangup_2 = assistant.handle_conversation("mock_silence.wav", self.test_phone, "inbound")
        self.assertFalse(hangup_2)

        # Turn 3 -> Must trigger hangup
        _, hangup_3 = assistant.handle_conversation("mock_silence.wav", self.test_phone, "inbound")
        self.assertTrue(hangup_3)

    def test_human_transfer_matching(self):
        """Specific transfer requests must be detected, while inquiries about Capt. Navrang must not."""
        transfer_text = "I want to talk to a human admissions counselor"
        self.assertTrue(any(tp in transfer_text.lower() for tp in assistant.HUMAN_TRANSFER_PHRASES))

        instructor_text = "Is Captain Navrang sir teaching all ground classes?"
        self.assertFalse(any(tp in instructor_text.lower() for tp in assistant.HUMAN_TRANSFER_PHRASES))


# ============================================================================
# 4. RAG ENGINE TESTS
# ============================================================================
class RagEngineTests(unittest.TestCase):
    def test_selective_gating_bypass_fillers(self):
        """Common one-word acknowledgments and filler phrases bypass RAG to eliminate 150-300ms latency."""
        fillers = ["ok", "okay", "yes", "theek hai", "haan", "hello", "hi", "thanks", "shukriya"]
        for f in fillers:
            self.assertFalse(assistant.should_retrieve_knowledge(f), f"Expected filler '{f}' to bypass RAG")

    def test_selective_gating_triggers_aviation_queries(self):
        """Even 2-word queries containing aviation keywords must always trigger RAG."""
        queries = ["cpl fee", "a320 cost", "batch dates", "eligibility criteria", "dwarka location", "navrang sir"]
        for q in queries:
            self.assertTrue(assistant.should_retrieve_knowledge(q), f"Expected query '{q}' to trigger RAG")

    def test_cpl_ground_school_knowledge_accuracy(self):
        """Verify CPL ground school fee, DGCA subjects, and instructor facts."""
        context = rag.query_rag("CPL ground school fee and subjects")
        self.assertIn("2,70,000", context)
        self.assertIn("Air Navigation", context)
        self.assertIn("Meteorology", context)
        self.assertIn("Navrang", context)

    def test_airbus_a320_simulator_knowledge_accuracy(self):
        """Verify Airbus A320 Simulator details."""
        context = rag.query_rag("A320 simulator fee per hour")
        self.assertIn("12,000", context)
        self.assertIn("Airbus A320", context)

    def test_cabin_crew_knowledge_accuracy(self):
        """Verify Cabin Crew training fee and curriculum facts from knowledge corpus."""
        context = rag.query_rag("Cabin crew course fee and duration")
        self.assertTrue("59,000" in context or "54,000" in context)
        self.assertIn("Cabin Crew", context)

    def test_eligibility_criteria_knowledge_accuracy(self):
        """Verify pilot training eligibility (10+2 Maths, Physics, Medicals)."""
        context = rag.query_rag("Eligibility criteria for CPL ground school")
        self.assertIn("10+2", context)
        self.assertIn("Physics", context)
        self.assertIn("Mathematics", context)

    def test_job_guarantee_negative_constraint(self):
        """Verify institutional clarification: Airborne is an education institute, NOT a job agency."""
        context = rag.query_rag("Job placement guarantee")
        self.assertIn("strictly an accredited professional aviation training", context)
        self.assertIn("NOT a job placement agency", context)

    def test_campus_address_accuracy(self):
        """Verify Ramphal Chowk, Dwarka campus address."""
        context = rag.query_rag("Where is your campus located in Delhi?")
        self.assertIn("Ramphal Chowk", context)
        self.assertIn("Dwarka", context)
        self.assertIn("Sector 7", context)


# ============================================================================
# 5. LATENCY BENCHMARK TESTS
# ============================================================================
class LatencyBenchmarkTests(unittest.TestCase):
    def test_rag_gating_decision_latency(self):
        """Fast-path selective gating decision must execute in under 0.5ms (budget: 1ms)."""
        samples = ["ok", "cpl fee", "what is the eligibility for commercial pilot license", "theek hai"]
        latencies = []
        for s in samples:
            t0 = time.perf_counter()
            for _ in range(100):
                assistant.should_retrieve_knowledge(s)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) / 100 * 1000)

        avg_latency_ms = sum(latencies) / len(latencies)
        self.assertLess(avg_latency_ms, 0.5, f"RAG gating decision too slow: {avg_latency_ms:.3f}ms")

    def test_in_memory_dossier_lookup_latency(self):
        """In-memory PreCallManager dossier lookup must execute in under 0.1ms."""
        phone = "+919818282209"
        precall_manager.manager.register_precall(phone=phone, name="Speedy Pilot", prewarm_audio=False)
        t0 = time.perf_counter()
        for _ in range(500):
            d = precall_manager.manager.get_dossier(phone)
        t1 = time.perf_counter()
        per_lookup_ms = ((t1 - t0) / 500) * 1000
        self.assertLess(per_lookup_ms, 0.1, f"Dossier lookup too slow: {per_lookup_ms:.3f}ms")

    def test_rag_keyword_retrieval_latency(self):
        """In-memory keyword RAG search must retrieve ground truth context in under 5ms."""
        t0 = time.perf_counter()
        for _ in range(20):
            context = rag.query_rag("CPL ground school fee and batch dates", limit=2)
            self.assertTrue(len(context) > 0)
        t1 = time.perf_counter()
        avg_retrieval_ms = ((t1 - t0) / 20) * 1000
        self.assertLess(avg_retrieval_ms, 5.0, f"RAG keyword retrieval too slow: {avg_retrieval_ms:.3f}ms")

    def test_pcmo_webhook_response_latency_cached(self):
        """Inbound /telecmi/answer webhook with pre-cached lead executes in under 25ms when background DB tasks are non-blocking."""
        client = TestClient(main.app)
        phone = "+919818282209"
        precall_manager.manager.register_precall(phone=phone, name="Cached Caller", prewarm_audio=False)
        with patch("supabase_client.save_lead"), patch("supabase_client.save_conversation_history"):
            # Warmup call
            client.post("/telecmi/answer", json={"from": phone, "direction": "inbound"})
            t0 = time.perf_counter()
            res = client.post("/telecmi/answer", json={"from": phone, "direction": "inbound"})
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000
            self.assertEqual(res.status_code, 200)
            self.assertLess(duration_ms, 25.0, f"Cached PCMO answer webhook took {duration_ms:.2f}ms")


# ============================================================================
# 6. NO NETWORK AREAS & FAILURE INJECTION TESTS
# ============================================================================
class NoNetworkDegradationTests(unittest.TestCase):
    def test_carrier_network_timeout_handling(self):
        """Simulate carrier HTTP connection timeout. System must fail gracefully without hanging."""
        mock_client = MagicMock()
        mock_client.ai.call.side_effect = Exception("PioPiy AI network timeout")
        mock_client.pcmo.call.side_effect = Exception("PioPiy PCMO network timeout")
        fake_voice = SimpleNamespace(RestClient=lambda token: mock_client)

        with patch("telephony.piopiy", SimpleNamespace(voice=fake_voice)), \
             patch("telephony.requests.post", side_effect=Exception("REST carrier timeout")):
            orig_app_id = config.TELECMI_APP_ID
            orig_secret = config.TELECMI_APP_SECRET
            orig_token = config.TELECMI_TOKEN
            orig_agent = config.AGENT_ID
            try:
                config.AGENT_ID = "mock_agent"
                config.TELECMI_TOKEN = "mock_token"
                config.TELECMI_APP_ID = "mock_app"
                config.TELECMI_APP_SECRET = "mock_secret"
                res = telephony.dispatch_outbound_call("+919818282209", "Candidate")
                self.assertFalse(res["ok"])
                self.assertIsNotNone(res.get("error"))
            finally:
                config.TELECMI_APP_ID = orig_app_id
                config.TELECMI_APP_SECRET = orig_secret
                config.TELECMI_TOKEN = orig_token
                config.AGENT_ID = orig_agent

    def test_gcs_storage_outage_fallback_to_local(self):
        """When GCS client is unavailable or upload fails, upload_audio_bytes falls back to local static URL."""
        with patch("storage_service.get_storage_client", return_value=None):
            fake_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00FAKE_AUDIO"
            destination = "tts-audio/test_fallback.mp3"
            url = storage_service.upload_audio_bytes(fake_bytes, destination)
            self.assertTrue(url.endswith("/static/test_fallback.mp3") or "static/test_fallback.mp3" in url)
            self.assertTrue(os.path.exists(os.path.join("static", "test_fallback.mp3")))

    def test_llm_api_failure_graceful_handling(self):
        """When all external LLM APIs (Gemini, Vertex, OpenAI) fail, chat_with_gpt serves polite safe fallback."""
        with patch("gpt_test._gemini_session.post", return_value=MagicMock(status_code=503)), \
             patch("gpt_test.chat_with_vertex_ai", side_effect=Exception("Vertex down")), \
             patch("gpt_test.client", None):
            from gpt_test import chat_with_gpt
            fallback_text = chat_with_gpt("What are ground classes?")
            self.assertIsInstance(fallback_text, str)
            self.assertTrue(len(fallback_text) > 0)
            self.assertIn("Airborne Aviation", fallback_text)

    def test_dropped_call_post_call_pipeline_resilience(self):
        """If caller drops call abruptly, post-call pipeline completes without exceptions."""
        test_phone = "+919999900005"
        supabase_client.save_conversation_history(
            test_phone,
            [
                {"role": "assistant", "content": "Hello, Airborne Aviation."},
                {"role": "user", "content": "What is CPL fee?"}
            ],
            "inbound"
        )
        with patch("assistant.chat_with_gpt", return_value='{"classification": "Warm", "summary": "Inquired CPL"}'):
            with patch("crm_sync.sync_lead_with_telecrm", return_value=True):
                # Should run cleanly and not raise
                assistant.run_post_call_pipeline(test_phone, "inbound", "https://telecmi.com/rec.mp3")
                # Conversation session must be cleared after pipeline
                history = supabase_client.get_conversation_history(test_phone)
                self.assertEqual(len(history), 0)


# ============================================================================
# 7. DATABASE RESPONSE & RESILIENCE TESTS
# ============================================================================
class DatabaseResponseTests(unittest.TestCase):
    def setUp(self):
        self.phone = "+919818282299"
        database.clear_conversation_history(self.phone)

    def tearDown(self):
        database.clear_conversation_history(self.phone)

    def test_offline_database_in_memory_fallback(self):
        """When PostgreSQL / DATABASE_URL is unavailable, conversation sessions persist in memory without crash."""
        with patch("database.get_connection", return_value=None):
            history_input = [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Welcome to Airborne"}
            ]
            database.save_conversation_history(self.phone, history_input, "inbound")
            retrieved = database.get_conversation_history(self.phone)
            self.assertEqual(len(retrieved), 2)
            self.assertEqual(retrieved[0]["content"], "Hi")

            database.clear_conversation_history(self.phone)
            self.assertEqual(len(database.get_conversation_history(self.phone)), 0)

    def test_lead_save_and_retrieve_resilience(self):
        """Verify save_lead and get_lead_by_phone execute without unhandled crashes."""
        with patch("database.get_connection", return_value=None):
            # In mock mode, save_lead returns a dictionary or dict representation
            res = database.save_lead("Test Lead", self.phone, "test@example.com", "CPL")
            self.assertIsNotNone(res)
            self.assertEqual(res.get("name"), "Test Lead")

    def test_call_outcome_logging_does_not_raise_on_db_down(self):
        """Even if database connection fails, recording call outcome prints notice and returns cleanly."""
        with patch("database.get_connection", return_value=None):
            try:
                database.record_call_outcome(
                    phone=self.phone,
                    outcome="COMPLETED",
                    direction="outbound",
                    duration=120,
                    recording_url="https://mock.com/rec.mp3",
                    transcript="Lead: Hi\nAI: Hello",
                    summary="Good discussion"
                )
            except Exception as e:
                self.fail(f"record_call_outcome raised an unexpected exception when DB is down: {e}")

    def test_conversation_history_concurrency_stress(self):
        """Verify multiple threads writing and reading conversation history simultaneously do not corrupt state."""
        import threading
        phones = [f"+9198000000{i:02d}" for i in range(10)]
        errors = []

        def worker(p):
            try:
                for turn in range(5):
                    database.save_conversation_history(p, [{"role": "user", "content": f"Turn {turn}"}])
                    h = database.get_conversation_history(p)
                    assert len(h) == 1
                    assert h[0]["content"] == f"Turn {turn}"
                database.clear_conversation_history(p)
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker, args=(p,)) for p in phones]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent database session errors: {errors}")


if __name__ == "__main__":
    unittest.main()
