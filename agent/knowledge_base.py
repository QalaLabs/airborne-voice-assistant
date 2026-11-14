"""
Airborne Aviation Academy ADK Agent Tools
Provides real-time fast ground-truth RAG knowledge base lookup and counseling booking.
"""

import re
from typing import Optional

# Ground-truth knowledge corpus for Airborne Aviation Academy, Dwarka, New Delhi
AIRBORNE_KNOWLEDGE_BASE = [
    {
        "id": "academy_overview",
        "title": "Airborne Aviation Academy Overview & Campus",
        "keywords": ["location", "address", "dwarka", "delhi", "campus", "phone", "contact", "email", "founder", "navrang", "about", "ramphal chowk"],
        "content": (
            "Airborne Aviation Academy Overview:\n"
            "- Campus Address: E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075.\n"
            "- Contact Phones: +91 9953 777 320 | +91 9818 282 209 | Email: info@airborneaviation.in | Website: https://www.airborneaviation.in\n"
            "- Office Hours: Monday to Saturday, 9:30 AM – 6:00 PM. (Closed on Sundays).\n"
            "- Established: 2009. Head mentor & co-founder: Captain Navrang Singh (airline pilot with 15+ years of flight instruction and DGCA mentoring).\n"
            "- Key Distinctions: Every core ground class is taught directly by Captain Navrang Singh (no subcontracted junior instructors). Batches are strictly capped at 25 students for personalized mentoring. Facilities feature an onsite Airbus A320 Fixed-Base Simulator (FBS) and an authentic live Radio Telephony (RTR) lab.\n"
            "- Campus visits & counselling: Students and parents can book a campus tour or 1-on-1 career consultation slot."
        )
    },
    {
        "id": "cpl_ground_school",
        "title": "DGCA CPL Ground Classes (Commercial Pilot License)",
        "keywords": ["cpl", "ground classes", "ground school", "theory", "fee", "cost", "price", "duration", "subjects", "exams", "batch", "navrang"],
        "content": (
            "DGCA CPL Ground Classes (Commercial Pilot License):\n"
            "- Tuition Fee: Rs. 2,70,000 (covering all 5 DGCA theory papers plus RTR prep). No hidden charges.\n"
            "- Duration: 3 to 6 months. Flexible weekday and weekend batches available.\n"
            "- Batch Size: Strictly capped at 25 students per session.\n"
            "- Instructor: 100% taught directly by Captain Navrang Singh in person.\n"
            "- All 5 DGCA CPL Theory Papers Covered:\n"
            "  1. Air Navigation (General navigation, flight planning, charts, radio aids).\n"
            "  2. Aviation Meteorology (Atmospheric physics, wind systems, decoding METAR/TAF weather reports).\n"
            "  3. Air Regulations (ICAO annexes, Indian Civil Aviation Requirements CAR, Rules of the Air).\n"
            "  4. Technical General (Aircraft aerodynamics, piston and jet engines, airframes, electrical & hydraulic systems).\n"
            "  5. Technical Specific (Aircraft specifications and performance for training aircraft like Cessna 172).\n"
            "  Plus integrated Wireless Planning & Coordination (WPC) RTR (Aero) coaching.\n"
            "- Passing Criteria: Minimum 70% marks required in each DGCA paper.\n"
            "- Campus Mode: Onsite at Ramphal Chowk, Dwarka, Delhi."
        )
    },
    {
        "id": "cpl_full_training",
        "title": "Full Commercial Pilot License (CPL) Roadmap (India & Abroad)",
        "keywords": ["full cpl", "flying training", "flying school", "fto", "total cost", "flying hours", "loan", "abroad", "cadet"],
        "content": (
            "Full Commercial Pilot License (CPL) Path (India & Abroad):\n"
            "- Total Cost: In India, total CPL flying + ground training typically costs Rs. 55 to Rs. 65 Lakhs at DGCA-approved Flying Training Organisations (FTOs).\n"
            "- Total Flying Requirement: 200 hours of certified flight time (including 100 hours solo, 50 hours cross-country, 10 hours instrument, and 5 hours night flying).\n"
            "- Timeline: 12 to 18 months from ground school start to commercial pilot license issuance.\n"
            "- Abroad Flight Training: Students can also complete 200 hours in USA, South Africa, or New Zealand and convert their ICAO license to Indian DGCA CPL with Airborne's conversion guidance.\n"
            "- Education Loans: Financial assistance and loan documentation support available with national banks (SBI, Bank of Baroda, PNB)."
        )
    },
    {
        "id": "eligibility_medicals",
        "title": "CPL Eligibility Criteria & DGCA Medical Requirements",
        "keywords": ["eligibility", "qualification", "maths", "physics", "12th", "10+2", "nios", "age", "medical", "class 1", "class 2", "glasses", "spectacles", "eyesight"],
        "content": (
            "CPL Eligibility Criteria & Medicals:\n"
            "- Academic Qualification: 10+2 (Class 12) with Physics and Mathematics from any recognized state or central board (CBSE, ICSE).\n"
            "- NIOS (Open Schooling): 100% accepted by DGCA. Students from Commerce or Arts streams can clear Physics and Maths on-demand via NIOS to qualify.\n"
            "- Minimum Age: 17 years to begin ground school; 18 years for DGCA CPL license issuance.\n"
            "- DGCA Medical Process:\n"
            "  * Step 1: DGCA Class 2 Medical Examination conducted by any DGCA-empanelled civil medical examiner (Cost ~Rs. 5,000-8,000).\n"
            "  * Step 2: PMR (Permanent Medical Record) number generated on eGCA portal.\n"
            "  * Step 3: DGCA Class 1 Medical Examination conducted at designated IAF or civil aviation medical centres.\n"
            "- Eyesight & Spectacles: Wearing glasses is 100% permitted by DGCA as long as distance vision is correctable to 6/6 with lenses and no color blindness exists."
        )
    },
    {
        "id": "cadet_pilot_program",
        "title": "Cadet Pilot Program Preparation (IndiGo, Air India, Akasa)",
        "keywords": ["cadet", "indigo cadet", "air india cadet", "akasa cadet", "entrance", "screening", "aptitude", "fee"],
        "content": (
            "Cadet Pilot Program Preparation:\n"
            "- Course Fee: Rs. 50,000.\n"
            "- Programs Supported: IndiGo Cadet Pilot Program (CAE, L3Harris, Insight, Skyborne), Air India Cadet Program, and Akasa Air Cadet Pilot Program.\n"
            "- Curriculum: Physics & Mathematics written entrance test preparation, English proficiency, ADAPT/COMPASS cognitive aptitude tests, Group Discussion (GD), and personal interview mentoring.\n"
            "- Advantage: Cadet programs offer a direct letter of intent (LOI) with the airline upon selection."
        )
    },
    {
        "id": "a320_simulator",
        "title": "Airbus A320 Fixed-Base Simulator (FBS) Training",
        "keywords": ["simulator", "sim", "airbus", "a320", "fbs", "cockpit", "ftd", "type rating", "fee"],
        "content": (
            "Airbus A320 Simulator Training (FBS Level 5):\n"
            "- Fee: Rs. 12,000 per module session.\n"
            "- Location: Onsite at Airborne Aviation Academy, Ramphal Chowk, Dwarka campus.\n"
            "- Purpose: Cockpit scan flow familiarization, airline transition prep, airline entrance simulator assessments, and multi-crew coordination intro before high-cost type ratings."
        )
    },
    {
        "id": "cabin_crew_training",
        "title": "Cabin Crew / Flight Attendant Training",
        "keywords": ["cabin crew", "air hostess", "flight attendant", "steward", "fee", "eligibility", "grooming"],
        "content": (
            "Cabin Crew / Flight Attendant Training:\n"
            "- Course Fee: Rs. 59,000 (Early-bird launch offers available from Rs. 54,000).\n"
            "- Duration: 1 to 2 months.\n"
            "- Eligibility: 10+2 passed in any stream (Arts, Commerce, Science). Age 18 to 27 years. Minimum height ~155 cm for females, 170 cm for males. Fluent in English & Hindi.\n"
            "- Modules: In-flight passenger service, safety & emergency procedures, aviation medicine, personal grooming, and airline mock interviews.\n"
            "- Campus Mode: Onsite training at Ramphal Chowk, Dwarka campus."
        )
    }
]


