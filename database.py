import os
import json
import config

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

# Get PostgreSQL Connection String
DATABASE_URL = os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL", ""))

def get_connection():
    """
    Creates and returns a new PostgreSQL connection if DATABASE_URL is configured.
    """
    if not DATABASE_URL or not psycopg2:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Database Connection Error: {e}")
        return None

def init_db():
    """
    Initializes PostgreSQL tables and pgvector extension from schema.sql if DATABASE_URL is present.
    """
    conn = get_connection()
    if not conn:
        if not psycopg2:
            print("Notice: 'psycopg2' package not installed in environment. Database operating in mock mode.")
        else:
            print("Notice: DATABASE_URL not configured. Database operating in mock mode.")
        return False
        
    try:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            print("PostgreSQL Database Schema initialized successfully.")
            return True
    except Exception as e:
        print(f"Database Initialization Error: {e}")
    finally:
        conn.close()
    return False

def save_lead(name: str, phone: str, email: str = None, course: str = None, status: str = "Cold"):
    """
    Saves or updates a lead record in PostgreSQL.
    """
    conn = get_connection()
    if not conn:
        print("Mock DB: Saving lead:", name, phone, course, status)
        return {"id": "mock-lead-uuid-1234", "name": name, "phone": phone, "classification": status}

    try:
        with conn.cursor() as cur:
            # Check existing lead
            cur.execute("SELECT * FROM leads WHERE phone = %s;", (phone,))
            existing = cur.fetchone()
            
            if existing:
                lead_id = existing["id"]
                cur.execute("""
                    UPDATE leads 
                    SET name = COALESCE(%s, name),
                        email = COALESCE(%s, email),
                        course_interest = COALESCE(%s, course_interest),
                        classification = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *;
                """, (name, email, course, status, lead_id))
                updated = cur.fetchone()
                return dict(updated) if updated else dict(existing)
            else:
                cur.execute("""
                    INSERT INTO leads (name, phone, email, course_interest, classification)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING *;
                """, (name or "Unknown", phone, email, course, status))
                inserted = cur.fetchone()
                return dict(inserted) if inserted else None
    except Exception as e:
        print(f"DB Error (save_lead): {e}")
        return None
    finally:
        conn.close()

def get_lead_by_phone(phone: str):
    """
    Retrieves lead details from PostgreSQL by phone number.
    """
    conn = get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM leads WHERE phone = %s;", (phone,))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"DB Error (get_lead_by_phone): {e}")
        return None
    finally:
        conn.close()

def update_lead_qualification(phone: str, budget_status: str, timeline_urgency: str, course_interest: str, classification: str):
    """
    Updates lead qualification status in PostgreSQL.
    """
    conn = get_connection()
    if not conn:
        print(f"Mock DB: Updating lead {phone} to classification={classification}")
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE leads 
                SET budget_status = %s,
                    timeline_urgency = %s,
                    course_interest = %s,
                    classification = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE phone = %s;
            """, (budget_status, timeline_urgency, course_interest, classification, phone))
    except Exception as e:
        print(f"DB Error (update_lead_qualification): {e}")
    finally:
        conn.close()

def save_call_log(phone: str, direction: str, duration: int, recording_url: str, transcript: str, summary: str):
    """
    Saves call log metadata and transcript into PostgreSQL calls table.
    """
    conn = get_connection()
    if not conn:
        print(f"Mock DB: Saving call log for {phone}: duration={duration}s")
        return None

    try:
        lead = get_lead_by_phone(phone)
        lead_id = lead["id"] if lead else None

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO calls (lead_id, direction, duration, recording_url, transcript, summary)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *;
            """, (lead_id, direction, duration, recording_url, transcript, summary))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"DB Error (save_call_log): {e}")
        return None
    finally:
        conn.close()

def insert_document(content: str, metadata: dict, embedding: list):
    """
    Inserts a text chunk and vector embedding into PostgreSQL documents table for RAG.
    """
    conn = get_connection()
    if not conn:
        return

    try:
        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        metadata_json = json.dumps(metadata or {})
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documents (content, metadata, embedding)
                VALUES (%s, %s::jsonb, %s::vector);
            """, (content, metadata_json, vector_str))
    except Exception as e:
        print(f"DB Error (insert_document): {e}")
    finally:
        conn.close()

def match_documents(query_embedding: list, match_threshold: float = 0.5, match_count: int = 3):
    """
    Queries vector similarity from PostgreSQL documents table using pgvector <=> operator or match_documents RPC.
    """
    conn = get_connection()
    if not conn:
        # Mock knowledge response for fallback when DB is unconfigured
        return [
            {
                "content": "Airborne Aviation Academy at Dwarka sector 7, Delhi offers DGCA CPL Ground Classes for 2,70,000 (2.7 Lakhs). Airbus A320 Simulator FBS training is 12,000. Captain Navrang Singh is the co-founder and head mentor.",
                "similarity": 0.85
            }
        ]

    try:
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        with conn.cursor() as cur:
            # Execute match_documents PL/pgSQL function or direct pgvector distance query
            cur.execute("""
                SELECT id, content, metadata, 1 - (embedding <=> %s::vector) AS similarity
                FROM documents
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (vector_str, vector_str, match_threshold, vector_str, match_count))
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"DB Error (match_documents): {e}")
        return []
    finally:
        conn.close()
