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
insert_document = database.insert_document
match_documents = database.match_documents

def get_supabase_client():
    return database.get_connection()
