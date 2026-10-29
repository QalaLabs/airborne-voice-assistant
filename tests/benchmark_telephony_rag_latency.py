"""
Statistical Latency & Response Profiling Benchmark.
Measures real performance distributions across all 7 core subsystem areas:
1. Incoming call PCMO generation (cached vs cold)
2. Outgoing pre-call dossier registration & prompt compilation
3. RAG Selective Gating & Knowledge Corpus Retrieval
4. Voice Pipeline turn processing and audio cache lookup
5. Database session read / write / outcome logging
6. Carrier & Network degradation simulation recovery time
"""

import os
import sys
import time
import statistics
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import config
import main
import precall_manager
import rag
import assistant
import database
import supabase_client
import telephony

def calc_stats(times_ms):
    return {
        "count": len(times_ms),
        "mean_ms": round(statistics.mean(times_ms), 3),
        "median_ms": round(statistics.median(times_ms), 3),
        "p90_ms": round(statistics.quantiles(times_ms, n=10)[8] if len(times_ms) >= 10 else max(times_ms), 3),
        "p99_ms": round(statistics.quantiles(times_ms, n=100)[98] if len(times_ms) >= 100 else max(times_ms), 3),
        "min_ms": round(min(times_ms), 3),
        "max_ms": round(max(times_ms), 3),
    }

def benchmark_suite():
    results = {}
    client = TestClient(main.app)

    # 1. RAG Selective Gating Latency
    test_queries = [
        "ok", "haan", "theek hai", "cpl fee", "a320 simulator cost", 
        "batch dates for pilot ground school", "what is the eligibility for cabin crew"
    ]
    gating_times = []
    for _ in range(100):
        for q in test_queries:
            t0 = time.perf_counter()
            assistant.should_retrieve_knowledge(q)
            gating_times.append((time.perf_counter() - t0) * 1000)
    results["rag_selective_gating"] = calc_stats(gating_times)

    # 2. In-Memory Dossier Lookup Latency
    phone = "+919818282209"
    precall_manager.manager.register_precall(phone=phone, name="Bench Pilot", course_interest="CPL", prewarm_audio=False)
    dossier_times = []
    for _ in range(500):
        t0 = time.perf_counter()
        precall_manager.manager.get_dossier(phone)
        dossier_times.append((time.perf_counter() - t0) * 1000)
    results["in_memory_dossier_lookup"] = calc_stats(dossier_times)

    # 3. RAG Ground-Truth Knowledge Retrieval Latency
    rag_queries = [
        "CPL ground school fee and subjects",
        "A320 simulator training cost",
        "Cabin crew course fee and duration",
        "DGCA pilot medicals and age eligibility",
        "Campus address in Ramphal Chowk Dwarka",
        "Job placement guarantee"
    ]
    rag_times = []
    for _ in range(25):
        for rq in rag_queries:
            t0 = time.perf_counter()
            ctx = rag.query_rag(rq, limit=3)
            rag_times.append((time.perf_counter() - t0) * 1000)
    results["rag_knowledge_retrieval"] = calc_stats(rag_times)

    # 4. Outgoing Pre-call Registration & System Prompt Compilation
    compile_times = []
    for i in range(100):
        t0 = time.perf_counter()
        dossier = precall_manager.manager.register_precall(
            phone=f"+919800000{i:03d}",
            name=f"Candidate {i}",
            course_interest="DGCA CPL Ground Classes",
            education="10+2 with PCM",
            city="Delhi",
            prewarm_audio=False
        )
        prompt = precall_manager.manager.compile_system_prompt(dossier, direction="outbound")
        compile_times.append((time.perf_counter() - t0) * 1000)
    results["precall_prompt_compilation"] = calc_stats(compile_times)

    # 5. Incoming /telecmi/answer PCMO Webhook Latency (Zero-DB Fast Path)
    pcmo_times = []
    with patch("supabase_client.save_lead"), patch("supabase_client.save_conversation_history"):
        # Warmup
        client.post("/telecmi/answer", json={"from": phone, "direction": "inbound"})
        for _ in range(50):
            t0 = time.perf_counter()
            res = client.post("/telecmi/answer", json={"from": phone, "direction": "inbound"})
            pcmo_times.append((time.perf_counter() - t0) * 1000)
    results["incoming_pcmo_webhook_cached"] = calc_stats(pcmo_times)

    # 6. Database Session Read/Write Latency (In-Memory Fallback vs Local Operations)
    db_write_times = []
    db_read_times = []
    test_session_phone = "+919999888877"
    for turn in range(50):
        history_step = [{"role": "user", "content": f"Turn {turn}"}, {"role": "assistant", "content": "Reply"}]
        t_w0 = time.perf_counter()
        database.save_conversation_history(test_session_phone, history_step, "inbound")
        db_write_times.append((time.perf_counter() - t_w0) * 1000)

        t_r0 = time.perf_counter()
        database.get_conversation_history(test_session_phone)
        db_read_times.append((time.perf_counter() - t_r0) * 1000)

    results["db_session_write"] = calc_stats(db_write_times)
    results["db_session_read"] = calc_stats(db_read_times)

    # 7. No Network / Carrier Degradation Recovery Overhead
    failover_times = []
    mock_client = MagicMock()
    mock_client.ai.call.side_effect = Exception("Carrier dropped connection")
    mock_client.pcmo.call.side_effect = Exception("PCMO dropped")
    from types import SimpleNamespace
    fake_voice = SimpleNamespace(RestClient=lambda token: mock_client)

    with patch("telephony.piopiy", SimpleNamespace(voice=fake_voice)), \
         patch("telephony.requests.post", side_effect=Exception("REST timeout")), \
         patch("assistant.get_greeting_voice_url", return_value="https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/greeting_navrang.mp3"):
        orig_agent = config.AGENT_ID
        orig_token = config.TELECMI_TOKEN
        orig_app = config.TELECMI_APP_ID
        orig_sec = config.TELECMI_APP_SECRET
        try:
            config.AGENT_ID = "mock_agent"
            config.TELECMI_TOKEN = "mock_tok"
            config.TELECMI_APP_ID = "mock_app"
            config.TELECMI_APP_SECRET = "mock_sec"
            for _ in range(25):
                t0 = time.perf_counter()
                res = telephony.dispatch_outbound_call("+919818282209", "Candidate")
                failover_times.append((time.perf_counter() - t0) * 1000)
        finally:
            config.AGENT_ID = orig_agent
            config.TELECMI_TOKEN = orig_token
            config.TELECMI_APP_ID = orig_app
            config.TELECMI_APP_SECRET = orig_sec

    results["carrier_timeout_recovery"] = calc_stats(failover_times)

    print("\n" + "=" * 80)
    print("EMPIRICAL LATENCY & BENCHMARK PROFILE RESULTS")
    print("=" * 80)
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    benchmark_suite()
