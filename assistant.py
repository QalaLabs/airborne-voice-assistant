import os
import json
from voice_test import listen
from tts_test import speak_and_get_url
from gpt_test import chat_with_gpt
import rag
import supabase_client
import crm_sync
import automation

# Memory store for conversation history: phone -> list of messages
histories = {}

EXIT_PHRASES = ["goodbye", "thank you", "bye", "exit", "stop", "shukriya", "alvida"]

SYSTEM_PROMPT = """
You are Capt. Modassir, an expert pilot advisor at Airborne Aviation Academy in Dwarka, Delhi.
Your job is to qualify prospective students who are interested in pilot training and cabin crew courses.

You must handle the conversation in a friendly, professional manner using a mix of Hindi and English (Hinglish).
Guide the conversation through these 3 steps naturally:
1. **Identify Course Interest:** Map their interest to one of our 11 courses:
   - DGCA CPL Ground Classes (Fee: Rs 2,70,000)
   - ATPL Ground School (Fee: Rs 1,50,000)
   - Radio Telephony (RTR-A) Exam Prep (Dedicated simulation lab)
   - Cadet Pilot Program Prep (Fee: Rs 50,000)
   - GD & PI Course (Fee: Rs 30,000)
   - Comprehensive Airline Selection Prep (Fee: Rs 1,25,000)
   - Psychomotor Test Prep (CASS/COMPASS/ADAPT) (Fee: Rs 30,000)
   - Airbus A320 Simulator FBS (Fee: Rs 12,000)
   - Cabin Crew / Flight Attendant Training (Fee: Rs 59,000)
   - Private Pilot License (PPL) Ground Classes
   - Multi-Engine Rating (MER) Ground School
2. **Qualify Budget:** Inform them of the relevant fee and check if they are comfortable with it or have a budget ready.
3. **Qualify Timeline:** Ask when they plan to start classes (Immediate, within 3 months, or 6+ months).

Objection Handling:
If they ask questions about eligibility (e.g. Class 2 medicals, 10+2 math/physics), course duration, syllabus, or hostel facilities, use the provided website context to answer concisely.

Formatting & Style:
- Keep your answers short, conversational, and direct (max 2-3 sentences) so it sounds natural when converted to speech.
- If you have successfully captured the Course, Budget, and Timeline, or if the user wants to end the call, say a polite goodbye and include the word "[EXIT]" in your response to signal call completion.
"""

def get_greeting_voice_url(text: str) -> str:
    """
    Synthesizes custom greeting audio.
    """
    return speak_and_get_url(text)

def handle_conversation(recording_url: str, phone: str, direction: str):
    """
    Main dialogue manager for the conversation loop.
    Transcribes audio, retrieves RAG context, gets LLM response, and detects exit.
    """
    caller_input = listen(recording_url)
    print(f"Conversation: Phone={phone}, Input='{caller_input}'")
    
    # Initialize history for this phone if not exists
    if phone not in histories:
        histories[phone] = []
        
    history = histories[phone]
    
    if not caller_input or "could not understand" in caller_input.lower():
        # Fallback greeting if no input detected
        response_text = "I couldn't hear you clearly. Could you please repeat that? (Aapki aawaz clear nahi thi. Kya aap dohara sakte hain?)"
        history.append({"role": "user", "content": "[Silence/Unrecognized Input]"})
        history.append({"role": "assistant", "content": response_text})
        return speak_and_get_url(response_text), False

    # Check for direct exit phrases
    for phrase in EXIT_PHRASES:
        if phrase in caller_input.lower():
            response_text = "Thank you for calling Airborne Aviation Academy. Have a great day ahead! Goodbye."
            history.append({"role": "user", "content": caller_input})
            history.append({"role": "assistant", "content": response_text + " [EXIT]"})
            return speak_and_get_url(response_text), True

    # Retrieve RAG context from the website database
    context = rag.query_rag(caller_input)
    
    # Dynamic system prompt with context
    dynamic_system_prompt = f"{SYSTEM_PROMPT}\n\nRELEVANT WEBSITE CONTEXT:\n{context}"
    
    # Chat with GPT
    ai_response = chat_with_gpt(caller_input, history, dynamic_system_prompt)
    print(f"AI Response: '{ai_response}'")
    
    # Append to memory
    history.append({"role": "user", "content": caller_input})
    history.append({"role": "assistant", "content": ai_response})
    
    # Detect exit signal in response
    should_hang_up = "[EXIT]" in ai_response
    clean_response = ai_response.replace("[EXIT]", "").strip()
    
    return speak_and_get_url(clean_response), should_hang_up

