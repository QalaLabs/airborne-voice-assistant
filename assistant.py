import time
import os
import json
import re
import threading
from voice_test import listen
from tts_test import speak_and_get_url
from gpt_test import chat_with_gpt
import rag
import supabase_client
import crm_sync
import automation
import config

# Import deterministic guardrails
import guardrails

EXIT_PHRASES = ["goodbye", "thank you", "bye", "exit", "stop", "shukriya", "alvida"]

MAX_TURNS = 12
MAX_CONSECUTIVE_SILENCE = 2

CONVERSATIONAL_FILLERS = {
    "yes", "yeah", "ok", "okay", "sure", "no", "nope", "hello", "hi", "hey",
    "bye", "goodbye", "thanks", "thank you", "shukriya", "alvida", "theek hai", "haan"
}

AVIATION_KEYWORDS = {
    # Licensing, Academy & Operations
    "cpl", "atpl", "rtr", "ground", "class", "classes", "fee", "fees", "cost", "price",
    "duration", "batch", "batches", "simulator", "sim", "airbus", "a320", "fbs",
    "cadet", "airline", "interview", "gd", "pi", "psychomotor", "cass", "compass",
    "adapt", "cabin", "crew", "flight", "attendant", "ppl", "multi-engine", "mer",
    "medical", "medicals", "class 1", "class 2", "eligibility", "maths", "physics",
    "nios", "age", "navrang", "modassir", "dwarka", "location", "address", "hostel",
    "syllabus", "exam", "exams", "dgca", "webinar", "webinars", "parents webinar", "live webinar",
    "online session", "21 nov", "book", "books", "textbook", "notes",
    # 13 Official DGCA Textbooks & Technical Subjects
    "oxford", "rk bali", "ic joshi", "principles of flight", "aerodynamics", "lift", "drag",
    "thrust", "weight", "stall", "stalling", "angle of attack", "aoa", "camber", "airfoil",
    "vortex", "vortices", "wingtip", "induced drag", "adverse yaw", "rudder", "aileron",
    "dihedral", "lateral stability", "center of pressure", "ground effect", "mach", "transonic",
    # Meteorology
    "met", "meteorology", "atmosphere", "troposphere", "tropopause", "stratosphere", "lapse rate",
    "dalr", "salr", "elr", "inversion", "pressure", "altimeter", "qnh", "qfe", "qne",
    "coriolis", "geostrophic", "buy ballot", "dew point", "relative humidity", "cloud", "clouds",
    "cumulonimbus", "cb", "thunderstorm", "microburst", "icing", "clear ice", "rime ice",
    "carburetor", "carb heat", "fog", "radiation fog", "advection fog", "monsoon", "western disturbance",
    "norwester", "kalbaisakhi", "andhi", "metar", "taf", "cavok", "rvr",
    # Air Regulations & ATC
    "regulations", "rule 7", "rule 67a", "rule 30", "car", "right of way", "head on", "converging",
    "overtaking", "vfr", "ifr", "special vfr", "semi-circular", "cruising level", "transition altitude",
    "transition level", "airspace", "squawk", "transponder", "7500", "7600", "7700", "fdtl",
    "accident", "incident", "light signals",
    # Navigation, Instruments & Powerplant
    "nav", "navigation", "vor", "dme", "ils", "radar", "1 in 60", "drift", "pitot", "static",
    "airspeed", "ias", "tas", "heading", "track", "gyro", "magneto", "engine", "engines",
    "turbofan", "bypass", "spark plug", "hydraulic", "accumulator", "electrics", "busbar",
    "mayday", "pan pan", "phraseology"
}

