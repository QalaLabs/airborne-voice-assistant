import time
import os
import json
import re
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

AVIATION_KEYWORDS = {
    "cpl", "atpl", "rtr", "ground", "class", "classes", "fee", "fees", "cost", "price",
    "duration", "batch", "batches", "simulator", "sim", "airbus", "a320", "fbs",
    "cadet", "airline", "interview", "gd", "pi", "psychomotor", "cass", "compass",
    "adapt", "cabin", "crew", "flight", "attendant", "ppl", "multi-engine", "mer",
    "medical", "medicals", "class 1", "class 2", "eligibility", "maths", "physics",
    "nios", "age", "navrang", "modassir", "dwarka", "location", "address", "hostel",
    "syllabus", "exam", "dgca"
}

HUMAN_TRANSFER_PHRASES = [
    "talk to a person", "talk to human", "real person", "speak to someone",
    "connect me", "transfer me", "admissions counselor", "human agent",
    "captain navrang", "navrang sir se baat"
]

def should_retrieve_knowledge(user_text: str) -> bool:
    """
    Selectively gates RAG vector searches to save 100-300ms on simple conversational filler turns,
    while guaranteeing that queries containing aviation questions, course queries, or pricing always trigger RAG.
    """
    cleaned = user_text.strip().lower()
    words = cleaned.split()
    
    # If any specific aviation term, course, or question keyword is present, always retrieve context
    if any(k in cleaned for k in AVIATION_KEYWORDS):
        return True
        
    if cleaned in CONVERSATIONAL_FILLERS or len(words) <= 1:
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
You are Capt. Modassir, a respected pilot advisor and admissions mentor at Airborne Aviation Academy at Ramphal Chowk, Dwarka, Delhi.
Your approach is NEVER pushy or aggressive. Instead, you act as an authentic, encouraging pilot mentor who listens, answers questions accurately from our official website, conducts essential verification checks, and naturally guides the caller toward booking an admission consultation or campus visit.

Tone, Language & Conversational Persona:
- Fluent Bilingual (English & Hinglish):
  * You speak both English and Hinglish fluently.
  * If the caller speaks in English, asks questions in English, or requests English (e.g., "Can you speak in English?", "Speak in English please"), respond immediately in fluent, professional, warm English.
  * If the caller speaks in Hindi or Hinglish, respond in warm, advisory Hinglish (Hindi + English natural mix).
  * Seamlessly match the caller's language preference.
- Advisory & Mentoring Tone: Warm, polite, advisory, and calm.
- Keep replies concise (2-3 short sentences max per turn) so it sounds crisp and natural over phone telephony.

Mandatory Conversational Framework & Verification Steps:
1. Personal Details & Intent:
   - Learn the caller's name (if not known).
   - Clarify which course they are calling about (e.g. DGCA CPL Ground Classes, Cadet Pilot Program, A320 Simulator, Airline Prep, Cabin Crew, etc.) and what their primary question or doubt is.
2. Accurate Course Guidance (RAG Context):
   - Answer their query accurately using the provided website context (fees, duration, DGCA medicals, 10+2 PCM eligibility, NIOS acceptance, etc.).
3. Essential Course Verification Checks (Ask smoothly across turns):
   - Age check: Verify if the candidate is 18 years or above (note: minimum 17 to start DGCA ground classes, 18 for commercial pilot license issuance).
   - Institutional Awareness: Ensure they know Airborne Aviation Academy is a professional aviation education and ground training academy, and NOT a job placement agency or consultancy (we train pilots to clear DGCA exams & airline selections on merit).
   - Location & Campus: Ask where they currently stay/live, and confirm if they are open to attending in-person classes and simulator sessions at our Ramphal Chowk, Sector 7, Dwarka, New Delhi campus.
