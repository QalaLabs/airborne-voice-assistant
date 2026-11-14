"""
VAGADK Lesson Injector
Fetches active, verified negative constraints and rules from the database and injects them
into the live agent's prompt to prevent past mistakes from repeating.
"""

import sys
import os
from typing import List, Dict, Any

VAGADK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if VAGADK_ROOT not in sys.path:
    sys.path.insert(0, VAGADK_ROOT)

import database

# In-memory fallback cache in case DB is unreachable
_CACHE_LESSONS: List[Dict[str, Any]] = [
    {
        "topic_tag": "DGCA_MEDICAL",
        "rule_instruction": "Class 2 medical must be completed first with a DGCA examiner, then Class 1 at designated DGCA centers (IAM, AFCME).",
        "negative_constraint": "Do NOT claim DGCA Class 1 can be done at local clinics or random private hospitals.",
        "priority_score": 9
    },
    {
        "topic_tag": "ELIGIBILITY",
        "rule_instruction": "10+2 with Physics and Maths is mandatory for CPL. Non-science students can clear them through NIOS.",
        "negative_constraint": "Do NOT tell Arts/Commerce students they are directly eligible without clearing Physics and Maths via NIOS.",
        "priority_score": 8
    },
    {
        "topic_tag": "INSTITUTIONAL_POLICY",
        "rule_instruction": "Airborne is an aviation training and DGCA ground school academy, not a job placement agency.",
        "negative_constraint": "NEVER promise or guarantee an airline job or 100% placement.",
        "priority_score": 9
    }
]

def fetch_active_lessons_from_db(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieves the highest priority active lessons from agent_lessons table.
    """
    try:
        conn = database.get_connection()
        if not conn:
            return _CACHE_LESSONS[:limit]

        with conn.cursor() as cur:
            cur.execute("""
                SELECT topic_tag, rule_instruction, negative_constraint, priority_score
                FROM agent_lessons
                WHERE is_active = TRUE
                ORDER BY priority_score DESC, created_at DESC
                LIMIT %s;
            """, (limit,))
            rows = cur.fetchall()
            if rows:
                return [
                    {
                        "topic_tag": r[0],
                        "rule_instruction": r[1],
                        "negative_constraint": r[2],
                        "priority_score": r[3]
                    }
                    for r in rows
                ]
    except Exception as e:
        # Fallback to cache without failing the live call
        print(f"[LESSON_INJECTOR] DB fetch warning ({e}). Using cached lessons.")

    return _CACHE_LESSONS[:limit]

def get_active_lessons_prompt(customer_phone: str = "", context: str = "") -> str:
    """
    Compiles active negative constraints and critical lessons into a prompt block.
    Called by Track A (adk_core/agent.py or precall_manager.py) before starting a call session.
    """
    lessons = fetch_active_lessons_from_db(limit=5)
    if not lessons:
        return ""

    lines = [
        "CRITICAL NEGATIVE CONSTRAINTS & ACCURACY RULES (DO NOT VIOLATE):"
    ]
    for idx, l in enumerate(lessons, 1):
        tag = l.get("topic_tag", "GENERAL")
        rule = l.get("rule_instruction", "")
        neg = l.get("negative_constraint", "")
        lines.append(f"{idx}. [{tag}] {neg} Correct approach: {rule}")

    return "\n".join(lines)