def get_transcript_string(phone: str) -> str:
    """
    Compiles the conversation history for a given phone number into a formatted text log.
    """
    history = histories.get(phone, [])
    log_lines = []
    for msg in history:
        role = "Lead" if msg["role"] == "user" else "AI"
        log_lines.append(f"{role}: {msg['content']}")
    return "\n".join(log_lines)

def clear_session(phone: str):
    """
    Clears the session memory after post-call actions are triggered.
    """
    if phone in histories:
        del histories[phone]

def run_post_call_pipeline(phone: str, direction: str, recording_url: str):
    """
    Asynchronous post-call processor. Extracts lead qualifiers, updates
    Supabase & TeleCRM, and triggers automation paths.
    """
    print(f"Post-Call: Starting pipeline for {phone}...")
    transcript = get_transcript_string(phone)
    if not transcript:
        print("Post-Call: Empty transcript. Skipping processing.")
        return
        
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
    2. budget_status: 'Ready' (comfortable with fees) / 'Not Ready' (uncomfortable/negotiating/needs loan) / 'Unknown'.
    3. timeline_urgency: 'Immediate' / '3 Months' / '6+ Months' / 'Unknown'.
    4. classification: 'Hot' (if course is known, budget is Ready, and timeline is Immediate or 3 Months) / 'Warm' (interested, but planning timeline/budget) / 'Cold' (no interest, wrong number, or no budget).

    Output ONLY as a valid JSON object. Do not include markdown wraps or explanations.
    Example output format:
    {{"course_interest": "DGCA CPL Ground Classes", "budget_status": "Ready", "timeline_urgency": "Immediate", "classification": "Hot"}}

    TRANSCRIPT:
    {transcript}
    """
    
    # Run parsing query
    parse_result = chat_with_gpt(parser_prompt)
    print(f"Post-Call: LLM Parser Output: {parse_result}")
    
    # Load defaults
    data = {
        "course_interest": "Unknown",
        "budget_status": "Unknown",
        "timeline_urgency": "Unknown",
        "classification": "Cold"
    }
    
    # Parse JSON output safely
    try:
        # Strip potential markdown formatting if returned
        clean_json = parse_result.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
            
        data.update(json.loads(clean_json))
    except Exception as e:
        print(f"Post-Call: JSON parsing failed ({e}). Attempting keyword fallback.")
        # Fallback keyword matching
        for course in [
            "CPL", "ATPL", "RTR", "Cadet", "GD", "Airline", "Psychomotor", "Simulator", "Cabin Crew", "PPL", "Multi-Engine"
        ]:
            if course.lower() in parse_result.lower():
                data["course_interest"] = course
        if "hot" in parse_result.lower():
            data["classification"] = "Hot"
        elif "warm" in parse_result.lower():
            data["classification"] = "Warm"
            
    # Retrieve lead profile from Supabase to fetch name
    lead_name = "Future Pilot"
    lead = supabase_client.get_lead_by_phone(phone)
    if lead:
        lead_name = lead.get("name", "Future Pilot")
        
    # 1. Update Qualification fields in Supabase
    supabase_client.update_lead_qualification(
        phone=phone,
        budget_status=data["budget_status"],
        timeline_urgency=data["timeline_urgency"],
        course_interest=data["course_interest"],
        classification=data["classification"]
    )
    
    # 2. Log Call Log to Supabase
    duration_estimate = len(transcript.split()) * 2 # Mock duration estimate (approx 2s per word spoken)
    summary = f"Qualifying conversation for {data['course_interest']}. Classified as {data['classification']}."
    supabase_client.save_call_log(
        phone=phone,
        direction=direction,
        duration=duration_estimate,
        recording_url=recording_url,
        transcript=transcript,
        summary=summary
    )
    
    # 3. Synchronize with TeleCRM
    lead_payload = {
        "name": lead_name,
        "phone": phone,
        "course_interest": data["course_interest"],
        "classification": data["classification"],
        "budget_status": data["budget_status"],
        "timeline_urgency": data["timeline_urgency"]
    }
    crm_sync.sync_lead_with_telecrm(lead_payload, transcript)
    
    # 4. Trigger WhatsApp automated follow-up
    automation.trigger_post_call_automations(phone, data["classification"], lead_name)
    
    # 5. Clear dialogue session
    clear_session(phone)
    print(f"Post-Call: Pipeline completed for {phone}.")

