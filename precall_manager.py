"""
Pre-Call Context & Latency Optimization Manager for Airborne Aviation Voice Agent.

Solves the real-time voice latency and conversational smoothness problem:
1. Pre-bakes lead intelligence (education, CPL status, city, notes, call objectives)
   directly into the LLM system prompt BEFORE the call starts.
   -> ZERO mid-call database queries.
   -> ZERO dynamic RAG search delay during live dialogue.
   -> LLM responds in < 250ms with razor-sharp personalization.
2. Pre-warms the opening greeting audio (ElevenLabs PCM in RAM + Cloud Storage MP3)
   WHILE the phone is ringing or before dialing.
   -> ZERO millisecond first-turn audio delay when recipient answers.
3. Provides flexible interfaces to feed info:
   - REST API (POST /api/calls/prefeed & POST /api/calls/dispatch)
   - Python function call (precall_manager.register_precall(...))
   - Webhooks & CSV import pipelines
"""

import os
import sys
import time
import json
import asyncio
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

import config

# Normalizes phone numbers for bulletproof lookup (e.g. +919811817062, 919811817062, 9811817062)
def normalize_phone_key(phone: str) -> str:
    clean = "".join(filter(str.isdigit, str(phone or "")))
    if len(clean) == 12 and clean.startswith("91"):
        return clean[2:]
    if len(clean) == 10:
        return clean
    return clean[-10:] if len(clean) >= 10 else clean

COURSE_KNOWLEDGE_SUMMARIES = {
    "cpl": """
DGCA COMMERCIAL PILOT LICENSE (CPL) FACTS:
- Ground School Fee: Rs. 2,70,000 (covers all 5 DGCA papers + WPC RTR aero). Strictly capped at 25 students. Taught personally by Capt. Navrang.
- Full CPL (Ground + 200 Flying Hours): Rs. 55 to 65 Lakhs at DGCA-approved flying schools in India or abroad (USA/South Africa/NZ).
- Eligibility: 10+2 with Physics & Maths (min 17 yrs). Students from Arts/Commerce can clear Physics & Maths via NIOS open school (100% accepted by DGCA).
- Medicals: Class 2 medical first -> PMR on eGCA -> Class 1 medical. Spectacles allowed if vision is correctable to 6/6.
- Campus: Ramphal Chowk, Sector 7, Dwarka, New Delhi. Onsite Airbus A320 Simulator.
""",
    "a320": """
AIRBUS A320 TYPE RATING & AIRLINE PREPARATION:
- For CPL holders: Do NOT take CPL ground school again! Transition directly into Airbus A320 Type Rating & Airline Interview Prep.
- Facilities: Fixed-Base Airbus A320 Simulator at Dwarka campus.
- Modules: Systems technical ground classes, FBS simulator training, GD/PI interview prep, psychomotor test battery.
- Guidance: If candidate holds a CPL and confirms interest in airline selection, assess their interview timeline before suggesting an in-person simulator session.
""",
    "cabin_crew": """
CABIN CREW TRAINING PROGRAM:
- Eligibility: 10+2 in any stream (Arts, Commerce, Science). Age 18 to 27 years.
- Minimum Height: 155 cm (females), 170 cm (males).
- Training: In-flight safety, aviation hospitality, grooming, emergency procedures, airline interview preparation.
- Campus: Ramphal Chowk, Sector 7, Dwarka campus.
""",
    "simulator": """
AIRBUS A320 SIMULATOR FLIGHT SESSIONS:
- Hardware: State-of-the-art Fixed-Base Airbus A320 Simulator at Dwarka Sector 7 campus.
- Experience: Cockpit familiarity, MCDU & flight computer setup, manual takeoffs & landings, emergency procedures.
- Available for both aspiring pilots seeking cockpit trial and CPL holders preparing for airline simulator checks.
"""
}

# Pre-synthesized, high-fidelity default greeting URL for instant (<10ms) incoming call pickup
INBOUND_DEFAULT_GREETING_URL = "https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/resp_c4ebcf9b42dd4c0faba14f4c1338765a.mp3"

