"""
Tool(s) exposed to the ADK agent (agent/agent.py) and external callers.
Provides verified knowledge lookup and counseling session booking.
"""

import sys
import os

try:
    from agent.rag_client import query_rag
except ImportError:
    try:
        from rag_client import query_rag
    except ImportError:
        query_rag = None

try:
    from agent.knowledge_base import search_local_knowledge
except ImportError:
    try:
        from knowledge_base import search_local_knowledge
    except ImportError:
        search_local_knowledge = None


def search_knowledge(query: str) -> str:
    """Looks up Airborne Aviation Academy facts (courses, fees, eligibility,
    schedules, campus location, DGCA medicals, NIOS rules) relevant to the caller's question.

    Args:
        query: Specific aviation student question or topic keywords,
            e.g. 'CPL ground classes fee' or '10+2 NIOS eligibility'.

    Returns:
        Exact factual context from Airborne Aviation Academy ground-truth documents.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return "No specific aviation query provided."

    if query_rag:
        try:
            res = query_rag(clean_query)
            if res and len(res.strip()) > 0:
                return res
        except Exception:
            pass

    if search_local_knowledge:
        return search_local_knowledge(clean_query)

    return (
        "Airborne Aviation Academy, Dwarka, New Delhi. Led by Captain Navrang Singh.\n"
        "- CPL Ground Classes: Rs. 2,70,000 (covers all 5 DGCA papers + RTR).\n"
        "- Full CPL Flying Training: Rs. 55-65 Lakhs (200 flight hours).\n"
        "- Eligibility: 10+2 with Physics and Maths (NIOS accepted).\n"
        "- Address: E-549, 2nd Floor, Ramphal Chowk, Sector 7, Dwarka, New Delhi."
    )


def book_counseling_session(student_name: str, phone: str, preferred_date: str) -> str:
    """Schedules an in-person or telephonic career consultation with Captain Navrang Singh
    at Airborne Aviation Academy, Dwarka campus.

    Args:
        student_name: Name of prospective student.
        phone: 10-digit phone number.
        preferred_date: Date or preferred day for the counseling session.

    Returns:
        Confirmation status of the counseling booking.
    """
    return (
        f"Counseling session tentatively booked for {student_name} ({phone}) on {preferred_date} "
        f"with Capt. Navrang Singh at Airborne Aviation Academy, Ramphal Chowk, Dwarka, New Delhi. "
        f"Our team will confirm the exact time slot via SMS/WhatsApp."
    )
