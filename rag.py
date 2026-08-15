import requests
import json
from openai import OpenAI
import config
import supabase_client

# Initialize OpenAI Client
openai_client = None
if config.OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize OpenAI client: {e}")

def get_embedding(text: str, model: str = "text-embedding-3-small"):
    """
    Generate 1536-dimensional vector embedding for a given text.
    """
    if not openai_client:
        # Return mock 1536-dimensional embedding
        return [0.0] * 1536
        
    text = text.replace("\n", " ")
    response = openai_client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding

def query_rag(query: str, threshold: float = 0.5, limit: int = 3) -> str:
    """
    Queries the RAG system to find relevant information from the website.
    """
    try:
        # Generate query embedding
        query_vector = get_embedding(query)
        
        # Search vector DB
        matches = supabase_client.match_documents(
            query_embedding=query_vector,
            match_threshold=threshold,
            match_count=limit
        )
        
        if not matches:
            return "No matching context found from Airborne Aviation website."
            
        context_blocks = []
        for doc in matches:
            content = doc.get("content", "")
            context_blocks.append(content)
            
        return "\n---\n".join(context_blocks)
        
    except Exception as e:
        print(f"Error querying RAG system: {e}")
        # Return fallback knowledge about Airborne Aviation
        return (
            "Airborne Aviation Academy,Dwarka,Delhi. Lead mentor is Captain Navrang Singh.\n"
            "Courses offered:\n"
            "1. DGCA CPL Ground School (Fee: Rs 2,70,000)\n"
            "2. ATPL Ground School (Fee: Rs 1,50,000)\n"
            "3. Radio Telephony (RTR-A) Exam Prep\n"
            "4. Cadet Pilot Program Preparation (Fee: Rs 50,000)\n"
            "5. GD & PI (Group Discussion & Personal Interview) (Fee: Rs 30,000)\n"
            "6. Comprehensive Airline Interview Prep (Fee: Rs 1,25,000)\n"
            "7. Psychomotor Prep (CASS/COMPASS/ADAPT) (Fee: Rs 30,000)\n"
            "8. Airbus A320 Simulator FBS training (Fee: Rs 12,000)\n"
            "9. Cabin Crew Training (Fee: Rs 59,000)\n"
            "10. Private Pilot License (PPL) Ground Classes\n"
            "11. Multi-Engine Rating (MER) Ground School"
        )

def ingest_text_chunk(text: str, metadata: dict = None):
    """
    Utility function to ingest a custom website text chunk into the RAG system.
    """
    try:
        embedding = get_embedding(text)
        supabase_client.insert_document(text, metadata or {}, embedding)
        print("Successfully ingested document chunk.")
    except Exception as e:
        print(f"Failed to ingest document chunk: {e}")

def seed_airborne_knowledge():
    """
    Seeds the vector database with comprehensive, detailed knowledge of Airborne Aviation's 11 core courses.
    """
    knowledge = [
        "Airborne Aviation Academy Overview: Headquartered at E-549, 2nd Floor, Ramphal Chowk, Sector 7, Dwarka, Delhi 110075. Phone: +91 9953 777 320, Email: info@airborneaviation.in. Co-founded and led by Captain Navrang Singh with over 15 years of flight instruction and DGCA exam mentoring experience.",
        
        "Course 1: DGCA Commercial Pilot License (CPL) Ground Classes. Fee: Rs 2,70,000. Comprehensive theoretical coaching covering all 5 DGCA exam papers: Air Navigation, Aviation Meteorology, Air Regulations, Technical General (Aircraft Systems), and Technical Specific. Includes integrated Radio Telephony (RTR-A) preparation and simulator lab sessions. Duration: 4 to 6 months. Eligibility: 10+2 with Physics and Mathematics (or equivalent from NIOS). Minimum age: 17 years.",
        
        "Course 2: ATPL Ground School (Airline Transport Pilot License). Fee: Rs 1,50,000. Specialized ground school for existing Commercial Pilot License (CPL) holders preparing to upgrade to Airline Captain status. Subjects: Advanced Air Navigation, Radio Navigation, Advanced Meteorology, and Aircraft Performance. Duration: 2 to 3 months.",
        
        "Course 3: Radio Telephony (RTR-A) Exam Prep. Essential radio communication licensing exam conducted by WPC (Wireless Planning & Coordination Wing). Airborne features a state-of-the-art live RTR simulator lab mimicking pilot-to-ATC transmissions, Part 1 practical transmission, and Part 2 regulations viva.",
        
        "Course 4: Cadet Pilot Program Preparation. Fee: Rs 50,000. Specialized entrance coaching for cadet pilot selection programs with major airlines including IndiGo Cadet Program, Air India Cadet Program, and Akasa Air Cadet Program. Covers written exams (Physics, Maths, English), COMPASS/ADAPT cognitive assessment, GD, and personal interviews.",
        
        "Course 5: GD & PI Course (Group Discussion & Personal Interview). Fee: Rs 30,000. Foundational soft-skills, public speaking, aviation situational judgment tests, current aviation trends, body language, and mock interview panels with airline veterans.",
        
        "Course 6: Comprehensive Airline Selection Prep. Fee: Rs 1,25,000. A 3-month intensive program led by senior aviation mentors such as former Air India AGM Rajeet Khalsa and Capt. Navrang Singh. Covers multi-round GD, technical viva, CASS/COMPASS psychomotor drills, HR interview preparation, and cockpit simulator familiarization.",
        
        "Course 7: Psychomotor Test Prep (CASS / COMPASS / ADAPT). Fee: Rs 30,000. Preparation for computerized pilot aptitude testing. Modules focus on eye-hand-foot coordination, spatial orientation, multi-tasking under pressure, short-term memory, and mental arithmetic.",
        
        "Course 8: Airbus A320 Simulator FBS (Fixed-Base Simulator). Fee: Rs 12,000. Practical cockpit familiarization on the A320 Fixed-Base Simulator. Covers cockpit panel layouts, Flight Management and Guidance System (FMGS) programming, glass cockpit scan flows, and normal/abnormal procedures.",
        
        "Course 9: Cabin Crew / Flight Attendant Training. Fee: Rs 59,000. Professional training covering in-flight service excellence, emergency evacuation drills, aviation medicine, grooming, etiquette, and interview preparation for top domestic and international airlines. Eligibility: 10+2 in any stream, age 18-26, fluent in English & Hindi.",
        
        "Course 10: Private Pilot License (PPL) Ground Classes. Designed for hobby flyers, business executives, and aviation enthusiasts wishing to fly private non-commercial aircraft. Covers basic Air Navigation, Meteorology, Air Regulations, and Aircraft Mechanics.",
        
        "Course 11: Multi-Engine Rating (MER) Ground School. Theoretical ground classes for CPL pilots upgrading to twin-engine aircraft certifications. Covers asymmetric thrust aerodynamics, critical engine failure procedures, single-engine climb performance, and multi-engine system operations.",
        
        "Medical Requirements: To obtain a CPL, candidates must undergo DGCA Class 2 Medical Examination first, followed by DGCA Class 1 Medical Examination at designated Air Force or civil medical centers. Wearing glasses is allowed as long as vision is correctable to 6/6."
    ]
    
    print(f"Seeding {len(knowledge)} Airborne knowledge blocks into Supabase Vector DB...")
    for i, fact in enumerate(knowledge):
        ingest_text_chunk(fact, {"source": "airborne_seed", "index": i})
    print("Database seeding completed successfully.")
