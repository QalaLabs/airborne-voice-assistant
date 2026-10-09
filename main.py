from fastapi import FastAPI, Request, Form, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
import uvicorn
import os
import hmac

from contextlib import asynccontextmanager

import config
import database
import rag
import scheduler
import supabase_client
from assistant import handle_conversation, get_greeting_voice_url, run_post_call_pipeline

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Starts background services, initializes PostgreSQL database schema,
    and runs the PioPiy AI Agent Worker for real-time signaling.
    """
    import asyncio
    database.init_db()
    scheduler.init_scheduler()

    # Launch Piopiy AI agent worker for real-time call signaling
    worker_task = None
    try:
        import piopiy_agent_worker
        if getattr(piopiy_agent_worker, "agent", None):
            worker_task = asyncio.create_task(piopiy_agent_worker.run_worker())
            print("🚀 Piopiy AI Agent Worker background task launched.")
    except Exception as e:
        print(f"Notice starting piopiy_agent_worker: {e}")

    yield

    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="Airborne Aviation AI Voice Assistant", lifespan=lifespan)

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
        course = data.get("course") or data.get("Course") or "Commercial Pilot License (CPL)"
        education = data.get("education") or data.get("Education")
        city = data.get("city") or data.get("City")
        notes = data.get("notes") or data.get("Notes")
        call_objective = data.get("call_objective") or data.get("objective")
        
        if not phone:
            return {"status": "error", "message": "Phone number is required."}
            
        # Register in PreCallManager for zero-latency prompt compilation & 0ms audio pre-warm
        import precall_manager
        dossier = precall_manager.manager.register_precall(
            phone=phone,
            name=name,
            course_interest=course,
            education=education,
            city=city,
            notes=notes,
            call_objective=call_objective,
            source="WEBHOOK_NEW_LEAD",
            prewarm_audio=True
        )

        # Ingest lead into database
        lead = supabase_client.save_lead(name, phone, email, course, status="Cold")
        
        # Schedule outbound call within 2 minutes (120 seconds)
        scheduler.schedule_outbound_call(name, phone, delay_seconds=120)
        
        return {
            "status": "success",
            "message": "Lead registered, pre-call dossier compiled, audio pre-warmed, and call scheduled.",
            "lead_id": lead.get("id") if lead else None,
            "greeting_text": precall_manager.manager.generate_greeting(dossier, direction="outbound")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/calls/prefeed")
async def api_feed_precall_data(request: Request):
    """
    Feeds lead context to the voice agent BEFORE making a call.
    Pre-compiles the LLM system prompt and pre-warms the opening greeting audio.
    Ensures the subsequent phone call has ZERO mid-call database lag and 0ms initial pickup latency.
    """
    try:
        data = await request.json()
        phone = data.get("phone")
        if not phone:
            return JSONResponse({"status": "error", "message": "Phone number is required."}, status_code=400)

        import precall_manager
        dossier = precall_manager.manager.register_precall(
            phone=phone,
            name=data.get("name", "Candidate"),
            course_interest=data.get("course_interest", "Commercial Pilot License (CPL)"),
            education=data.get("education"),
            age=data.get("age"),
            city=data.get("city"),
            prior_aviation_exp=data.get("prior_aviation_exp"),
            medicals_status=data.get("medicals_status"),
            budget_or_loan=data.get("budget_or_loan"),
            notes=data.get("notes"),
            call_objective=data.get("call_objective"),
            preferred_language=data.get("preferred_language", "Hinglish"),
            custom_instructions=data.get("custom_instructions"),
            source=data.get("source", "PREFEED_API"),
            prewarm_audio=data.get("prewarm_audio", True)
        )

        greeting = precall_manager.manager.generate_greeting(dossier, direction="outbound")
        compiled_prompt = precall_manager.manager.compile_system_prompt(dossier, direction="outbound")

        return JSONResponse({
            "status": "success",
            "message": "Pre-call context successfully fed and cached.",
            "phone": phone,
            "candidate_name": dossier.name,
            "course": dossier.course_interest,
            "generated_greeting": greeting,
            "prewarm_audio_triggered": True,
            "prompt_length_chars": len(compiled_prompt)
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/calls/dispatch")
async def api_dispatch_call_with_prefeed(request: Request, background_tasks: BackgroundTasks):
    """
    Feeds lead context AND immediately triggers the outbound call.
    The agent answers with pre-warmed audio (0ms latency) and full candidate context baked in.
    """
    try:
        data = await request.json()
        phone = data.get("phone")
        if not phone:
            return JSONResponse({"status": "error", "message": "Phone number is required."}, status_code=400)

        import precall_manager
        import telephony

        # 1. Register & pre-warm
        dossier = precall_manager.manager.register_precall(
            phone=phone,
            name=data.get("name", "Candidate"),
            course_interest=data.get("course_interest", "Commercial Pilot License (CPL)"),
            education=data.get("education"),
            age=data.get("age"),
            city=data.get("city"),
            prior_aviation_exp=data.get("prior_aviation_exp"),
            medicals_status=data.get("medicals_status"),
            budget_or_loan=data.get("budget_or_loan"),
            notes=data.get("notes"),
            call_objective=data.get("call_objective"),
            preferred_language=data.get("preferred_language", "Hinglish"),
            custom_instructions=data.get("custom_instructions"),
            source=data.get("source", "API_DISPATCH"),
            prewarm_audio=True
        )

        # 2. Trigger call in background task or immediately
        def _dispatch():
            telephony.make_outbound_call(phone, dossier.name, precall_data=dossier.to_dict())

        background_tasks.add_task(_dispatch)

        return JSONResponse({
            "status": "success",
            "message": "Outbound call initiated with pre-fed context and pre-warmed audio.",
            "phone": phone,
            "candidate": dossier.name,
            "course": dossier.course_interest,
            "greeting": precall_manager.manager.generate_greeting(dossier, direction="outbound")
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/calls/prefeed/{phone}")
async def api_get_precall_data(phone: str):
    """
    Retrieves current pre-call dossier and audio cache status for a phone number.
    """
    import precall_manager
    dossier = precall_manager.manager.get_dossier(phone)
    if not dossier:
        return JSONResponse({"status": "not_found", "message": "No active dossier for this number."}, status_code=404)
    return JSONResponse({
        "status": "found",
        "dossier": dossier.to_dict(),
        "greeting": precall_manager.manager.generate_greeting(dossier, direction="outbound"),
        "audio_url": precall_manager.manager.get_prewarmed_audio_url(phone)
    })

@app.post("/answer-call", response_class=PlainTextResponse)
async def answer_call(
    request: Request,
    background_tasks: BackgroundTasks,
    From: str = Form(None), 
    phone: str = Query(None), 
    direction: str = Query("inbound")
):
    """
    Twilio SIP / Voice entrypoint for inbound and outbound calls.
    Directs the call into the AI processing loop with sub-15ms greeting response.
    """
    import precall_manager
    caller_phone = phone or From or ""
    base_url = get_base_url(request)
    
    # Rapid in-memory dossier check (<1ms)
    dossier = precall_manager.manager.get_dossier(caller_phone) if caller_phone else None
    
    if direction == "inbound":
        if dossier and dossier.name not in ["Candidate", "Future Pilot", "Inbound Caller", "New Lead"]:
            greeting_text = f"Hello {dossier.name}! Thank you for calling Airborne Aviation Academy, Dwarka. Captain Navrang here. How may I help you today?"
            greeting_url = precall_manager.manager.get_prewarmed_audio_url(caller_phone) or precall_manager.INBOUND_DEFAULT_GREETING_URL
        else:
            greeting_text = "Hello! Thank you for calling Airborne Aviation Academy in Dwarka. I am Captain Navrang, Chief Pilot Instructor. May I know your good name, and which course or query are you calling about today?"
            greeting_url = precall_manager.INBOUND_DEFAULT_GREETING_URL

        # Save lead and history non-blockingly
        if caller_phone:
            background_tasks.add_task(supabase_client.save_lead, name="Inbound Caller", phone=caller_phone, course="General Inquiry", status="NEW")
            background_tasks.add_task(supabase_client.save_conversation_history, caller_phone, [{"role": "assistant", "content": greeting_text}], direction)
    else:
        # Outbound call path
        lead_name = dossier.name if dossier else "Future Pilot"
        course_interest = dossier.course_interest if dossier else "Commercial Pilot License"
        greeting_text = precall_manager.manager.generate_greeting(dossier, direction="outbound") if dossier else f"Hi {lead_name}, calling from Airborne Aviation Academy regarding {course_interest}."
        greeting_url = precall_manager.manager.get_prewarmed_audio_url(caller_phone) if caller_phone else get_greeting_voice_url(greeting_text)
        if caller_phone:
            background_tasks.add_task(supabase_client.save_conversation_history, caller_phone, [{"role": "assistant", "content": greeting_text}], direction)

    # Twilio Voice Response: instant play
    resp = VoiceResponse()
    resp.play(greeting_url)
    
    # Record caller input and route back to process-recording (absolute URL required by Twilio)
    action_url = f"{base_url}/process-recording?phone={caller_phone}&direction={direction}"
    resp.record(
        action=action_url,
        method="POST",
        max_length=15,
        play_beep=False,
        timeout=3
    )
    return str(resp)

@app.post("/process-recording", response_class=PlainTextResponse)
def process_recording(
    request: Request,
    background_tasks: BackgroundTasks,
    RecordingUrl: str = Form(...),
    phone: str = Query(None),
    direction: str = Query("inbound")
):
    """
    Process caller recording, query RAG, generate reply using LLM, and loop.
    """
    caller_phone = phone or ""
    base_url = get_base_url(request)
    
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
        action_url = f"{base_url}/process-recording?phone={caller_phone}&direction={direction}"
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

@app.get("/telecmi/answer", operation_id="telecmi_answer_get")
@app.post("/telecmi/answer", operation_id="telecmi_answer_post")
async def telecmi_answer(request: Request, background_tasks: BackgroundTasks):
    """
    TeleCMI PIOPIY Answer URL Webhook.
    Returns PCMO instructions in sub-15ms using pre-synthesized inbound greetings
    and non-blocking background CRM synchronization.
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

        if not caller_phone:
            caller_phone = "guest"

        direction = data.get("direction", "inbound")

        import precall_manager
        dossier = precall_manager.manager.get_dossier(caller_phone) if caller_phone != "guest" else None

        if direction == "inbound":
            if dossier and dossier.name not in ["Candidate", "Future Pilot", "Inbound Caller", "TeleCMI Inbound Lead", "New Lead"]:
                greeting_text = f"Hello {dossier.name}! Thank you for calling Airborne Aviation Academy, Dwarka. Captain Navrang here. How may I help you today?"
                greeting_url = precall_manager.manager.get_prewarmed_audio_url(caller_phone) or precall_manager.INBOUND_DEFAULT_GREETING_URL
            else:
                greeting_text = "Hello! Thank you for calling Airborne Aviation Academy in Dwarka. I am Captain Navrang, Chief Pilot Instructor. May I know your good name, and which course or query are you calling about today?"
                greeting_url = precall_manager.INBOUND_DEFAULT_GREETING_URL

            # Non-blocking background CRM synchronization
            if caller_phone != "guest":
                background_tasks.add_task(supabase_client.save_lead, name="TeleCMI Inbound Lead", phone=caller_phone, course="General Inquiry", status="NEW")
                background_tasks.add_task(supabase_client.save_conversation_history, caller_phone, [{"role": "assistant", "content": greeting_text}], direction)
        else:
            # Outbound call path
            greeting_text = precall_manager.manager.generate_greeting(dossier, direction="outbound") if dossier else f"Hi, this is Captain Navrang from Airborne Aviation Academy."
            greeting_url = precall_manager.manager.get_prewarmed_audio_url(caller_phone) or "https://storage.googleapis.com/airborne-aviation-media-prod/tts-audio/greeting_navrang.mp3"
            if caller_phone != "guest":
                background_tasks.add_task(supabase_client.save_conversation_history, caller_phone, [{"role": "assistant", "content": greeting_text}], direction)

        action_url = f"{base_url}/telecmi/process-recording?phone={caller_phone}&direction={direction}"
        pcmo_response = [
            {
                "action": "play_get_input",
                "prompt": {
                    "type": "file",
                    "file_name": greeting_url
                },
                "input": ["speech", "dtmf"],
                "on_result": {
                    "type": "url",
                    "url": action_url
                }
            }
        ]
        return pcmo_response
    except Exception as e:
        print(f"TeleCMI Answer Error: {e}")
        return [{"action": "play", "file_name": precall_manager.INBOUND_DEFAULT_GREETING_URL}]

