import asyncio
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main
import precall_manager
import scheduler
import storage_service


class SchedulerEligibilityTests(unittest.TestCase):
    def test_do_not_call_statuses_are_blocked(self):
        for status in ("NOT_INTERESTED", "INVALID_NUMBER", "CONVERTED", "not_interested"):
            self.assertFalse(scheduler.is_callable_lead({"status": status}), status)

    def test_normal_and_missing_leads(self):
        self.assertTrue(scheduler.is_callable_lead({"status": "NEW"}))
        self.assertTrue(scheduler.is_callable_lead({"status": "CONTACTED", "classification": "CONTACTED"}))
        self.assertFalse(scheduler.is_callable_lead(None))

    def test_calling_window_ist(self):
        ist = scheduler.IST
        self.assertTrue(scheduler.in_call_window(datetime(2026, 10, 15, 10, 0, tzinfo=ist)))
        self.assertFalse(scheduler.in_call_window(datetime(2026, 10, 15, 8, 59, tzinfo=ist)))
        self.assertFalse(scheduler.in_call_window(datetime(2026, 10, 15, 20, 0, tzinfo=ist)))
        reopen = scheduler.next_window_open(datetime(2026, 10, 15, 21, 0, tzinfo=ist))
        self.assertEqual((reopen.day, reopen.hour), (16, 9))

    def test_job_skips_do_not_call_lead(self):
        with patch.object(scheduler.supabase_client, "get_lead_by_phone", return_value={"status": "NOT_INTERESTED"}), \
             patch.object(scheduler.telephony, "make_outbound_call") as dial:
            scheduler.trigger_call_job("X", "+919000000001")
            dial.assert_not_called()

    def test_job_dials_eligible_lead_in_window(self):
        with patch.object(scheduler.supabase_client, "get_lead_by_phone", return_value={"status": "NEW"}), \
             patch.object(scheduler, "in_call_window", return_value=True), \
             patch.object(scheduler.telephony, "make_outbound_call", return_value=True) as dial:
            scheduler.trigger_call_job("X", "+919000000001")
            dial.assert_called_once()

    def test_job_defers_outside_window(self):
        with patch.object(scheduler.supabase_client, "get_lead_by_phone", return_value={"status": "NEW"}), \
             patch.object(scheduler, "in_call_window", return_value=False), \
             patch.object(scheduler.telephony, "make_outbound_call") as dial:
            scheduler.trigger_call_job("X", "+919000000001")
            dial.assert_not_called()


class RecordingUrlSafetyTests(unittest.TestCase):
    def test_rejects_unsafe_urls(self):
        for url in (
            "http://api.twilio.com/rec.mp3",                       # not https
            "https://evil.example.com/twilio/rec.mp3",             # host not allowlisted, 'twilio' in path
            "https://twilio.com.evil.example.com/rec.mp3",         # lookalike host
            "https://169.254.169.254/computeMetadata/v1/",         # metadata server
            "https://localhost/rec.mp3",
            "file:///etc/passwd",
            "",
        ):
            self.assertFalse(storage_service.is_safe_recording_url(url), url)

    def test_allows_allowlisted_public_host(self):
        public = [(2, 1, 6, "", ("142.250.0.1", 443))]
        with patch("socket.getaddrinfo", return_value=public):
            self.assertTrue(storage_service.is_safe_recording_url("https://api.twilio.com/rec.mp3"))

    def test_rejects_allowlisted_host_resolving_to_private_ip(self):
        private = [(2, 1, 6, "", ("10.0.0.5", 443))]
        with patch("socket.getaddrinfo", return_value=private):
            self.assertFalse(storage_service.is_safe_recording_url("https://api.twilio.com/rec.mp3"))

    def test_unsafe_url_is_returned_unchanged_without_download(self):
        with patch.object(storage_service.requests, "get") as get:
            out = storage_service.upload_call_recording_from_url("https://evil.example.com/x.mp3", "id1")
            self.assertEqual(out, "https://evil.example.com/x.mp3")
            get.assert_not_called()


class CacheBoundTests(unittest.TestCase):
    def test_dossier_cache_is_bounded(self):
        mgr = precall_manager.PreCallManager()
        mgr.MAX_CACHED_ENTRIES = 5
        for i in range(12):
            mgr.register_precall(phone=f"+9190000000{i:02d}", name=f"N{i}", prewarm_audio=False)
        self.assertLessEqual(len(mgr._cache), 5)
        self.assertIsNotNone(mgr.get_dossier("+919000000011"))  # newest kept


class AnswerWebhookTests(unittest.TestCase):
    def test_agent_connect_pcmo_shape(self):
        pcmo = main._agent_connect_pcmo()
        self.assertEqual(pcmo[0]["action"], "connect")
        self.assertEqual(pcmo[0]["endpoints"][0]["type"], "agent")
        self.assertTrue(pcmo[0]["endpoints"][0]["id"])

    def test_error_in_handler_still_connects_to_agent(self):
        from fastapi.testclient import TestClient
        with patch.object(main, "get_base_url", side_effect=RuntimeError("boom")):
            r = TestClient(main.app).get("/telecmi/answer?from=919000000001")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["action"], "connect")

    def test_head_probe_ok(self):
        from fastapi.testclient import TestClient
        self.assertEqual(TestClient(main.app).head("/telecmi/answer").status_code, 200)


if __name__ == "__main__":
    unittest.main()