@dataclass
class PreCallDossier:
    phone: str
    name: str = "Candidate"
    course_interest: str = "Commercial Pilot License (CPL)"
    education: Optional[str] = None           # e.g., "10+2 Non-PCM (Arts)" or "10+2 PCM 85%"
    age: Optional[str] = None                 # e.g., "18"
    city: Optional[str] = None                # e.g., "Delhi NCR", "Jaipur"
    prior_aviation_exp: Optional[str] = None  # e.g., "Holds CPL", "None", "50 flying hours"
    medicals_status: Optional[str] = None     # e.g., "Wears glasses", "Class 2 cleared"
    budget_or_loan: Optional[str] = None      # e.g., "Seeking bank loan assistance"
    notes: Optional[str] = None               # e.g., "Inquired on WhatsApp about weekend batches"
    call_objective: Optional[str] = None      # e.g., "Address NIOS, quote 2.7L, book Dwarka simulator visit"
    preferred_language: str = "Hinglish"      # "English", "Hindi", "Hinglish"
    custom_instructions: Optional[str] = None
    source: str = "DIRECT"
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        raw = asdict(self)
        # Piopiy requires all variable values to be string, number, or boolean (disallowing None)
        return {k: ("" if v is None else v) for k, v in raw.items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreCallDossier":
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class PreCallManager:
    """
    Central coordinator for pre-call data feeding, prompt pre-compilation,
    and greeting audio pre-warming.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, PreCallDossier] = {}
        self._audio_cache_urls: Dict[str, str] = {}

    MAX_CACHED_ENTRIES = 500

    def _evict_oldest(self, mapping: dict):
        """Caller must hold self._lock. Drops the oldest entries (insertion order) beyond the cap."""
        while len(mapping) > self.MAX_CACHED_ENTRIES:
            mapping.pop(next(iter(mapping)))

    def register_precall(
        self,
        phone: str,
        name: str = "Candidate",
        course_interest: str = "Commercial Pilot License (CPL)",
        education: str = None,
        age: str = None,
        city: str = None,
        prior_aviation_exp: str = None,
        medicals_status: str = None,
        budget_or_loan: str = None,
        notes: str = None,
        call_objective: str = None,
        preferred_language: str = "Hinglish",
        custom_instructions: str = None,
        source: str = "DIRECT",
        prewarm_audio: bool = True
    ) -> PreCallDossier:
        """
        Registers lead information before the call is placed.
        Compiles the dossier, stores in memory + DB, and pre-warms opening audio.
        """
        clean_key = normalize_phone_key(phone)
        dossier = PreCallDossier(
            phone=phone,
            name=name or "Candidate",
            course_interest=course_interest or "Commercial Pilot License (CPL)",
            education=education,
            age=str(age) if age else None,
            city=city,
            prior_aviation_exp=prior_aviation_exp,
            medicals_status=medicals_status,
            budget_or_loan=budget_or_loan,
            notes=notes,
            call_objective=call_objective,
            preferred_language=preferred_language,
            custom_instructions=custom_instructions,
            source=source,
            created_at=time.time()
        )

        with self._lock:
            self._cache[clean_key] = dossier
            self._evict_oldest(self._cache)

        print(f"[PreCallManager] Dossier registered for {dossier.name} ({phone}) [Course: {dossier.course_interest}]")

        # Persist to Cloud SQL / Supabase asynchronously
        try:
            import database
            database.save_lead(
                name=dossier.name,
                phone=phone,
                course=dossier.course_interest,
                city=dossier.city,
                source=dossier.source,
                custom_fields={
                    "education": dossier.education,
                    "age": dossier.age,
                    "prior_aviation_exp": dossier.prior_aviation_exp,
                    "medicals_status": dossier.medicals_status,
                    "budget_or_loan": dossier.budget_or_loan,
                    "call_objective": dossier.call_objective,
                },
                notes=dossier.notes
            )
        except Exception as dbe:
            print(f"PreCallManager: Note on DB persistence ({dbe})")

        # Pre-warm opening greeting audio immediately
        if prewarm_audio:
            self.trigger_audio_prewarm(dossier)

        return dossier

    def find_phone_by_last_digits(self, digits: str) -> Optional[str]:
        """
        Returns the registered pre-call phone ending in `digits` if exactly one
        matches, else None. Used only to resolve outbound calls whose carrier
        context carries just a short token (e.g. the room name 'piopiyai_0151_...').
        """
        if not digits:
            return None
        with self._lock:
            matches = [d.phone for key, d in self._cache.items() if key.endswith(digits)]
        return matches[0] if len(matches) == 1 else None

    def clear_dossier(self, phone: Optional[str] = None):
        """Clears cached dossier (and pre-warmed audio) for a phone or all phones."""
        with self._lock:
            if phone:
                clean_key = normalize_phone_key(phone)
                self._cache.pop(clean_key, None)
                self._audio_cache_urls.pop(clean_key, None)
            else:
                self._cache.clear()
                self._audio_cache_urls.clear()

    def get_dossier(self, phone: str) -> Optional[PreCallDossier]:
        """
        Retrieves pre-call dossier in < 1ms from in-memory cache.
        Falls back to database lookup if not found in memory.
        """
        clean_key = normalize_phone_key(phone)
        with self._lock:
            if clean_key in self._cache:
                return self._cache[clean_key]

        # Fallback to CRM database
        try:
            import database
            lead = database.get_lead_by_phone(phone)
            if lead:
                custom_fields = lead.get("custom_fields") or {}
                dossier = PreCallDossier(
                    phone=phone,
                    name=lead.get("name") or "Candidate",
                    course_interest=lead.get("course_interest") or "Commercial Pilot License (CPL)",
                    city=lead.get("city"),
                    education=custom_fields.get("education"),
                    age=custom_fields.get("age"),
                    prior_aviation_exp=custom_fields.get("prior_aviation_exp"),
                    medicals_status=custom_fields.get("medicals_status"),
                    budget_or_loan=custom_fields.get("budget_or_loan"),
                    notes=custom_fields.get("notes") or lead.get("notes"),
                    call_objective=custom_fields.get("call_objective"),
                    source=lead.get("source") or "DATABASE",
                    created_at=time.time()
                )
                with self._lock:
                    self._cache[clean_key] = dossier
                    self._evict_oldest(self._cache)
                return dossier
        except Exception as e:
            print(f"PreCallManager: Fallback lookup error: {e}")

        return None

    def generate_greeting(self, dossier: PreCallDossier, direction: str = "outbound") -> str:
        """
        Constructs a crisp, natural opening greeting reflecting known lead facts.
        """
        name = dossier.name if dossier.name and dossier.name not in ["Candidate", "New Lead", "Future Pilot", "Inbound Caller", "Guest"] else None
        course = (dossier.course_interest or "Commercial Pilot License").strip()

        if direction == "inbound":
            if name:
                return f"Hello {name}! Thank you for calling Airborne Aviation Academy, Dwarka. Piyush, the admission counsellor here. How may I help you today?"
            return "Hello! Thank you for calling Airborne Aviation Academy in Dwarka. I am Piyush, the admission counsellor. May I know your good name, and which course or query are you calling about today?"

        # Outbound call
        if "cabin" in course.lower():
            if name:
                return f"Hi {name}! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about cabin crew training. How can I guide you today?"
            return "Hello! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about cabin crew training. How can I guide you today?"
        
        is_holding_cpl = False
        if dossier.prior_aviation_exp:
            exp_l = dossier.prior_aviation_exp.lower()
            if not any(neg in exp_l for neg in ["non", "no ", "not", "without", "none", "pursuing", "zero", "aspiring", "don't"]):
                if "cpl" in exp_l or "license" in exp_l or "licence" in exp_l or "type rated" in exp_l:
                    is_holding_cpl = True

        if is_holding_cpl or "type rating" in course.lower() or "a320" in course.lower():
            if name:
                return f"Hi {name}! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about Airbus A320 Type Rating and airline prep. How can I guide you today?"
            return "Hello! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about Airbus A320 Type Rating and airline prep. How can I guide you today?"

        if "interview" in course.lower() or "airline prep" in course.lower():
            if name:
                return f"Hi {name}! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about airline interview preparation. How can I guide your aviation journey today?"
            return "Hello! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about airline interview preparation. How can I guide your aviation journey today?"

        # Standard Pilot Training / CPL inquiry
        if name:
            return f"Hi {name}! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about {course}. How can I guide your pilot training journey today?"
        return "Hello! This is Piyush, the admission counsellor from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about pilot training. How can I guide your aviation journey today?"

    def compile_system_prompt(self, dossier: Optional[PreCallDossier], direction: str = "outbound") -> str:
        """
        Bakes the candidate dossier and pre-selected course cheat-sheet directly into
        the system instructions so the LLM requires ZERO mid-call RAG lookups.
        """
        base_prompt = """
You are Piyush, the admission counsellor at Airborne Aviation Academy, Ramphal Chowk, Sector 7, Dwarka, New Delhi.
Captain Navrang Singh is our Chief Pilot Instructor & Head of Training who leads the DGCA ground classes and simulator training.
You are on a live call. Your primary mission is to be an ADVISOR, HELPFUL COUNSELOR, and INFORMATIVE GUIDE for aspiring pilots, students, and parents.

CORE CONVERSATIONAL PRINCIPLES:
1. Answer the Specific Question First (No Rigid Script Recitation):
   - Always address the caller's exact question or topic immediately and directly in sentence 1.
   - If the caller asks about eGCA, DGCA medicals, 10+2 NIOS subjects, syllabus, or training details, explain that specific topic clearly. DO NOT deflect to unrequested sales topics.
   - STRICT PRICING RULE: NEVER volunteer course fees (e.g. Rs. 2,70,000 or Rs. 55-65 Lakhs) unless the caller explicitly asks about fees, cost, tuition, or budget.
   - Active Listening & Pausing: If the candidate begins talking, asking questions, or says 'wait' / 'pause', pause immediately and listen with complete focus. Never speak over the caller.

2. Intent-Gated CTA Funnel (DO NOT Push Outcomes Prematurely):
   - Step 1 (Educate & Answer): Fully answer what the caller is asking. Do NOT pitch visits or simulator bookings during normal informational Q&A.
   - Step 2 (Check Intent & Understanding): Follow up with a gentle check-in on their understanding or situation (e.g., "Does that help clarify the DGCA process for you?", "Are you currently completing your 12th or looking to start soon?").
   - Step 3 (Push CTA Only After Intent is Verified): ONLY invite them to visit the Ramphal Chowk campus or schedule a simulator counseling session if:
     a) The caller explicitly asks to visit, asks about campus location, or asks how to enroll.
     b) The caller has received full answers to their queries AND expressed positive readiness to explore next steps.
   - Never push an outcome or CTA on a caller who is still asking questions, hesitating, or confused.

