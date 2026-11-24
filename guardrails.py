"""
Guardrails module for Captain Navrang Voice Agent.
Enforces deterministic behavioral contracts for:
1. Identity Verification (Voice Capsule vs. Real Pilot)
2. Campus Visit & In-Person Meeting (12:30 Class End & Counselor Routing)
3. Language Adaptation (Hindi -> English, English -> English, Hinglish -> Hinglish)

Provides prominent visual highlighted logging across stdout, stderr, and cloud logs.
"""

import re
import logging
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("CaptainNavrangGuardrails")

# Canonical golden responses
IDENTITY_GUARDRAIL_RESPONSE = (
    "I am his voice speaking through a small knowledge capsule of his experience, "
    "but during your visit you will be meeting a real pilot."
)

VISIT_MEETING_GUARDRAIL_RESPONSE = (
    "My classes end by 12:30. You can set up a meeting with our admissions counselor "
    "and mention that you want to discuss your roadmap with Captain Navrang. "
    "Should I ask them to get in touch with you?"
)

AMD_GUARDRAIL_RESPONSE = (
    "Thank you for contacting Airborne Aviation Academy. We will connect with you shortly. Clear skies! [EXIT]"
)

# Language-specific audibility responses
AUDIBILITY_RESPONSE_HINDI = "Kya aap mujhe sun pa rahe hain?"
AUDIBILITY_RESPONSE_ENGLISH = "Can you hear me?"
AUDIBILITY_GUARDRAIL_RESPONSE = AUDIBILITY_RESPONSE_HINDI

# Global in-memory session tracking for hello count and language per phone
_phone_hello_tracker: Dict[str, int] = {}
_phone_language_tracker: Dict[str, str] = {}

def reset_phone_session(phone: str):
    """Resets session-level tracking (hello counts, language preference) for a phone number."""
    if phone:
        _phone_hello_tracker.pop(phone, None)
        _phone_language_tracker.pop(phone, None)

# Regex patterns for Answering Machine / Carrier IVR / Voicemail
AMD_PATTERNS = [
    r"\b(record your message|at the tone|after the tone|after the beep|leave a message)\b",
    r"\b(person you are trying to reach|number you are calling|subscriber is|is currently (unavailable|busy|switched off))\b",
    r"\b(welcome to (our\s+)?(youtube|channel|telecom|airtel|jio|vi|vodafone|bsnl))\b",
    r"\b(press [0-9]|dial [0-9]|for english press|hindi ke liye)\b",
    r"\b(call waiting|forwarded to voicemail|customer care)\b",
]

# Regex patterns for in-call explicit audibility check
EXPLICIT_AUDIBILITY_PATTERNS = [
    r"\b(aawaz nahi aa rahi|awaz nahi aa rahi|awaz nahi|sunai nahi de raha|awaz kat rahi hai|awaz nahi aa rahi hai)\b",
    r"\b(can you hear me|am i audible|are you there|are you listening|can you hear|hello are you there)\b",
    r"\b(kya aap mujhe sun sakte hain|kya meri aawaz aa rahi hai|kya aap sun pa rahe|sun pa rahe ho|sun pa rahe hain)\b"
]

HELLO_ONLY_REGEX = re.compile(r"^(hello[\.\?\s,!]*)+$", re.IGNORECASE)

AUDIBILITY_PATTERNS = EXPLICIT_AUDIBILITY_PATTERNS + [r"^(hello[\.\?\s,!]*)+$"]

# Regex patterns for Identity queries
IDENTITY_PATTERNS = [
    r"\b(are you|r u)\s+(an?\s+)?(ai|bot|robot|machine|computer|artificial|virtual|avatar)\b",
    r"\b(are you|r u)\s+(really\s+)?(real|human|actual|a\s+real\s+person)\b",
    r"\b(am i|am i\s+talking to|am i\s+speaking to|am i\s+speaking with)\s+(an?\s+)?(ai|bot|robot|machine|computer|real person|human)\b",
    r"\b(talking to|speaking with)\s+(an?\s+)?(ai|bot|robot|real person|human)\b",
    r"\bis this (an?\s+)?(ai|bot|robot|recording|automated)\b",
    r"\bare you (really\s+)?(captain|capt\.?)\s*(navrang)?\b",
    r"\b(kya aap|aap)\s+(ai|bot|robot|machine)\s+(ho|hai)\b",
    r"\bkya mai (ai|bot|computer)\s+se baat kar raha hoon\b",
    r"\basli (navrang|pilot|insan)\s+ho\b",
    r"\breal captain navrang\b",
    r"\breal person\b",
]

