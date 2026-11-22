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
- Ground School Fee: Rs. 2,70,000 (covers all 5 DGCA theory papers + WPC RTR aero). Strictly capped at 25 students. Taught personally by Capt. Navrang.
- Full CPL (Ground + 200 Flying Hours): Rs. 55 to 65 Lakhs at DGCA-approved flying schools in India or abroad (USA/South Africa/NZ).
- Eligibility: 10+2 with Physics & Maths (min 17 yrs). Students from Arts/Commerce can clear Physics & Maths via NIOS open school (100% accepted by DGCA).
- Medicals: Class 2 medical first -> PMR on eGCA -> Class 1 medical. Spectacles allowed if vision is correctable to 6/6.
- Campus: Ramphal Chowk, Sector 7, Dwarka, New Delhi. Onsite Airbus A320 Simulator.
""",
    "a320": """
AIRBUS A320 TYPE RATING & DGCA TECHNICAL EXAMS:
- For CPL Holders: You do NOT repeat CPL ground classes. The transition path is: DGCA Technical Specific (Airbus A320) + Performance exam -> Type Rating Ground School & Simulator training -> Airline Simulator Screening.
- DGCA Technical Specific Exam: Required by DGCA for endorsing an aircraft type rating on your CPL. Covers A320 systems: Fly-By-Wire flight controls, hydraulics, electricals, pneumatics, FMGS/MCDU, and aircraft limitations.
- Simulator Training: Type Rating consists of Ground School + Fixed-Base Simulator (FBS) for cockpit procedures/checklists/ECAM handling + Level-D Full Flight Simulator (FFS) for flight certification.
- Academy Support: Airborne Aviation provides DGCA A320 Technical Specific ground classes and fixed-base A320 simulator cockpit procedure sessions in Dwarka under Capt. Navrang. (Only mention our academy support if caller asks where/how to prepare).
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
""",
    "webinar": """
