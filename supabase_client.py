"""
Supabase / PostgreSQL Client Adapter.
Proxies all database operations directly to database.py (PostgreSQL / Cloud Run Database).
"""
import database

# Export standard database functions from database.py
save_lead = database.save_lead
get_lead_by_phone = database.get_lead_by_phone
update_lead_qualification = database.update_lead_qualification
save_call_log = database.save_call_log
record_call_outcome = database.record_call_outcome
assign_counselor_to_lead = database.assign_counselor_to_lead
schedule_followup = database.schedule_followup
schedule_meeting = database.schedule_meeting
get_available_counselors = database.get_available_counselors
parse_flexible_datetime = database.parse_flexible_datetime
CRM_LEAD_STATUSES = getattr(database, "CRM_LEAD_STATUSES", {})
CRM_LOST_REASONS = getattr(database, "CRM_LOST_REASONS", {})
VALID_LEAD_STATUSES = getattr(database, "VALID_LEAD_STATUSES", CRM_LEAD_STATUSES)
insert_document = database.insert_document
match_documents = database.match_documents
get_conversation_history = database.get_conversation_history
save_conversation_history = database.save_conversation_history
clear_conversation_history = database.clear_conversation_history

def get_supabase_client():
    return database.get_connection()
