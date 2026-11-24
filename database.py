import os
import json
import re
import uuid
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

import time

_pool = None
_db_circuit_open_until = 0.0
DB_CIRCUIT_BREAKER_SECS = 60.0

def _is_circuit_open() -> bool:
    return time.time() < _db_circuit_open_until

def _trip_circuit(reason: str):
    global _db_circuit_open_until, _pool
    _pool = None
    _db_circuit_open_until = time.time() + DB_CIRCUIT_BREAKER_SECS
    print(f"Database Notice: Circuit breaker open for {int(DB_CIRCUIT_BREAKER_SECS)}s ({reason}). Operating in zero-latency fallback mode.")

def _format_dsn(url: str, timeout_secs: int = 2) -> str:
    if not url:
        return ""
    if "connect_timeout=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}connect_timeout={timeout_secs}"

def get_pool():
    global _pool
    if os.environ.get("TESTING", "").lower() in ("true", "1") or os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return None
    if _is_circuit_open():
        return None
    if _pool is None and DATABASE_URL and ThreadedConnectionPool:
        try:
            dsn = _format_dsn(DATABASE_URL, timeout_secs=2)
            _pool = ThreadedConnectionPool(
                minconn=2,
                maxconn=30,
                dsn=dsn,
                cursor_factory=RealDictCursor
            )
        except Exception as e:
            _trip_circuit(f"Pool init failed: {e}")
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
    Guarded by a zero-latency circuit breaker to avoid hanging event loops on unreachable DBs.
    """
    if os.environ.get("TESTING", "").lower() in ("true", "1") or os.environ.get("PYTEST_CURRENT_TEST") is not None:
        return None
    if not DATABASE_URL or not psycopg2 or _is_circuit_open():
        return None

    pool = get_pool()
    if pool:
        try:
            raw_conn = pool.getconn()
            raw_conn.autocommit = True
            return PooledConnectionWrapper(pool, raw_conn)
        except Exception as e:
            print(f"Database Pool Checkout Error: {e}")

    if _is_circuit_open():
        return None

    try:
        dsn = _format_dsn(DATABASE_URL, timeout_secs=2)
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception as e:
        # Only trip circuit if the pool was also unavailable (prevent transient checkout spikes from killing pool)
        if pool is None:
            _trip_circuit(f"Direct connection failed: {e}")
        else:
            print(f"Database Direct Fallback Failed (pool preserved): {e}")
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
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "latestCallStatus" VARCHAR(50);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "latestCallOutcome" VARCHAR(50);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "lastCallAt" TIMESTAMP WITH TIME ZONE;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "lastCallDuration" INTEGER;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "callAttemptCount" INTEGER DEFAULT 0;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "nextCallAt" TIMESTAMP WITH TIME ZONE;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "doNotCall" BOOLEAN DEFAULT false;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "lastCallSummary" TEXT;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "telecmiConversationId" VARCHAR(255);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "autoCallingEnabled" BOOLEAN DEFAULT true;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "assignedTo" UUID;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS "lostReason" VARCHAR(100);
                    ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS "performedBy" UUID;
                    ALTER TABLE lead_activities ADD COLUMN IF NOT EXISTS "nextAction" TEXT;
                    ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ACTIVE';
                    CREATE TABLE IF NOT EXISTS users (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        "orgId" UUID,
                        name VARCHAR(255) NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        phone VARCHAR(20),
                        role VARCHAR(50) DEFAULT 'ADMISSIONS_COUNSELOR',
                        "isActive" BOOLEAN DEFAULT true,
                        "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    DO $$ BEGIN ALTER TYPE "LeadSource" ADD VALUE IF NOT EXISTS 'VOICE_AGENT'; EXCEPTION WHEN undefined_object THEN NULL; END $$;

                    -- Agent critique, quality metrics, and continuous learning tables
                    CREATE TABLE IF NOT EXISTS agent_eval_metrics (
                        id SERIAL PRIMARY KEY,
                        call_id VARCHAR(255) UNIQUE,
                        customer_phone VARCHAR(50),
                        direction VARCHAR(20),
                        caller_sentiment_score FLOAT,
                        friction_detected BOOLEAN,
                        friction_type VARCHAR(100),
                        factual_accuracy_score FLOAT,
                        compliance_passed BOOLEAN,
                        total_turns INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS agent_issues (
                        id SERIAL PRIMARY KEY,
                        call_id VARCHAR(255),
                        customer_phone VARCHAR(50),
                        direction VARCHAR(20),
                        mistake_category VARCHAR(100),
                        severity VARCHAR(50),
                        turn_index INTEGER,
                        caller_utterance TEXT,
                        agent_response TEXT,
                        critic_reasoning TEXT,
                        suggested_correction TEXT,
                        proposed_negative_constraint TEXT,
                        status VARCHAR(50) DEFAULT 'PENDING_REVIEW',
                        reviewer_notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS agent_lessons (
                        id SERIAL PRIMARY KEY,
                        source_issue_id INTEGER REFERENCES agent_issues(id) ON DELETE SET NULL,
                        topic_tag VARCHAR(100),
                        rule_instruction TEXT,
                        negative_constraint TEXT,
                        priority_score INTEGER DEFAULT 5,
                        is_active BOOLEAN DEFAULT TRUE,
                        verified_by VARCHAR(100) DEFAULT 'PENDING_REVIEW',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );

                    -- Fix legacy voice_calls constraint if referencing obsolete voice_leads
                    DO $$ BEGIN
                        IF EXISTS (
                            SELECT 1 FROM information_schema.table_constraints 
                            WHERE constraint_name = 'voice_calls_lead_id_fkey'
                        ) THEN
                            ALTER TABLE voice_calls DROP CONSTRAINT voice_calls_lead_id_fkey;
                        END IF;
                    EXCEPTION WHEN OTHERS THEN NULL;
                    END $$;
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
                SELECT *
                FROM leads
                WHERE phone = %s OR phone = %s OR phone LIKE %s
                LIMIT 1;
            """, (phone, cleaned, f"%{last10}%"))
            row = cur.fetchone()

            if row:
                return {
                    "id": row.get("id"),
                    "name": row.get("name") or "Future Pilot",
                    "phone": row.get("phone"),
                    "email": row.get("email"),
                    "course_interest": row.get("courseInterest") or row.get("course_interest") or "Flight Training",
                    "status": row.get("status"),
                    "classification": row.get("classification") or row.get("status"),
                    "source": row.get("source") or "Website",
                    "city": row.get("city") or "",
                    "org_id": row.get("orgId"),
                    "assigned_to": row.get("assignedTo"),
                    "lost_reason": row.get("lostReason"),
                    "next_follow_up": row.get("nextFollowUp"),
                    "created_at": row.get("createdAt") or row.get("created_at"),
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

    VALID_LEAD_STATUSES = {
        'NEW', 'CONTACTED', 'INTERESTED', 'FOLLOW_UP', 'COUNSELED', 'APPLICATION_SUBMITTED', 
        'CONVERTED', 'LOST', 'CONNECTED', 'CALL_BACK', 'PROSPECT', 'WON', 'NOT_CONNECTED', 
        'RINGING', 'NOT_REACHABLE', 'SWITCHED_OFF', 'VOICEMAIL', 'INCOMING_BARD', 
        'OUT_OF_SERVICE', 'NOT_AWARE', 'NOT_CONTACTABLE', 'LOCATION_OUT_OF_SCOPE', 
        'LANGUAGE_BARRIER', 'PRICE_HIGH', 'JOINED_OTHERS', 'NOT_ELIGIBLE', 'INVALID_NUMBER', 
        'TEST_LEAD', 'NOT_INTERESTED', 'REASON_NOT_SHARED', 'JOB_SEEKER'
    }
    VALID_LEAD_SOURCES = {
        'HOMEPAGE_CTA', 'COURSE_PAGE', 'CONTACT_FORM', 'CALLBACK_REQUEST', 
        'BROCHURE_DOWNLOAD', 'GOOGLE_ADS', 'FACEBOOK_ADS', 'ORGANIC', 'REFERRAL', 
        'WHATSAPP', 'DIRECT', 'VOICE_AGENT'
    }

    clean_status = (status or "NEW").upper()
    if clean_status not in VALID_LEAD_STATUSES:
        clean_status = "NEW"

    clean_source = (source or "DIRECT").upper()
    if clean_source not in VALID_LEAD_SOURCES:
        if "VOICE" in clean_source or "CALL" in clean_source:
            clean_source = "VOICE_AGENT"
        elif "FACEBOOK" in clean_source:
            clean_source = "FACEBOOK_ADS"
        elif "GOOGLE" in clean_source:
            clean_source = "GOOGLE_ADS"
        elif "WHATSAPP" in clean_source:
            clean_source = "WHATSAPP"
        else:
            clean_source = "DIRECT"

    try:
        cleaned_phone = clean_phone_number(phone)
        raw_digits = re.sub(r"\D", "", phone or "")
        last10 = raw_digits[-10:] if len(raw_digits) >= 10 else (raw_digits or "0000000000")
        custom_fields_json = json.dumps(custom_fields or {})
        with conn.cursor() as cur:
            org_id = get_default_org_id(cur)
            # Check existing lead in CRM leads table matching exact phone or last 10 digits
            cur.execute("""
                SELECT id, "courseInterest", status, metadata, "customFields" 
                FROM leads 
                WHERE phone = %s 
                   OR phone = %s 
                   OR ("right"(regexp_replace(phone::text, '\\D'::text, ''::text, 'g'::text), 10) = %s)
                ORDER BY "updatedAt" DESC
                LIMIT 1;
            """, (phone, cleaned_phone, last10))
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
                try:
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
                        clean_status, clean_source, custom_fields_json, custom_fields_json
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
                except Exception as insert_err:
                    # Gracefully handle unique constraint conflict (idx_leads_unique_org_last10)
                    err_msg = str(insert_err).lower()
                    if "unique constraint" in err_msg or "duplicate key" in err_msg or "idx_leads" in err_msg:
                        cur.execute("""
                            SELECT id, "courseInterest", status, metadata, "customFields" 
                            FROM leads 
                            WHERE phone = %s 
                               OR phone = %s 
                               OR ("right"(regexp_replace(phone::text, '\\D'::text, ''::text, 'g'::text), 10) = %s)
                            ORDER BY "updatedAt" DESC
                            LIMIT 1;
                        """, (phone, cleaned_phone, last10))
                        conflict_row = cur.fetchone()
                        if conflict_row:
                            lead_id = conflict_row["id"]
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
                            return dict(updated) if updated else dict(conflict_row)
                    raise insert_err
    except Exception as e:
        print(f"DB Error (save_lead): {e}")
        return None
    finally:
        conn.close()

CRM_LEAD_STATUSES = {
    "NEW": "Newly created lead in CRM, not yet engaged in a qualifying conversation.",
    "CONTACTED": "Spoke to lead, initial conversation conducted, but neutral, exploring, or undecided.",
    "INTERESTED": "Lead showed positive interest in courses, ground classes, simulator, or requested syllabus/details.",
    "FOLLOW_UP": "Callback requested at a specific date/time, caller busy, or line was unanswered/busy.",
    "COUNSELED": "Full in-depth counseling delivered during the call regarding courses, eligibility, NIOS, medicals, and flying syllabus.",
    "APPLICATION_SUBMITTED": "Lead confirmed registration for webinar seat or submitted academy application.",
    "CONVERTED": "Enrolled student (fees paid / batch confirmed).",
    "LOST": "Disqualified, dropped out, or not viable for training."
}

CRM_LOST_REASONS = {
    "NOT_ELIGIBLE": "Underage (<17), non-PCM unwilling to do NIOS, or medically disqualified.",
    "PRICE_HIGH": "Tuition / flying cost beyond candidate's budget.",
    "LOCATION_OUT_OF_SCOPE": "Unable to attend Dwarka Ramphal Chowk campus or relocate.",
    "JOB_SEEKER": "Seeking immediate job/employment rather than aviation education/training.",
    "NOT_INTERESTED": "Explicitly confirmed they are no longer interested in aviation.",
    "INVALID_NUMBER": "Wrong number, invalid contact, or junk lead.",
    "LANGUAGE_BARRIER": "Unable to communicate despite language adaptation (unsupported language). Note: Speaking in Hindi/Hinglish is accommodated in caller's preferred language."
}

VALID_LEAD_STATUSES = {
    'NEW', 'CONTACTED', 'INTERESTED', 'FOLLOW_UP', 'COUNSELED', 'APPLICATION_SUBMITTED', 
    'CONVERTED', 'LOST', 'CONNECTED', 'CALL_BACK', 'PROSPECT', 'WON', 'NOT_CONNECTED', 
    'RINGING', 'NOT_REACHABLE', 'SWITCHED_OFF', 'VOICEMAIL', 'INCOMING_BARD', 
    'OUT_OF_SERVICE', 'NOT_AWARE', 'NOT_CONTACTABLE', 'LOCATION_OUT_OF_SCOPE', 
    'LANGUAGE_BARRIER', 'PRICE_HIGH', 'JOINED_OTHERS', 'NOT_ELIGIBLE', 'INVALID_NUMBER', 
    'TEST_LEAD', 'NOT_INTERESTED', 'REASON_NOT_SHARED', 'JOB_SEEKER'
}

DEFAULT_COUNSELORS = [
    {
        "id": "340e4b30-22bc-44f2-be56-85b061daadd1",
        "name": "Senior Admissions Counselor",
        "email": "admissions@airborneaviation.in",
        "role": "ADMISSIONS_COUNSELOR"
    },
    {
        "id": "340e4b30-22bc-44f2-be56-85b061daadd2",
        "name": "Capt. Navrang Singh (Chief Mentor)",
        "email": "navrang@airborneaviation.in",
        "role": "ADMISSIONS_COUNSELOR"
    }
]

def _ensure_uuid(val: str) -> str:
    """Safely converts string to a valid UUID string (or deterministic namespace UUID5)."""
    if not val:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(val)))