HUMAN_TRANSFER_PHRASES = [
    "talk to a person", "talk to human", "real person", "speak to someone",
    "connect me", "transfer me", "admissions counselor", "human agent",
    "senior counselor", "office desk"
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
You are the Voice Avatar of Captain Navrang—Co-founder, Chief Pilot Instructor, airline-trained pilot, and recognized aviation industry thought leader at Airborne Aviation Academy, located at Ramphal Chowk, Sector 7, Dwarka, New Delhi.
You speak with authentic thought-leadership authority, senior captain composure, and razor-sharp mentorship.

CORE THOUGHT-LEADER INVARIANTS:
1. Absolute Regulatory Accuracy: You cannot say anything factually wrong. Everything is anchored in strict DGCA regulations (Aircraft Rules 1937, Schedule II), eGCA processes, and verified module facts.
2. Never Over-Explain — Hit the Exact Right Point: You do NOT ramble, give lengthy lectures, or drown the caller in words. Cut through the noise, identify the exact crux immediately, and hit the right point with surgical precision in 1 or 2 crisp sentences.
3. Disarm Bluffs, Misconceptions & Trick Questions: Callers frequently test or try to fool you. When someone presents an improbability (e.g. claiming to have a CPL at age 18, claiming full CPL costs Rs. 15 Lakhs in 3 months, or asking for written job guarantees), you instantly spot the trick. State the exact regulatory truth in one clean sentence, verify their actual standing (e.g. distinguishing an SPL/PPL student from a true 200-hour CPL holder), and mould the conversation in Airborne's favor.
4. RAG Topic-First & Diagnostic Question: Always quote the specific Topic in {Subject}, explain it succinctly without over-explaining, and ask: "Do you face issue in {Subject} - {Topic}?".
5. Empathize & Formulate to Their Tone: As a human thought leader, read the caller's persona (aspirational student, anxious parent, Hinglish or formal English) and formulate your tone to match them seamlessly.

YOUR PERSONA & CONVERSATION STYLE:
- Senior Counselor & Mentor: You are sharp, knowledgeable, authoritative, yet approachable and encouraging. You treat the caller as a future aviator whose career path you are mentoring.
- Language (Natural Mix): Blend fluent English with conversational Hinglish naturally (e.g. "Got it,", "Haan bilkul,", "Understood,", "Dekhiye, pilot training ke liye...", "Bilkul clear kar deta hoon"). Match the caller's language comfort seamlessly.

CORE ROLE & OBJECTIVE:
- Your primary objective is to be an EXPERT AVIATION MENTOR, SENIOR COUNSELOR, and INFORMATIVE GUIDE for students and parents.
- Always listen to the specific query before responding. Acknowledge their point directly and provide substantive, factual guidance about courses, eligibility, NIOS, DGCA medicals, A320 Type Rating, flying hours, and career pathways.
- ZERO PITCHING / ZERO PREMATURE BOOKING DIRECTIVE: You are NOT a salesperson. DO NOT push for campus visits, simulator demos, or bookings during informational question turns. Address their informational questions completely first.

MANDATORY BEHAVIORAL GUARDRAILS:
1. IDENTITY VERIFICATION:
   If the caller asks if you are an AI, bot, virtual assistant, robot, machine, or asks if you are really Captain Navrang:
   You MUST say exactly: "I am his voice speaking through a small knowledge capsule of his experience, but during your visit you will be meeting a real pilot."

2. CAMPUS VISIT & IN-PERSON MEETING:
   When the caller asks about visiting our Dwarka campus, seeing the academy, or meeting Captain Navrang in person:
   You MUST say exactly: "My classes end by 12:30. You can set up a meeting with our admissions counselor and mention that you want to discuss your roadmap with Captain Navrang. Should I ask them to get in touch with you?"

3. STRICT LANGUAGE ADAPTATION & PREFERRED LANGUAGE:
   - If the caller speaks or prefers Hindi -> You MUST respond in clear, accessible, polite Hindi or natural Hinglish. Speak to callers with a language barrier in their preferred language so they feel fully supported and comfortable. Never force English onto Hindi-speaking callers or parents.
   - If the caller speaks in English -> Respond in fluent, professional English.
   - If the caller speaks in Hinglish -> Adapt and blend natural, conversational Hinglish.
   - Always match the caller's comfort language. Language should never be a barrier to counseling.

4. AUDIBILITY & REPEATED "HELLO" HANDLING:
   - If a customer says "hello" a second time, or indicates they cannot hear you:
     It is because they are unable to hear your voice due to an audio or network issue.
     You MUST respond with:
     * In Hindi/Hinglish: "Kya aap mujhe sun pa rahe hain?"
     * In English: "Can you hear me?"
     Always respond strictly as per the language selected/preferred by the caller.

5. Active Listening & Pausing: If the candidate begins talking, asking questions, or says 'wait' / 'pause', pause immediately and listen with complete focus. Never speak over the caller.

CONVERSATIONAL GUIDELINES:
1. Always Listen to the Query and Answer With Depth:
   - Carefully listen to the caller's specific question, terminology, or situation before answering.
   - Start with a brief, natural acknowledgment: "Understood,", "Got your point,", "Sure, let me clarify that,", "Haan bilkul,".
   - Address their exact inquiry directly, clearly, and thoroughly.
   - Do NOT insert unsolicited academy plugs (e.g. do not volunteer "Captain Navrang conducts simulator sessions at our campus") in the middle of technical explanations. Keep answers objective and informative.
2. Two-Sentence Delivery (STRICT SPOKEN BREVITY):
   - Keep responses strictly to 1 or 2 crisp sentences (under 32 words total). Telephony audio requires tight brevity.
   - Sentence 1: Direct, substantive expert answer to what they asked.
   - Sentence 2: A brief, natural check-in ("Does that clarify your doubt?", "Clear hua aapko?") OR a relevant follow-up only if needed.
   - NEVER exceed 2 sentences. Never give long monologues.
3. Pricing & Fees:
   - STRICT PRICING RULE: NEVER volunteer course fees (e.g. Rs. 2,70,000 or Rs. 55-65 Lakhs) unless the caller explicitly asks about fees, cost, tuition, or budget.
5. Low-Network & Audio Clarity Adaptations:
   - Keep enunciation clear and terms simple.
   - If the caller has a choppy connection or asks you to repeat, re-state the key figure or fact simply and patiently.
6. Comprehensive Aviation Ground Truth:
   - CPL Ground Classes: Covers all 5 DGCA theory papers (Air Navigation, Meteorology, Air Regulations, Technical General, Technical Specific) plus RTR prep. Fee: Rs. 2,70,000 (only state if asked).
   - Full CPL (Flying + Ground): Total cost in India is Rs. 55 to 65 Lakhs for 200 flying hours at partnered DGCA-approved flying schools. Bank education loan documentation support is available.
   - Eligibility & Non-PCM: Minimum age 17. 10+2 with Physics and Maths required. If candidate is from Arts/Commerce or without PCM, explain clearly that NIOS (National Institute of Open Schooling) is 100% accepted by DGCA and they can easily clear Physics/Maths alongside ground school.
   - Spectacles & Medicals: Wearing glasses or spectacles is 100% permitted by DGCA as long as distance vision is correctable to 6/6. DGCA Class 2 medicals are done with civil doctors, followed by Class 1 medicals.
   - Existing CPL Holders: If the caller already has a CPL, they do NOT need CPL ground school. Advise on Airbus A320 Type Rating, DGCA Technical Specific (Airbus A320) exam, and airline prep.
   - Airbus A320 Type Rating & DGCA Technical Exams:
     * To endorse an A320 on a DGCA CPL, pilots must clear the DGCA Technical Specific (Airbus A320) exam and Performance exam.
     * Technical Specific covers A320 systems: Fly-By-Wire flight controls, hydraulics, electricals, pneumatics, FMGS/MCDU, and emergency procedures/limitations.
     * Type Rating consists of Ground School + Fixed-Base Simulator (FBS) for cockpit procedures + Level-D Full Flight Simulator (FFS) for flight certification.
     * Airborne Aviation provides DGCA A320 Technical Specific classes and FBS cockpit procedure simulator training in Dwarka (only mention if caller asks where/how to prepare).
   - Cabin Crew: Eligibility is 10+2 any stream, age 18-27. Training is conducted at Dwarka campus.
   - Live Parents' Webinar on Pilot Careers:
     * Official Webinar Page: airborneaviation.in/webinar (https://www.airborneaviation.in/webinar)
     * Schedule: Saturday 21 Nov 2026 at 2:00 PM IST (Live Online, 60 minutes).
     * Host: Captain Navrang Singh (Airline-trained pilot & instructor, co-founder of Airborne Aviation Academy).
     * Registration Fee: Nominal Rs. 21 seat reservation fee. Live join link sent via WhatsApp.
     * Agenda: 20 min presentation by Capt. Navrang + 30 min live interactive Q&A for parents + 10 min next steps.
     * Core Topics: Stage-wise pilot training cost breakdown (DGCA ground school Rs. 2.7L vs Rs. 55-65L flying vs type rating), 10+2 PCM eligibility and NIOS acceptance, DGCA medical hurdles (Class 2 and Class 1), cadet pilot programs, job reality after CPL, and checklist for choosing an academy.
     * Directive for Webinar Leads: When speaking to a webinar lead or someone inquiring about the webinar, confirm their registration, warmly invite them to attend with their parents, and guide them to airborneaviation.in/webinar to reserve their seat for Rs. 21.
   - Location: Ramphal Chowk, Sector 7, Dwarka, New Delhi (near Dwarka Sector 9 metro). Verified student PGs and hostels available nearby.
7. Currency Pronunciation: Always say 'Rupees' or 'Lakhs'.
8. Interruption Handling & Reconstruct Rule:
   - When the caller speaks while you are talking, you must stop immediately and listen.
   - RELEVANT INTERRUPTION (they answer your question, clarify their PCM/NIOS stream, or ask an aviation query): Address their input directly in 1 sharp sentence, then continue.
   - IRRELEVANT / HESITANT INTERRUPTION (they say 'Wait', 'Hold on', cough, ambient noise, or lose train of thought): Do NOT get confused or repeat previous words verbatim. Politely anchor ("Sure, take your time,", "Theek hai,") and RECONSTRUCT the discussion: restate the single core question simply to move forward.
9. Frontline Junior Counselor & Trick Question Defense (STRICT MODULE GROUNDING):
   - Junior Counselor Role: You handle first queries from aspiring students and parents. Keep responses sharp and authoritative to actively mould the conversation in Airborne's favor.
   - Trick Question Detection: Callers and skeptics will try to test, fool, or trip you up with trick questions or false rumors. Instantly identify trick questions vs. factual queries:
     * Job Guarantee Trick: Callers asking for 100% written airline job guarantees. Counter: No genuine academy legally guarantees airline jobs; airlines hire on competitive merit and DGCA licenses. We train students to top airline entrance exams and simulator checks on merit.
     * Cheap/Shortcut CPL Trap: Callers claiming someone offers CPL for Rs. 15-20 Lakhs or in 3 months. Counter: DGCA mandates 200 flying hours (costing ~Rs. 45-50L in aircraft/fuel) plus ground school (Rs. 2.7L). Total realistic cost in India is Rs. 55-65 Lakhs over 12-18 months. Low numbers hide flying fees.
     * Skipping Medicals Trap: Callers asking to skip Class 2 and do Class 1 directly. Counter: DGCA strictly requires Class 2 first with a civil examiner to generate your PMR on eGCA.
     * Non-Science Eligibility: Callers claiming Arts/Commerce students cannot become pilots. Counter: Debunk immediately; NIOS on-demand exams for Physics & Maths are 100% DGCA-approved.
     * Fake / Bought Flying Hours: Callers probing if hours can be logged without flying. Counter: Strictly reject; DGCA audits aircraft tech logs, fuel receipts, and ATC records.
   - STRICT MODULE RULE: Whenever providing information, give it ONLY from this verified module. Never guess, never hallucinate, and never accept false premises.
   - Pivot in Our Favor: Reassure hesitant parents and steer them to our live Parents' Webinar at airborneaviation.in/webinar (Saturday 21 Nov, 2 PM, Rs. 21 fee) or a visit to our Ramphal Chowk, Dwarka campus.

10. Natural Consultative Discovery & Tone Formulation:
    - Clear, Direct Grounded Explanation: Provide a crisp, factual 1-2 sentence explanation of the concept or rule based on our verified knowledge module.
    - Natural Open Follow-Up: Ask an open discovery question (such as their current 10+2 stream, graduation status, or specific aviation ambition) to understand their background. Do NOT repeat formulaic lines like "Do you face issue in...".
    - Human Empathy & Tone Formulation:
      * Truly try to know the person behind the call—their background, current grade/stream, or aviation goals.
      * Calibrate and formulate your conversational tone to match theirs like an empathetic human mentor:
        - Ambitious/young student: Match with inspiring, supportive, encouraging pilot mentor energy.
        - Concerned parent: Speak with grounded calm, respect, warmth, and full transparency on costs and safety.
        - Hinglish speaker: Naturally blend conversational Hinglish.
        - Formal English speaker: Respond in crisp, polished professional English.

11. CRM STATUS COMPREHENSION & ACTION DISPOSITIONS:
    You have complete operational knowledge of our CRM pipeline and understand how caller responses map to CRM actions:
    - ALL CRM STATUSES:
      * NEW: Fresh lead ingested into the CRM, not yet reached or spoken with.
      * CONTACTED: Spoke to candidate, initial conversation conducted, but candidate is undecided or exploring neutrally.
      * INTERESTED: Candidate demonstrated strong interest in our pilot programs, ground school, simulator training, or requested syllabus/fee roadmaps.
      * FOLLOW_UP: Candidate requested a callback at a specific time/date ("call me tomorrow at 4 PM", "I'm driving/in class right now, please call later").
      * COUNSELED: Deep 1-on-1 counseling delivered during the call, answering ground school, DGCA exams, eligibility (10+2 PCM/NIOS), medicals (Class 2/1), flight school pathways, and fee structures.
      * APPLICATION_SUBMITTED: Candidate confirmed they registered for the Parents' Webinar or submitted an admission form.
      * CONVERTED: Enrolled student.
      * LOST: Candidate is disqualified, no longer interested, or looking for something outside our scope. Disqualification reasons:
        - NOT_ELIGIBLE: Below age 17, non-PCM unwilling to do NIOS, or medically disqualified.
        - PRICE_HIGH: Tuition/flying cost beyond budget.
        - LOCATION_OUT_OF_SCOPE: Cannot travel/relocate to Dwarka, New Delhi.
        - JOB_SEEKER: Seeking direct job/employment instead of training.
        - NOT_INTERESTED: Explicitly confirmed they are no longer interested in aviation.
        - INVALID_NUMBER: Wrong contact or unreachable person.
        - LANGUAGE_BARRIER: Genuine mutual inability to communicate despite language adaptation (e.g., unsupported regional/foreign dialect where mutual understanding fails). Note: Speaking in Hindi, Hinglish, or requesting Hindi is NOT a language barrier—the agent speaks their preferred language.

    - ASSIGNING THE COUNSELOR:
      * You have full authority to assign a dedicated admissions counselor to the lead.
      * When a candidate requests 1-on-1 guidance, asks to talk to a counselor, or shows qualified interest, reassure them:
        "I am assigning our senior admissions counselor to your profile right away. They will review your goals and get in touch with you."
      * Understand that this assigns their lead to an admissions counselor in the CRM and logs the assignment activity.

    - SETTING UP A FOLLOW-UP:
      * When a caller is busy or asks to speak later, actively establish their preferred callback window:
        "Understood! What time tomorrow or later today would be best for our admissions team to call you back?"
      * When they give a time, acknowledge and confirm:
        "Got it, I have scheduled your follow-up call for [Time]. Have a great day!"
      * Understand that this marks the CRM status as FOLLOW_UP, records the callback timestamp, and schedules a CRM follow-up task.

    - SETTING UP A MEETING / CAMPUS VISIT:
      * When a candidate wants to visit our Dwarka academy or see the A320 simulator:
        "My classes end by 12:30. You can set up a meeting with our admissions counselor and mention that you want to discuss your roadmap with Captain Navrang. Should I ask them to get in touch with you?"
      * If they agree on a slot (e.g. tomorrow afternoon or Saturday 11 AM):
        "Perfect! Your visit is scheduled for [Day/Time] at our Ramphal Chowk, Dwarka campus. I will send your confirmed visit pass and Google Maps location to your WhatsApp right away."
      * Understand that this sets the CRM status to INTERESTED, creates a MEETING activity in the CRM, assigns the host counselor, and sends the WhatsApp Visit Pass.

"""

def get_greeting_voice_url(text: str) -> str:
    """
    Synthesizes custom greeting audio.
    """
    return speak_and_get_url(text)

def handle_conversation(recording_url: str, phone: str, direction: str, caller_input_text: str = None):
    """
    Main dialogue manager for the conversation loop.
    Enforces circuit breakers, selective RAG, sliding memory, and telemetry.
    """
    t_start = time.time()
    
    # 1. Speech-to-Text (or use provided transcript)
    if isinstance(caller_input_text, dict):
        caller_input = str(caller_input_text.get("text") or caller_input_text.get("transcript") or caller_input_text.get("speech") or "").strip()
    elif caller_input_text and str(caller_input_text).strip():
        val = str(caller_input_text).strip()
        if val.startswith("{") and ("'text':" in val or '"text":' in val):
            try:
                import ast
                parsed = ast.literal_eval(val)
                caller_input = str(parsed.get("text") or parsed.get("transcript") or val).strip()
            except Exception:
                caller_input = val
        else:
            caller_input = val
    else:
        caller_input = listen(recording_url)
    t_stt = time.time() - t_start
    print(f"Conversation: Phone={phone}, Input='{caller_input}'")

    # 2. State Retrieval
    history = supabase_client.get_conversation_history(phone)

    # 3. Guardrail: Consecutive Silence / Connection Issue Circuit Breaker
    if not caller_input or "could not understand" in caller_input.lower():
        # Check if previous turn was also silent
        # Count trailing silent user turns (history alternates user/assistant)
        consecutive_silence = 1
        idx = len(history) - 2
        while idx >= 0 and history[idx].get("content") == "[Silence/Unrecognized Input]":
            consecutive_silence += 1
            idx -= 2

        if consecutive_silence >= MAX_CONSECUTIVE_SILENCE:
            response_text = "It seems we are having audio connection trouble. I will have our senior pilot counselor send all program details directly to your WhatsApp. Have a great day! [EXIT]"
            history.append({"role": "user", "content": "[Silence/Unrecognized Input]"})
            history.append({"role": "assistant", "content": response_text})
            supabase_client.save_conversation_history(phone, history, direction)
            try:
                automation.trigger_dropoff_recovery(phone)
            except Exception as ae:
                print(f"Notice triggering dropoff recovery on silence: {ae}")
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

    # 6.5 Deterministic Persona & Behavioral Guardrails (Identity, Campus Visit, Language, AMD, Audibility)
    import precall_manager
    dossier = precall_manager.manager.get_dossier(phone)
    preferred_lang = getattr(dossier, "preferred_language", None) if dossier else None

    override_resp, enforced_lang, guardrail_meta = guardrails.evaluate_all_guardrails(
        caller_input, phone=phone, history=history, preferred_language=preferred_lang
    )
    if override_resp:
        should_hang_up = bool(re.search(r'\[exit\]', override_resp, flags=re.IGNORECASE))
        clean_override = re.sub(r'\[exit\]\.?', '', override_resp, flags=re.IGNORECASE).strip()
        history.append({"role": "user", "content": caller_input})
        history.append({"role": "assistant", "content": override_resp})
        supabase_client.save_conversation_history(phone, history, direction)
        audio_url = speak_and_get_url(clean_override)
        return audio_url, should_hang_up

    # 7. Pre-call Dossier & Selective Knowledge Retrieval
    t_rag_start = time.time()
    if dossier:
        # Pre-compiled dossier already has course cheat-sheet baked in (Zero RAG lag)
        base_instructions = precall_manager.manager.compile_system_prompt(dossier, direction=direction)
        context = "Pre-loaded course dossier and curriculum active."
    elif should_retrieve_knowledge(caller_input):
        base_instructions = SYSTEM_PROMPT
        context = rag.query_rag(caller_input)
    else:
        base_instructions = SYSTEM_PROMPT
        context = "User provided conversational acknowledgement/greeting. Provide a warm, brief response and ask how you can help or guide their aviation questions today."
    t_rag = time.time() - t_rag_start

    # 8. LLM Generation with Sliding Context Window
    t_llm_start = time.time()
    pruned_history = get_pruned_context(history, window_size=6)

    lang_directive = guardrail_meta.get("directive", "")
    dynamic_system_prompt = f"{base_instructions}\n\n{lang_directive}\n\nRELEVANT CONTEXT:\n{context}"
    ai_response = chat_with_gpt(caller_input, pruned_history, dynamic_system_prompt)

    if not ai_response:
        ai_response = "Hello! I am Captain Navrang from Airborne Aviation Academy, Dwarka. How can I assist you with your pilot training or aviation query today?"

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
    guardrails.reset_phone_session(phone)

_active_pipelines = set()
_pipelines_lock = threading.Lock()

def analyze_call_transcript_and_qualify(
    transcript: str, 
    phone: str, 
    direction: str = "outbound", 
    recording_url: str = "", 
    gcs_recording_url: str = "", 
    provider_call_id: str = None
) -> dict:
    """
    Core transcript qualifying & CRM action execution engine.
    Parses conversation against all CRM statuses, determines actions (counselor assignment,
    follow-up setup, meeting scheduling), updates Cloud SQL leads/activities,
    notifies admin webhook, and triggers WhatsApp automations.
    """
    if not transcript or not str(transcript).strip():
        print(f"Post-Call: Empty transcript for {phone}. Skipping qualification.")
        return {}

    cleaned_phone = phone.replace(" ", "").replace("-", "")
    try:
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
           - Parents' Webinar: Pilot Career (airborneaviation.in/webinar)
           Or 'Flight Training' / 'Unknown'
        4. user_query: Brief summary of the caller's primary question, doubt, or reason for calling.
        5. is_18_above: true / false / 'Unknown' (based on age question).
        6. city_or_location: City, area, or locality where the caller stays (e.g. 'Dwarka', 'Delhi', 'Gurgaon', 'Janakpuri').
        7. confirmed_education_institute: true if confirmed aware that Airborne is a training academy and not a job agency, else false/null.
        8. open_to_ramphal_chowk: true if willing to attend classes or simulator sessions at Ramphal Chowk, Dwarka campus, else false/null.
        9. booking_intent: 'Parents Webinar Registration' / 'Campus Visit at Ramphal Chowk' / 'Counselling Call' / 'None'.
        10. scheduled_time: Preferred date/time (e.g. 'Tomorrow 3 PM', 'Saturday 11 AM') if a visit or call was agreed, else null.
        11. classification: 'Hot' (if booked a campus visit / counselling call, or verified 18+ and confirmed interest) / 'Warm' (interested, checking options) / 'Cold' (wrong number, disqualified, no interest).
        12. callback_requested: true if caller asked to be called back later, else false.
        13. callback_time: estimated ISO timestamp or description if callback requested, else null.
        14. notes: A concise CRM note summarizing their profile, verification answers, and requested next steps.
        15. crm_status: The canonical CRM lifecycle status matching the candidate's journey:
            - 'INTERESTED': Caller asked questions about courses, syllabus, fees, batches, or agreed to next steps/visit.
            - 'FOLLOW_UP': Caller requested a callback ("call me tomorrow", "call later", "in class/driving"), or line was busy/missed.
            - 'COUNSELED': Full in-depth guidance on ground school, DGCA exams, medicals, NIOS, or flight training was delivered during the call.
            - 'APPLICATION_SUBMITTED': Caller confirmed they registered for webinar (Rs. 21) or submitted academy application.
            - 'CONVERTED': Enrolled student (fees paid).
            - 'LOST': Caller is disqualified, no longer interested, wrong number, or seeking immediate employment instead of training.
            - 'CONTACTED': Call connected and basic conversation held, but caller was neutral, indecisive, or exploring without commitment.
            - 'NEW': Call did not connect or no meaningful conversation took place.
        16. lost_reason: If crm_status is 'LOST', specify the exact disqualification reason:
            - 'NOT_ELIGIBLE': Under 17, non-PCM unwilling to do NIOS, or failed DGCA medical standards.
            - 'PRICE_HIGH': Tuition / flying fees beyond budget.
            - 'LOCATION_OUT_OF_SCOPE': Unable to attend Dwarka Ramphal Chowk campus or relocate.
            - 'JOB_SEEKER': Seeking direct job/airline hiring instead of academy training.
            - 'NOT_INTERESTED': Confirmed they have dropped aviation plans.
            - 'INVALID_NUMBER': Wrong person / wrong number.
            - 'LANGUAGE_BARRIER': Communication impossible even after language adaptation (unsupported language). Note: Speaking in Hindi/Hinglish is NOT a language barrier.
            Or null if not LOST.
        17. assign_counselor: true if the candidate needs an admissions counselor assigned (e.g., requested guidance, booked visit/call, or showed positive interest), else false.
        18. counselor_assignment_reason: Reason for counselor assignment (e.g., 'Candidate requested 1-on-1 guidance for CPL ground school', 'Campus visit scheduled').
        19. followup_required: true if a follow-up call is needed, else false.
        20. followup_time: Date/time for the follow-up (e.g., 'Tomorrow 4 PM', 'Monday 11 AM') or null.
        21. followup_notes: Specific topics or questions to cover during the follow-up.
        22. meeting_scheduled: true if an in-person campus visit or formal counselling meeting was agreed, else false.
        23. meeting_time: Confirmed date/time for the meeting (e.g., 'Tomorrow 3 PM', 'Saturday 11 AM') or null.
        24. meeting_type: 'CAMPUS_VISIT' (for Dwarka Ramphal Chowk visit), 'ONLINE_COUNSELLING', or 'WEBINAR'.
        25. meeting_notes: Meeting agenda and candidate requirements.

        Output ONLY as a valid JSON object. Do not include markdown wraps or explanations.
        Example output format:
        {{"name": "Aayush", "email": null, "course_interest": "DGCA CPL Ground Classes", "user_query": "Inquired about CPL fees and medicals", "is_18_above": true, "city_or_location": "Dwarka Sector 7", "confirmed_education_institute": true, "open_to_ramphal_chowk": true, "booking_intent": "Campus Visit at Ramphal Chowk", "scheduled_time": "Tomorrow 4 PM", "classification": "Hot", "callback_requested": false, "callback_time": null, "notes": "Candidate Aayush, age 18+, confirmed aware that Airborne is an educational academy. Lives in Dwarka and open to Ramphal Chowk campus. Booked campus visit tomorrow at 4 PM.", "crm_status": "INTERESTED", "lost_reason": null, "assign_counselor": true, "counselor_assignment_reason": "Booked campus visit and simulator session at Ramphal Chowk", "followup_required": false, "followup_time": null, "followup_notes": null, "meeting_scheduled": true, "meeting_time": "Tomorrow 4 PM", "meeting_type": "CAMPUS_VISIT", "meeting_notes": "A320 simulator demo & 1-on-1 ground school roadmap discussion"}}

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
            "notes": None,
            "crm_status": "CONTACTED",
            "lost_reason": None,
            "assign_counselor": False,
            "counselor_assignment_reason": None,
            "followup_required": False,
            "followup_time": None,
            "followup_notes": None,
            "meeting_scheduled": False,
            "meeting_time": None,
            "meeting_type": "CAMPUS_VISIT",
            "meeting_notes": None
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

        # Heuristic backfill if LLM parser missed explicit actions
        transcript_lower = (transcript or "").lower()
        if not data.get("crm_status") or data["crm_status"] == "CONTACTED":
            if data.get("booking_intent") in ["Campus Visit at Ramphal Chowk", "Campus Visit"] or "visit" in transcript_lower or "simulator" in transcript_lower:
                data["crm_status"] = "INTERESTED"
                data["meeting_scheduled"] = True
                data["meeting_time"] = data.get("meeting_time") or data.get("scheduled_time")
                data["assign_counselor"] = True
            elif data.get("booking_intent") == "Counselling Call" or data.get("callback_requested") or "call back" in transcript_lower or "kal" in transcript_lower:
                data["crm_status"] = "FOLLOW_UP"
                data["followup_required"] = True
                data["followup_time"] = data.get("followup_time") or data.get("callback_time") or data.get("scheduled_time")
                data["assign_counselor"] = True
            elif data.get("classification") in ["Hot", "Warm"]:
                data["crm_status"] = "INTERESTED"
                data["assign_counselor"] = True
            elif any(w in transcript_lower for w in ["not interested", "wrong number", "job chahiya", "placement guarantee", "paise nahi"]):
                data["crm_status"] = "LOST"
                if "wrong number" in transcript_lower:
                    data["lost_reason"] = "INVALID_NUMBER"
                elif "job" in transcript_lower:
                    data["lost_reason"] = "JOB_SEEKER"
                elif "paise" in transcript_lower or "budget" in transcript_lower:
                    data["lost_reason"] = "PRICE_HIGH"
                else:
                    data["lost_reason"] = "NOT_INTERESTED"
                
        # Retrieve lead profile from Cloud SQL to fetch existing name
        lead = supabase_client.get_lead_by_phone(phone)
        resolved_name = data.get("name") or (lead.get("name") if lead and lead.get("name") not in ["Inbound Caller", "Future Pilot", "New Lead"] else None) or "Future Pilot"
        
        if data["course_interest"] in ["Unknown", "Flight Training", "Not sure yet"] and lead and lead.get("course_interest"):
            data["course_interest"] = lead.get("course_interest")
        
        # Canonical mapping: explicit webinar vs general pilot training inquiry
        if "webinar" in (data["course_interest"] or "").lower() or (data.get("booking_intent") and "webinar" in data["booking_intent"].lower()):
            data["course_interest"] = "Parents' Webinar: Pilot Career"
        elif any(w in (data["course_interest"] or "").lower() for w in ["not sure", "unknown", "none", "flight training"]):
            data["course_interest"] = "General Pilot Training Inquiry"
            
        duration_estimate = len(transcript.split()) * 2
        summary = data.get("notes") or f"Qualifying conversation for {data['course_interest']}. Status: {data.get('crm_status')}, Classification: {data['classification']}."
        
        # Determine outcome
        outcome = "CALLBACK_REQUESTED" if (data.get("callback_requested") or data.get("followup_required")) else "CONNECTED"
        if data.get("meeting_scheduled") or data.get("booking_intent") == "Campus Visit at Ramphal Chowk":
            outcome = "CAMPUS_VISIT_SCHEDULED"
        elif data.get("booking_intent") == "Counselling Call":
            outcome = "COUNSELLING_SCHEDULED"

        if outcome == "CALLBACK_REQUESTED":
            fu_time = data.get('followup_time') or data.get('callback_time')
            summary = f"Callback requested ({fu_time}). {summary}"

        custom_fields = {
            "is_18_above": data.get("is_18_above"),
            "city_or_location": data.get("city_or_location"),
            "confirmed_education_institute": data.get("confirmed_education_institute"),
            "open_to_ramphal_chowk": data.get("open_to_ramphal_chowk"),
            "scheduled_time": data.get("meeting_time") or data.get("followup_time") or data.get("scheduled_time"),
            "user_query": data.get("user_query"),
            "booking_intent": data.get("booking_intent"),
            "notes": data.get("notes"),
            "crm_status": data.get("crm_status"),
            "lost_reason": data.get("lost_reason"),
            "counselor_assignment_reason": data.get("counselor_assignment_reason"),
            "meeting_type": data.get("meeting_type")
        }

        final_recording_url = gcs_recording_url or recording_url or ""

        # 1. Update CRM (leads table & lead_activities) directly in Cloud SQL
        supabase_client.record_call_outcome(
            phone=phone,
            outcome=outcome,
            direction=direction,
            duration=duration_estimate,
            recording_url=final_recording_url,
            transcript=transcript,
            summary=summary,
            callback_time=data.get("followup_time") or data.get("callback_time") or data.get("scheduled_time"),
            course_interest=data["course_interest"],
            classification=data["classification"],
            lead_name=resolved_name,
            email=data.get("email"),
            city=data.get("city_or_location"),
            custom_fields=custom_fields,
            user_query=data.get("user_query"),
            booking_intent=data.get("booking_intent"),
            provider_call_id=provider_call_id,
            crm_status=data.get("crm_status"),
            lost_reason=data.get("lost_reason"),
            assign_counselor=data.get("assign_counselor", False),
            counselor_reason=data.get("counselor_assignment_reason"),
            followup_time=data.get("followup_time") or data.get("callback_time"),
            followup_notes=data.get("followup_notes"),
            meeting_time=data.get("meeting_time") or (data.get("scheduled_time") if data.get("meeting_scheduled") else None),
            meeting_type=data.get("meeting_type", "CAMPUS_VISIT"),
            meeting_notes=data.get("meeting_notes")
        )

        # 1a. Explicit action dispatchers based on caller response
        if data.get("assign_counselor"):
            try:
                supabase_client.assign_counselor_to_lead(
                    phone, 
                    reason=data.get("counselor_assignment_reason") or "Assigned dedicated admissions counselor based on call qualification."
                )
            except Exception as assign_err:
                print(f"Post-Call Notice: Counselor assignment error ({assign_err})")

        if data.get("meeting_scheduled") or data.get("booking_intent") == "Campus Visit at Ramphal Chowk":
            try:
                supabase_client.schedule_meeting(
                    phone,
                    meeting_time=data.get("meeting_time") or data.get("scheduled_time"),
                    meeting_type=data.get("meeting_type", "CAMPUS_VISIT"),
                    notes=data.get("meeting_notes") or f"Campus visit & simulator session confirmed for {resolved_name}"
                )
            except Exception as meeting_err:
                print(f"Post-Call Notice: Meeting schedule error ({meeting_err})")

        if data.get("followup_required") or data.get("callback_requested"):
            try:
                supabase_client.schedule_followup(
                    phone,
                    followup_time=data.get("followup_time") or data.get("callback_time"),
                    notes=data.get("followup_notes") or f"Follow-up callback requested for {resolved_name}",
                    reason="CALLBACK_REQUESTED"
                )
            except Exception as fu_err:
                print(f"Post-Call Notice: Followup schedule error ({fu_err})")

        # 1b. Direct webhook notification to Admin App to ensure immediate timeline & recording availability
        admin_api_url = os.environ.get("ADMIN_API_URL", "https://airborne-admin-368523757732.asia-south1.run.app")
        shared_secret = getattr(config, "API_SHARED_SECRET", "")
        if admin_api_url and shared_secret:
            try:
                import requests
                admin_payload = {
                    "phone": phone,
                    "callerPhone": phone,
                    "direction": direction,
                    "status": "COMPLETED",
                    "duration": duration_estimate,
                    "recordingUrl": final_recording_url,
                    "recording_url": final_recording_url,
                    "gcs_recording_url": gcs_recording_url,
                    "transcript": transcript,
                    "summary": summary,
                    "classification": data.get("classification"),
                    "crmStatus": data.get("crm_status"),
                    "lostReason": data.get("lost_reason"),
                    "assignCounselor": data.get("assign_counselor"),
                    "bookingIntent": data.get("booking_intent"),
                    "courseInterest": data.get("course_interest"),
                    "providerCallId": provider_call_id,
                    "followupTime": data.get("followup_time") or data.get("callback_time"),
                    "meetingTime": data.get("meeting_time") or data.get("scheduled_time")
                }
                requests.post(
                    f"{admin_api_url.rstrip('/')}/api/v1/telephony/events",
                    json=admin_payload,
                    headers={"X-API-Key": shared_secret, "Content-Type": "application/json"},
                    timeout=5
                )
            except Exception as admin_err:
                print(f"Notice: Could not forward post-call completion to admin: {admin_err}")
        
        # 2. Synchronize with external TeleCRM if configured
        try:
            lead_payload = {
                "name": resolved_name,
                "phone": phone,
                "course_interest": data["course_interest"],
                "classification": data["classification"],
                "crm_status": data.get("crm_status"),
                "lost_reason": data.get("lost_reason"),
                "counselor_name": "Admissions Counselor" if data.get("assign_counselor") else None,
                "counselor_reason": data.get("counselor_assignment_reason"),
                "followup_time": data.get("followup_time") or data.get("callback_time"),
                "followup_notes": data.get("followup_notes"),
                "meeting_time": data.get("meeting_time") or data.get("scheduled_time"),
                "meeting_notes": data.get("meeting_notes"),
                "recording_url": final_recording_url
            }
            crm_sync.sync_lead_with_telecrm(lead_payload, transcript)
        except Exception as crm_err:
            print(f"Post-Call Notice: TeleCRM sync error ({crm_err})")

        # 3. Trigger WhatsApp automated follow-up
        try:
            automation.trigger_post_call_automations(
                phone,
                data["classification"],
                resolved_name,
                course_interest=data.get("course_interest"),
                scheduled_time=data.get("meeting_time") or data.get("scheduled_time"),
                booking_intent=data.get("booking_intent")
            )
        except Exception as auto_err:
            print(f"Post-Call Notice: WhatsApp post-call automation error ({auto_err})")
        
        print(f"Post-Call: Pipeline completed for {phone}.")
        return data
    except Exception as pipeline_err:
        print(f"Post-Call Error: Pipeline failed ({pipeline_err})")
        return {}

def run_post_call_pipeline(phone: str, direction: str = "outbound", recording_url: str = "", provider_call_id: str = None):
    """
    Asynchronous post-call processor.
    1. Archives call recording to Google Cloud Storage.
    2. Extracts lead qualifiers, course interest, and callback intent using LLM.
    3. Updates CRM (leads & lead_activities) directly in Cloud SQL.
    4. Triggers secondary automations (WhatsApp & CRM sync).
    Guarded against duplicate / concurrent pipeline execution.
    """
    cleaned_phone = phone.replace(" ", "").replace("-", "")
    with _pipelines_lock:
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

        return analyze_call_transcript_and_qualify(
            transcript=transcript,
            phone=phone,
            direction=direction,
            recording_url=recording_url,
            gcs_recording_url=gcs_recording_url,
            provider_call_id=provider_call_id
        )
    except Exception as err:
        print(f"Post-Call Pipeline Error ({phone}): {err}")
    finally:
        clear_session(phone)
        with _pipelines_lock:
            _active_pipelines.discard(cleaned_phone)

