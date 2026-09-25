from fastapi import FastAPI, Request, Form, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
import uvicorn
import os

import config
import database
import rag
import scheduler
import supabase_client
from assistant import handle_conversation, get_greeting_voice_url, run_post_call_pipeline

app = FastAPI(title="Airborne Aviation AI Voice Assistant")

# Ensure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_base_url(request: Request) -> str:
    """
    Dynamically resolves the public base URL from reverse-proxy headers (Cloud Run),
    falling back to config.NGROK_URL or default production domain.
    """
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        return f"{proto}://{host}".rstrip("/")
    if config.NGROK_URL:
        return config.NGROK_URL.rstrip("/")
    return "https://airborne-voice-assistant-368523757732.asia-south1.run.app"

WELCOME_MUSIC_URL = "https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/airborne_welcome_connecting.mp3"

def format_lead_date(dt) -> str:
    """Formats a datetime or timestamp into natural date string like '27th October'."""
    if not dt:
        return "recently"
    if isinstance(dt, str):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return "recently"
    try:
        day = dt.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} {dt.strftime('%B')}"
    except Exception:
        return "recently"

@app.on_event("startup")
def startup_event():
    """
    Starts background services and initializes PostgreSQL database schema on startup.
    """
    database.init_db()
    scheduler.init_scheduler()

