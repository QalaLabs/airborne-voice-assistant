"""
Unit tests for Captain Navrang Guardrails & Highlighted Telemetry.
Validates:
1. Identity Verification Guardrail
2. Campus Visit & In-Person Meeting Guardrail
3. Language Adaptation Guardrail (Hindi -> English, English -> English, Hinglish -> Hinglish)
4. Highlighted Logging format
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import guardrails

def test_identity_guardrail():
    queries = [
        "Are you really Captain Navrang or an AI?",
        "Are you an AI bot?",
        "Am I talking to a real person?",
        "kya aap AI ho?",
        "Are you a robot?",
        "Is this an automated recording?"
    ]
    for q in queries:
        resp = guardrails.check_identity_guardrail(q, phone="+919999999999")
        assert resp == guardrails.IDENTITY_GUARDRAIL_RESPONSE, f"Failed on query: {q}"
        assert "small knowledge capsule" in resp
        assert "real pilot" in resp

def test_campus_visit_guardrail():
    queries = [
        "Can I visit the campus tomorrow?",
        "I want to meet Captain Navrang in person at Dwarka",
        "Can we schedule a meeting at your academy?",
        "Dwarka campus visit kar sakta hoon?",
        "Can I meet you at the office?"
    ]
    for q in queries:
        resp = guardrails.check_visit_meeting_guardrail(q, phone="+919999999999")
        assert resp == guardrails.VISIT_MEETING_GUARDRAIL_RESPONSE, f"Failed on query: {q}"
        assert "classes end by 12:30" in resp
        assert "admissions counselor" in resp

def test_language_adaptation():
    # Pure Hindi -> Enforced Hindi (speak in caller's preferred language to remove language barrier)
    hindi_queries = [
        "kya main pilot ban sakta hoon bina physics ke",
        "mujhe ground classes ke baare mein janna hai kitna kharcha aayega",
        "kripya hindi mein baat karein",
        "can you speak in hindi"
    ]
    for q in hindi_queries:
        detected, enforced, directive = guardrails.detect_language_adaptation(q, phone="+919999999999")
        assert detected == "HINDI", f"Expected HINDI for: {q}, got {detected}"
        assert enforced == "HINDI", f"Expected HINDI enforced for: {q}"
        assert "preferred language" in directive.lower()

    # Hinglish -> Enforced Hinglish
    hinglish_queries = [
        "What is the CPL ground class fee and batch timings kya hain?",
        "Can I clear DGCA exams if 12th mein PCM nahi tha?"
    ]
    for q in hinglish_queries:
        detected, enforced, directive = guardrails.detect_language_adaptation(q, phone="+919999999999")
        assert detected == "HINGLISH", f"Expected HINGLISH for: {q}, got {detected}"
        assert enforced == "HINGLISH", f"Expected HINGLISH enforced for: {q}"

    # Pure English -> Enforced English
    english_queries = [
        "What are the DGCA Class 2 medical requirements for aspiring pilots?",
        "How many flying hours are required to obtain a Commercial Pilot License?"
    ]
    for q in english_queries:
        detected, enforced, directive = guardrails.detect_language_adaptation(q, phone="+919999999999")
        assert detected == "ENGLISH", f"Expected ENGLISH for: {q}, got {detected}"
        assert enforced == "ENGLISH", f"Expected ENGLISH enforced for: {q}"

def test_evaluate_all_guardrails():
    # Test AMD bypass
    override, enforced, meta = guardrails.evaluate_all_guardrails("The person you are trying to reach is not available. Please record your message at the tone.")
    assert override == guardrails.AMD_GUARDRAIL_RESPONSE
    assert meta["guardrail"] == "AMD_CARRIER_IVR"

    # Test audibility check-in bypass
    override, enforced, meta = guardrails.evaluate_all_guardrails("Hello? Hello? Aawaz nahi aa rahi")
    assert override == guardrails.AUDIBILITY_GUARDRAIL_RESPONSE
    assert meta["guardrail"] == "AUDIBILITY_CHECK"

    # Test identity bypass
    override, enforced, meta = guardrails.evaluate_all_guardrails("Are you an AI or real Navrang sir?", phone="+919876543210")
    assert override == guardrails.IDENTITY_GUARDRAIL_RESPONSE
    assert meta["guardrail"] == "IDENTITY"

    # Test visit bypass
    override, enforced, meta = guardrails.evaluate_all_guardrails("How can I visit your Dwarka academy to meet you?", phone="+919876543210")
    assert override == guardrails.VISIT_MEETING_GUARDRAIL_RESPONSE
    assert meta["guardrail"] == "CAMPUS_VISIT_MEETING"

    # Test standard aviation query (no override, but language evaluated)
    override, enforced, meta = guardrails.evaluate_all_guardrails("Explain the difference between Class 1 and Class 2 medicals.")
    assert override is None
    assert enforced == "ENGLISH"
    assert meta["guardrail"] == "LANGUAGE_ADAPTATION"

def test_placeholder_sanitization():
    import precall_manager
    dossier = precall_manager.PreCallDossier(
        phone="+919999999999",
        name="Amit",
        course_interest="Not sure yet",
        source="Website"
    )
    greeting = precall_manager.manager.generate_greeting(dossier, direction="outbound")
    assert "not sure yet" not in greeting.lower()
    assert "about pilot training" in greeting

if __name__ == "__main__":
    test_identity_guardrail()
    test_campus_visit_guardrail()
    test_language_adaptation()
    test_evaluate_all_guardrails()
    test_placeholder_sanitization()
    print("\n✅ ALL GUARDRAIL & TELEMETRY TESTS PASSED SUCCESSFULLY!")
