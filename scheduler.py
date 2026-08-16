from datetime import datetime, timedelta
import telephony
import supabase_client

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
except ImportError:
    scheduler = None

def init_scheduler():
    """
    Initializes and starts the background scheduler.
    """
    if scheduler and not scheduler.running:
        scheduler.start()
        print("Outbound call scheduler started successfully.")
    elif not scheduler:
        print("Notice: 'apscheduler' package not installed. Outbound scheduler operating in mock mode.")

def trigger_call_job(lead_name: str, lead_phone: str):
    """
    Background job that executes after the delay to trigger the outbound SIP call.
    """
    print(f"Executing scheduled call for {lead_name} ({lead_phone})...")
    lead = supabase_client.get_lead_by_phone(lead_phone)
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
    
    if scheduler:
        scheduler.add_job(
            trigger_call_job,
            'date',
            run_date=run_time,
            args=[lead_name, lead_phone],
            id=job_id
        )
    print(f"Scheduled outbound call for {lead_name} ({lead_phone}) at {run_time}.")
    return job_id