# Regex patterns for Campus Visit / In-Person Meeting queries
VISIT_MEETING_PATTERNS = [
    r"\b(visit|come to|drop by|see)\s+(the\s+|your\s+|our\s+)?(\w+\s+)?(campus|academy|center|dwarka|office|institute)\b",
    r"\b(can i|may i|want to|wanna|how can i|planning to)\s+(meet|see|talk to|interact with)\s+(you|captain\s*navrang|navrang\s*sir|in person)\b",
    r"\b(can we|could we)\s+(meet|schedule a meeting|book an appointment|meet in person)\b",
    r"\b(schedule|book|setup|set up)\s+(a\s+)?(meeting|visit|counseling|appointment)\b",
    r"\b(when can i|what time can i)\s+(visit|meet you|come over)\b",
    r"\b(dwarka|campus|academy)\s+(aa sakta hoon|visit kar sakta hoon|kab aaun|mil sakta hoon)\b",
    r"\b(aapse|navrang sir se)\s+(milna|face to face|in person)\b",
    r"\bappointment (chahiye|milega|book karna hai)\b",
]

# Hindi markers (Devanagari or Roman Hindi functional words)
HINDI_DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")

# Roman Hindi functional words (carefully avoiding collisions with standard English words like 'the' / 'in' / 'to')
ROMAN_HINDI_INDICATORS = {
    "kya", "kaise", "kyun", "kab", "kahan", "kitna", "kitni", "kitne",
    "mujhe", "mera", "meri", "mere", "main", "mein", "hum", "aap", "aapka", "aapki", "aapke",
    "hoga", "hogi", "hoge", "hai", "hain", "hoon", "tha", "thi", "thhey",
    "karna", "karne", "karni", "chahiye", "sakte", "sakti", "sakta",
    "bataiye", "batao", "bol", "raha", "rahi", "rahe", "lekar", "baat",
    "padhega", "padhegi", "paisa", "rupaye", "kharcha", "lagta", "lagti",
    "bina", "ban", "lena", "lene", "leni", "aata", "aati", "aate", "jana", "jane",
    "nahi", "nahin", "aawaz", "awaz", "sun", "sunai", "pa", "rahe", "de"
}

ENGLISH_INDICATORS = {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "can", "could", "would", "should", "will", "shall", "is", "are", "am",
    "the", "about", "training", "course", "ground",
    "hours", "exam", "exams", "medical", "class", "eligibility"
}

def log_highlight(title: str, items: Dict[str, Any], border_char: str = "=", level: str = "INFO"):
    """
    Prints a prominent, boxed log entry that is unmistakable in terminal,
    Docker logs, Cloud Logging, and test outputs.
    """
    border = border_char * 80
    lines = [
        f"\n{border}",
        f"🚨 {title}",
        f"{'-' * 80}"
    ]
    for k, v in items.items():
        lines.append(f"   {k:<18} : {v}")
    lines.append(f"{border}\n")
    log_msg = "\n".join(lines)
    
    if level == "WARNING":
        logger.warning(log_msg)
    elif level == "ERROR":
        logger.error(log_msg)
    else:
        logger.info(log_msg)
    # Also print directly to stdout to guarantee visibility in all container environments
    print(log_msg, flush=True)


def check_identity_guardrail(caller_input: str, phone: str = "") -> Optional[str]:
    """
    Evaluates whether caller is probing the agent's identity/authenticity.
    Returns canonical response if triggered, else None.
    """
    cleaned = (caller_input or "").strip().lower()
    for pattern in IDENTITY_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            log_highlight(
                "[GUARDRAIL TRIGGERED: IDENTITY VERIFICATION]",
                {
                    "Caller Phone": phone or "N/A",
                    "Matched Pattern": pattern,
                    "Caller Input": caller_input,
                    "Action": "Enforce Voice-Capsule Truth Grounding",
                    "Response": IDENTITY_GUARDRAIL_RESPONSE
                },
                border_char="="
            )
            return IDENTITY_GUARDRAIL_RESPONSE
    return None