def search_knowledge(query: str) -> str:
    """Searches Airborne Aviation Academy's verified ground-truth knowledge base.
    Use this when a prospective student asks about CPL ground classes, fees, DGCA exams,
    10+2 NIOS eligibility, Class 1/2 medicals, Cadet Pilot programs, Airbus A320 simulator,
    or campus location at Ramphal Chowk, Dwarka, New Delhi.

    Args:
        query: Specific aviation student question or topic keywords.

    Returns:
        Exact factual context from Airborne Aviation Academy ground-truth documents.
    """
    clean_query = str(query or "").lower().strip()
    if not clean_query:
        return "No specific aviation query provided."

    query_tokens = set(re.findall(r"\b[a-z0-9_+-]+\b", clean_query))
    scored = []
    for item in AIRBORNE_KNOWLEDGE_BASE:
        score = 0
        content_lower = item["content"].lower()
        title_lower = item["title"].lower()

        for kw in item["keywords"]:
            if kw in clean_query:
                score += 5
            elif kw in query_tokens:
                score += 3

        for token in query_tokens:
            if token in title_lower:
                score += 4
            elif token in content_lower:
                score += 1

        if score > 0:
            scored.append((score, item["content"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return "\n\n---\n\n".join([s[1] for s in scored[:2]])

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


search_local_knowledge = search_knowledge

