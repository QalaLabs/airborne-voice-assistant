from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import telephony
import supabase_client

scheduler = BackgroundScheduler()

def init_scheduler():
    """
    Initializes and starts the background scheduler.
    """
    if not scheduler.running:
        scheduler.start()
        print("Outbound call scheduler started successfully.")

def trigger_call_job(lead_name: str, lead_phone: str):
    """
    Background job that executes after the delay to trigger the outbound SIP call.
    """
    print(f"Executing scheduled call for {lead_name} ({lead_phone})...")
    # Retrieve lead profile from Supabase to check if call is still required
    lead = supabase_client.get_lead_by_phone(lead_phone)
    
    # We can check if they've already called inbound or if call status is resolved.
    # If not resolved, trigger the call.
    if lead and lead.get("classification") != "Resolved":
        success = telephony.make_outbound_call(lead_phone, lead_name)
        if success:
            print(f"Outbound call successfully initiated for {lead_phone}.")
        else:
            print(f"Failed to initiate outbound call for {lead_phone}.")

def schedule_outbound_call(lead_name: str, lead_phone: str, delay_seconds: int = 120):
    """
    Schedules an outbound call task with a specific delay.
    Default delay is 120 seconds (2 minutes).
    """
    run_time = datetime.now() + timedelta(seconds=delay_seconds)
    job_id = f"call_{lead_phone}_{int(datetime.now().timestamp())}"
    
    scheduler.add_job(
        trigger_call_job,
        'date',
        run_date=run_time,
        args=[lead_name, lead_phone],
        id=job_id
    )
    print(f"Scheduled outbound call for {lead_name} ({lead_phone}) at {run_time}.")
    return job_id