@app.get("/")
async def root_status(request: Request):
    """
    Public health & service status endpoint.
    Serves interactive HTML dashboard for browser requests, or JSON for API monitors.
    """
    base_url = get_base_url(request)
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse({
            "service": "Airborne Aviation AI Voice Assistant",
            "version": "1.0.0",
            "status": "healthy",
            "base_url": base_url,
            "endpoints": {
                "docs": f"{base_url}/docs",
                "telecmi_answer": f"{base_url}/telecmi/answer",
                "telecmi_process_recording": f"{base_url}/telecmi/process-recording",
                "telecmi_events": f"{base_url}/telecmi/events",
                "webhooks_new_lead": f"{base_url}/webhooks/new-lead",
                "twilio_answer_call": f"{base_url}/answer-call"
            }
        })

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Airborne Aviation AI Voice Assistant</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #090e17;
            color: #f1f5f9;
            margin: 0;
            padding: 40px 16px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .card {{
            background: #111827;
            border-radius: 16px;
            padding: 36px;
            max-width: 680px;
            width: 100%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            border: 1px solid #1f2937;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
            font-size: 12px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 9999px;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .dot {{ width: 8px; height: 8px; background: #10b981; border-radius: 50%; box-shadow: 0 0 8px #10b981; }}
        h1 {{ margin: 0 0 10px 0; font-size: 26px; color: #ffffff; letter-spacing: -0.02em; }}
        p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; margin: 0 0 28px 0; }}
        .endpoints {{ background: #0b1120; border-radius: 10px; padding: 18px; border: 1px solid #1e293b; }}
        .item {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #1e293b; gap: 12px; }}
        .item:last-child {{ border-bottom: none; }}
        .label {{ font-size: 13px; color: #cbd5e1; font-weight: 500; min-width: 170px; }}
        a.link {{ color: #38bdf8; text-decoration: none; font-size: 13px; font-family: monospace; word-break: break-all; }}
        a.link:hover {{ text-decoration: underline; }}
        .actions {{ margin-top: 24px; display: flex; gap: 12px; }}
        .btn {{
            background: #2563eb;
            color: #fff;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            text-decoration: none;
            display: inline-block;
            transition: background 0.15s;
        }}
        .btn:hover {{ background: #1d4ed8; text-decoration: none; }}
        .btn-subtle {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155; }}
        .btn-subtle:hover {{ background: #334155; color: #fff; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge"><div class="dot"></div> System Operational & Ready</div>
        <h1>Airborne Aviation AI Voice Agent</h1>
        <p>Telephony gateway, RAG knowledge engine, and automated CRM pipeline deployed on Google Cloud Run for Airborne Aviation Academy, Dwarka, Delhi.</p>
        <div class="endpoints">
            <div class="item"><span class="label">Swagger API Docs:</span> <a class="link" href="{base_url}/docs" target="_blank">{base_url}/docs</a></div>
            <div class="item"><span class="label">TeleCMI Inbound Answer:</span> <a class="link" href="{base_url}/telecmi/answer" target="_blank">{base_url}/telecmi/answer</a></div>
            <div class="item"><span class="label">TeleCMI Events / CDR:</span> <a class="link" href="{base_url}/telecmi/events" target="_blank">{base_url}/telecmi/events</a></div>
            <div class="item"><span class="label">New Lead Intake:</span> <a class="link" href="{base_url}/webhooks/new-lead" target="_blank">{base_url}/webhooks/new-lead</a></div>
            <div class="item"><span class="label">Twilio Voice Entry:</span> <a class="link" href="{base_url}/answer-call" target="_blank">{base_url}/answer-call</a></div>
        </div>
        <div class="actions">
            <a class="btn" href="{base_url}/docs" target="_blank">Open Swagger UI →</a>
            <a class="btn btn-subtle" href="https://www.airborneaviation.in" target="_blank">Visit Academy Website</a>
        </div>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@app.post("/internal/rag/query")
async def internal_rag_query(request: Request):
    """
    Internal-only knowledge lookup endpoint, called by the ADK agent's
    search_knowledge tool (agent/rag_client.py) when the conversational core
    is deployed on Vertex AI Agent Engine (config.USE_AGENT_ENGINE / the
    per-phone rollout allowlist). Thin wrapper around rag.query_rag() so RAG
    logic and its pgvector/Cloud SQL connection stay canonical in Cloud Run.

    Auth: requires header 'X-Internal-Secret' matching config.INTERNAL_RAG_SHARED_SECRET.
    If that secret is unset, the endpoint refuses all requests (fails closed)
    rather than silently running unauthenticated.
    """
    if not config.INTERNAL_RAG_SHARED_SECRET:
        return JSONResponse({"error": "internal RAG endpoint not configured"}, status_code=503)

    provided_secret = request.headers.get("x-internal-secret", "")
    if provided_secret != config.INTERNAL_RAG_SHARED_SECRET:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        data = {}

    query = (data.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "missing 'query'"}, status_code=400)

    limit = int(data.get("limit", 3))
    context = rag.query_rag(query, limit=limit)
    return JSONResponse({"context": context})

@app.get("/webhooks/new-lead")
async def get_new_lead_webhook_info():
    """
    Informational endpoint for the new lead ingestion webhook.
    """
    return {
        "status": "ready",
        "method": "POST",
        "description": "Send new leads via JSON or application/x-www-form-urlencoded POST request.",
        "expected_payload": {
            "name": "Candidate Name (optional, defaults to 'New Lead')",
            "phone": "Candidate phone with country code (e.g. +919953777320) [Required]",
            "email": "Candidate email (optional)",
            "course": "Program of interest (e.g. 'CPL', 'A320 Simulator', 'Cabin Crew') [Optional]"
        }
    }

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
    lead_date = "recently"
    lead_source = "our website"
    if caller_phone:
        lead = supabase_client.get_lead_by_phone(caller_phone)
        if lead:
            lead_name = lead.get("name") or "Future Pilot"
            course_interest = lead.get("course_interest") or "Flight Training"
            lead_date = format_lead_date(lead.get("created_at"))
            lead_source = (lead.get("source") or "our website").replace("_", " ").title()
        elif direction == "inbound":
            # Automatically ingest new inbound caller as a lead
            supabase_client.save_lead(name="Inbound Lead", phone=caller_phone, course="Flight Training", status="NEW")

    # Generate custom greeting audio URL
    if direction == "outbound":
        greeting_text = f"Hi {lead_name}, you filled a lead on {lead_date} on {lead_source} showcasing your interest in {course_interest}. I am Capt. Modassir from Airborne Aviation Academy Dwarka. How can I help you regarding your pilot training today?"
    else:
        greeting_text = "Hello, I am Capt. Modassir, admissions advisor and pilot mentor at Airborne Aviation Academy Dwarka. May I know your good name, and which course or query are you calling about today?"
        
    greeting_url = get_greeting_voice_url(greeting_text)
    
    # Persist opening greeting into conversation session
    if caller_phone:
        supabase_client.save_conversation_history(
            caller_phone,
            [{"role": "assistant", "content": greeting_text}],
            direction
        )
    
    # Twilio Voice Response: play hold music first on inbound, then agent greeting
    resp = VoiceResponse()
    if direction == "inbound":
        resp.play(WELCOME_MUSIC_URL)
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
        # Continue loop: record caller's next input directly without repeating opening greeting
        action_url = f"/process-recording?phone={caller_phone}&direction={direction}"
        resp.record(
            action=action_url,
            method="POST",
            max_length=15,
            play_beep=False,
            timeout=3
        )
        
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

        base_url = get_base_url(request)

        raw_phone = (
            data.get("phone") or 
            data.get("from") or 
            data.get("From") or 
            data.get("caller") or
            data.get("caller_id") or 
            data.get("cuser") or
            data.get("customer_number") or
            data.get("call_from") or
            data.get("cli") or
            data.get("user") or
            ""
        )
        caller_phone = str(raw_phone).strip()

        # Format caller phone with +91 if Indian 10-digit number
        if caller_phone and not caller_phone.startswith("+"):
            if caller_phone.isdigit() and len(caller_phone) == 10:
                caller_phone = "+91" + caller_phone
            elif caller_phone.isdigit():
                caller_phone = "+" + caller_phone

        # Safe fallback for direct browser / curl tests
        if not caller_phone:
            caller_phone = "guest"

        direction = data.get("direction", "inbound")

        # Check lead in Cloud SQL CRM
        lead_name = "Future Pilot"
        course_interest = "Flight Training"
        lead_date = "recently"
        lead_source = "our website"
        if caller_phone and caller_phone != "guest":
            lead = supabase_client.get_lead_by_phone(caller_phone)
            if lead:
                lead_name = lead.get("name") or "Future Pilot"
                course_interest = lead.get("course_interest") or "Flight Training"
                lead_date = format_lead_date(lead.get("created_at"))
                lead_source = (lead.get("source") or "our website").replace("_", " ").title()
            elif direction == "inbound":
                supabase_client.save_lead(name="TeleCMI Inbound Lead", phone=caller_phone, course="Flight Training", status="NEW")

        # Generate custom greeting audio
        if direction == "outbound":
            greeting_text = f"Hi {lead_name}, you filled a lead on {lead_date} on {lead_source} showcasing your interest in {course_interest}. I am Capt. Modassir from Airborne Aviation Academy Dwarka. How can I help you regarding your pilot training today?"
        else:
            greeting_text = "Hello, I am Capt. Modassir, admissions advisor and pilot mentor at Airborne Aviation Academy Dwarka. May I know your good name, and which course or query are you calling about today?"

        greeting_url = get_greeting_voice_url(greeting_text)

        # Persist opening greeting into conversation session for TeleCMI
        if caller_phone and caller_phone != "guest":
            supabase_client.save_conversation_history(
                caller_phone,
                [{"role": "assistant", "content": greeting_text}],
                direction
            )

        # PCMO response for TeleCMI / PIOPIY:
        # Inbound: plays hold music & announcement first ("Welcome to Airborne Aviation..."), then agent intro, then records.
        # Outbound: plays personalized lead greeting, then records.
        action_url = f"{base_url}/telecmi/process-recording?phone={caller_phone}&direction={direction}"
        if direction == "inbound":
            pcmo_response = [
                {
                    "action": "play",
                    "file_name": WELCOME_MUSIC_URL
                },
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
        else:
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
        base_url = get_base_url(request)
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
        raw_phone = (
            data.get("phone") or 
            data.get("from") or 
            data.get("From") or 
            data.get("caller") or 
            data.get("caller_id") or 
            data.get("cuser") or 
            data.get("customer_number") or
            ""
        )
        caller_phone = str(raw_phone).strip() or "guest"
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
            if caller_phone != "guest":
                background_tasks.add_task(run_post_call_pipeline, caller_phone, direction, recording_url)
            return [
                {"action": "play", "file_name": audio_url},
                {"action": "hangup"}
            ]
        else:
            action_url = f"{base_url}/telecmi/process-recording?phone={caller_phone}&direction={direction}"
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
            hist = supabase_client.get_conversation_history(caller_phone)
            # Only trigger if session has dialogue history to process
            if hist and len(hist) > 1:
                background_tasks.add_task(run_post_call_pipeline, caller_phone, direction, recording_url)

        return {"status": "success", "event_received": True, "event_type": status or "logged"}
    except Exception as e:
        print(f"TeleCMI Event Error: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