3. Two-Sentence Delivery: Keep responses to 1 or 2 crisp, clear sentences (under 30 words total).
   - Sentence 1: Direct answer to the caller's exact inquiry.
   - Sentence 2: Essential context or a gentle check-in on their understanding (NOT an aggressive sales CTA).
3. Fluent Bilingual (English & Hinglish):
   - If caller speaks English, respond in authoritative, polished English.
   - If caller speaks Hindi/Hinglish, respond in natural, friendly Hinglish.
4. Low-Network & Telephony Adaptations:
   - Speak with crisp, concise phrasing to ensure intelligibility in low mobile reception areas.
   - If connection is faint or caller asks to repeat, restate the core information gently and clearly.
5. Currency Pronunciation: Always say 'Rupees' or 'Lakhs'.
6. Campus Location: Ramphal Chowk, Sector 7, Dwarka, New Delhi (near Dwarka Sector 9 metro).
"""
        if not dossier:
            return base_prompt

        if direction == "inbound":
            # For incoming calls, caller can ask about ANY program or facility.
            # Pre-load full academy ground-truth cheat-sheet so model NEVER needs mid-call RAG queries!
            all_courses_snippet = (
                COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["a320"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["simulator"] + "\n" +
                """
ACADEMY LOCATION & HOSTEL FACILITIES:
- Address: E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075.
- Landmark: Ramphal Chowk, near Dwarka Sector 9 metro station (5 mins by rickshaw).
- Hostels: Separate verified student PGs and hostels available for boys and girls within walking distance in Sector 7 Dwarka.
- Timing: Open Monday to Saturday, 9:30 AM to 6:00 PM.
"""
            )
            dossier_text = f"""
