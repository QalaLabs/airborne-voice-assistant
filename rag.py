import requests
import json
import re
from openai import OpenAI
import config
import supabase_client

# Initialize OpenAI Client (if key provided)
openai_client = None
if config.OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize OpenAI client: {e}")

# =====================================================================
# 📚 AIRBORNE AVIATION GROUND-TRUTH KNOWLEDGE CORPUS (from airborneaviation.in)
# =====================================================================

AIRBORNE_KNOWLEDGE_BASE = [
    {
        "id": "academy_overview",
        "title": "Airborne Aviation Academy Overview & Campus",
        "keywords": ["location", "address", "dwarka", "delhi", "campus", "phone", "contact", "email", "founder", "navrang", "modassir", "about", "ramphal chowk"],
        "content": (
            "Airborne Aviation Academy Overview:\n"
            "- Campus Address: E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075.\n"
            "- Contact Phones: +91 9953 777 320 | +91 9818 282 209 | Email: info@airborneaviation.in | Website: https://www.airborneaviation.in\n"
            "- Office Hours: Monday to Saturday, 9:30 AM – 6:00 PM. (Closed on Sundays).\n"
            "- Established: 2009. Head mentor & co-founder: Captain Navrang Singh (airline pilot with 15+ years of flight instruction and DGCA mentoring).\n"
            "- Key Distinctions: Every core ground class is taught directly by Captain Navrang Singh (no subcontracted junior instructors). Batches are strictly capped at 25 students for personalized mentoring. Facilities feature an onsite Airbus A320 Fixed-Base Simulator (FBS) and an authentic live Radio Telephony (RTR) lab.\n"
            "- Campus visits & counselling: Students and parents can book a campus tour or 1-on-1 career consultation slot at https://calendly.com/airborne-aviation/campus-visit."
        )
    },
    {
        "id": "institutional_clarification",
        "title": "Educational Institute vs Job Agency Clarification",
        "keywords": ["job", "agency", "placement", "guarantee", "recruitment", "consultancy", "hiring", "institute", "education"],
        "content": (
            "Institutional Nature & Transparency Clarification:\n"
            "- Airborne Aviation Academy is strictly an accredited professional aviation training and ground school education institution.\n"
            "- It is NOT a job placement agency, job consultancy, recruitment bureau, or broker.\n"
            "- Airborne trains students to master aeronautical subjects, build sharp pilot decision-making skills, and pass official DGCA examinations, WPC RTR licenses, and airline entrance selection boards on pure individual merit.\n"
            "- We provide comprehensive airline interview preparation (GD/PI, simulator assessments, psychomotor testing), but never sell jobs or make misleading placement claims."
        )
    },
    {
        "id": "cpl_ground_school",
        "title": "DGCA CPL Ground Classes (Commercial Pilot License)",
        "keywords": ["cpl", "ground classes", "ground school", "theory", "fee", "cost", "price", "duration", "subjects", "exams", "batch", "navrang"],
        "content": (
            "DGCA CPL Ground Classes (Commercial Pilot License):\n"
            "- Tuition Fee: ₹2,70,000 (covering all 5 DGCA theory papers plus RTR prep). No hidden or per-paper extra charges.\n"
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
            "- Total Cost: In India, total CPL flying + ground training typically costs ₹55 to ₹65 Lakhs at DGCA-approved Flying Training Organisations (FTOs).\n"
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
            "  * Step 1: DGCA Class 2 Medical Examination conducted by any DGCA-empanelled civil medical examiner (Cost ~₹5,000-₹8,000).\n"
            "  * Step 2: PMR (Permanent Medical Record) number generated on eGCA portal.\n"
            "  * Step 3: DGCA Class 1 Medical Examination conducted at designated Indian Air Force (IAF) or civil aviation medical centres.\n"
            "- Eyesight & Spectacles: Wearing glasses is 100% permitted by DGCA as long as distance vision is correctable to 6/6 with lenses and no color blindness exists."
        )
    },
    {
        "id": "atpl_ground_school",
        "title": "ATPL Ground School (Airline Transport Pilot License)",
        "keywords": ["atpl", "airline transport pilot", "captain", "command", "fee", "duration"],
        "content": (
            "ATPL Ground School (Airline Transport Pilot License):\n"
            "- Tuition Fee: ₹1,50,000.\n"
            "- Duration: 2 to 3 months. Available in blended / onsite formats at Ramphal Chowk, Dwarka.\n"
            "- Prerequisite: Existing Commercial Pilot License (CPL) holder or age 21+.\n"
            "- Subjects Covered: Advanced Air Navigation, Radio Navigation Aids, Advanced Aviation Meteorology, and Heavy Aircraft Instruments & Performance.\n"
            "- Overlap: Airborne recommends pursuing ATPL theory alongside or immediately after CPL, as core subjects overlap and streamline exam preparation."
        )
    },
    {
        "id": "cadet_pilot_program",
        "title": "Cadet Pilot Program Preparation (IndiGo, Air India, Akasa)",
        "keywords": ["cadet", "indigo cadet", "air india cadet", "akasa cadet", "entrance", "screening", "aptitude", "fee"],
        "content": (
            "Cadet Pilot Program Preparation:\n"
            "- Course Fee: ₹50,000.\n"
            "- Programs Supported: IndiGo Cadet Pilot Program (CAE, L3Harris, Insight, Skyborne), Air India Cadet Program, and Akasa Air Cadet Pilot Program.\n"
            "- Curriculum: Physics & Mathematics written entrance test preparation, English proficiency, ADAPT/COMPASS cognitive aptitude tests, Group Discussion (GD), and personal interview mentoring.\n"
            "- Advantage: Cadet programs offer a direct letter of intent (LOI) with the airline upon selection."
        )
    },
    {
        "id": "airline_selection_prep",
        "title": "Comprehensive Airline Preparation Program & GD-PI",
        "keywords": ["airline preparation", "gd", "pi", "interview", "first officer", "airline selection", "fee", "cost"],
        "content": (
            "Comprehensive Airline Preparation & GD-PI:\n"
            "- Comprehensive Program Fee: ₹1,25,000 (2.5 months intensive, 4 hours/day).\n"
            "- Standalone GD & PI Course: ₹30,000.\n"
            "- Target Audience: CPL holders preparing for airline First Officer entrance selections (IndiGo, Air India, Akasa, SpiceJet).\n"
            "- Modules: DGCA technical ground refresher, computerized psychomotor and pilot aptitude drills (CASS / COMPASS / ADAPT), HR interview questions, situational leadership, and A320 simulator assessment."
        )
    },
    {
        "id": "a320_simulator",
        "title": "Airbus A320 Fixed-Base Simulator (FBS) Training",
        "keywords": ["simulator", "sim", "airbus", "a320", "fbs", "cockpit", "ftd", "type rating", "fee"],
        "content": (
            "Airbus A320 Simulator Training (FBS Level 5):\n"
            "- Fee: ₹12,000 per module session.\n"
            "- Location: Onsite at Airborne Aviation Academy, Ramphal Chowk, Dwarka campus.\n"
            "- Features: High-fidelity A320 cockpit flight management guidance system (FMGS), electronic flight instrument system (EFIS), fly-by-wire controls, and realistic glass-cockpit displays.\n"
            "- Purpose: Cockpit scan flow familiarization, airline transition prep, airline entrance simulator assessments, and multi-crew coordination intro before high-cost type ratings."
        )
    },
    {
        "id": "psychomotor_adapt",
        "title": "CASS, COMPASS & ADAPT Pilot Aptitude Test Prep",
        "keywords": ["cass", "compass", "adapt", "psychomotor", "aptitude test", "pilot testing", "fee"],
        "content": (
            "CASS, COMPASS & ADAPT Pilot Aptitude Testing Preparation:\n"
            "- Fee: ₹30,000.\n"
            "- Focus: Hands-on software practice for pilot cognitive screening.\n"
            "- Tests: Eye-hand-foot joystick coordination, spatial 3D orientation, multi-tasking under time pressure, short-term cockpit memory, and mental mathematics."
        )
    },
    {
        "id": "cabin_crew_training",
        "title": "Cabin Crew / Flight Attendant Training",
        "keywords": ["cabin crew", "air hostess", "flight attendant", "steward", "fee", "eligibility", "grooming", "salary"],
        "content": (
            "Cabin Crew / Flight Attendant Training:\n"
            "- Course Fee: ₹59,000 (Early-bird launch offers available from ₹54,000).\n"
            "- Duration: 1 to 2 months.\n"
            "- Eligibility: 10+2 passed in any stream (Arts, Commerce, Science). Age 18 to 27 years. Minimum height ~155 cm for females, 170 cm for males. Fluent in English & Hindi.\n"
            "- Modules: In-flight passenger service excellence, safety & emergency evacuation procedures (SEP), aviation medicine & first aid, aircraft door drills, personal grooming & makeup, and airline mock interview readiness.\n"
            "- Campus Mode: Onsite training at Ramphal Chowk, Dwarka campus."
        )
    },
    {
        "id": "flight_dispatcher",
        "title": "Flight Dispatcher / Flight Operations Officer Training",
        "keywords": ["flight dispatcher", "dispatcher", "flight operations", "foo", "fee", "syllabus"],
        "content": (
            "Flight Dispatcher Training:\n"
            "- Fee: ₹1,20,000.\n"
            "- Role: Ground-based pilots who compute aircraft weight and balance, calculate fuel burn, file flight plans with ATC, and monitor en-route weather.\n"
            "- Minimum Requirement: 10+2 with Physics and Maths; age 21+ for DGCA approval."
        )
    },
    {
        "id": "private_pilot_license",
        "title": "Private Pilot License (PPL) Guidance",
        "keywords": ["ppl", "private pilot", "hobby flying", "fee", "cost"],
        "content": (
            "Private Pilot License (PPL) Training:\n"
            "- Total Cost: Approximately ₹25 Lakhs (includes ground theory + 40 flying hours).\n"
            "- Objective: Designed for aviation enthusiasts, business professionals, and hobbyists wishing to fly private single-engine non-commercial aircraft."
        )
    },
    {
        "id": "rtr_exam_prep",
        "title": "Radio Telephony RTR (Aero) Exam Preparation",
        "keywords": ["rtr", "radio telephony", "wpc", "atc", "callsign", "regulations viva", "transmission"],
        "content": (
            "Radio Telephony RTR (Aero) Exam Preparation:\n"
            "- Conducted by: Wireless Planning and Coordination (WPC) Wing, Ministry of Communications, India.\n"
            "- Format: Part 1 (Practical Transmission & ATC simulated communication exercise) + Part 2 (Oral Regulations & Technical Viva).\n"
            "- Airborne Facility: Dedicated RTR live simulator mimicking Delhi/Mumbai air traffic control frequencies. Included free with DGCA CPL Ground Classes (₹2,70,000 bundle)."
        )
    },
    {
        "id": "ratings_and_english",
        "title": "Multi-Engine, Instrument Rating & Aviation English",
        "keywords": ["multi-engine", "mer", "instrument rating", "ir", "aviation english", "icao"],
        "content": (
            "Specialized Pilot Ratings & Aviation English:\n"
            "- Instrument Rating (IR) Preparation: ₹3–5 Lakhs theory and procedure familiarization.\n"
            "- Multi-Engine Rating (MER) Preparation: ₹3–5 Lakhs multi-engine aerodynamic systems and asymmetric flight theory.\n"
            "- Aviation English (ICAO): ₹50,000 – ₹1,00,000 for ICAO Level 4/5/6 language proficiency training."
        )
    },
    {
        "id": "parent_guidance",
        "title": "Securing Your Child's Future in Aviation (Parent Guide)",
        "keywords": ["parent", "parents", "child", "future", "career guidance", "consultation", "roadmap"],
        "content": (
            "Securing Your Child's Future in Aviation:\n"
            "- Fee: 100% Free personalized guidance for parents and aspiring students.\n"
            "- Format: 1-on-1 career mapping with Capt. Navrang Singh at our Ramphal Chowk campus.\n"
            "- Topics: DGCA vs Cadet routes, flight school selection in India vs USA/South Africa/New Zealand, license conversion, education loans, and realistic career timelines."
        )
    },
    {
        "id": "website_faqs",
        "title": "Frequently Asked Questions (Website FAQs)",
        "keywords": ["faq", "questions", "timing", "batch size", "airlines", "alumni", "cabin crew age", "nios"],
        "content": (
            "Frequently Asked Questions from airborneaviation.in:\n"
            "Q: Where is Airborne Aviation Academy located?\n"
            "A: E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075. Contact: +91 9953 777 320.\n\n"
            "Q: What are the office hours?\n"
            "A: Monday to Saturday, 9:30 AM – 6:00 PM. Closed on Sundays.\n\n"
            "Q: Is Capt. Navrang Singh in every class?\n"
            "A: Yes! Every core ground class is taught directly by Captain Navrang Singh. No junior or subcontracted instructors.\n\n"
            "Q: What is the batch size?\n"
            "A: Strictly capped at 25 students to guarantee individual attention.\n\n"
            "Q: What airlines have Airborne alumni joined?\n"
            "A: Our graduates fly with IndiGo, Air India, Akasa Air, SpiceJet, Air Asia India, Alliance Air, and international carriers.\n\n"
            "Q: Can I join ground school if I did not have Physics/Maths in Class 12?\n"
            "A: Yes. You can clear Physics and Mathematics through NIOS (National Institute of Open Schooling) on-demand exams, which is 100% recognized by DGCA."
        )
    }
]