def check_visit_meeting_guardrail(caller_input: str, phone: str = "") -> Optional[str]:
    """
    Evaluates whether caller is asking to visit campus or meet Captain Navrang.
    Returns canonical response if triggered, else None.
    """
    cleaned = (caller_input or "").strip().lower()
    for pattern in VISIT_MEETING_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            log_highlight(
                "[GUARDRAIL TRIGGERED: CAMPUS VISIT & MEETING]",
                {
                    "Caller Phone": phone or "N/A",
                    "Matched Pattern": pattern,
                    "Caller Input": caller_input,
                    "Action": "Enforce 12:30 Class End & Counselor Routing",
                    "Response": VISIT_MEETING_GUARDRAIL_RESPONSE
                },
                border_char="="
            )
            return VISIT_MEETING_GUARDRAIL_RESPONSE
    return None


def check_amd_guardrail(caller_input: str, phone: str = "") -> Optional[str]:
    """
    Evaluates whether caller is an answering machine, carrier IVR, or voicemail prompt.
    Returns graceful exit prompt to disconnect immediately.
    """
    cleaned = (caller_input or "").strip().lower()
    for pattern in AMD_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            log_highlight(
                "[GUARDRAIL TRIGGERED: AMD / CARRIER IVR DETECTED]",
                {
                    "Caller Phone": phone or "N/A",
                    "Matched Pattern": pattern,
                    "Caller Input": caller_input,
                    "Action": "Disconnect Immediately to save billing",
                    "Response": AMD_GUARDRAIL_RESPONSE
                },
                border_char="!"
            )
            return AMD_GUARDRAIL_RESPONSE
    return None