================================================================================
INCOMING CALL CONTEXT:
- Caller Phone: {dossier.phone}
- Caller Name: {dossier.name if dossier.name not in ['Candidate', 'Inbound Caller', 'New Lead'] else 'Prospective Student (welcome warmly & ask for their good name)'}
- Known Program Interest: {dossier.course_interest or 'General Inquiry'}
- INBOUND GOAL: Focus 100% on answering the caller's questions with complete clarity. Check their understanding and intent first. DO NOT push campus visits or simulator CTAs unless the caller explicitly asks or confirms readiness for next steps.
================================================================================
COMPLETE AIRBORNE AVIATION CHEAT-SHEET (ZERO-RAG WORKING MEMORY):
{all_courses_snippet}
================================================================================
INBOUND CONVERSATIONAL DIRECTIVES:
- Answer First: Sentence 1 answers their specific question directly. Sentence 2 checks their understanding or asks a relevant question.
- No Premature CTA: Do NOT offer campus visits or simulator sessions until the caller's questions are answered and positive intent is shown.
- CPL Fee: Rs. 2,70,000 for ground classes (5 DGCA papers + RTR). Full 200 flying hours is Rs. 55 to 65 Lakhs. STRICTLY ONLY state fees if asked.
- CPL Eligibility: 10+2 with Physics & Maths. If Non-PCM/Commerce, explain NIOS open school is 100% DGCA accepted.
- CPL Holders: If caller already has a CPL, discuss Airbus A320 Type Rating & airline prep in Dwarka.
- Cabin Crew: 10+2 any stream, age 18-27, height 155cm+ (female) / 170cm+ (male).
- Location: Ramphal Chowk, Sector 7, Dwarka, New Delhi. Only share location details when requested.
================================================================================
"""
            return base_prompt + "\n" + dossier_text

        # Outbound call path
        course_lower = (dossier.course_interest or "").lower()
        prior_exp_lower = (dossier.prior_aviation_exp or "").lower()
        is_holding_cpl = False
        if dossier.prior_aviation_exp:
            if not any(neg in prior_exp_lower for neg in ["non", "no ", "not", "without", "none", "pursuing", "zero", "aspiring", "don't"]):
                if "cpl" in prior_exp_lower or "license" in prior_exp_lower or "licence" in prior_exp_lower or "type rated" in prior_exp_lower:
                    is_holding_cpl = True

        if "cabin" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"]
        elif is_holding_cpl:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["a320"]
        elif "a320" in course_lower or "type rating" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["a320"]
        elif "interview" in course_lower or "airline" in course_lower:
            # Non-CPL holder inquiring about airline interview prep:
            # Provide CPL Ground School knowledge (the required foundation) + A320 simulator info
            knowledge_snippet = (
                COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["a320"]
            )
        elif "sim" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["simulator"]
        else:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["cpl"]

        dossier_text = f"""
