from fastapi import FastAPI, Request, Form, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
import uvicorn
import os

import config
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
    Starts background services on application startup.
    """
    scheduler.init_scheduler()

@app.post("/webhooks/new-lead")
async def new_lead_webhook(request: Request):
    """
    Webhook triggered when a new lead is submitted on the website or WhatsApp.
    Ingests the lead into Supabase and schedules an outbound call.
    """
    try:
        data = await request.json()
        name = data.get("name", "New Lead")
        phone = data.get("phone")
        email = data.get("email")
        course = data.get("course")
        
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
    
    # Check if caller is a known lead
    lead_name = "Future Pilot"
    if caller_phone:
        lead = supabase_client.get_lead_by_phone(caller_phone)
        if lead:
            lead_name = lead.get("name", "Future Pilot")
        elif direction == "inbound":
            # Automatically ingest new inbound caller as a lead
            supabase_client.save_lead(name="Inbound Lead", phone=caller_phone, status="Cold")
            lead_name = "Future Pilot"

    # Generate custom billing/greeting audio URL using ElevenLabs
    if direction == "outbound":
        greeting_text = f"Hello {lead_name}! I am Modassir from Airborne Aviation Academy. I noticed you submitted an interest in our pilot training courses. How can I help you today?"
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
async def process_recording(
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
