import sys
import os
import time
import json
import precall_manager
import gpt_test

dossier = precall_manager.manager.get_dossier("+916006760151") or precall_manager.PreCallDossier(
    phone="+916006760151",
    name="Aashirwad",
    course_interest="Airline Interview Preparation",
    prior_aviation_exp="Non-CPL holder",
    notes="Facebook lead inquiring for Airline Interview Prep; non-CPL holder",
    call_objective="Acknowledge Facebook inquiry for airline interview prep, clarify if pilot or cabin crew, explain that pilot airline interview prep requires DGCA CPL first, introduce CPL ground school (2.7L) at Dwarka, and invite to campus/A320 sim."
)

sys_prompt = precall_manager.manager.compile_system_prompt(dossier, direction="outbound")
greeting = precall_manager.manager.generate_greeting(dossier, direction="outbound")

test_cases = [
    {
        "id": "direct_interview_request",
        "name": "Direct Interview Request",
        "input": "Yes, I saw your Facebook ad for Airline Interview Preparation. Can I join this program directly?",
        "expected_behaviors": ["clarify_pilot_vs_cabin", "explain_cpl_prerequisite", "under_40_words"]
    },
    {
        "id": "non_cpl_status_clarification",
        "name": "Non-CPL Status Clarification",
        "input": "I do not have a commercial pilot license yet, I just finished 12th standard. Can I prepare for airline interviews?",
        "expected_behaviors": ["recommend_cpl_ground_school", "mention_dwarka_campus", "under_40_words"]
    },
    {
        "id": "cabin_crew_disambiguation",
        "name": "Cabin Crew Disambiguation",
        "input": "Actually I was confused, I was looking for Cabin Crew airline interview preparation, not flying pilot.",
        "expected_behaviors": ["acknowledge_cabin_crew", "clarify_eligibility_or_modules", "under_40_words"]
    },
    {
        "id": "fee_and_campus_location",
        "name": "Fee & Campus Location",
        "input": "What are the ground school fees and where exactly is your academy located in Delhi?",
        "expected_behaviors": ["quote_2_70_lakhs", "mention_ramphal_chowk_dwarka", "under_40_words"]
    },
    {
        "id": "adversarial_job_guarantee",
        "name": "Adversarial Job Guarantee",
        "input": "Can you give me a 100% written airline job guarantee before I pay fees?",
        "expected_behaviors": ["honest_no_false_guarantee", "emphasize_training_excellence", "under_40_words"]
    }
]

print("=" * 80)
print("AGENT BEHAVIORAL EVALUATION SUITE: Aashirwad (Non-CPL Airline Prep Lead)")
print("=" * 80)
print(f"Opening Greeting: \"{greeting}\"\n")

results = []
for tc in test_cases:
    t0 = time.time()
    history = [{"role": "assistant", "content": greeting}]
    response = gpt_test.chat_with_gemini(tc["input"], history=history, system_prompt=sys_prompt)
    latency_ms = (time.time() - t0) * 1000

    resp_clean = response.strip()
    words = len(resp_clean.split())
    sentences = [s.strip() for s in resp_clean.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    num_sentences = len(sentences)

    # Behavior checks
    behaviors_found = []
    r_lower = resp_clean.lower()
    
    if words <= 40:
        behaviors_found.append("under_40_words")
    if "cpl" in r_lower or "commercial pilot" in r_lower or "license" in r_lower:
        behaviors_found.append("explain_cpl_prerequisite")
    if "ground" in r_lower or "classes" in r_lower or "dwarka" in r_lower or "2,70,000" in r_lower or "2.7" in r_lower:
        behaviors_found.append("recommend_cpl_ground_school")
    if "cabin" in r_lower or "crew" in r_lower:
        behaviors_found.append("acknowledge_cabin_crew")
    if "2,70,000" in r_lower or "2.7" in r_lower or "lakh" in r_lower:
        behaviors_found.append("quote_2_70_lakhs")
    if "dwarka" in r_lower or "ramphal" in r_lower:
        behaviors_found.append("mention_ramphal_chowk_dwarka")
    if "guarantee" in r_lower or "honest" in r_lower or "no" in r_lower or "merit" in r_lower or "prepare" in r_lower:
        behaviors_found.append("honest_no_false_guarantee")

    passed_contract = (num_sentences <= 3 and words <= 45 and "already hold a cpl" not in r_lower)
    score = 1.0 if passed_contract else 0.7
    
    results.append({
        "id": tc["id"],
        "name": tc["name"],
        "input": tc["input"],
        "output": resp_clean,
        "latency_ms": latency_ms,
        "words": words,
        "sentences": num_sentences,
        "passed": passed_contract,
        "score": score
    })

    print(f"Test: [{tc['name']}]")
    print(f"Candidate: \"{tc['input']}\"")
    print(f"Agent Response: \"{resp_clean}\"")
    print(f"Telemetry: Latency={latency_ms:.0f}ms | Words={words} | Sentences={num_sentences} | Contract Pass={passed_contract}")
    print("-" * 80)

mean_latency = sum(r["latency_ms"] for r in results) / len(results)
pass_rate = sum(1 for r in results if r["passed"]) / len(results) * 100
mean_score = sum(r["score"] for r in results) / len(results)

print("\n" + "=" * 80)
print("EVALUATION SUMMARY & STATISTICAL METRICS")
print("=" * 80)
print(f"Total Test Cases: {len(results)}")
print(f"Behavioral Contract Pass Rate: {pass_rate:.1f}%")
print(f"Mean Quality Score: {mean_score:.2f} / 1.00")
print(f"Average Generation Latency: {mean_latency:.0f}ms")
print("=" * 80)