def check_audibility_guardrail_with_lang(
    caller_input: str,
    phone: str = "",
    history: Optional[list] = None,
    preferred_language: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Evaluates whether caller is indicating an audibility issue or saying 'hello' a second time.
    If a customer says 'hello' a second time, it is because they are unable to hear the assistant.
    Responds with:
    - Hindi/Hinglish: 'Kya aap mujhe sun pa rahe hain?'
    - English: 'Can you hear me?'
    as per the language selected.
    """
    cleaned = (caller_input or "").strip().lower()
    if not cleaned:
        return None, None

    # Determine target language:
    target_lang = "ENGLISH"
    if preferred_language:
        p_low = preferred_language.lower()
        if "hindi" in p_low or "hinglish" in p_low:
            target_lang = "HINDI"
        elif "english" in p_low:
            target_lang = "ENGLISH"
    elif phone and phone in _phone_language_tracker:
        target_lang = _phone_language_tracker[phone]
    elif history:
        for msg in reversed(history):
            if msg.get("role") == "user":
                c = msg.get("content", "")
                d_lang, _, _ = detect_language_adaptation(c)
                if d_lang in ("HINDI", "HINGLISH"):
                    target_lang = "HINDI"
                    break
                elif d_lang == "ENGLISH" and len(c.split()) > 2:
                    target_lang = "ENGLISH"
                    break

    # If current input has explicit Hindi words or Devanagari, adapt to Hindi
    d_current, _, _ = detect_language_adaptation(caller_input, phone=phone)
    if d_current in ("HINDI", "HINGLISH"):
        target_lang = "HINDI"

    if phone:
        _phone_language_tracker[phone] = target_lang

    expected_resp = AUDIBILITY_RESPONSE_HINDI if target_lang in ("HINDI", "HINGLISH") else AUDIBILITY_RESPONSE_ENGLISH

    # 1. Check explicit audibility phrases (e.g. "Can you hear me?", "Aawaz nahi aa rahi")
    for pattern in EXPLICIT_AUDIBILITY_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            log_highlight(
                "[GUARDRAIL TRIGGERED: AUDIBILITY CHECK-IN]",
                {
                    "Caller Phone": phone or "N/A",
                    "Matched Pattern": pattern,
                    "Caller Input": caller_input,
                    "Detected Lang": target_lang,
                    "Action": "Instant Audibility Response",
                    "Response": expected_resp
                },
                border_char="="
            )
            return expected_resp, target_lang

    # 2. Check repeated 'hello'
    hello_count_in_input = len(re.findall(r"\bhello\b", cleaned, re.IGNORECASE))
    is_hello_input = bool(HELLO_ONLY_REGEX.match(cleaned))

    # If the user repeats hello multiple times in the SAME turn (e.g. "Hello? Hello?")
    if hello_count_in_input >= 2:
        log_highlight(
            "[GUARDRAIL TRIGGERED: REPEATED HELLO AUDIBILITY]",
            {
                "Caller Phone": phone or "N/A",
                "Caller Input": caller_input,
                "Detected Lang": target_lang,
                "Action": "Multi-Hello in Single Turn",
                "Response": expected_resp
            },
            border_char="="
        )
        return expected_resp, target_lang

    # If this turn is a pure "hello"
    if is_hello_input:
        # Check prior hellos in conversation history
        prior_hellos = 0
        if history:
            for msg in history:
                if msg.get("role") == "user":
                    prev_c = (msg.get("content") or "").strip().lower()
                    if HELLO_ONLY_REGEX.match(prev_c):
                        prior_hellos += 1

        phone_key = phone or "default"
        session_hello_count = _phone_hello_tracker.get(phone_key, 0) + 1
        _phone_hello_tracker[phone_key] = session_hello_count

        # If customer is saying hello for the second time (or more), or mid-call after previous conversation turns
        is_mid_call = bool(history and len(history) >= 2)
        if prior_hellos >= 1 or session_hello_count >= 2 or is_mid_call:
            log_highlight(
                "[GUARDRAIL TRIGGERED: HELLO AUDIBILITY CONFIRMATION]",
                {
                    "Caller Phone": phone or "N/A",
                    "Caller Input": caller_input,
                    "Detected Lang": target_lang,
                    "Action": "Mid-Call or Repeated Hello - Caller confirming connection",
                    "Response": expected_resp
                },
                border_char="="
            )
            return expected_resp, target_lang

    return None, None


def check_audibility_guardrail(
    caller_input: str,
    phone: str = "",
    history: Optional[list] = None,
    preferred_language: Optional[str] = None
) -> Optional[str]:
    """
    Evaluates whether caller is asking if they are audible or repeating 'hello'.
    Returns instant confirmation without regenerating an entire sales pitch.
    """
    resp, _ = check_audibility_guardrail_with_lang(
        caller_input, phone=phone, history=history, preferred_language=preferred_language
    )
    return resp


# Explicit language preference requests (e.g., caller asking for Hindi)
HINDI_REQUEST_PATTERNS = [
    r"\b(hindi\s+(me|mein|mai)\s+(baat|bolo|boliye|samjhao|batao))\b",
    r"\b(can (we|you)|could you|please)\s+(speak|talk)\s+(in\s+)?hindi\b",
    r"\b(kya aap|aap)\s+hindi\s+(bol sakte|bolti|bolte)\b",
    r"\bhindi\s+please\b",
    r"\bspeak in hindi\b",
    r"\btalk in hindi\b"
]

def detect_language_adaptation(caller_input: str, phone: str = "") -> Tuple[str, str, str]:
    """
    Classifies caller's input into:
    - 'HINDI'   -> Enforced Agent Output: 'HINDI' (speaks in caller's preferred language to eliminate language barrier)
    - 'ENGLISH' -> Enforced Agent Output: 'ENGLISH'
    - 'HINGLISH'-> Enforced Agent Output: 'HINGLISH'

    Returns: (detected_language, enforced_language, directive_instruction)
    """
    text = (caller_input or "").strip().lower()
    if not text:
        return "ENGLISH", "ENGLISH", "Respond in clear English."

    # 0. Check explicit request to converse in Hindi
    for pat in HINDI_REQUEST_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            detected = "HINDI"
            enforced = "HINDI"
            directive = (
                "LANGUAGE GUARDRAIL ACTIVE: The caller explicitly requested to speak in Hindi. "
                "You MUST respond in polite, clear, and reassuring conversational Hindi (or natural Hinglish) "
                "in their preferred language to ensure complete comfort and eliminate any language barrier."
            )
            log_highlight(
                "[GUARDRAIL ENFORCED: LANGUAGE ADAPTATION]",
                {
                    "Caller Phone": phone or "N/A",
                    "Caller Input": caller_input,
                    "Detected Lang": detected,
                    "Enforced Lang": enforced,
                    "Directive": directive
                },
                border_char="~"
            )
            return detected, enforced, directive

    # 1. Check Devanagari script presence
    has_devanagari = bool(HINDI_DEVANAGARI_REGEX.search(text))

    # Tokenize words
    words = set(re.findall(r"\b[a-z\u0900-\u097F]+\b", text))
    hindi_hits = words.intersection(ROMAN_HINDI_INDICATORS)
    english_hits = words.intersection(ENGLISH_INDICATORS)

    hindi_count = len(hindi_hits) + (10 if has_devanagari else 0)
    english_count = len(english_hits)

    if has_devanagari or (hindi_count >= 2 and english_count == 0) or (hindi_count >= 3 and english_count <= 1):
        detected = "HINDI"
        enforced = "HINDI"
        directive = (
            "LANGUAGE GUARDRAIL ACTIVE: The caller spoke in Hindi. "
            "You MUST reply in clear, polite, and accessible conversational Hindi (or natural Hinglish). "
            "Speak to them in their preferred language so they feel fully supported and there is no language barrier."
        )
    elif hindi_count >= 1 and english_count >= 1:
        detected = "HINGLISH"
        enforced = "HINGLISH"
        directive = (
            "LANGUAGE GUARDRAIL ACTIVE: The caller spoke in Hinglish. "
            "You may adapt and reply in natural, professional Hinglish blended with English."
        )
    else:
        detected = "ENGLISH"
        enforced = "ENGLISH"
        directive = (
            "LANGUAGE GUARDRAIL ACTIVE: The caller spoke in English. "
            "You MUST reply in fluent, polished English."
        )

    log_highlight(
        "[GUARDRAIL ENFORCED: LANGUAGE ADAPTATION]",
        {
            "Caller Phone": phone or "N/A",
            "Caller Input": caller_input,
            "Detected Lang": detected,
            "Enforced Lang": enforced,
            "Directive": directive
        },
        border_char="~"
    )

    return detected, enforced, directive


def evaluate_all_guardrails(
    caller_input: str,
    phone: str = "",
    history: Optional[list] = None,
    preferred_language: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """
    Single unified entrypoint for evaluating all deterministic guardrails.
    Returns:
    (immediate_override_response, enforced_language, guardrail_metadata)
    If immediate_override_response is not None, bypass the LLM and deliver this exact response!
    """
    meta = {}
    
    # 0. Answering Machine Detection (AMD) / Carrier IVR Check
    amd_resp = check_amd_guardrail(caller_input, phone=phone)
    if amd_resp:
        meta["guardrail"] = "AMD_CARRIER_IVR"
        meta["action"] = "IMMEDIATE_RESPONSE"
        return amd_resp, "ENGLISH", meta

    # 1. Audibility / "Can you hear me?" / Second Hello Check
    audibility_resp, audibility_lang = check_audibility_guardrail_with_lang(
        caller_input, phone=phone, history=history, preferred_language=preferred_language
    )
    if audibility_resp:
        meta["guardrail"] = "AUDIBILITY_CHECK"
        meta["action"] = "IMMEDIATE_RESPONSE"
        meta["language"] = audibility_lang
        return audibility_resp, audibility_lang, meta

    # 2. Identity Guardrail
    identity_resp = check_identity_guardrail(caller_input, phone=phone)
    if identity_resp:
        meta["guardrail"] = "IDENTITY"
        meta["action"] = "IMMEDIATE_RESPONSE"
        return identity_resp, "ENGLISH", meta

    # 3. Campus Visit / Meeting Guardrail
    visit_resp = check_visit_meeting_guardrail(caller_input, phone=phone)
    if visit_resp:
        meta["guardrail"] = "CAMPUS_VISIT_MEETING"
        meta["action"] = "IMMEDIATE_RESPONSE"
        return visit_resp, "ENGLISH", meta

    # 4. Language Adaptation Guardrail
    detected_lang, enforced_lang, directive = detect_language_adaptation(caller_input, phone=phone)
    meta["guardrail"] = "LANGUAGE_ADAPTATION"
    meta["detected_language"] = detected_lang
    meta["enforced_language"] = enforced_lang
    meta["directive"] = directive

    return None, enforced_lang, meta
