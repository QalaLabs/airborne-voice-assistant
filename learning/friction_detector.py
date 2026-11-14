"""
VAGADK Friction Detector (Signal 1)
Identifies caller pushback, explicit corrections, repetitions, and frustration signals during a live phone call.
"""

import re
from typing import Dict, Any, List

# Explicit caller correction patterns
CORRECTION_PATTERNS = [
    r"\b(?:no|nope|not)\s+(?:that'?s\s+not|what\s+i\s+(?:asked|said|meant))\b",
    r"\bi\s+already\s+(?:told|said|explained|mentioned)\b",
    r"\blisten\s+to\s+me\b",
    r"\byou\s+(?:are\s+not\s+listening|don'?t\s+understand|missed\s+my\s+point)\b",
    r"\bthat(?:'s|\s+is)\s+(?:wrong|incorrect|false|not\s+true)\b",
    r"\bhow\s+many\s+times\s+do\s+i\s+have\s+to\s+(?:repeat|say|tell)\b",
    r"\byou\s+already\s+asked\s+that\b",
    r"\bwhy\s+are\s+you\s+repeating\b",
    r"\bmaine\s+pehle\s+hi\s+bola\b",           # Hindi/Hinglish
    r"\bgalat\s+bol\s+rahe\s+ho\b",            # Hindi/Hinglish
    r"\bye\s+nahi\s+pucha\s+maine\b",          # Hindi/Hinglish
    r"\bsuno\s+to\s+sahi\b"                    # Hindi/Hinglish
]

_COMPILED_CORRECTIONS = [re.compile(p, re.IGNORECASE) for p in CORRECTION_PATTERNS]

def analyze_transcript_friction(call_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Scans a completed call transcript for signs of caller friction or breakdown.
    Returns:
        {
            "friction_detected": bool,
            "friction_type": str,
            "turn_index": int,
            "caller_utterance": str,
            "agent_prior_response": str,
            "severity": str
        }
    """
    if not call_history or len(call_history) < 2:
        return {"friction_detected": False, "friction_type": "NONE"}

    user_utterances = []
    
    for idx, turn in enumerate(call_history):
        role = turn.get("role", "").lower()
        content = turn.get("content", "").strip()

        if role == "user":
            user_utterances.append(content)
            # 1. Check for explicit correction patterns
            for pattern in _COMPILED_CORRECTIONS:
                if pattern.search(content):
                    # Fetch agent's previous response that triggered the correction
                    prior_agent_response = ""
                    if idx > 0 and call_history[idx - 1].get("role", "").lower() == "assistant":
                        prior_agent_response = call_history[idx - 1].get("content", "")

                    return {
                        "friction_detected": True,
                        "friction_type": "CALLER_CORRECTION",
                        "turn_index": idx,
                        "caller_utterance": content,
                        "agent_prior_response": prior_agent_response,
                        "severity": "HIGH"
                    }

            # 2. Check for caller repeated question (caller asked nearly same question 2+ turns apart)
            if len(user_utterances) >= 2:
                current_words = set(content.lower().split())
                for prev_idx, prev_utt in enumerate(user_utterances[:-1]):
                    prev_words = set(prev_utt.lower().split())
                    if len(current_words) > 4 and len(prev_words) > 4:
                        overlap = len(current_words.intersection(prev_words)) / max(len(current_words), len(prev_words))
                        if overlap > 0.75:
                            prior_agent_response = call_history[idx - 1].get("content", "") if idx > 0 else ""
                            return {
                                "friction_detected": True,
                                "friction_type": "REPETITION",
                                "turn_index": idx,
                                "caller_utterance": content,
                                "agent_prior_response": prior_agent_response,
                                "severity": "MEDIUM"
                            }

    return {
        "friction_detected": False,
        "friction_type": "NONE"
    }