def parse_flexible_datetime(val, base_dt=None):
    """
    Parses datetime objects, ISO strings, or human natural language phrases like
    'Tomorrow 3 PM', 'Saturday 11 AM', 'in 2 hours', 'after 3 days' into a timezone-aware UTC datetime.
    """
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if not isinstance(val, str):
        return None
    text = val.strip()
    try:
        clean_iso = text.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean_iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass

    base = base_dt or datetime.now(timezone.utc)
    lower = text.lower()

    # Relative hours or days
    m_hours = re.search(r'(?:in|after)\s+(\d+)\s+hour', lower)
    if m_hours:
        return base + timedelta(hours=int(m_hours.group(1)))
    m_days = re.search(r'(?:in|after)\s+(\d+)\s+day', lower)
    if m_days:
        return base + timedelta(days=int(m_days.group(1)))

    days_ahead = 0
    if 'tomorrow' in lower:
        days_ahead = 1
    elif 'day after tomorrow' in lower:
        days_ahead = 2
    else:
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for i, w in enumerate(weekdays):
            if w in lower:
                current_w = base.weekday()
                days_ahead = (i - current_w) % 7
                if days_ahead == 0:
                    days_ahead = 7
                break

    target_date = (base + timedelta(days=days_ahead)).date()

    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', lower)
    hour = 11
    minute = 0
    if time_match:
        h = int(time_match.group(1))
        m = int(time_match.group(2)) if time_match.group(2) else 0
        meridiem = time_match.group(3)
        if meridiem == 'pm' and h < 12:
            h += 12
        elif meridiem == 'am' and h == 12:
            h = 0
        elif not meridiem and h < 8:
            h += 12
        hour = h
        minute = m

    ist_offset = timezone(timedelta(hours=5, minutes=30))
    dt_ist = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=ist_offset)
    return dt_ist.astimezone(timezone.utc)

