import os
import json
import re
from datetime import datetime, timedelta, timezone
import config

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import ThreadedConnectionPool
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    ThreadedConnectionPool = None

# Get PostgreSQL Connection String
DATABASE_URL = os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL", ""))

_pool = None

def get_pool():
    global _pool
    if _pool is None and DATABASE_URL and ThreadedConnectionPool:
        try:
            _pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=DATABASE_URL,
                cursor_factory=RealDictCursor
            )
        except Exception as e:
            print(f"Database Pool Creation Error: {e}")
            _pool = None
    return _pool

class PooledConnectionWrapper:
    """
    Wraps a pooled psycopg2 connection so calling .close() returns the connection
    to the ThreadedConnectionPool instead of tearing down the socket.
    """
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._closed = False

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._pool.putconn(self._conn)
            except Exception:
                pass

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_connection():
    """
    Creates and returns a PostgreSQL connection from the connection pool (with direct fallback).
    """
    if not DATABASE_URL or not psycopg2:
        return None

    pool = get_pool()
    if pool:
        try:
            raw_conn = pool.getconn()
            raw_conn.autocommit = True
            return PooledConnectionWrapper(pool, raw_conn)
        except Exception as e:
            print(f"Database Pool Checkout Error: {e}")

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
                # Safely ensure all columns exist if table was previously created with older schema
                migration_sql = """
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "orgId" UUID;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "courseInterest" VARCHAR(255);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS course_interest VARCHAR(255);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS budget_status VARCHAR(255);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS timeline_urgency VARCHAR(255);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'NEW';
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS classification VARCHAR(50) DEFAULT 'Cold';
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'VOICE_AGENT';
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS city VARCHAR(100);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS state VARCHAR(100);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "customFields" JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "lastActivityAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "nextFollowUp" TIMESTAMP WITH TIME ZONE;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                    ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ACTIVE';
                """
                try:
                    cur.execute(migration_sql)
                except Exception as me:
                    print(f"Database Migration Notice: {me}")
            print("PostgreSQL Database Schema initialized successfully.")
            return True
    except Exception as e:
        print(f"Database Initialization Error: {e}")
    finally:
        conn.close()
    return False

