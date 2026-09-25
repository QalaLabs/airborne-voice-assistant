import time
import os
import json
from voice_test import listen
from tts_test import speak_and_get_url
from gpt_test import chat_with_gpt
import rag
import supabase_client
import crm_sync
import automation

EXIT_PHRASES = ["goodbye", "thank you", "bye", "exit", "stop", "shukriya", "alvida"]

MAX_TURNS = 12
MAX_CONSECUTIVE_SILENCE = 2

CONVERSATIONAL_FILLERS = {
    "yes", "yeah", "ok", "okay", "sure", "no", "nope", "hello", "hi", "hey",
    "bye", "goodbye", "thanks", "thank you", "shukriya", "alvida", "theek hai", "haan"
}

HUMAN_TRANSFER_PHRASES = [
    "talk to a person", "talk to human", "real person", "speak to someone",
    "connect me", "transfer me", "admissions counselor", "human agent",
    "captain navrang", "navrang sir se baat"
]

def should_retrieve_knowledge(user_text: str) -> bool:
    """
    Selectively gates RAG vector searches to save 100-300ms on simple conversational filler turns.
    """
    cleaned = user_text.strip().lower()
    if cleaned in CONVERSATIONAL_FILLERS or len(cleaned.split()) <= 2:
        return False
    return True

def get_pruned_context(history: list, window_size: int = 6) -> list:
    """
    Retains the most recent conversational window to minimize TTFT and prompt token bloat.
    """
    if len(history) <= window_size:
        return history
    return history[-window_size:]

SYSTEM_PROMPT = """
You are Capt. Modassir, a respected pilot advisor and mentor at Airborne Aviation Academy in Dwarka, Delhi.
Your approach is NEVER pushy or salesy. Instead, you act as a genuine mentor who listens, validates the student's aviation dream, and naturally moulds the conversation so the student feels eager and excited to take the next step.

Tone & Conversational Persona:
- Warm, advisory, encouraging, and calm Hinglish tone (Hindi + English mix).
- Keep replies concise (2-3 short sentences max per turn) so it sounds natural when spoken over the phone.

Consultative Steering Framework:
1. **Empathy & Rapport:** Validate their career ambition (e.g. "CPL is an amazing career choice! Clearing DGCA exams early gives you a huge advantage in airline selections.").
2. **Clear Information:** Answer their questions on course fees, DGCA Class 1/2 medicals, or eligibility (10+2 Physics/Maths) accurately using the provided website context.
3. **Subtle & Eager Value Offering (Not Pushy):**
   - Frame the counselling call or campus visit as a rare, highly valuable experience for their personal clarity.
   - Example moulding phrases:
     * "Instead of just reading about pilot rules, most students find it super helpful to spend 15 minutes talking directly to Capt. Navrang Singh or experiencing our A320 simulator at Dwarka. It gives you total clarity."
     * "Would you like me to hold a free simulator trial slot or a mentor call for you this week so you can see how it feels?"
4. **Confirm & Close:** When the student eagerly agrees, ask for their preferred day/time, confirm that the instant booking confirmation link will be sent to their WhatsApp, wish them clear skies, and include "[EXIT]" in your response to complete the call.
"""

def get_greeting_voice_url(text: str) -> str:
    """
    Synthesizes custom greeting audio.
    """
    return speak_and_get_url(text)

