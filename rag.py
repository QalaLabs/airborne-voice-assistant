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
    Seeds the vector database with detailed mock information about Airborne Aviation's 11 courses.
    This provides fallback database records for immediate operation.
    """
    knowledge = [
        "Airborne Aviation Academy is located at E-549, 2nd Floor, Ramphal Chowk, Sector 7, Dwarka, Delhi 110075. Contact numbers: +91 9953 777 320. Email: info@airborneaviation.in.",
        
        "Course 1: DGCA Commercial Pilot License (CPL) Ground Classes. This course prepares students for the core theory papers required by DGCA, including Air Navigation, Aviation Meteorology, Air Regulations, Technical General, and Technical Specific. It includes integrated RTR-A exam preparation. The fee is Rs 2,70,000.",
        
        "Course 2: ATPL Ground School. The Airline Transport Pilot License course is intended for active CPL holders who are preparing to transition to the Captain seat. The ground training covers advanced systems and operational procedures. The fee is Rs 1,50,000.",
        
        "Course 3: Radio Telephony (RTR-A) Exam Prep. Preparing students for the RTR exam conducted by WPC. Airborne features a dedicated RTR simulation lab mimicking pilot-to-controller live communication patterns.",
        
        "Course 4: Cadet Pilot Program Preparation. Tailored test and exam coaching for cadet pilot entry processes for major airlines such as IndiGo, Air India, and Akasa. Fee: Rs 50,000.",
        
        "Course 5: GD & PI Course. Group Discussion and Personal Interview prep, covering aviation topics, situational judgment, and communication enhancement. Fee: Rs 30,000.",
        
        "Course 6: Comprehensive Airline Selection Prep. Led by expert mentors like former Air India AGM Rajeet Khalsa, this 3-month program covers technical and personal interview preparation, mock sessions, and airline simulators. Fee: Rs 1,25,000.",
        
        "Course 7: Psychomotor Test Prep (CASS/COMPASS/ADAPT). Prepares students for pilot psychomotor, spatial awareness, memory, and cognitive aptitude testing. Fee: Rs 30,000.",
        
        "Course 8: Airbus A320 Simulator FBS. Practical training on the Fixed-Base Simulator (FBS) to familiarise candidates with cockpit controls, layout, flight management systems (FMS), and flight dynamics of the A320. Fee: Rs 12,000.",
        
        "Course 9: Cabin Crew / Flight Attendant Training. Professional cabin services training covering safety, emergency drills, grooming, etiquette, and airline customer support. Fee: Rs 59,000.",
        
        "Course 10: Private Pilot License (PPL) Ground Classes. Designed for hobby flyers and aircraft owners who wish to fly privately. Covers basic theory classes on flying mechanics and navigation.",
        
        "Course 11: Multi-Engine Rating (MER) Ground School. Teaches asymmetric thrust aerodynamics, engine-out procedures, and cockpit controls mapping for multi-engine aircraft certifications."
    ]
    
    for i, fact in enumerate(knowledge):
        ingest_text_chunk(fact, {"source": "manual_seed", "index": i})