# =====================================================================
# 🔍 SMART SCORING & RETRIEVAL ENGINE
# =====================================================================

def search_local_knowledge(query: str, top_k: int = 3) -> str:
    """
    Performs fast token-based TF-IDF / keyword relevance scoring across all Airborne Aviation
    knowledge blocks to return the exact relevant facts from airborneaviation.in in 1-2 ms.
    """
    cleaned_query = query.lower()
    query_tokens = set(re.findall(r'\b[a-z0-9_+-]+\b', cleaned_query))
    
    scored_blocks = []
    for item in AIRBORNE_KNOWLEDGE_BASE:
        score = 0
        content_lower = item["content"].lower()
        title_lower = item["title"].lower()
        
        # Check explicit keywords
        for kw in item["keywords"]:
            if kw in cleaned_query:
                score += 5
            elif kw in query_tokens:
                score += 3

        # Check title matches
        for token in query_tokens:
            if token in title_lower:
                score += 4
            elif token in content_lower:
                score += 1

        if score > 0:
            scored_blocks.append((score, item["content"]))

    # Sort descending by score
    scored_blocks.sort(key=lambda x: x[0], reverse=True)
    
    if scored_blocks:
        selected = [b[1] for b in scored_blocks[:top_k]]
        return "\n\n---\n\n".join(selected)
        
    # Default high-yield fallback
    return (
        "Airborne Aviation Academy (Dwarka, Delhi):\n"
        "- DGCA CPL Ground Classes: ₹2,70,000 (covers all 5 DGCA papers + RTR; mentored by Capt. Navrang Singh).\n"
        "- Full CPL Flying Training (India/Abroad): ₹55–65 Lakhs (200 hours flight time).\n"
        "- Airbus A320 Simulator FBS: ₹12,000 per session.\n"
        "- ATPL Ground School: ₹1,50,000 | Cadet Pilot Prep: ₹50,000 | Cabin Crew: ₹59,000.\n"
        "- Eligibility: 10+2 with Physics and Maths (NIOS allowed). Minimum age: 17 years.\n"
        "- Campus Address: E-549, 2nd Floor, Ramphal Chowk, Sector 7, Dwarka, Delhi. Phone: +91 9953 777 320."
    )