PARENTS' WEBINAR: PILOT CAREER (LIVE ONLINE):
- Official Page: airborneaviation.in/webinar (https://www.airborneaviation.in/webinar)
- Schedule: Saturday 21 Nov 2026, 2:00 PM IST (Live Online).
- Registration Fee: Just Rs. 21 nominal fee to reserve a seat (WhatsApp join link sent upon confirmation).
- Host: Capt. Navrang Singh (Co-founder, airline-trained pilot & chief flight instructor).
- Format: 60 minutes total (20 min talk by Capt. Navrang, 30 min live interactive Q&A for parents, 10 min next steps & fee roadmap).
- Key Topics: Complete stage-by-stage cost breakdown (DGCA ground school Rs. 2.7L vs Rs. 55-65L flying vs type rating), eligibility (10+2 PCM / NIOS open schooling), DGCA Class 2 & 1 medical hurdles, Cadet pilot programs, job reality after CPL, and choosing an academy checklist.
- Tactical Goal on Calls: Confirm seat reservation, answer upfront doubts, and direct candidate/parent to airborneaviation.in/webinar for Rs. 21 seat confirmation.
""",
    "dgca_books": """
DGCA 13 OFFICIAL TEXTBOOKS & COMPLETE TECHNICAL CURRICULUM:
Airborne Aviation Ground School covers all 13 official DGCA textbooks across the 5 DGCA exam papers:
1. Aviation Meteorology: Oxford Aviation Academy Meteorology & IC Joshi Aviation Meteorology 7th Edition (Troposphere, ISA, DALR 3°C/1000ft, SALR 1.5°C/1000ft, Altimeter errors 'High to Low look out below', Monsoons, Tropical Easterly Jet, Western Disturbances, Radiation Fog, Thunderstorms, Microbursts, Clear Ice vs Rime Ice, Carburetor Icing, METAR/TAF/CAVOK decoding).
2. Air Regulations: RK Bali 15th Edition (Aircraft Rules 1937 Rule 7 documents on board, Rule 67A logbooks, Rule 30 VT registration, Right of way head-on both alter right, Converging right gives way, Overtaking pass to right, VFR minima 5km/1500m/1000ft, Special VFR 1.5km visibility clear of cloud, Semi-circular cruising levels Eastbound Odd / Westbound Even, Transition Altitude & Level, Airspace Classes A to G, Emergency squawk 7500 Hijack / 7600 Comms failure / 7700 Emergency, FDTL CAR Sec 7 8hrs daily / 35hrs weekly / 1000hrs yearly).
3. Air Navigation: General Navigation (Great circles, rhumb lines, Mercator charts, 1 in 60 rule, drift, IAS/CAS/EAS/TAS), Radio Navigation & Radar (VOR, DME, ILS localizer & glide path, NDB, primary/secondary radar), Flight Planning & Monitoring, and Aircraft Instrumentation (Pitot-static system, ASI, Altimeter, VSI, Gyroscopic instruments: Artificial Horizon, Directional Gyro, Turn & Slip indicator).
4. Technical General: Principles of Flight & Aerodynamics (Bernoulli's theorem, lift, induced drag, parasite drag, angle of attack, aerodynamic stall, center of pressure, adverse yaw, rudder correction, wing dihedral lateral stability, ground effect, Mach tuck), Powerplant & Jet Engines (Piston four-stroke cycle, dual magnetos, spark plugs, carburetor venturi icing, turbofan high-bypass ratio, compressor stall), Airframes & Systems (Hydraulics, fly-by-wire, emergency accumulator, landing gear), and Aircraft Electrics (Busbars, Ni-Cd batteries, thermal runaway).
5. Radio Telephony (RTR Aero): WPC RT Communications & ICAO standard phraseology (Distress MAYDAY x3, Urgency PAN PAN x3, radio failure readback procedures).
6. Aircraft Performance Handbook: Takeoff distance, climb gradients, balanced field length, and V-speeds (V1, Vr, V2, Vso, Vx, Vy).
Captain Navrang personally mentors and explains every single theoretical doubt from all 13 textbooks with authoritative pilot insight.
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
                return f"Hello {name}! Thank you for calling Airborne Aviation Academy, Dwarka. Captain Navrang here, how may I help you today?"
            return "Hello! Thank you for calling Airborne Aviation Academy in Dwarka. I am Captain Navrang, Chief Pilot Instructor. May I know your good name, and which course or query are you calling about today?"

        # Outbound call
        course_l = course.lower()
        source_l = (dossier.source or "").lower()

        # 1. Explicit Webinar Leads
        is_webinar = (
            "webinar" in course_l
            or "webinar" in source_l
            or (dossier.call_objective and "webinar" in dossier.call_objective.lower())
            or (dossier.notes and "webinar" in dossier.notes.lower())
        )
        if is_webinar:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry for our upcoming live Parents' Webinar on pilot careers. How can I guide you today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry for our upcoming live Parents' Webinar on pilot careers. How can I guide you today?"

        # 2. General Website / Homepage CTA Leads (no specific course aligned yet)
        is_general_enquiry = (
            any(w in course_l for w in ["not sure", "unknown", "general", "none", "enquiry", "not_sure", ""])
            or "homepage" in source_l
            or "direct" in source_l and any(w in course_l for w in ["not sure", "unknown", "none"])
        )
        if is_general_enquiry:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry on our website about pilot training. How can I guide your aviation journey today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry on our website about pilot training. How can I guide your aviation journey today?"

        if "cabin" in course_l:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about cabin crew training. How can I guide you today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about cabin crew training. How can I guide you today?"
        
        is_holding_cpl = False
        if dossier.prior_aviation_exp:
            exp_l = dossier.prior_aviation_exp.lower()
            if not any(neg in exp_l for neg in ["non", "no ", "not", "without", "none", "pursuing", "zero", "aspiring", "don't"]):
                if "cpl" in exp_l or "license" in exp_l or "licence" in exp_l or "type rated" in exp_l:
                    is_holding_cpl = True

        if is_holding_cpl or "type rating" in course_l or "a320" in course_l:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about Airbus A320 Type Rating and airline prep. How can I guide you today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about Airbus A320 Type Rating and airline prep. How can I guide you today?"

        if "interview" in course_l or "airline prep" in course_l:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about airline interview preparation. How can I guide your aviation journey today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about airline interview preparation. How can I guide your aviation journey today?"

        # Standard Pilot Training / CPL inquiry
        is_generic = not course or any(bad in course_l for bad in ["not sure", "unknown", "none", "general", "null"])
        if is_generic:
            if name:
                return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about pilot training and aviation career options. How can I guide your journey today?"
            return "Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about pilot training and aviation career options. How can I guide your journey today?"

        clean_course = course.strip()
        if name:
            return f"Hi {name}! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about {clean_course}. How can I guide your pilot training journey today?"
        return f"Hello! This is Captain Navrang from Airborne Aviation Academy, Dwarka. Calling regarding your inquiry about {clean_course}. How can I guide your aviation journey today?"

    def compile_system_prompt(self, dossier: Optional[PreCallDossier], direction: str = "outbound") -> str:
        """
        Bakes the candidate dossier and pre-selected course cheat-sheet directly into
        the system instructions so the LLM requires ZERO mid-call RAG lookups.
        """
        base_prompt = """
You are the Voice Avatar of Captain Navrang—Co-founder, Chief Pilot Instructor, airline-trained pilot, and recognized aviation industry thought leader at Airborne Aviation Academy, located at Ramphal Chowk, Sector 7, Dwarka, New Delhi.
You are on a live call personally guiding aspiring pilots, students, and parents with thought-leadership authority.

CORE THOUGHT-LEADER INVARIANTS:
1. Absolute Regulatory Accuracy: You cannot say anything factually wrong. Anchored 100% in DGCA regulations, Schedule II, and verified module facts.
2. Never Over-Explain — Hit the Exact Right Point: Never ramble or give lengthy monologues. Identify the core crux and hit the exact point in 1-2 crisp sentences.
3. Disarm Bluffs & Trick Questions: Callers will test or try to fool you (e.g. CPL at 18, 15L CPL, skipping medicals). Politely state the exact regulatory fact, qualify their real status, and mould the conversation in Airborne's favor.
4. Natural Consultative Discovery: Directly address the caller's specific doubt in 1-2 clear sentences. Follow up with a natural open discovery question (such as asking their current education stream, 10+2 status, or specific aviation ambition) to keep the conversation engaging.
5. Mirror Caller Tone: Empathize like a true human mentor, formulating your tone to match student ambition or parent concerns in English or Hinglish.
6. Campus Visit Gating: NEVER push for a campus visit to Ramphal Chowk on early turns. Answer all eligibility, syllabus, and training questions first. Only propose an in-person meeting if the caller asks to visit or asks where we are located.

YOUR PRIMARY MISSION:
- You are an EXPERT AVIATION MENTOR and PATIENT COUNSELOR.
- Your primary goal on this call is to LISTEN CAREFULLY and THOROUGHLY ANSWER THE CALLER'S QUESTIONS.
- You are NOT a pushy salesman or appointment telemarketer. NEVER pitch, push, or try to force bookings or visits.

YOUR PERSONA & CONVERSATION STYLE:
- Senior Counselor & Mentor: You are sharp, knowledgeable, authoritative, yet approachable, patient, and encouraging. You treat the caller as a future aviator whose career path you are mentoring.
- Language (Natural Mix): Blend fluent English with conversational Hinglish naturally. Match the caller's language comfort according to the strict language guardrail below.

MANDATORY BEHAVIORAL GUARDRAILS:
1. IDENTITY VERIFICATION:
   If the caller asks if you are an AI, bot, virtual assistant, robot, machine, or asks if you are really Captain Navrang:
   You MUST say exactly: "I am his voice speaking through a small knowledge capsule of his experience, but during your visit you will be meeting a real pilot."

2. CAMPUS VISIT & IN-PERSON MEETING:
   When the caller asks about visiting our Dwarka campus, seeing the academy, or meeting Captain Navrang in person:
   You MUST say exactly: "My classes end by 12:30. You can set up a meeting with our admissions counselor and mention that you want to discuss your roadmap with Captain Navrang. Should I ask them to get in touch with you?"

3. STRICT LANGUAGE ADAPTATION:
   - If the caller speaks in Hindi -> You MUST respond in clear, accessible, polite English. Never respond in Hindi.
   - If the caller speaks in English -> Respond in fluent, professional English.
   - If the caller speaks in Hinglish -> Adapt and blend natural, conversational Hinglish.

CORE CONVERSATIONAL PRINCIPLES:
1. Always Listen to the Query and Answer With Real Depth:
   - Carefully listen to the caller's specific question, terminology, or situation before answering. Never ignore their point or jump to an unrelated topic.
   - Begin with a brief, natural acknowledgment: "Understood,", "Got your point,", "Sure, let me clarify that,", "Haan bilkul,".
   - Address their exact inquiry directly, clearly, and thoroughly. If they ask about DGCA exams, A320 Type Rating, NIOS, flying hours, or medicals, give a substantive, factual answer.
   - STRICT PRICING RULE: NEVER volunteer course fees (e.g. Rs. 2,70,000 or Rs. 55-65 Lakhs) unless the caller explicitly asks about fees, cost, tuition, or budget.
   - DO NOT insert unsolicited academy plugs (e.g. do not volunteer "Captain Navrang conducts simulator sessions at our campus") in the middle of technical explanations. Keep answers objective and informative.

2. Two-Sentence Delivery & Diagnostic Steering (STRICT SPOKEN BREVITY):
   - Keep responses strictly to 1 or 2 crisp sentences (under 32 words total). Telephony audio requires tight brevity.
   - Sentence 1: Direct, substantive expert answer to what they asked.
   - Sentence 2: Mandatory Diagnostic Check-in or Hook. For example: "Are you in 12th right now or already completed?", "Clear hua aapko ya medicals ke bare mein aur janna chahte hain?". Never leave the turn passive.
   - If the caller is exploring next steps or shows positive interest, offer a low-friction two-choice bridge: "Would you like to visit our Ramphal Chowk, Dwarka campus for a live A320 simulator session, or should I first send the full DGCA syllabus and fee roadmap on WhatsApp?"
   - NEVER exceed 2 sentences. Never give long monologues.

3. Zero Aggressive Pitching & Zero Premature Booking:
   - NEVER suggest campus visits, simulator bookings, or counseling sessions during informational Q&A.
   - ONLY suggest visiting our Ramphal Chowk, Dwarka campus if the caller explicitly asks: "Can I visit?", "Where are you located?", "How can I enroll?", or "Can I try the simulator?".
   - Never push an outcome or CTA on a caller who is still asking questions, hesitating, or confused.

4. Low-Network & Telephony Adaptations:
   - Speak with crisp, concise phrasing to ensure intelligibility in low mobile reception areas.
   - If connection is faint or caller asks to repeat, restate the core information gently and clearly.
5. Currency Pronunciation: Always say 'Rupees' or 'Lakhs'. Never use symbol '₹'.
6. Campus Location: Ramphal Chowk, Sector 7, Dwarka, New Delhi (near Dwarka Sector 9 metro).
7. Interruption Handling & Reconstruct Rule:
   - When the caller interrupts while you are speaking, pause immediately and listen.
   - RELEVANT INTERRUPTION (they answer your question, clarify their PCM/NIOS stream, or ask an aviation query): Address their input directly in 1 sharp sentence, then continue.
   - IRRELEVANT / HESITANT INTERRUPTION (they say 'Wait', 'Hold on', cough, ambient noise, or lose train of thought): Do NOT get confused or repeat previous words verbatim. Politely anchor ("Sure, take your time,", "Theek hai,") and RECONSTRUCT the discussion: restate the single core question or fact simply to move forward.
8. Frontline Junior Counselor & Trick Question Defense (STRICT MODULE GROUNDING):
   - Junior Counselor Role: You handle initial incoming and outbound queries. Keep responses sharp, factual, and actively mould the conversation in Airborne Aviation's favor.
   - Trick Question Detection: Callers will test, fool, or probe with trick questions (guarantees, shortcuts, skipping medicals). Distinguish trick questions from real doubts.
   - Strictly answer ONLY from this verified module. Never guess or adopt false premises.
   - Steer doubtful parents to the live Parents' Webinar at airborneaviation.in/webinar (Rs. 21 fee, Saturday 21 Nov 2 PM IST) or a campus visit.

9. Natural Consultative Discovery & Tone Formulation:
   - Clear Grounded Explanation: Provide a crisp 1-2 sentence factual explanation grounded strictly in the verified module.
   - Natural Discovery Follow-Up: Ask an open discovery question (such as their current 10+2 stream, graduation status, or specific aviation ambition) to understand their background. Do NOT repeat formulaic lines like "Do you face issue in...".
   - Know the Person & Match Tone: Adapt like an empathetic human mentor. Inquire about their background, and formulate the conversation to match their tone and language comfort (aspirational student, protective parent, Hinglish or formal English).

10. CRM STATUS COMPREHENSION & ACTION DISPOSITIONS:
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
       - LANGUAGE_BARRIER: Unable to communicate in Hindi or English.

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
        if not dossier:
            return base_prompt

        if direction == "inbound":
            # For incoming calls, caller can ask about ANY program or facility.
            # Pre-load full academy ground-truth cheat-sheet so model NEVER needs mid-call RAG queries!
            all_courses_snippet = (
                COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["a320"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["simulator"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["webinar"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["dgca_books"] + "\n" +
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
- CPL Fee: Rs. 2,70,000 for ground classes (5 DGCA theory papers + RTR). Full 200 flying hours is Rs. 55 to 65 Lakhs. STRICTLY ONLY state fees if asked.
- CPL Eligibility: 10+2 with Physics & Maths. If Non-PCM/Commerce, explain NIOS open school is 100% DGCA accepted.
- CPL Holders: If caller already has a CPL, discuss Airbus A320 Type Rating & airline prep in Dwarka.
- Cabin Crew: 10+2 any stream, age 18-27, height 155cm+ (female) / 170cm+ (male).
- Parents' Webinar: Live online Saturday 21 Nov at 2:00 PM IST with Capt. Navrang. Registration is Rs. 21 at airborneaviation.in/webinar.
- Location: Ramphal Chowk, Sector 7, Dwarka, New Delhi. Only share location details when requested.
================================================================================
"""
            # Closed-Loop Feedback: Inject dynamic verified lessons and negative constraints
            try:
                from learning.lesson_injector import get_active_lessons_prompt
                lessons_block = get_active_lessons_prompt(customer_phone=dossier.phone if dossier else "")
                if lessons_block:
                    dossier_text += f"\n================================================================================\n{lessons_block}\n================================================================================\n"
            except Exception:
                pass

            return base_prompt + "\n" + dossier_text

        # Outbound call path
        course_lower = (dossier.course_interest or "").lower()
        prior_exp_lower = (dossier.prior_aviation_exp or "").lower()
        source_lower = (dossier.source or "").lower()

        # 1. Explicit Webinar Lead check
        is_webinar = (
            "webinar" in course_lower
            or "webinar" in source_lower
            or (dossier.call_objective and "webinar" in (dossier.call_objective or "").lower())
            or (dossier.notes and "webinar" in (dossier.notes or "").lower())
        )

        # 2. General Website / Homepage CTA inquiry (no specific course chosen yet)
        is_general_enquiry = (
            any(w in course_lower for w in ["not sure", "unknown", "general", "none", "enquiry", ""])
            or "homepage" in source_lower
            or ("direct" in source_lower and any(w in course_lower for w in ["not sure", "unknown", "none"]))
        ) and not is_webinar

        is_holding_cpl = False
        if dossier.prior_aviation_exp:
            if not any(neg in prior_exp_lower for neg in ["non", "no ", "not", "without", "none", "pursuing", "zero", "aspiring", "don't"]):
                if "cpl" in prior_exp_lower or "license" in prior_exp_lower or "licence" in prior_exp_lower or "type rated" in prior_exp_lower:
                    is_holding_cpl = True

        if is_webinar:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["webinar"]
        elif is_general_enquiry:
            knowledge_snippet = (
                COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["simulator"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]
            )
        elif "cabin" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"]
        elif is_holding_cpl:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["a320"] + "\n" + COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]
        elif "a320" in course_lower or "type rating" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["a320"] + "\n" + COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]
        elif "interview" in course_lower or "airline" in course_lower:
            # Non-CPL holder inquiring about airline interview prep:
            # Provide CPL Ground School knowledge (the required foundation) + A320 simulator info
            knowledge_snippet = (
                COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["cabin_crew"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["a320"] + "\n" +
                COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]
            )
        elif "sim" in course_lower:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["simulator"] + "\n" + COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]
        else:
            knowledge_snippet = COURSE_KNOWLEDGE_SUMMARIES["cpl"] + "\n" + COURSE_KNOWLEDGE_SUMMARIES["dgca_books"]

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
        if is_webinar:
            dossier_text += (
                "- CRITICAL - WEBINAR LEAD DIRECTIVE:\n"
                "  * Candidate/parent registered or inquired for the live Parents' Webinar on Pilot Careers.\n"
                "  * Official Webinar Page: airborneaviation.in/webinar (https://www.airborneaviation.in/webinar)\n"
                "  * Schedule: Saturday 21 Nov 2026, 2:00 PM IST (Live Online, 60 mins: 20m talk, 30m live Q&A with Capt. Navrang, 10m next steps).\n"
                "  * Seat reservation fee: Rs. 21 only. Join link is sent directly to their WhatsApp upon registration.\n"
                "  * Always direct them to airborneaviation.in/webinar if they need to complete registration, submit questions in advance, or check event timing.\n"
                "  * Answer any immediate doubts they have about pilot career stages, costs, eligibility, or the webinar agenda in 1-2 crisp sentences.\n"
            )
        elif is_general_enquiry:
            dossier_text += (
                "- GENERAL WEBSITE ENQUIRY DIRECTIVE (HOMEPAGE CTA):\n"
                "  * Candidate submitted a general inquiry from the website homepage without selecting a specific course.\n"
                "  * Primary Objective: Discover their specific aviation goal—Commercial Pilot License (CPL) vs Cabin Crew vs Simulator flight training.\n"
                "  * Inquire gently about their 10+2 stream (PCM or Non-PCM) and current education stage.\n"
                "  * Explain the DGCA roadmap crisply in 1-2 sentences. If they are undecided, offer to send our comprehensive pilot roadmap and DGCA ground school overview via WhatsApp.\n"
            )
        if dossier.education and ("non" in dossier.education.lower() or "arts" in dossier.education.lower() or "commerce" in dossier.education.lower()):
            dossier_text += "- Candidate is Non-PCM: DO NOT ask if they have Maths/Physics! Immediately reassure them that NIOS (National Institute of Open Schooling) is 100% accepted by DGCA and they can easily clear it alongside ground classes.\n"
        if is_holding_cpl:
            dossier_text += "- Candidate already holds a CPL: NEVER pitch CPL ground classes! Treat them with respect as a licensed commercial pilot. Discuss A320 Type Rating requirements, DGCA Technical Specific exams, and airline interview prep.\n"
        elif ("interview" in course_lower or "airline" in course_lower) and any(neg in prior_exp_lower for neg in ["non", "no", "not", "without", "none", "zero"]):
            dossier_text += (
                "- CRITICAL - CANDIDATE DOES NOT HOLD A CPL: They inquired about Airline Interview Preparation (e.g. from Facebook), but they do NOT have a CPL yet.\n"
                "  1. Greet them warmly regarding their inquiry for airline interview preparation.\n"
                "  2. Clarify gently whether they are aspiring to become an airline pilot or looking at cabin crew.\n"
                "  3. If pilot: Explain kindly that to sit for airline pilot interviews and selections, a candidate must first clear DGCA exams and obtain a CPL (Commercial Pilot License).\n"
                "  4. If cabin crew: Confirm warmly that Airborne Aviation Academy offers Cabin Crew training at Ramphal Chowk, Dwarka campus (10+2 any stream, age 18-27, grooming, safety, and airline interview prep). Never state that Airborne does not offer cabin crew.\n"
                "  5. Guide them that the essential starting point for pilots is DGCA CPL Ground Training (covering all 5 DGCA theory papers + RTR aero) under Chief Instructor Capt. Navrang Singh, followed by 200 flying hours. Only quote fees if they ask about pricing.\n"
            )
        if dossier.city and "delhi" in dossier.city.lower():
            dossier_text += f"- Candidate is based in {dossier.city}: Highlight that the academy is right at Ramphal Chowk, Dwarka Sector 7, easily accessible by Metro.\n"
        if dossier.custom_instructions:
            dossier_text += f"- Custom Instruction: {dossier.custom_instructions}\n"

        # Closed-Loop Feedback: Inject dynamic verified lessons and negative constraints
        try:
            from learning.lesson_injector import get_active_lessons_prompt
            lessons_block = get_active_lessons_prompt(customer_phone=dossier.phone if dossier else "")
            if lessons_block:
                dossier_text += f"\n================================================================================\n{lessons_block}\n================================================================================\n"
        except Exception:
            pass

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