def handle_conversation(recording_url: str, phone: str, direction: str):
    """
    Main dialogue manager for the conversation loop.
    Enforces circuit breakers, selective RAG, sliding memory, and telemetry.
    """
    t_start = time.time()
    
    # 1. Speech-to-Text
    caller_input = listen(recording_url)
    t_stt = time.time() - t_start
    print(f"Conversation: Phone={phone}, Input='{caller_input}'")

    # 2. State Retrieval
    history = supabase_client.get_conversation_history(phone)

    # 3. Guardrail: Consecutive Silence / Connection Issue Circuit Breaker
    if not caller_input or "could not understand" in caller_input.lower():
        # Check if previous turn was also silent
        consecutive_silence = 1
        if len(history) >= 2 and history[-2].get("content") == "[Silence/Unrecognized Input]":
            consecutive_silence = 2

        if consecutive_silence >= MAX_CONSECUTIVE_SILENCE:
            response_text = "It seems we are having audio connection trouble. I will have our senior pilot counselor send all program details directly to your WhatsApp. Have a great day! [EXIT]"
            history.append({"role": "user", "content": "[Silence/Unrecognized Input]"})
            history.append({"role": "assistant", "content": response_text})
            supabase_client.save_conversation_history(phone, history, direction)
            audio_url = speak_and_get_url(response_text.replace("[EXIT]", "").strip())
            return audio_url, True

        response_text = "I couldn't hear you clearly. Could you please repeat that? (Aapki aawaz clear nahi thi. Kya aap dohara sakte hain?)"
        history.append({"role": "user", "content": "[Silence/Unrecognized Input]"})
        history.append({"role": "assistant", "content": response_text})
        supabase_client.save_conversation_history(phone, history, direction)
        audio_url = speak_and_get_url(response_text)
        return audio_url, False

    # 4. Guardrail: Caller Direct Exit
    for phrase in EXIT_PHRASES:
        if phrase in caller_input.lower():
            response_text = "Thank you for calling Airborne Aviation Academy. Have a great day ahead! Clear skies! [EXIT]"
            history.append({"role": "user", "content": caller_input})
            history.append({"role": "assistant", "content": response_text})
            supabase_client.save_conversation_history(phone, history, direction)
            audio_url = speak_and_get_url(response_text.replace("[EXIT]", "").strip())
            return audio_url, True

    # 5. Guardrail: Human Transfer Escalation
    if any(phrase in caller_input.lower() for phrase in HUMAN_TRANSFER_PHRASES):
        response_text = "Certainly! I am notifying our senior admissions desk at Dwarka right now. A pilot mentor will call you back on this number immediately. Clear skies! [EXIT]"
        history.append({"role": "user", "content": caller_input})
        history.append({"role": "assistant", "content": response_text})
        supabase_client.save_conversation_history(phone, history, direction)
        audio_url = speak_and_get_url(response_text.replace("[EXIT]", "").strip())
        return audio_url, True

    # 6. Guardrail: Max Conversation Turns Cap
    user_turn_count = sum(1 for m in history if m["role"] == "user")
    if user_turn_count >= MAX_TURNS:
        response_text = "Thank you so much for discussing your aviation career with me. I've noted all your goals, and our mentor will send our full brochure and scheduling link on WhatsApp. Clear skies! [EXIT]"
        history.append({"role": "user", "content": caller_input})
        history.append({"role": "assistant", "content": response_text})
        supabase_client.save_conversation_history(phone, history, direction)
        audio_url = speak_and_get_url(response_text.replace("[EXIT]", "").strip())
        return audio_url, True

    # 7. Selective RAG Knowledge Retrieval
    t_rag_start = time.time()
    if should_retrieve_knowledge(caller_input):
        context = rag.query_rag(caller_input)
    else:
        context = "User provided conversational acknowledgement/greeting. Provide warm, brief response and offer campus visit or counseling."
    t_rag = time.time() - t_rag_start

    # 8. LLM Generation with Sliding Context Window
    t_llm_start = time.time()
    dynamic_system_prompt = f"{SYSTEM_PROMPT}\n\nRELEVANT WEBSITE CONTEXT:\n{context}"
    pruned_history = get_pruned_context(history, window_size=6)
    ai_response = chat_with_gpt(caller_input, pruned_history, dynamic_system_prompt)
    t_llm = time.time() - t_llm_start
    print(f"AI Response: '{ai_response}'")

    # 9. Append to Full History & State Persistence
    history.append({"role": "user", "content": caller_input})
    history.append({"role": "assistant", "content": ai_response})

    # Detect exit signal in response
    should_hang_up = "[EXIT]" in ai_response or "[exit]" in ai_response.lower()
    clean_response = ai_response.replace("[EXIT]", "").replace("[exit]", "").strip()

    supabase_client.save_conversation_history(phone, history, direction)

    # 10. Text-to-Speech Synthesis
    t_tts_start = time.time()
    audio_url = speak_and_get_url(clean_response)
    t_tts = time.time() - t_tts_start

    # 11. Latency Waterfall Telemetry
    t_total = time.time() - t_start
    print(f"[METRICS] Phone={phone} Total={int(t_total*1000)}ms | STT={int(t_stt*1000)}ms | RAG={int(t_rag*1000)}ms | LLM={int(t_llm*1000)}ms | TTS={int(t_tts*1000)}ms")

    return audio_url, should_hang_up

def get_transcript_string(phone: str) -> str:
    """
    Compiles the conversation history for a given phone number into a formatted text log.
    """
    history = supabase_client.get_conversation_history(phone)
    log_lines = []
    for msg in history:
        role = "Lead" if msg["role"] == "user" else "AI"
        log_lines.append(f"{role}: {msg['content']}")
    return "\n".join(log_lines)

def clear_session(phone: str):
    """
    Clears the persisted conversation session after post-call actions are triggered.
    """
    supabase_client.clear_conversation_history(phone)