@app.get("/telecmi/process-recording", operation_id="telecmi_process_recording_get")
@app.post("/telecmi/process-recording", operation_id="telecmi_process_recording_post")
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
        raw_speech = (
            data.get("speech") or 
            data.get("transcript") or 
            data.get("text") or 
            data.get("digit") or 
            data.get("digits") or 
            data.get("dtmf") or 
            ""
        )
        if isinstance(raw_speech, dict):
            caller_speech = raw_speech.get("text") or raw_speech.get("transcript") or raw_speech.get("speech") or str(raw_speech)
        else:
            caller_speech = str(raw_speech)
        recording_url = (
            data.get("record_url") or 
            data.get("recording_url") or 
            data.get("file_url") or 
            ""
        )

        import anyio
        audio_url, should_hang_up = await anyio.to_thread.run_sync(
            handle_conversation, recording_url, caller_phone, direction, caller_speech
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
                {
                    "action": "play_get_input",
                    "prompt": {
                        "type": "file",
                        "file_name": audio_url
                    },
                    "input": ["speech", "dtmf"],
                    "on_result": {
                        "type": "url",
                        "url": action_url
                    }
                }
            ]
    except Exception as e:
        print(f"TeleCMI Process Recording Error: {e}")
        return [
            {"action": "play", "file_name": get_greeting_voice_url("Thank you for calling Airborne Aviation Academy.")},
            {"action": "hangup"}
        ]


@app.get("/telecmi/events", operation_id="telecmi_events_get")
@app.post("/telecmi/events", operation_id="telecmi_events_post")
@app.get("/telecmi/debug", operation_id="telecmi_debug_get")
@app.post("/telecmi/debug", operation_id="telecmi_debug_post")
async def telecmi_events(request: Request, background_tasks: BackgroundTasks):
    """
    TeleCMI Debug / Event URL Webhook.
    Receives real-time call lifecycle events (ringing, answered, hangup, CDR).
    Triggers post-call processing on call completion.
    """
    try:
        query_params = dict(request.query_params)

        # Verify the shared webhook token (configured as ?token=... on the TeleCMI
        # Debug/Event URL and/or an X-Webhook-Token header) so arbitrary callers can't
        # forge call-outcome events and trigger CRM writes / post-call pipelines.
        if config.TELECMI_WEBHOOK_TOKEN:
            provided_token = query_params.get("token") or request.headers.get("x-webhook-token") or ""
            if not hmac.compare_digest(provided_token, config.TELECMI_WEBHOOK_TOKEN):
                print("TeleCMI Event Rejected: invalid or missing webhook token")
                return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

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