def clean_phone_number(phone: str) -> str:
    """
    Normalizes phone numbers to standard format (with +91 or clean digits).
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+91{digits}"
    elif len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    return f"+{digits}" if not phone.startswith("+") else phone

def get_default_org_id(cur) -> str:
    """
    Retrieves default orgId from organizations table if present.
    """
    try:
        cur.execute('SELECT "id" FROM organizations LIMIT 1;')
        row = cur.fetchone()
        if row:
            return row["id"]
    except Exception:
        pass
    return "340e4b30-22bc-44f2-be56-85b061daaddd"

def get_lead_by_phone(phone: str):
    """
    Retrieves lead details from Cloud SQL CRM leads table (or voice_leads fallback)
    by phone number.
    """
    conn = get_connection()
    if not conn:
        return None

    try:
        cleaned = clean_phone_number(phone)
        raw_digits = re.sub(r"\D", "", phone)
        last10 = raw_digits[-10:] if len(raw_digits) >= 10 else raw_digits

        with conn.cursor() as cur:
            # 1. Search CRM leads table (Prisma schema)
            cur.execute("""
                SELECT id, "orgId", name, phone, email, "courseInterest", status, source, "nextFollowUp", metadata, "customFields", "createdAt", city
                FROM leads
                WHERE phone = %s OR phone = %s OR phone LIKE %s
                LIMIT 1;
            """, (phone, cleaned, f"%{last10}%"))
            row = cur.fetchone()

            if row:
                return {
                    "id": row["id"],
                    "name": row["name"] or "Future Pilot",
                    "phone": row["phone"],
                    "email": row["email"],
                    "course_interest": row["courseInterest"] or "Flight Training",
                    "status": row["status"],
                    "classification": row["status"],
                    "source": row.get("source") or "Website",
                    "city": row.get("city") or "",
                    "org_id": row.get("orgId"),
                    "next_follow_up": row.get("nextFollowUp"),
                    "created_at": row.get("createdAt"),
                    "metadata": row.get("metadata") or {},
                    "custom_fields": row.get("customFields") or {}
                }

            # 2. Fallback to voice_leads table
            try:
                cur.execute("""
                    SELECT id, name, phone, email, course_interest, classification
                    FROM voice_leads
                    WHERE phone = %s OR phone = %s OR phone LIKE %s
                    LIMIT 1;
                """, (phone, cleaned, f"%{last10}%"))
                vrow = cur.fetchone()
                if vrow:
                    return {
                        "id": vrow["id"],
                        "name": vrow["name"] or "Future Pilot",
                        "phone": vrow["phone"],
                        "email": vrow["email"],
                        "course_interest": vrow["course_interest"] or "Flight Training",
                        "status": vrow["classification"],
                        "classification": vrow["classification"],
                        "source": "Voice Call",
                        "city": "",
                        "org_id": None,
                        "next_follow_up": None,
                        "created_at": None,
                        "metadata": {},
                        "custom_fields": {}
                    }
            except Exception:
                pass

            return None
    except Exception as e:
        print(f"DB Error (get_lead_by_phone): {e}")
        return None
    finally:
        conn.close()

def save_lead(
    name: str, 
    phone: str, 
    email: str = None, 
    course: str = None, 
    status: str = "NEW",
    city: str = None,
    source: str = "VOICE_AGENT",
    custom_fields: dict = None,
    notes: str = None
):
    """
    Saves or updates a lead record in the CRM leads table in Cloud SQL with all Add New Lead fields.
    """
    conn = get_connection()
    if not conn:
        print("Mock DB: Saving lead:", name, phone, course, status)
        return {"id": "mock-lead-uuid-1234", "name": name, "phone": phone, "classification": status}

    try:
        cleaned_phone = clean_phone_number(phone)
        custom_fields_json = json.dumps(custom_fields or {})
        with conn.cursor() as cur:
            org_id = get_default_org_id(cur)
            # Check existing lead in CRM leads table
            cur.execute('SELECT id, "courseInterest", status, metadata, "customFields" FROM leads WHERE phone = %s OR phone = %s;', (phone, cleaned_phone))
            existing = cur.fetchone()

            if existing:
                lead_id = existing["id"]
                cur.execute("""
                    UPDATE leads 
                    SET name = COALESCE(%s, name),
                        email = COALESCE(%s, email),
                        city = COALESCE(%s, city),
                        "courseInterest" = COALESCE(%s, "courseInterest"),
                        "customFields" = COALESCE("customFields", '{}'::jsonb) || %s::jsonb,
                        metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                        "lastActivityAt" = CURRENT_TIMESTAMP,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *;
                """, (name, email, city, course, custom_fields_json, custom_fields_json, lead_id))
                updated = cur.fetchone()
                return dict(updated) if updated else dict(existing)
            else:
                cur.execute("""
                    INSERT INTO leads (
                        id, "orgId", name, phone, email, city, "courseInterest", status, source, 
                        "customFields", metadata, "lastActivityAt", "createdAt", "updatedAt"
                    )
                    VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, 
                        %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING *;
                """, (
                    org_id, name or "New Lead", cleaned_phone, email, city, course, 
                    status or "NEW", source or "VOICE_AGENT", custom_fields_json, custom_fields_json
                ))
                inserted = cur.fetchone()
                lead_id = inserted["id"] if inserted else None

                # Log initial note activity if provided
                if lead_id and notes:
                    cur.execute("""
                        INSERT INTO lead_activities (
                            id, "leadId", "orgId", "activityType", title, notes, outcome, "createdAt"
                        ) VALUES (
                            gen_random_uuid(), %s, %s, 'NOTE', 'Initial Lead Intake Note', %s, 'RECORDED', CURRENT_TIMESTAMP
                        );
                    """, (lead_id, org_id, notes))

                return dict(inserted) if inserted else None
    except Exception as e:
        print(f"DB Error (save_lead): {e}")
        return None
    finally:
        conn.close()

def record_call_outcome(
    phone: str,
    outcome: str,
    direction: str = "outbound",
    duration: int = 0,
    recording_url: str = None,
    transcript: str = None,
    summary: str = None,
    callback_time = None,
    course_interest: str = None,
    classification: str = None,
    lead_name: str = None,
    email: str = None,
    city: str = None,
    custom_fields: dict = None,
    user_query: str = None,
    booking_intent: str = None
):
    """
    Core CRM synchronization function.
    Updates the Cloud SQL leads table and logs a structured activity in lead_activities.
    Handles all qualification verification fields and call outcomes:
      - Validates lead (Hot/Warm/Cold)
      - Records age 18+ verification, education institute awareness, Ramphal Chowk campus preference
      - Books a call with admission counsellor or schedules a visit at Ramphal Chowk
    """
    conn = get_connection()
    if not conn:
        print(f"Mock DB: record_call_outcome for {phone} - outcome={outcome}")
        return

    try:
        lead = get_lead_by_phone(phone)
        lead_id = lead["id"] if lead else None
        org_id = lead.get("org_id") if lead else None

        now = datetime.now(timezone.utc)
        next_follow_up = None
        new_status = None
        activity_type = "CALL"
        activity_title = f"AI Voice Call ({direction.title()})"
        activity_notes = summary or ""

        # Check booking intent / outcome
        if booking_intent in ["Campus Visit at Ramphal Chowk", "Campus Visit"]:
            new_status = "INTERESTED"
            activity_type = "MEETING"
            activity_title = "Scheduled Campus Visit - Ramphal Chowk, Dwarka"
        elif booking_intent in ["Counselling Call", "Admissions Call"]:
            new_status = "INTERESTED"
            activity_type = "CALL"
            activity_title = "Scheduled Admission Counsellor Call"

        if outcome in ["NO_ANSWER", "BUSY", "REJECTED", "MISSED", "FAILED"]:
            new_status = "FOLLOW_UP"
            next_follow_up = now + timedelta(hours=2)
            activity_title = f"AI Voice Call - {outcome.replace('_', ' ').title()}"
            activity_notes = f"Caller did not answer / line {outcome.lower()}. Automated follow-up set for 2 hours later."
        elif outcome == "EARLY_HANGUP":
            new_status = "FOLLOW_UP"
            next_follow_up = now + timedelta(hours=4)
            activity_title = "AI Voice Call - Disconnected Early"
            activity_notes = f"Call disconnected shortly after pickup (duration: {duration}s). Follow-up scheduled for 4 hours later."
        elif outcome == "CALLBACK_REQUESTED":
            new_status = "FOLLOW_UP"
            activity_type = "FOLLOW_UP"
            activity_title = "AI Voice Call - Callback Requested"
            if isinstance(callback_time, datetime):
                next_follow_up = callback_time
            elif isinstance(callback_time, str) and callback_time:
                try:
                    next_follow_up = datetime.fromisoformat(callback_time.replace("Z", "+00:00"))
                except Exception:
                    next_follow_up = now + timedelta(hours=24)
            else:
                next_follow_up = now + timedelta(hours=24)
            activity_notes = f"Customer requested a callback at {next_follow_up.strftime('%Y-%m-%d %H:%M UTC')}. {summary or ''}"
        elif outcome in ["CONNECTED", "COMPLETED"]:
            if not new_status:
                if classification in ["Hot", "Warm"]:
                    new_status = "INTERESTED"
                else:
                    new_status = "CONTACTED"
            if not activity_title.startswith("Scheduled"):
                activity_title = f"AI Call Completed - {course_interest or (lead.get('course_interest') if lead else 'Pilot Training')}"
            activity_notes = summary or f"AI qualifying call completed. Classification: {classification}."

        custom_fields_payload = custom_fields or {}
        if user_query:
            custom_fields_payload["user_query"] = user_query
        if booking_intent:
            custom_fields_payload["booking_intent"] = booking_intent
        if classification:
            custom_fields_payload["classification"] = classification
        custom_fields_json = json.dumps(custom_fields_payload)

        with conn.cursor() as cur:
            if not org_id:
                org_id = get_default_org_id(cur)

            # If lead doesn't exist yet in CRM, create one
            if not lead_id:
                cleaned_phone = clean_phone_number(phone)
                cur.execute("""
                    INSERT INTO leads (
                        id, "orgId", name, phone, email, city, "courseInterest", status, 
                        classification, source, "customFields", metadata, "lastActivityAt", 
                        "nextFollowUp", "createdAt", "updatedAt"
                    )
                    VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, 
                        %s, 'VOICE_AGENT', %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP, 
                        %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id;
                """, (
                    org_id, lead_name or "Inbound Caller", cleaned_phone, email, city, 
                    course_interest or "Flight Training", new_status or "NEW",
                    classification or "Cold", custom_fields_json, custom_fields_json, next_follow_up
                ))
                new_row = cur.fetchone()
                lead_id = new_row["id"] if new_row else None
            else:
                # Update existing lead in CRM leads table
                update_fields = [
                    '"lastActivityAt" = CURRENT_TIMESTAMP',
                    '"updatedAt" = CURRENT_TIMESTAMP',
                    '"customFields" = COALESCE("customFields", \'{}\'::jsonb) || %s::jsonb',
                    'metadata = COALESCE(metadata, \'{}\'::jsonb) || %s::jsonb'
                ]
                params = [custom_fields_json, custom_fields_json]

                if lead_name and lead_name not in ["Inbound Caller", "Future Pilot", "New Lead"]:
                    update_fields.append('name = %s')
                    params.append(lead_name)

                if email:
                    update_fields.append('email = %s')
                    params.append(email)

                if city:
                    update_fields.append('city = %s')
                    params.append(city)

                if new_status:
                    update_fields.append('status = %s')
                    params.append(new_status)

                if classification:
                    update_fields.append('classification = %s')
                    params.append(classification)

                if next_follow_up is not None:
                    update_fields.append('"nextFollowUp" = %s')
                    params.append(next_follow_up)

                if course_interest and (not lead or not lead.get("course_interest") or lead.get("course_interest") == "Flight Training"):
                    update_fields.append('"courseInterest" = %s')
                    params.append(course_interest)

                params.append(lead_id)
                query = f'UPDATE leads SET {", ".join(update_fields)} WHERE id = %s;'
                cur.execute(query, tuple(params))

            # Log into CRM lead_activities table
            duration_mins = max(1, duration // 60) if duration > 0 else 0
            activity_metadata = {
                "outcome": outcome,
                "direction": direction,
                "duration_seconds": duration,
                "recording_url": recording_url or "",
                "transcript": transcript or "",
                "classification": classification or "",
                "booking_intent": booking_intent or "",
                "custom_fields": custom_fields_payload
            }

            cur.execute("""
                INSERT INTO lead_activities (
                    id, "leadId", "orgId", "activityType", title, notes, outcome, "dueAt", "completedAt", "durationMins", metadata, "createdAt"
                ) VALUES (
                    gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP
                );
            """, (
                lead_id,
                org_id,
                activity_type,
                activity_title,
                activity_notes,
                outcome,
                next_follow_up,
                now if outcome in ["CONNECTED", "COMPLETED", "EARLY_HANGUP"] else None,
                duration_mins,
                json.dumps(activity_metadata)
            ))

            # Also persist into voice_calls and calls table for backward-compatible call analytics
            for tbl in ["calls", "voice_calls"]:
                try:
                    cur.execute(f"""
                        INSERT INTO {tbl} (lead_id, direction, duration, recording_url, transcript, summary)
                        VALUES (%s, %s, %s, %s, %s, %s);
                    """, (lead_id, direction, duration, recording_url, transcript, summary))
                except Exception as tbl_err:
                    print(f"DB Notice (record_call_outcome): failed to insert into '{tbl}': {tbl_err}")

        print(f"CRM Updated via Cloud SQL: lead={phone}, outcome={outcome}, status={new_status}, followUp={next_follow_up}")
    except Exception as e:
        print(f"DB Error (record_call_outcome): {e}")
    finally:
        conn.close()

def save_call_log(phone: str, direction: str, duration: int, recording_url: str, transcript: str, summary: str):
    """
    Wrapper for save_call_log to call record_call_outcome.
    """
    record_call_outcome(
        phone=phone,
        outcome="CONNECTED",
        direction=direction,
        duration=duration,
        recording_url=recording_url,
        transcript=transcript,
        summary=summary
    )

def update_lead_qualification(phone: str, budget_status: str, timeline_urgency: str, course_interest: str, classification: str):
    """
    Updates lead qualification status in PostgreSQL CRM leads table.
    """
    conn = get_connection()
    if not conn:
        print(f"Mock DB: Updating lead {phone} to classification={classification}")
        return

    try:
        new_status = "INTERESTED" if classification in ["Hot", "Warm"] else "CONTACTED"
        cleaned_phone = clean_phone_number(phone)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE leads 
                SET status = %s,
                    "courseInterest" = COALESCE(%s, "courseInterest"),
                    "lastActivityAt" = CURRENT_TIMESTAMP,
                    "updatedAt" = CURRENT_TIMESTAMP
                WHERE phone = %s OR phone = %s;
            """, (new_status, course_interest, phone, cleaned_phone))
    except Exception as e:
        print(f"DB Error (update_lead_qualification): {e}")
    finally:
        conn.close()