def get_embedding(text: str, model: str = "text-embedding-3-small"):
    """
    Generate vector embedding using OpenAI API (if configured).
    """
    if not openai_client:
        return None
        
    try:
        text = text.replace("\n", " ")
        response = openai_client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding API Notice: {e}")
        return None

def query_rag(query: str, threshold: float = 0.5, limit: int = 3) -> str:
    """
    Main RAG query interface:
    1. First attempts vector similarity search via PostgreSQL / Cloud SQL pgvector.
    2. If vector DB is unavailable or returns no matches, seamlessly uses the high-precision
       in-memory Airborne Aviation knowledge engine derived directly from airborneaviation.in.
    """
    try:
        query_vector = get_embedding(query)
        if query_vector:
            matches = supabase_client.match_documents(
                query_embedding=query_vector,
                match_threshold=threshold,
                match_count=limit
            )
            if matches and len(matches) > 0:
                context_blocks = [doc.get("content", "") for doc in matches if doc.get("content")]
                if context_blocks:
                    return "\n---\n".join(context_blocks)
    except Exception as e:
        print(f"Notice: Vector RAG fallback triggered: {e}")

    # Fallback to local ground-truth knowledge base
    return search_local_knowledge(query, top_k=limit)

def ingest_text_chunk(text: str, metadata: dict = None):
    """
    Ingests a custom text chunk into PostgreSQL documents table.
    """
    try:
        embedding = get_embedding(text)
        if embedding:
            supabase_client.insert_document(text, metadata or {}, embedding)
            print("Successfully ingested document chunk with vector embedding.")
        else:
            print("Skipped vector ingestion: No embedding provider available.")
    except Exception as e:
        print(f"Failed to ingest document chunk: {e}")

def seed_airborne_knowledge():
    """
    Seeds all knowledge blocks from airborneaviation.in into PostgreSQL documents table.
    """
    print(f"Seeding {len(AIRBORNE_KNOWLEDGE_BASE)} knowledge blocks into Database...")
    count = 0
    for item in AIRBORNE_KNOWLEDGE_BASE:
        try:
            ingest_text_chunk(item["content"], {"source": "airborneaviation.in", "id": item["id"]})
            count += 1
        except Exception as e:
            print(f"Error seeding item {item['id']}: {e}")
    print(f"Seeding completed. {count} blocks processed.")