4. Call Outcome Goal (Must achieve on every call):
   - Validate the lead.
   - Secure one of two primary outcomes:
     a) Book a 1-on-1 career consultation call with senior pilot mentor Capt. Navrang Singh, OR
     b) Schedule an in-person campus visit and A320 simulator walkthrough at our Ramphal Chowk, Dwarka campus.
   - Ask for their preferred day and time (e.g. in Hinglish: "Kal dopahar 3 baje ya Saturday morning?", or in English: "Would tomorrow at 3 PM or Saturday morning suit you best?").
   - Confirm that the instant calendar link and syllabus brochure are being sent directly to their WhatsApp, wish them clear skies, and include "[EXIT]" in your response to close the call.
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
    ai_response = ai_response.replace("₹", "Rs. ")
    t_llm = time.time() - t_llm_start
    try:
        print(f"AI Response: '{ai_response}'")
    except Exception:
        print(f"AI Response: '{ai_response.encode('ascii', errors='replace').decode('ascii')}'")

    # 9. Append to Full History & State Persistence
    history.append({"role": "user", "content": caller_input})
    history.append({"role": "assistant", "content": ai_response})

    # Detect exit signal in response
    should_hang_up = bool(re.search(r'\[exit\]', ai_response, flags=re.IGNORECASE))
    clean_response = re.sub(r'\[exit\]\.?', '', ai_response, flags=re.IGNORECASE).strip()

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

_active_pipelines = set()

