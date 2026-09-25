from fastapi import FastAPI, Request, Form, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
import uvicorn
import os

import config
import database
import scheduler
import supabase_client
from assistant import handle_conversation, get_greeting_voice_url, run_post_call_pipeline

app = FastAPI(title="Airborne Aviation AI Voice Assistant")

# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
def startup_event():
    """
    Starts background services and initializes PostgreSQL database schema on startup.
    """
    database.init_db()
    scheduler.init_scheduler()

@app.post("/webhooks/new-lead")
async def new_lead_webhook(request: Request):
    """
    Webhook triggered when a new lead is submitted on the website or WhatsApp.
    Ingests the lead into Supabase and schedules an outbound call.
    """
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form_data = await request.form()
            data = dict(form_data)
            
        name = data.get("name") or data.get("Name") or "New Lead"
        phone = data.get("phone") or data.get("Phone") or data.get("mobile")
        email = data.get("email") or data.get("Email")
        course = data.get("course") or data.get("Course")
        
        if not phone:
            return {"status": "error", "message": "Phone number is required."}
            
        # Ingest lead into Supabase
        lead = supabase_client.save_lead(name, phone, email, course, status="Cold")
        
        # Schedule outbound call within 2 minutes (120 seconds)
        scheduler.schedule_outbound_call(name, phone, delay_seconds=120)
        
        return {
            "status": "success",
            "message": "Lead registered and outbound call scheduled.",
            "lead_id": lead.get("id") if lead else None
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/answer-call", response_class=PlainTextResponse)
async def answer_call(
    From: str = Form(None), 
    phone: str = Query(None), 
    direction: str = Query("inbound")
):
    """
    Twilio SIP / Voice entrypoint for inbound and outbound calls.
    Directs the call into the AI processing loop.
    """
    # Determine the caller's phone number
    caller_phone = phone or From or ""
    
    # Check if caller is a known lead in Cloud SQL
    lead_name = "Future Pilot"
    course_interest = "Flight Training"
    if caller_phone:
        lead = supabase_client.get_lead_by_phone(caller_phone)
        if lead:
            lead_name = lead.get("name") or "Future Pilot"
            course_interest = lead.get("course_interest") or "Flight Training"
        elif direction == "inbound":
            # Automatically ingest new inbound caller as a lead
            supabase_client.save_lead(name="Inbound Lead", phone=caller_phone, course="Flight Training", status="NEW")

    # Generate custom billing/greeting audio URL using ElevenLabs or neural voice
    if direction == "outbound":
        greeting_text = f"Hello {lead_name}! I am Modassir from Airborne Aviation Academy. I noticed your interest in our {course_interest} program. How can I help you regarding your flight training today?"
    else:
        greeting_text = f"Welcome to Airborne Aviation Academy Dwarka. I am your AI pilot advisor. How can I help you regarding our flight programs today?"
        
    greeting_url = get_greeting_voice_url(greeting_text)
    
    # Twilio Voice Response
    resp = VoiceResponse()
    resp.play(greeting_url)
    
    # Record caller input and route back to process-recording
    action_url = f"/process-recording?phone={caller_phone}&direction={direction}"
    resp.record(
        action=action_url,
        method="POST",
        max_length=15,
        play_beep=True,
        timeout=3
    )
    return str(resp)

@app.post("/process-recording", response_class=PlainTextResponse)
def process_recording(
    background_tasks: BackgroundTasks,
    RecordingUrl: str = Form(...),
    phone: str = Query(None),
    direction: str = Query("inbound")
):
    """
    Process caller recording, query RAG, generate reply using LLM, and loop.
    """
    caller_phone = phone or ""
    
    # Process speech using Whisper/LLM/TTS
    audio_url, should_hang_up = handle_conversation(RecordingUrl, caller_phone, direction)
    
    resp = VoiceResponse()
    resp.play(audio_url)
    
    if should_hang_up:
        resp.hangup()
        # Schedule post-call processing in a background task
        background_tasks.add_task(run_post_call_pipeline, caller_phone, direction, RecordingUrl)
    else:
        # Continue loop: redirect back to /answer-call to record next input
        redirect_url = f"/answer-call?phone={caller_phone}&direction={direction}"
        resp.redirect(redirect_url)
        
    return str(resp)

# ==========================================
# TeleCMI Voice API & SIP Trunk Endpoints
# ==========================================

@app.api_route("/telecmi/answer", methods=["GET", "POST"])
async def telecmi_answer(request: Request):
    """
    TeleCMI PIOPIY Answer URL Webhook.
    Called when an inbound call arrives on TeleCMI or an outbound call is answered.
    Returns PCMO (PIOPIY Call Management Object) JSON instructions.
    """
    try:
        # Extract parameters from query params, json, or form data
        query_params = dict(request.query_params)
        body_data = {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body_data = await request.json()
            except Exception:
                pass
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                body_data = dict(form)
            except Exception:
                pass

        data = {**query_params, **body_data}
        print(f"TeleCMI Answer Webhook Received: {data}")

        caller_phone = (
            data.get("phone") or 
            data.get("from") or 
            data.get("From") or 
            data.get("caller_id") or 
            ""
        )
        direction = data.get("direction", "inbound")

        # Format caller phone
        if caller_phone and not str(caller_phone).startswith("+"):
            caller_phone = "+" + str(caller_phone)

        # Check lead in Cloud SQL CRM
        lead_name = "Future Pilot"
        course_interest = "Flight Training"
        if caller_phone:
            lead = supabase_client.get_lead_by_phone(caller_phone)
            if lead:
                lead_name = lead.get("name") or "Future Pilot"
                course_interest = lead.get("course_interest") or "Flight Training"
            elif direction == "inbound":
                supabase_client.save_lead(name="TeleCMI Inbound Lead", phone=caller_phone, course="Flight Training", status="NEW")

        # Generate custom greeting audio
        if direction == "outbound":
            greeting_text = f"Hello {lead_name}! I am Modassir from Airborne Aviation Academy. I noticed your interest in our {course_interest} program. How can I help you regarding your flight training today?"
        else:
            greeting_text = f"Welcome to Airborne Aviation Academy Dwarka. I am your AI pilot advisor. How can I help you regarding our flight programs today?"

        greeting_url = get_greeting_voice_url(greeting_text)

        # PCMO response for TeleCMI / PIOPIY: play greeting and record user input
        action_url = f"{config.NGROK_URL}/telecmi/process-recording?phone={caller_phone}&direction={direction}"
        pcmo_response = [
            {
                "action": "play",
                "file_name": greeting_url
            },
            {
                "action": "record",
                "action_url": action_url,
                "max_length": 15,
                "timeout": 3
            }
        ]
        return pcmo_response
    except Exception as e:
        print(f"TeleCMI Answer Error: {e}")
        return [{"action": "play", "file_name": get_greeting_voice_url("Welcome to Airborne Aviation Academy.")}]

@app.api_route("/telecmi/process-recording", methods=["GET", "POST"])
async def telecmi_process_recording(request: Request, background_tasks: BackgroundTasks):
    """
    Process caller recording from TeleCMI / PIOPIY, query RAG/LLM/TTS, and return next PCMO action.
    """
    try:
        query_params = dict(request.query_params)
        body_data = {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body_data = await request.json()
            except Exception:
                pass
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                body_data = dict(form)
            except Exception:
                pass

        data = {**query_params, **body_data}
        caller_phone = str(data.get("phone") or data.get("from") or data.get("From") or "")
        direction = data.get("direction", "inbound")
        recording_url = (
            data.get("record_url") or 
            data.get("recording_url") or 
            data.get("file_url") or 
            ""
        )

        import anyio
        audio_url, should_hang_up = await anyio.to_thread.run_sync(
            handle_conversation, recording_url, caller_phone, direction
        )

        if should_hang_up:
            background_tasks.add_task(run_post_call_pipeline, caller_phone, direction, recording_url)
            return [
                {"action": "play", "file_name": audio_url},
                {"action": "hangup"}
            ]
        else:
            action_url = f"{config.NGROK_URL}/telecmi/process-recording?phone={caller_phone}&direction={direction}"
            return [
                {"action": "play", "file_name": audio_url},
                {
                    "action": "record",
                    "action_url": action_url,
                    "max_length": 15,
                    "timeout": 3
                }
            ]
    except Exception as e:
        print(f"TeleCMI Process Recording Error: {e}")
        return [
            {"action": "play", "file_name": get_greeting_voice_url("Thank you for calling Airborne Aviation Academy.")},
            {"action": "hangup"}
        ]

@app.api_route("/telecmi/events", methods=["GET", "POST"])
@app.api_route("/telecmi/debug", methods=["GET", "POST"])
async def telecmi_events(request: Request, background_tasks: BackgroundTasks):
    """
    TeleCMI Debug / Event URL Webhook.
    Receives real-time call lifecycle events (ringing, answered, hangup, CDR).
    Triggers post-call processing on call completion.
    """
    try:
        query_params = dict(request.query_params)
        body_data = {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body_data = await request.json()
            except Exception:
                pass
        elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            try:
                form = await request.form()
                body_data = dict(form)
            except Exception:
                pass

        data = {**query_params, **body_data}
        print(f"[TeleCMI Debug / Event Log]: {data}")

        status = (data.get("status") or data.get("event") or "").lower()
        caller_phone = str(data.get("from") or data.get("phone") or data.get("to") or "")
        direction = data.get("direction", "inbound")
        recording_url = data.get("record_url") or data.get("recording_url") or data.get("file_url") or ""
        duration = int(data.get("duration") or data.get("billsec") or 0)

        if caller_phone and not caller_phone.startswith("+"):
            caller_phone = "+" + caller_phone

        # 1. Unanswered, Busy, or Rejected calls -> Schedule 2-hour CRM follow-up in Cloud SQL
        if status in ["missed", "no-answer", "no_answer", "busy", "rejected", "failed", "cancelled", "unavailable"] and caller_phone:
            outcome = "BUSY" if status == "busy" else "NO_ANSWER"
            background_tasks.add_task(
                database.record_call_outcome,
                phone=caller_phone,
                outcome=outcome,
                direction=direction,
                duration=duration,
                recording_url=""
            )
        # 2. Early hangup (answered, but disconnected under 8 seconds) -> Schedule 4-hour CRM follow-up
        elif status in ["completed", "hangup", "end", "terminated"] and 0 < duration <= 8 and caller_phone:
            background_tasks.add_task(
                database.record_call_outcome,
                phone=caller_phone,
                outcome="EARLY_HANGUP",
                direction=direction,
                duration=duration,
                recording_url=recording_url
            )
        # 3. Conversed call completed -> Execute full AI qualification, GCS archiving, and CRM sync
        elif status in ["completed", "hangup", "end", "terminated"] and caller_phone:
            background_tasks.add_task(run_post_call_pipeline, caller_phone, direction, recording_url)

        return {"status": "success", "event_received": True, "event_type": status or "logged"}
    except Exception as e:
        print(f"TeleCMI Event Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