def get_available_counselors(org_id: str = None) -> list:
    """
    Fetches active admissions counselors from the users table.
    Falls back to system counselors if DB is offline or table is empty.
    """
    conn = get_connection()
    if not conn:
        return DEFAULT_COUNSELORS

    try:
        with conn.cursor() as cur:
            cur.execute('''
                SELECT id, name, email, role 
                FROM users 
                WHERE role IN ('ADMISSIONS_COUNSELOR', 'ADMIN', 'SUPER_ADMIN')
                  AND "isActive" = true
                ORDER BY "createdAt" ASC;
            ''')
            rows = cur.fetchall()
            if rows:
                return [
                    {
                        "id": str(row["id"]),
                        "name": row["name"],
                        "email": row["email"],
                        "role": row["role"]
                    }
                    for row in rows
                ]
    except Exception as e:
        print(f"Notice: get_available_counselors fallback ({e})")
    finally:
        conn.close()

    return DEFAULT_COUNSELORS

def assign_counselor_to_lead(
    phone_or_lead_id: str,
    counselor_id: str = None,
    counselor_name: str = None,
    reason: str = None,
    org_id: str = None
) -> dict:
    """
    Assigns an admissions counselor to a lead in the CRM leads table.
    Updates leads."assignedTo" and logs an 'ASSIGNMENT' activity in lead_activities.
    """
    counselors = get_available_counselors(org_id)
    selected_c = None
    if counselor_id:
        selected_c = next((c for c in counselors if str(c["id"]) == str(counselor_id)), None)
    if not selected_c and counselor_name:
        selected_c = next((c for c in counselors if counselor_name.lower() in c["name"].lower()), None)
    if not selected_c:
        selected_c = counselors[0] if counselors else DEFAULT_COUNSELORS[0]

    assigned_uuid = _ensure_uuid(selected_c["id"])
    c_name = selected_c["name"]
    res_payload = {
        "counselor_id": assigned_uuid,
        "counselor_name": c_name,
        "reason": reason or "Lead qualified for 1-on-1 counselor guidance",
        "status": "ASSIGNED"
    }

    conn = get_connection()
    if not conn:
        print(f"Mock DB: Assigned counselor {c_name} ({assigned_uuid}) to {phone_or_lead_id}")
        res_payload["phone_or_id"] = phone_or_lead_id
        return res_payload

    try:
        with conn.cursor() as cur:
            if not org_id:
                org_id = get_default_org_id(cur)
            cur.execute('SELECT id, phone, name FROM leads WHERE phone = %s OR id::text = %s LIMIT 1;', (phone_or_lead_id, phone_or_lead_id))
            lead = cur.fetchone()
            if lead:
                lead_id = lead["id"]
                cur.execute('''
                    UPDATE leads 
                    SET "assignedTo" = %s,
                        "customFields" = COALESCE("customFields", '{}'::jsonb) || %s::jsonb,
                        "lastActivityAt" = CURRENT_TIMESTAMP,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = %s;
                ''', (
                    assigned_uuid,
                    json.dumps({"assigned_counselor": c_name, "counselor_id": assigned_uuid, "assigned_reason": reason}),
                    lead_id
                ))
                cur.execute('''
                    INSERT INTO lead_activities (
                        id, "leadId", "orgId", "performedBy", "activityType", title, notes, outcome, "completedAt", metadata, "createdAt"
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, 'ASSIGNMENT', %s, %s, 'ASSIGNED', CURRENT_TIMESTAMP, %s::jsonb, CURRENT_TIMESTAMP
                    );
                ''', (
                    lead_id,
                    org_id,
                    assigned_uuid,
                    f"Counselor Assigned: {c_name}",
                    reason or "Assigned dedicated admissions counselor based on call qualification.",
                    json.dumps(res_payload)
                ))
                print(f"CRM: Lead {lead_id} ({lead['phone']}) assigned to counselor {c_name}")
                res_payload["lead_id"] = str(lead_id)
    except Exception as e:
        print(f"DB Error (assign_counselor_to_lead): {e}")
    finally:
        conn.close()

    return res_payload

