"""
VAGADK Ground-Truth Fact Auditor (Signal 2)
Audits statements made by the voice agent against Airborne Aviation Academy's verified rules and regulations.
"""

import re
from typing import Dict, Any, List

# Immutable ground-truth facts for Airborne Aviation Academy
FACTUAL_RULES = [
    {
        "id": "RULE_DGCA_MEDICAL",
        "topic": "DGCA_MEDICAL",
        # Bad pattern: agent claims Class 1 can be done at any local hospital or clinic
        "violation_regex": r"\b(?:any\s+(?:local\s+)?(?:hospital|clinic|doctor)|nearby\s+clinic)\b",
        "context_trigger": r"\b(?:class\s*1|medical)\b",
        "critic_reasoning": "DGCA Class 1 medicals are strictly conducted at DGCA-authorized centers (such as IAM Bengaluru, AFCME New Delhi, or empanelled centers), not random private hospitals.",
        "suggested_correction": "Inform the student that Class 2 medical is done first by a DGCA-empanelled examiner, followed by Class 1 at designated DGCA centers.",
        "negative_constraint": "NEVER state that DGCA Class 1 medicals can be performed at any local clinic or general hospital. Always state Class 2 must come first, followed by DGCA-authorized centers."
    },
    {
        "id": "RULE_ELIGIBILITY_MATH_PHYSICS",
        "topic": "ELIGIBILITY",
        # Bad pattern: agent claiming 10+2 without science or math/physics is directly eligible without NIOS
        "violation_regex": r"\b(?:no\s+maths?\s+(?:needed|required)|without\s+(?:maths?|physics)\s+directly\s+eligible)\b",
        "context_trigger": r"\b(?:eligib|commerce|arts|qualification|10\+2)\b",
        "critic_reasoning": "DGCA requires 10+2 with Physics and Mathematics. Commerce or Arts students MUST clear these subjects through NIOS (National Institute of Open Schooling).",
        "suggested_correction": "Clarify that Physics and Maths are mandatory for DGCA CPL, but students from Arts or Commerce can clear them via NIOS with Airborne's guidance.",
        "negative_constraint": "NEVER tell non-science students they are directly eligible for CPL. Explain that 10+2 with Physics and Maths is mandatory, but obtainable via NIOS."
    },
    {
        "id": "RULE_JOB_GUARANTEE",
        "topic": "INSTITUTIONAL_POLICY",
        # Bad pattern: agent promising guaranteed airline job
        "violation_regex": r"\b(?:guaranteed?\s+(?:job|placement|airline\s+seat)|100%\s+placement)\b",
        "context_trigger": r"\b(?:job|placement|guarantee|hire)\b",
        "critic_reasoning": "Airborne Aviation is strictly a training institute and does NOT offer guaranteed job placement or act as a recruitment agency.",
        "suggested_correction": "State that Airborne provides rigorous airline selection prep (GD/PI, simulator, aptitude) but airline selection is on pure individual merit.",
        "negative_constraint": "NEVER promise or guarantee an airline job. Emphasize that Airborne prepares students to excel in DGCA exams and airline entrance tests on merit."
    },
    {
        "id": "RULE_CAMPUS_LOCATION",
        "topic": "CAMPUS_INFO",
        # Bad pattern: wrong campus city / location
        "violation_regex": r"\b(?:mumbai|bangalore|bengaluru|kolkata|chennai|gurgaon|noida)\s+campus\b",
        "context_trigger": r"\b(?:where|location|address|campus|dwarka)\b",
        "critic_reasoning": "Airborne Aviation Academy's main ground training campus is located at Ramphal Chowk Road, Sector 7, Dwarka, New Delhi.",
        "suggested_correction": "Direct students to our central campus in Dwarka, New Delhi for simulator training, RTR lab, and ground classes.",
        "negative_constraint": "Do NOT claim Airborne has training campuses in other cities; ground classes are held at Dwarka, New Delhi."
    }
]

def audit_transcript_facts(call_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Audits every agent turn against ground-truth academy guidelines.
    Returns:
        {
            "factual_error_detected": bool,
            "rule_id": str,
            "topic": str,
            "turn_index": int,
            "agent_response": str,
            "critic_reasoning": str,
            "suggested_correction": str,
            "negative_constraint": str
        }
    """
    for idx, turn in enumerate(call_history):
        if turn.get("role", "").lower() in ["assistant", "model"]:
            content = turn.get("content", "")
            for rule in FACTUAL_RULES:
                # If the context is triggered and a violation pattern matches
                if re.search(rule["context_trigger"], content, re.IGNORECASE):
                    if re.search(rule["violation_regex"], content, re.IGNORECASE):
                        return {
                            "factual_error_detected": True,
                            "rule_id": rule["id"],
                            "topic": rule["topic"],
                            "turn_index": idx,
                            "agent_response": content,
                            "critic_reasoning": rule["critic_reasoning"],
                            "suggested_correction": rule["suggested_correction"],
                            "negative_constraint": rule["negative_constraint"]
                        }

    return {
        "factual_error_detected": False,
        "rule_id": "NONE"
    }
