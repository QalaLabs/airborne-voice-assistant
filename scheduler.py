from datetime import datetime, timedelta, timezone
import telephony
import supabase_client

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
except ImportError:
    scheduler = None

IST = timezone(timedelta(hours=5, minutes=30))
CALL_WINDOW_START_HOUR = 9    # no automated calls before 09:00 IST
CALL_WINDOW_END_HOUR = 20     # none at or after 20:00 IST

# Lead statuses that must never be auto-dialled again.
DO_NOT_CALL_STATUSES = {
    "NOT_INTERESTED", "INVALID_NUMBER", "NOT_ELIGIBLE", "OUT_OF_SERVICE",
    "CONVERTED", "WON", "LOST", "JOINED_OTHERS", "TEST_LEAD", "JOB_SEEKER",
    "LANGUAGE_BARRIER", "LOCATION_OUT_OF_SCOPE", "DND", "RESOLVED",
}

def init_scheduler():
    """
    Initializes and starts the background scheduler.
    """
    if scheduler and not scheduler.running:
        scheduler.start()
        print("Outbound call scheduler started successfully.")
    elif not scheduler:
        print("Notice: 'apscheduler' package not installed. Outbound scheduler operating in mock mode.")

def is_callable_lead(lead) -> bool:
    """A lead may be auto-dialled only if it exists and is not in a do-not-call status."""
    if not lead:
        return False
    for key in ("status", "classification"):
        if str(lead.get(key) or "").strip().upper() in DO_NOT_CALL_STATUSES:
            return False
    return True

def in_call_window(now: datetime = None) -> bool:
    """True when `now` (default: current time) falls inside the permitted IST calling hours."""
    now = (now or datetime.now(IST)).astimezone(IST)
    return CALL_WINDOW_START_HOUR <= now.hour < CALL_WINDOW_END_HOUR

def next_window_open(now: datetime = None) -> datetime:
    """Next moment the calling window opens (09:00 IST), used to defer out-of-hours jobs."""
    now = (now or datetime.now(IST)).astimezone(IST)
    opens = now.replace(hour=CALL_WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    if now >= opens:
        opens += timedelta(days=1)
    return opens

def trigger_call_job(lead_name: str, lead_phone: str):
    """
    Background job that executes after the delay to trigger the outbound call.
    Skips leads that opted out / are invalid and defers calls outside 09:00-20:00 IST.
    """
    print(f"Executing scheduled call for {lead_name} ({lead_phone})...")
    lead = supabase_client.get_lead_by_phone(lead_phone)
    if lead is None:
        # Lead not in CRM yet (e.g. DB unavailable): allow the call, there is no opt-out to honour.
        lead = {}
    elif not is_callable_lead(lead):
        print(f"Skipping call to {lead_phone}: lead status is do-not-call ({lead.get('status')}).")
        return

    if not in_call_window():
        reopen = next_window_open()
        if scheduler:
            scheduler.add_job(
                trigger_call_job, 'date', run_date=reopen,
                args=[lead_name, lead_phone],
                id=f"call_{lead_phone}_{int(reopen.timestamp())}",
                replace_existing=True,
            )
        print(f"Outside calling hours: deferred call to {lead_phone} until {reopen.isoformat()}.")
        return

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
    else:
        print(f"Notice: APScheduler not active. Mock schedule outbound call for {lead_name} ({lead_phone}) at {run_time}.")
    return job_id
