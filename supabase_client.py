try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

import config

supabase = None

if config.SUPABASE_URL and config.SUPABASE_KEY and create_client:
    try:
        supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    except Exception as e:
        print(f"Failed to initialize Supabase client: {e}")
else:
    if not create_client:
        print("Notice: 'supabase' package not installed in environment. Operating in mock mode.")
    else:
        print("Warning: SUPABASE_URL and SUPABASE_KEY are not configured.")

def get_supabase_client():
    return supabase

def save_lead(name: str, phone: str, email: str = None, course: str = None, status: str = "Cold"):
    """
    Saves or updates a lead in the leads table.
    """
    if not supabase:
        print("Mock: Saving lead to Supabase:", name, phone, course, status)
        return {"id": "mock-uuid-1234", "name": name, "phone": phone, "classification": status}
    
    # Try fetching existing lead by phone
    response = supabase.table("leads").select("*").eq("phone", phone).execute()
    if response.data:
        lead_id = response.data[0]["id"]
        # Update existing lead
        update_data = {}
        if name: update_data["name"] = name
        if email: update_data["email"] = email
        if course: update_data["course_interest"] = course
        update_data["classification"] = status
        
        up_resp = supabase.table("leads").update(update_data).eq("id", lead_id).execute()
        return up_resp.data[0] if up_resp.data else response.data[0]
    else:
        # Create new lead
        insert_data = {
            "name": name or "Unknown",
            "phone": phone,
            "email": email,
            "course_interest": course,
            "classification": status
        }
        ins_resp = supabase.table("leads").insert(insert_data).execute()
        return ins_resp.data[0] if ins_resp.data else None

def get_lead_by_phone(phone: str):
    """
    Retrieves lead details from Supabase using their phone number.
    """
    if not supabase:
        return None
    response = supabase.table("leads").select("*").eq("phone", phone).execute()
    return response.data[0] if response.data else None

def update_lead_qualification(phone: str, budget_status: str, timeline_urgency: str, course_interest: str, classification: str):
    """
    Updates the qualification status of an existing lead.
    """
    if not supabase:
        print(f"Mock: Updating lead {phone} to status={classification}")
        return
    lead = get_lead_by_phone(phone)
    if lead:
        update_data = {
            "budget_status": budget_status,
            "timeline_urgency": timeline_urgency,
            "course_interest": course_interest,
            "classification": classification
        }
        supabase.table("leads").update(update_data).eq("id", lead["id"]).execute()

def save_call_log(phone: str, direction: str, duration: int, recording_url: str, transcript: str, summary: str):
    """
    Saves a completed call log to Supabase.
    """
    if not supabase:
        print(f"Mock: Saving call log for {phone}: duration={duration}s, transcript={transcript[:50]}...")
        return None
        
    lead = get_lead_by_phone(phone)
    lead_id = lead["id"] if lead else None
    
    call_data = {
        "lead_id": lead_id,
        "direction": direction,
        "duration": duration,
        "recording_url": recording_url,
        "transcript": transcript,
        "summary": summary
    }
    response = supabase.table("calls").insert(call_data).execute()
    return response.data[0] if response.data else None

def insert_document(content: str, metadata: dict, embedding: list):
    """
    Saves a text chunk and its vector embedding into the documents table for RAG.
    """
    if not supabase:
        return
    doc_data = {
        "content": content,
        "metadata": metadata,
        "embedding": embedding
    }
    supabase.table("documents").insert(doc_data).execute()

def match_documents(query_embedding: list, match_threshold: float = 0.5, match_count: int = 3):
    """
    Performs cosine similarity search using match_documents RPC in Supabase.
    """
    if not supabase:
        # Mock responses for tests or when Supabase is unconfigured
        return [
            {
                "content": "Airborne Aviation Academy at Dwarka Dwarka sector 7, Delhi offers DGCA CPL Ground Classes for 2,70,000 (2.7 Lakhs). Airbus A320 Simulator FBS training is 12,000. Captain Navrang Singh is the co-founder and head mentor.",
                "similarity": 0.85
            }
        ]
        
    params = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count
    }
    response = supabase.rpc("match_documents", params).execute()
    return response.data if response.data else []