def run_post_call_pipeline(phone: str, direction: str, recording_url: str):
    """
    Asynchronous post-call processor.
    1. Archives call recording to Google Cloud Storage.
    2. Extracts lead qualifiers, course interest, and callback intent using LLM.
    3. Updates CRM (leads & lead_activities) directly in Cloud SQL.
    4. Triggers secondary automations (WhatsApp & CRM sync).
    Guarded against duplicate / concurrent pipeline execution.
    """
    cleaned_phone = phone.replace(" ", "").replace("-", "")
    if cleaned_phone in _active_pipelines:
        print(f"Post-Call: Pipeline already executing for {cleaned_phone}. Skipping duplicate trigger.")
        return

    _active_pipelines.add(cleaned_phone)
    try:
        print(f"Post-Call: Starting pipeline for {phone}...")
        transcript = get_transcript_string(phone)
        if not transcript:
            print(f"Post-Call: Empty transcript or session already processed for {phone}. Skipping processing.")
            return

        # 1. Archive call recording to Google Cloud Storage bucket
        import storage_service
        gcs_recording_url = storage_service.upload_call_recording_from_url(
            recording_url, phone.replace("+", "")
        ) if recording_url else ""
            
        parser_prompt = f"""
        You are an automated CRM lead parser for Airborne Aviation Academy (Ramphal Chowk, Dwarka, Delhi).
        Review the telephone call transcript below and extract all lead details to match our CRM Add New Lead form:
        1. name: Caller's full name (if stated in call, else null).
        2. email: Email address (if stated, else null).
        3. course_interest: Canonical course of interest:
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
           - Flight Dispatcher Training
           - Multi-Engine Rating (MER) Ground School
           Or 'Flight Training' / 'Unknown'
        4. user_query: Brief summary of the caller's primary question, doubt, or reason for calling.
        5. is_18_above: true / false / 'Unknown' (based on age question).
        6. city_or_location: City, area, or locality where the caller stays (e.g. 'Dwarka', 'Delhi', 'Gurgaon', 'Janakpuri').
        7. confirmed_education_institute: true if confirmed aware that Airborne is a training academy and not a job agency, else false/null.
        8. open_to_ramphal_chowk: true if willing to attend classes or simulator sessions at Ramphal Chowk, Dwarka campus, else false/null.
        9. booking_intent: 'Campus Visit at Ramphal Chowk' / 'Counselling Call' / 'None'.
        10. scheduled_time: Preferred date/time (e.g. 'Tomorrow 3 PM', 'Saturday 11 AM') if a visit or call was agreed, else null.
        11. classification: 'Hot' (if booked a campus visit / counselling call, or verified 18+ and confirmed interest) / 'Warm' (interested, checking options) / 'Cold' (wrong number, disqualified, no interest).
        12. callback_requested: true if caller asked to be called back later, else false.
        13. callback_time: estimated ISO timestamp or description if callback requested, else null.
        14. notes: A concise CRM note summarizing their profile, verification answers, and requested next steps.

        Output ONLY as a valid JSON object. Do not include markdown wraps or explanations.
        Example output format:
        {{"name": "Aayush", "email": null, "course_interest": "DGCA CPL Ground Classes", "user_query": "Inquired about CPL fees and medicals", "is_18_above": true, "city_or_location": "Dwarka Sector 7", "confirmed_education_institute": true, "open_to_ramphal_chowk": true, "booking_intent": "Campus Visit at Ramphal Chowk", "scheduled_time": "Tomorrow 4 PM", "classification": "Hot", "callback_requested": false, "callback_time": null, "notes": "Candidate Aayush, age 18+, confirmed aware that Airborne is an educational academy. Lives in Dwarka and open to Ramphal Chowk campus. Booked campus visit tomorrow at 4 PM."}}

        TRANSCRIPT:
        {transcript}
        """
        
        # Run parsing query with structured JSON mode
        parse_result = chat_with_gpt(parser_prompt, json_mode=True)
        print(f"Post-Call: LLM Parser Output: {parse_result}")
        
        # Load defaults
        data = {
            "name": None,
            "email": None,
            "course_interest": "Unknown",
            "user_query": None,
            "is_18_above": "Unknown",
            "city_or_location": None,
            "confirmed_education_institute": None,
            "open_to_ramphal_chowk": None,
            "booking_intent": "None",
            "scheduled_time": None,
            "classification": "Cold",
            "callback_requested": False,
            "callback_time": None,
            "notes": None
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
                
        # Retrieve lead profile from Cloud SQL to fetch existing name
        lead = supabase_client.get_lead_by_phone(phone)
        resolved_name = data.get("name") or (lead.get("name") if lead and lead.get("name") not in ["Inbound Caller", "Future Pilot", "New Lead"] else None) or "Future Pilot"
        
        if data["course_interest"] in ["Unknown", "Flight Training"] and lead and lead.get("course_interest"):
            data["course_interest"] = lead.get("course_interest")
            
        duration_estimate = len(transcript.split()) * 2
        summary = data.get("notes") or f"Qualifying conversation for {data['course_interest']}. Classified as {data['classification']}."
        
        # Determine outcome
        outcome = "CALLBACK_REQUESTED" if data.get("callback_requested") else "CONNECTED"
        if data.get("booking_intent") == "Campus Visit at Ramphal Chowk":
            outcome = "CAMPUS_VISIT_SCHEDULED"
        elif data.get("booking_intent") == "Counselling Call":
            outcome = "COUNSELLING_SCHEDULED"

        if outcome == "CALLBACK_REQUESTED":
            summary = f"Callback requested ({data.get('callback_time')}). {summary}"

        custom_fields = {
            "is_18_above": data.get("is_18_above"),
            "city_or_location": data.get("city_or_location"),
            "confirmed_education_institute": data.get("confirmed_education_institute"),
            "open_to_ramphal_chowk": data.get("open_to_ramphal_chowk"),
            "scheduled_time": data.get("scheduled_time"),
            "user_query": data.get("user_query"),
            "booking_intent": data.get("booking_intent"),
            "notes": data.get("notes")
        }

        # 1. Update CRM (leads table & lead_activities) directly in Cloud SQL
        supabase_client.record_call_outcome(
            phone=phone,
            outcome=outcome,
            direction=direction,
            duration=duration_estimate,
            recording_url=gcs_recording_url,
            transcript=transcript,
            summary=summary,
            callback_time=data.get("callback_time") or data.get("scheduled_time"),
            course_interest=data["course_interest"],
            classification=data["classification"],
            lead_name=resolved_name,
            email=data.get("email"),
            city=data.get("city_or_location"),
            custom_fields=custom_fields,
            user_query=data.get("user_query"),
            booking_intent=data.get("booking_intent")
        )
        
        # 2. Synchronize with external TeleCRM if configured
        lead_payload = {
            "name": resolved_name,
            "phone": phone,
            "course_interest": data["course_interest"],
            "classification": data["classification"],
            "recording_url": gcs_recording_url
        }
        crm_sync.sync_lead_with_telecrm(lead_payload, transcript)

        # 3. Trigger WhatsApp automated follow-up
        automation.trigger_post_call_automations(phone, data["classification"], resolved_name)
        
        # 4. Clear dialogue session
        clear_session(phone)
        print(f"Post-Call: Pipeline completed for {phone}.")
    finally:
        _active_pipelines.discard(cleaned_phone)