def schedule_followup(
    phone_or_lead_id: str,
    followup_time,
    notes: str = None,
    reason: str = "CALLBACK_REQUESTED",
    org_id: str = None
) -> dict:
    """
    Schedules an automated or counselor follow-up task in the CRM.
    Updates leads.status to 'FOLLOW_UP', updates 'nextFollowUp', and logs activity.
    """
    now = datetime.now(timezone.utc)
    target_dt = parse_flexible_datetime(followup_time, base_dt=now) or (now + timedelta(hours=24))

    res_payload = {
        "status": "FOLLOW_UP",
        "next_follow_up": target_dt.isoformat(),
        "notes": notes or f"Follow-up callback scheduled for {target_dt.strftime('%Y-%m-%d %H:%M UTC')}",
        "reason": reason
    }

    conn = get_connection()
    if not conn:
        print(f"Mock DB: Scheduled follow-up for {phone_or_lead_id} at {target_dt.isoformat()}")
        res_payload["phone_or_id"] = phone_or_lead_id
        return res_payload

    try:
        with conn.cursor() as cur:
            if not org_id:
                org_id = get_default_org_id(cur)
            cur.execute('SELECT id, phone, name FROM leads WHERE phone = %s OR id::text = %s LIMIT 1;', (phone_or_lead_id, phone_or_lead_id))
            lead = cur.fetchone()
            if lead:
                lead_id = lead["id"]
                cur.execute('''
                    UPDATE leads 
                    SET status = 'FOLLOW_UP',
                        "nextFollowUp" = %s,
                        "nextCallAt" = %s,
                        "lastActivityAt" = CURRENT_TIMESTAMP,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = %s;
                ''', (target_dt, target_dt, lead_id))

                cur.execute('''
                    INSERT INTO lead_activities (
                        id, "leadId", "orgId", "activityType", title, notes, outcome, "dueAt", metadata, "createdAt"
                    ) VALUES (
                        gen_random_uuid(), %s, %s, 'FOLLOW_UP', %s, %s, 'SCHEDULED', %s, %s::jsonb, CURRENT_TIMESTAMP
                    );
                ''', (
                    lead_id,
                    org_id,
                    f"Scheduled Follow-up: {reason}",
                    res_payload["notes"],
                    target_dt,
                    json.dumps(res_payload)
                ))
                print(f"CRM: Follow-up scheduled for lead {lead_id} at {target_dt}")
                res_payload["lead_id"] = str(lead_id)
    except Exception as e:
        print(f"DB Error (schedule_followup): {e}")
    finally:
        conn.close()

    return res_payload