# In-process fallback store, used only when DATABASE_URL is not configured (local dev)
_mock_conversation_sessions = {}

def get_conversation_history(phone: str) -> list:
    """
    Retrieves the in-progress call's conversation history for a phone number.
    Backed by PostgreSQL so state survives across Cloud Run instances.
    """
    conn = get_connection()
    if not conn:
        return _mock_conversation_sessions.get(phone, [])

    try:
        cleaned_phone = clean_phone_number(phone)
        with conn.cursor() as cur:
            cur.execute("SELECT history FROM conversation_sessions WHERE phone = %s OR phone = %s;", (phone, cleaned_phone))
            row = cur.fetchone()
            return row["history"] if row and row["history"] else []
    except Exception as e:
        print(f"DB Error (get_conversation_history): {e}")
        return []
    finally:
        conn.close()

def save_conversation_history(phone: str, history: list, direction: str = None):
    """
    Persists the in-progress call's conversation history for a phone number.
    """
    conn = get_connection()
    if not conn:
        _mock_conversation_sessions[phone] = history
        return

    try:
        cleaned_phone = clean_phone_number(phone)
        history_json = json.dumps(history)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversation_sessions (phone, direction, history, updated_at)
                VALUES (%s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (phone) DO UPDATE
                SET history = EXCLUDED.history,
                    direction = COALESCE(EXCLUDED.direction, conversation_sessions.direction),
                    updated_at = CURRENT_TIMESTAMP;
            """, (cleaned_phone, direction, history_json))
    except Exception as e:
        print(f"DB Error (save_conversation_history): {e}")
    finally:
        conn.close()

def clear_conversation_history(phone: str):
    """
    Clears the conversation session once a call ends and post-call processing starts.
    """
    conn = get_connection()
    if not conn:
        _mock_conversation_sessions.pop(phone, None)
        return

    try:
        cleaned_phone = clean_phone_number(phone)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversation_sessions WHERE phone = %s OR phone = %s;", (phone, cleaned_phone))
    except Exception as e:
        print(f"DB Error (clear_conversation_history): {e}")
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
        return [
            {
                "content": "Airborne Aviation Academy at Dwarka sector 7, Delhi offers DGCA CPL Ground Classes for 2,70,000 (2.7 Lakhs). Airbus A320 Simulator FBS training is 12,000. Captain Navrang Singh is the co-founder and head mentor.",
                "similarity": 0.85
            }
        ]

    try:
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        with conn.cursor() as cur:
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