def run_post_call_pipeline(phone: str, direction: str, recording_url: str):
    """
    Asynchronous post-call processor.
    1. Archives call recording to Google Cloud Storage.
    2. Extracts lead qualifiers, course interest, and callback intent using LLM.
    3. Updates CRM (leads & lead_activities) directly in Cloud SQL.
    4. Triggers secondary automations (WhatsApp & CRM sync).
    """
    print(f"Post-Call: Starting pipeline for {phone}...")
    transcript = get_transcript_string(phone)
    if not transcript:
        print("Post-Call: Empty transcript. Skipping processing.")
        return

    # 1. Archive call recording to Google Cloud Storage bucket
    import storage_service
    gcs_recording_url = storage_service.upload_call_recording_from_url(
        recording_url, phone.replace("+", "")
    ) if recording_url else ""
        
    parser_prompt = f"""
    You are an automated CRM parser for a pilot school: Airborne Aviation Academy.
    Review the call transcript below and extract:
    1. course_interest: One of the 11 courses of Airborne:
       - DGCA CPL Ground Classes
       - ATPL Ground School
       - Radio Telephony (RTR-A) Exam Prep
       - Cadet Pilot Program Prep
       - GD & PI Course
       - Comprehensive Airline Selection Prep
       - Psychomotor Test Prep (CASS/COMPASS/ADAPT)
       - Airbus A320 Simulator FBS
       - Cabin Crew / Flight Attendant Training
       - Private Pilot License (PPL) Ground Classes
       - Multi-Engine Rating (MER) Ground School
       Or 'Unknown' if not mentioned.
    2. booking_intent: 'Counselling Call' / 'Campus Visit' / 'None'.
    3. budget_status: 'Ready' / 'Not Ready' / 'Unknown'.
    4. timeline_urgency: 'Immediate' / '3 Months' / '6+ Months' / 'Unknown'.
    5. classification: 'Hot' (if booking_intent is Counselling Call or Campus Visit, or budget is Ready + immediate timeline) / 'Warm' (interested, but planning) / 'Cold' (no interest/wrong number).
    6. callback_requested: true if the caller specifically asked to call back later / tomorrow / at another time, otherwise false.
    7. callback_time: estimated ISO timestamp or relative description (e.g. 'Tomorrow 4 PM', '2 hours later') if callback_requested is true, else null.

    Output ONLY as a valid JSON object. Do not include markdown wraps or explanations.
    Example output format:
    {{"course_interest": "DGCA CPL Ground Classes", "booking_intent": "Campus Visit", "budget_status": "Ready", "timeline_urgency": "Immediate", "classification": "Hot", "callback_requested": false, "callback_time": null}}

    TRANSCRIPT:
    {transcript}
    """
    
    # Run parsing query with structured JSON mode
    parse_result = chat_with_gpt(parser_prompt, json_mode=True)
    print(f"Post-Call: LLM Parser Output: {parse_result}")
    
    # Load defaults
    data = {
        "course_interest": "Unknown",
        "budget_status": "Unknown",
        "timeline_urgency": "Unknown",
        "classification": "Cold",
        "callback_requested": False,
        "callback_time": None
    }
    
    # Parse JSON output safely
    try:
        clean_json = parse_result.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
        data.update(json.loads(clean_json))
    except Exception as e:
        print(f"Post-Call: JSON parsing failed ({e}). Attempting keyword fallback.")
        for course in [
            "CPL", "ATPL", "RTR", "Cadet", "GD", "Airline", "Psychomotor", "Simulator", "Cabin Crew", "PPL", "Multi-Engine"
        ]:
            if course.lower() in parse_result.lower():
                data["course_interest"] = course
        if "hot" in parse_result.lower():
            data["classification"] = "Hot"
        elif "warm" in parse_result.lower():
            data["classification"] = "Warm"
            
    # Retrieve lead profile from Cloud SQL to fetch name
    lead_name = "Future Pilot"
    lead = supabase_client.get_lead_by_phone(phone)
    if lead:
        lead_name = lead.get("name", "Future Pilot")
        if data["course_interest"] == "Unknown" and lead.get("course_interest"):
            data["course_interest"] = lead.get("course_interest")
        
    duration_estimate = len(transcript.split()) * 2
    summary = f"Qualifying conversation for {data['course_interest']}. Classified as {data['classification']}."
    
    # Determine outcome
    outcome = "CALLBACK_REQUESTED" if data.get("callback_requested") else "CONNECTED"
    if outcome == "CALLBACK_REQUESTED":
        summary = f"Callback requested ({data.get('callback_time')}). {summary}"

    # 1. Update CRM (leads table & lead_activities) directly in Cloud SQL
    supabase_client.record_call_outcome(
        phone=phone,
        outcome=outcome,
        direction=direction,
        duration=duration_estimate,
        recording_url=gcs_recording_url,
        transcript=transcript,
        summary=summary,
        callback_time=data.get("callback_time"),
        course_interest=data["course_interest"],
        classification=data["classification"]
    )
    
    # 2. Synchronize with external TeleCRM if configured
    lead_payload = {
        "name": lead_name,
        "phone": phone,
        "course_interest": data["course_interest"],
        "classification": data["classification"],
        "budget_status": data["budget_status"],
        "timeline_urgency": data["timeline_urgency"],
        "recording_url": gcs_recording_url
    }
    crm_sync.sync_lead_with_telecrm(lead_payload, transcript)
    
    # 3. Trigger WhatsApp automated follow-up
    automation.trigger_post_call_automations(phone, data["classification"], lead_name)
    
    # 4. Clear dialogue session
    clear_session(phone)
    print(f"Post-Call: Pipeline completed for {phone}.")