def schedule_meeting(
    phone_or_lead_id: str,
    meeting_time,
    meeting_type: str = "CAMPUS_VISIT",
    notes: str = None,
    counselor_id: str = None,
    counselor_name: str = None,
    org_id: str = None
) -> dict:
    """
    Schedules an in-person campus visit or formal counselling meeting at Dwarka campus.
    Updates lead status to 'INTERESTED', assigns host counselor, and logs 'MEETING' activity.
    """
    now = datetime.now(timezone.utc)
    target_dt = parse_flexible_datetime(meeting_time, base_dt=now) or (now + timedelta(days=1))
    location = "Airborne Aviation Academy, E-549, 2nd Floor, Ramphal Chowk Road, Sector 7, Dwarka, New Delhi 110075" if meeting_type == "CAMPUS_VISIT" else "Online Meeting / WhatsApp Video"

    res_payload = {
        "status": "INTERESTED",
        "meeting_type": meeting_type,
        "meeting_time": target_dt.isoformat(),
        "next_follow_up": target_dt.isoformat(),
        "location": location,
        "notes": notes or f"Campus visit & A320 simulator demo at Ramphal Chowk, Dwarka scheduled for {target_dt.strftime('%Y-%m-%d %H:%M UTC')}"
    }

    conn = get_connection()
    if not conn:
        print(f"Mock DB: Scheduled meeting ({meeting_type}) for {phone_or_lead_id} at {target_dt.isoformat()}")
        res_payload["phone_or_id"] = phone_or_lead_id
        return res_payload

    try:
        with conn.cursor() as cur:
            if not org_id:
                org_id = get_default_org_id(cur)
            cur.execute('SELECT id, phone, name FROM leads WHERE phone = %s OR id::text = %s LIMIT 1;', (phone_or_lead_id, phone_or_lead_id))
            lead = cur.fetchone()
            if lead:
                lead_id = lead["id"]
                counselors = get_available_counselors(org_id)
                assigned_c = counselors[0] if counselors else DEFAULT_COUNSELORS[0]
                assigned_uuid = _ensure_uuid(assigned_c["id"])

                cur.execute('''
                    UPDATE leads 
                    SET status = 'INTERESTED',
                        classification = 'Hot',
                        "assignedTo" = COALESCE("assignedTo", %s),
                        "nextFollowUp" = %s,
                        "customFields" = COALESCE("customFields", '{}'::jsonb) || %s::jsonb,
                        "lastActivityAt" = CURRENT_TIMESTAMP,
                        "updatedAt" = CURRENT_TIMESTAMP
                    WHERE id = %s;
                ''', (
                    assigned_uuid,
                    target_dt,
                    json.dumps({"meeting_time": target_dt.isoformat(), "meeting_type": meeting_type, "location": location}),
                    lead_id
                ))

                cur.execute('''
                    INSERT INTO lead_activities (
                        id, "leadId", "orgId", "performedBy", "activityType", title, notes, outcome, "dueAt", metadata, "createdAt"
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, 'MEETING', %s, %s, 'CONFIRMED', %s, %s::jsonb, CURRENT_TIMESTAMP
                    );
                ''', (
                    lead_id,
                    org_id,
                    assigned_uuid,
                    f"Campus Visit & Simulator Session - Ramphal Chowk, Dwarka",
                    res_payload["notes"],
                    target_dt,
                    json.dumps(res_payload)
                ))
                print(f"CRM: Meeting scheduled for lead {lead_id} at {target_dt}")
                res_payload["lead_id"] = str(lead_id)
                res_payload["counselor_name"] = assigned_c["name"]
    except Exception as e:
        print(f"DB Error (schedule_meeting): {e}")
    finally:
        conn.close()

    return res_payload

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
    booking_intent: str = None,
    provider_call_id: str = None,
    crm_status: str = None,
    lost_reason: str = None,
    assign_counselor: bool = False,
    counselor_id: str = None,
    counselor_name: str = None,
    counselor_reason: str = None,
    followup_time = None,
    followup_notes: str = None,
    meeting_time = None,
    meeting_type: str = None,
    meeting_notes: str = None
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

        # Determine priority CRM Status if explicitly classified
        if crm_status and crm_status.upper() in VALID_LEAD_STATUSES:
            new_status = crm_status.upper()

        # Handle Lost status and specific lost reasons
        if new_status == "LOST" or lost_reason:
            if not new_status:
                new_status = "LOST"
            clean_reason = (lost_reason or "NOT_INTERESTED").upper()
            activity_title = f"AI Call - Lost / Disqualified ({clean_reason})"
            activity_notes = f"Disqualified/Lost reason: {clean_reason}. {summary or ''}"

        # Check booking intent / meeting scheduling
        parsed_meeting = parse_flexible_datetime(meeting_time or (custom_fields.get("scheduled_time") if custom_fields else None))
        if meeting_time or booking_intent in ["Campus Visit at Ramphal Chowk", "Campus Visit"]:
            if new_status != "LOST":
                new_status = "INTERESTED"
            activity_type = "MEETING"
            activity_title = "Scheduled Campus Visit - Ramphal Chowk, Dwarka"
            if parsed_meeting:
                next_follow_up = parsed_meeting
        elif booking_intent in ["Counselling Call", "Admissions Call"]:
            if new_status != "LOST":
                new_status = "INTERESTED"
            activity_type = "CALL"
            activity_title = "Scheduled Admission Counsellor Call"

        # Check follow-up scheduling
        parsed_followup = parse_flexible_datetime(followup_time or callback_time)
        if parsed_followup:
            next_follow_up = parsed_followup
            if activity_type != "MEETING" and new_status != "LOST":
                new_status = "FOLLOW_UP"
                activity_type = "FOLLOW_UP"
                activity_title = "AI Voice Call - Follow-up Scheduled"
                activity_notes = f"Follow-up scheduled for {parsed_followup.strftime('%Y-%m-%d %H:%M UTC')}. {followup_notes or summary or ''}"

        if outcome in ["NO_ANSWER", "BUSY", "REJECTED", "MISSED", "FAILED"]:
            if not new_status or new_status in ["NEW", "CONTACTED"]:
                new_status = "FOLLOW_UP"
            next_follow_up = next_follow_up or (now + timedelta(hours=2))
            activity_title = f"AI Voice Call - {outcome.replace('_', ' ').title()}"
            activity_notes = f"Caller did not answer / line {outcome.lower()}. Automated follow-up set for 2 hours later."
        elif outcome == "EARLY_HANGUP":
            if not new_status or new_status in ["NEW", "CONTACTED"]:
                new_status = "FOLLOW_UP"
            next_follow_up = next_follow_up or (now + timedelta(hours=4))
            activity_title = "AI Voice Call - Disconnected Early"
            activity_notes = f"Call disconnected shortly after pickup (duration: {duration}s). Follow-up scheduled for 4 hours later."
        elif outcome == "CALLBACK_REQUESTED":
            if not new_status or new_status in ["NEW", "CONTACTED"]:
                new_status = "FOLLOW_UP"
            if activity_type != "MEETING":
                activity_type = "FOLLOW_UP"
                activity_title = "AI Voice Call - Callback Requested"
            next_follow_up = next_follow_up or (now + timedelta(hours=24))
            activity_notes = f"Customer requested a callback at {next_follow_up.strftime('%Y-%m-%d %H:%M UTC')}. {summary or ''}"
        elif outcome in ["CONNECTED", "COMPLETED"]:
            if not new_status:
                if classification in ["Hot", "Warm"]:
                    new_status = "INTERESTED"
                else:
                    new_status = "CONTACTED"
            if not activity_title.startswith("Scheduled") and new_status != "LOST":
                activity_title = f"AI Call Completed - {course_interest or (lead.get('course_interest') if lead else 'Pilot Training')}"
            if new_status != "LOST":
                activity_notes = summary or f"AI qualifying call completed. Status: {new_status}, Classification: {classification}."

        # Counselor assignment lookup
        assigned_counselor_uuid = None
        if assign_counselor or new_status in ["INTERESTED", "COUNSELED"] or meeting_time or booking_intent in ["Campus Visit at Ramphal Chowk", "Campus Visit", "Counselling Call"]:
            counselors = get_available_counselors(org_id)
            selected_c = None
            if counselor_id:
                selected_c = next((c for c in counselors if str(c.get("id")) == str(counselor_id)), None)
            if not selected_c and counselor_name:
                selected_c = next((c for c in counselors if counselor_name.lower() in c.get("name", "").lower()), None)
            if not selected_c:
                selected_c = counselors[0] if counselors else DEFAULT_COUNSELORS[0]
            assigned_counselor_uuid = _ensure_uuid(selected_c["id"])
            counselor_name = counselor_name or selected_c["name"]

        custom_fields_payload = custom_fields or {}
        if user_query:
            custom_fields_payload["user_query"] = user_query
        if booking_intent:
            custom_fields_payload["booking_intent"] = booking_intent
        if classification:
            custom_fields_payload["classification"] = classification
        if new_status:
            custom_fields_payload["crm_status"] = new_status
        if lost_reason:
            custom_fields_payload["lost_reason"] = lost_reason
        if counselor_name:
            custom_fields_payload["assigned_counselor"] = counselor_name
        if next_follow_up:
            custom_fields_payload["scheduled_time"] = next_follow_up.isoformat()
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
                        classification, source, "assignedTo", "lostReason", "customFields", metadata, "lastActivityAt", 
                        "nextFollowUp", "createdAt", "updatedAt"
                    )
                    VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, 
                        %s, 'VOICE_AGENT', %s, %s, %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP, 
                        %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id;
                """, (
                    org_id, lead_name or "Inbound Caller", cleaned_phone, email, city, 
                    course_interest or "Flight Training", new_status or "NEW",
                    classification or "Cold", assigned_counselor_uuid, lost_reason,
                    custom_fields_json, custom_fields_json, next_follow_up
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

                if lost_reason:
                    update_fields.append('"lostReason" = %s')
                    params.append(lost_reason)

                if assigned_counselor_uuid:
                    update_fields.append('"assignedTo" = %s')
                    params.append(assigned_counselor_uuid)

                if classification:
                    update_fields.append('classification = %s')
                    params.append(classification)

                if next_follow_up is not None:
                    update_fields.append('"nextFollowUp" = %s')
                    params.append(next_follow_up)

                if course_interest and (not lead or not lead.get("course_interest") or lead.get("course_interest") == "Flight Training"):
                    update_fields.append('"courseInterest" = %s')
                    params.append(course_interest)

                # Update call tracking fields on lead
                completed_outcomes = {
                    "CONNECTED", "COMPLETED", "COUNSELLING_SCHEDULED", "QUALIFIED",
                    "INTERESTED", "NOT_INTERESTED", "CALLBACK_REQUESTED", "VOICEMAIL"
                }
                failed_outcomes = {
                    "FAILED", "NO_ANSWER", "BUSY", "MISSED", "REJECTED",
                    "STALLED_CARRIER_OR_DND", "FALLBACK_FAILED", "CANCELLED", "UNAVAILABLE"
                }
                if outcome in completed_outcomes or (duration and duration > 0):
                    call_stat = "COMPLETED"
                elif outcome in failed_outcomes:
                    call_stat = "FAILED"
                else:
                    call_stat = outcome

                update_fields.append('"latestCallStatus" = %s')
                params.append(call_stat)
                update_fields.append('"latestCallOutcome" = %s')
                params.append(outcome)
                update_fields.append('"lastCallAt" = CURRENT_TIMESTAMP')
                if duration > 0:
                    update_fields.append('"lastCallDuration" = %s')
                    params.append(duration)
                if summary:
                    update_fields.append('"lastCallSummary" = %s')
                    params.append(summary)
                if provider_call_id:
                    update_fields.append('"telecmiConversationId" = %s')
                    params.append(provider_call_id)
                if direction == "outbound":
                    update_fields.append('"callAttemptCount" = COALESCE("callAttemptCount", 0) + 1')
                if next_follow_up is not None:
                    update_fields.append('"nextCallAt" = %s')
                    params.append(next_follow_up)

                params.append(lead_id)
                query = f'UPDATE leads SET {", ".join(update_fields)} WHERE id = %s;'
                cur.execute(query, tuple(params))

            # Log / update into CRM lead_activities table
            duration_mins = max(1, duration // 60) if duration > 0 else 0
            activity_metadata = {
                "outcome": outcome,
                "direction": direction,
                "duration_seconds": duration,
                "recording_url": recording_url or "",
                "recordingUrl": recording_url or "",
                "record_url": recording_url or "",
                "gcs_recording_url": recording_url or "",
                "transcript": transcript or "",
                "classification": classification or "",
                "booking_intent": booking_intent or "",
                "provider_call_id": provider_call_id or "",
                "custom_fields": custom_fields_payload
            }

            # Check if an in-progress or initiated activity exists for this lead to update
            existing_act_id = None
            if lead_id:
                try:
                    cur.execute("""
                        SELECT id FROM lead_activities
                        WHERE "leadId" = %s
                          AND "activityType" = 'CALL'
                          AND "completedAt" IS NULL
                          AND outcome IN ('INITIATED', 'IN_PROGRESS', 'QUEUED', 'RINGING', 'DISPATCHED')
                        ORDER BY "createdAt" DESC
                        LIMIT 1;
                    """, (lead_id,))
                    act_row = cur.fetchone()
                    if act_row:
                        existing_act_id = act_row["id"]
                except Exception as act_check_err:
                    print(f"DB Notice (lead_activities check): {act_check_err}")

            if existing_act_id:
                cur.execute("""
                    UPDATE lead_activities SET
                        outcome = %s,
                        title = %s,
                        notes = %s,
                        "dueAt" = %s,
                        "completedAt" = %s,
                        "durationMins" = %s,
                        metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                    WHERE id = %s;
                """, (
                    outcome,
                    activity_title,
                    activity_notes,
                    next_follow_up,
                    now if outcome not in ["INITIATED", "IN_PROGRESS", "RINGING", "DISPATCHED", "QUEUED"] else None,
                    duration_mins,
                    json.dumps(activity_metadata),
                    existing_act_id
                ))
            else:
                cur.execute("""
                    INSERT INTO lead_activities (
                        id, "leadId", "orgId", "performedBy", "activityType", title, notes, outcome, "dueAt", "completedAt", "durationMins", metadata, "createdAt"
                    ) VALUES (
                        gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP
                    );
                """, (
                    lead_id,
                    org_id,
                    assigned_counselor_uuid,
                    activity_type,
                    activity_title,
                    activity_notes,
                    outcome,
                    next_follow_up,
                    now if outcome not in ["INITIATED", "IN_PROGRESS", "RINGING", "DISPATCHED", "QUEUED"] else None,
                    duration_mins,
                    json.dumps(activity_metadata)
                ))

            # If counselor assigned and distinct activity desired
            if lead_id and assigned_counselor_uuid and (assign_counselor or new_status in ["INTERESTED", "COUNSELED"]):
                try:
                    cur.execute("""
                        INSERT INTO lead_activities (
                            id, "leadId", "orgId", "performedBy", "activityType", title, notes, outcome, "completedAt", metadata, "createdAt"
                        ) VALUES (
                            gen_random_uuid(), %s, %s, %s, 'ASSIGNMENT', %s, %s, 'ASSIGNED', CURRENT_TIMESTAMP, %s::jsonb, CURRENT_TIMESTAMP
                        );
                    """, (
                        lead_id,
                        org_id,
                        assigned_counselor_uuid,
                        f"Counselor Assigned: {counselor_name}",
                        counselor_reason or "Assigned dedicated admissions counselor based on lead call response.",
                        json.dumps({"counselor_id": assigned_counselor_uuid, "counselor_name": counselor_name})
                    ))
                except Exception as assign_act_err:
                    print(f"DB Notice (assignment activity log): {assign_act_err}")

            # If a distinct follow-up callback was requested during the call
            if lead_id and followup_time and activity_type != "FOLLOW_UP":
                try:
                    cur.execute("""
                        INSERT INTO lead_activities (
                            id, "leadId", "orgId", "performedBy", "activityType", title, notes, outcome, "dueAt", metadata, "createdAt"
                        ) VALUES (
                            gen_random_uuid(), %s, %s, %s, 'FOLLOW_UP', %s, %s, 'SCHEDULED', %s, %s::jsonb, CURRENT_TIMESTAMP
                        );
                    """, (
                        lead_id,
                        org_id,
                        assigned_counselor_uuid,
                        "Scheduled Follow-up Call",
                        followup_notes or f"Follow-up callback requested for {next_follow_up.strftime('%Y-%m-%d %H:%M UTC') if next_follow_up else 'later'}",
                        next_follow_up,
                        json.dumps({"followup_time": str(next_follow_up), "followup_notes": followup_notes})
                    ))
                except Exception as fu_act_err:
                    print(f"DB Notice (followup activity log): {fu_act_err}")

            # Update calling_jobs table if it exists
            if lead_id or provider_call_id:
                try:
                    if outcome in completed_outcomes or (duration and duration > 0):
                        final_job_status = "COMPLETED"
                    elif outcome in failed_outcomes:
                        final_job_status = "FAILED"
                    else:
                        final_job_status = "COMPLETED" if (duration and duration > 0) else "FAILED"

                    cur.execute("""
                        UPDATE calling_jobs SET
                            status = %s::"CallingJobStatus",
                            "callOutcome" = COALESCE(%s, "callOutcome"),
                            "callCompletedAt" = CURRENT_TIMESTAMP,
                            "durationSecs" = %s,
                            "recordingUrl" = COALESCE(%s, "recordingUrl"),
                            transcript = COALESCE(%s, transcript),
                            summary = COALESCE(%s, summary),
                            "updatedAt" = CURRENT_TIMESTAMP
                        WHERE ("providerCallId" = %s AND %s IS NOT NULL)
                           OR ("leadId" = %s AND status IN ('PROCESSING', 'INITIATED', 'RINGING', 'ANSWERED', 'QUEUED'));
                    """, (final_job_status, outcome, duration, recording_url, transcript, summary, provider_call_id, provider_call_id, lead_id))
                except Exception as cj_err:
                    print(f"DB Notice (calling_jobs update): {cj_err}")

            # Also persist into voice_calls and calls table for backward-compatible call analytics
            for tbl in ["calls", "voice_calls"]:
                try:
                    cur.execute(f"""
                        INSERT INTO {tbl} (lead_id, direction, duration, recording_url, transcript, summary)
                        VALUES (%s, %s, %s, %s, %s, %s);
                    """, (lead_id, direction, duration, recording_url, transcript, summary))
                except Exception as tbl_err:
                    # If foreign key fails on legacy voice_leads, fallback to inserting with lead_id = None
                    try:
                        cur.execute(f"""
                            INSERT INTO {tbl} (lead_id, direction, duration, recording_url, transcript, summary)
                            VALUES (NULL, %s, %s, %s, %s, %s);
                        """, (direction, duration, recording_url, transcript, summary))
                    except Exception:
                        pass
                    print(f"DB Notice (record_call_outcome): fallback used for '{tbl}': {tbl_err}")

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
