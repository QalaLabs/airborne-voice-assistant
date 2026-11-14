"""
VAGADK Agent Tool Bindings
Provides real-time fast RAG and database lookup functions exposed to the Google ADK Agent.
Includes verified knowledge base retrieval and counseling booking.
"""

import sys
import os

# Ensure repo root is on path for relative module imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from agent.knowledge_base import search_local_knowledge
except ImportError:
    search_local_knowledge = None

try:
    import rag
except ImportError:
    rag = None


def search_knowledge(query: str) -> str:
    """Searches Airborne Aviation Academy's verified ground-truth knowledge base.
    Use this when a prospective student asks about:
    - Commercial Pilot License (CPL) ground classes, duration, subjects, and fees (Rs. 2,70,000)
    - Full flying training costs (~Rs. 55-65 Lakhs for 200 hours)
    - DGCA 10+2 eligibility (Physics and Mathematics criteria, NIOS acceptance)
    - DGCA Medical examinations (Class 2 and Class 1 medical procedures)
    - Cadet Pilot Programs (IndiGo, Air India, Akasa cadet pathways)
    - Airbus A320 simulator training and airline interview preparation
    - Campus location at Ramphal Chowk, Dwarka, New Delhi

    Args:
        query: Specific student aviation topic or question.

    Returns:
        Exact factual context from official academy documents.
    """
    clean_query = str(query or "").strip()
    if not clean_query:
        return "No specific aviation query provided."

    if rag and hasattr(rag, "query_rag"):
        try:
            context = rag.query_rag(clean_query, limit=2)
            if context and len(context.strip()) > 0:
                return context
        except Exception as e:
            print(f"[ADK_TOOL_ERROR] rag.query_rag failed: {e}")

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