================================================================================
PRE-CALL CANDIDATE DOSSIER (ALREADY KNOWN - DO NOT RE-ASK THESE FACTS!):
- Candidate Name: {dossier.name}
- Inquired Program: {dossier.course_interest}
- Education Background: {dossier.education or 'Unknown'}
- Location / City: {dossier.city or 'Unknown (Dwarka campus is accessible by Delhi Metro)'}
- Prior Aviation Background: {dossier.prior_aviation_exp or 'Beginner'}
- Medicals / Glasses: {dossier.medicals_status or 'Standard'}
- Budget / Finance Notes: {dossier.budget_or_loan or 'Standard tuition'}
- Caller Notes: {dossier.notes or 'Inquiry submitted online'}
- TACTICAL CALL OBJECTIVE: {dossier.call_objective or 'Answer candidate questions patiently and thoroughly. Verify their understanding and intent before suggesting campus visits or next steps.'}
================================================================================
{knowledge_snippet}
================================================================================
CRITICAL CONVERSATIONAL RULES FOR THIS LEAD:
"""
        # Tailored rules based on dossier
        if dossier.education and ("non" in dossier.education.lower() or "arts" in dossier.education.lower() or "commerce" in dossier.education.lower()):
            dossier_text += "- Candidate is Non-PCM: DO NOT ask if they have Maths/Physics! Immediately reassure them that NIOS (National Institute of Open Schooling) is 100% accepted by DGCA and they can easily clear it alongside ground classes.\n"
        if is_holding_cpl:
            dossier_text += "- Candidate already holds a CPL: NEVER pitch CPL ground classes! Directly discuss A320 Type Rating, simulator sessions in Dwarka, and airline interview preparation.\n"
        elif ("interview" in course_lower or "airline" in course_lower) and any(neg in prior_exp_lower for neg in ["non", "no", "not", "without", "none", "zero"]):
            dossier_text += (
                "- CRITICAL - CANDIDATE DOES NOT HOLD A CPL: They inquired about Airline Interview Preparation (e.g. from Facebook), but they do NOT have a CPL yet.\n"
                "  1. Greet them warmly regarding their inquiry for airline interview preparation.\n"
                "  2. Clarify gently whether they are aspiring to become an airline pilot or looking at cabin crew.\n"
                "  3. If pilot: Explain kindly that to sit for airline pilot interviews and selections, a candidate must first clear DGCA exams and obtain a CPL (Commercial Pilot License).\n"
                "  4. Guide them that the essential starting point is DGCA CPL Ground Training (covering all 5 DGCA papers + RTR aero) at Airborne Aviation Academy, Dwarka under Chief Instructor Capt. Navrang Singh, followed by 200 flying hours. Only quote fees if they ask about pricing.\n"
                "  5. Mention that our Dwarka campus has an onsite Airbus A320 simulator so students get early airline cockpit familiarity from day one.\n"
                "  6. Invite them to visit the Dwarka campus for counseling and to experience the simulator.\n"
            )
        if dossier.city and "delhi" in dossier.city.lower():
            dossier_text += f"- Candidate is based in {dossier.city}: Highlight that the academy is right at Ramphal Chowk, Dwarka Sector 7, easily accessible by Metro.\n"
        if dossier.custom_instructions:
            dossier_text += f"- Custom Instruction: {dossier.custom_instructions}\n"

        return base_prompt + "\n" + dossier_text

    def trigger_audio_prewarm(self, dossier: PreCallDossier):
        """
        Asynchronously pre-warms both in-memory ElevenLabs PCM (for WebRTC worker)
        and static Cloud Storage MP3 (for TeleCMI/Twilio webhook PCMO).
        """
        greeting_text = self.generate_greeting(dossier, direction="outbound")

        def _worker():
            # 1. Pre-warm ElevenLabs PCM in RAM (if worker is running in same process or has global_eleven_tts)
            try:
                import piopiy_agent_worker
                tts = getattr(piopiy_agent_worker, "global_eleven_tts", None)
                loop = getattr(piopiy_agent_worker, "main_loop", None)
                # Run on the worker's own loop: the shared ElevenLabs HTTP client is bound to it,
                # and a separate asyncio.run() here would swap that client out from under live calls.
                if tts and loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(tts.prewarm_greeting(greeting_text), loop).result(timeout=30)
            except Exception as e:
                print(f"[PreCallManager] PCM pre-warm skipped: {e}")

            # 2. Pre-generate Cloud Storage / static audio URL
            try:
                import assistant
                clean_key = normalize_phone_key(dossier.phone)
                url = assistant.get_greeting_voice_url(greeting_text)
                with self._lock:
                    self._audio_cache_urls[clean_key] = url
                    self._evict_oldest(self._audio_cache_urls)
                print(f"[PreCallManager] Pre-warmed audio URL for {dossier.phone}: {url}")
            except Exception as e:
                print(f"Pre-warm audio exception: {e}")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def get_prewarmed_audio_url(self, phone: str) -> Optional[str]:
        clean_key = normalize_phone_key(phone)
        with self._lock:
            return self._audio_cache_urls.get(clean_key)


# Global Singleton
manager = PreCallManager()
