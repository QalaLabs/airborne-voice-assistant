import os
import sys

# Force UTF-8 on Windows so rupee symbols or special characters never throw charmap encoding error
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import logging
import edge_tts
import miniaudio
from loguru import logger

import config
import rag
from piopiy.agent import Agent, logger as piopiy_logger
from piopiy.voice_agent import VoiceAgent
from piopiy.services.whisper.stt import WhisperSTTService
from piopiy.services.google.llm import GoogleLLMService
from piopiy.services.tts_service import TTSService
from piopiy.audio.vad.silero import SileroVADAnalyzer
from piopiy.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSSpeakFrame,
)

logging.basicConfig(level=logging.INFO)

AGENT_ID = config.TELECMI_APP_ID or os.getenv("TELECMI_APP_ID", "edc5b96c-9e10-4b1f-b2b0-528da3c30978")
AGENT_TOKEN = config.AGENT_TOKEN or os.getenv("AGENT_TOKEN", "")

# -------------------------------------------------------------
# 1. Custom Fast Neural TTS (Reliable 0-quota, ultra crisp Hindi/English voice)
# -------------------------------------------------------------
class FastEdgeTTSService(TTSService):
    """
    Direct streaming neural TTS that never fails on quotas or gRPC deadlocks.
    Uses Microsoft Neural Voice (en-IN-PrabhatNeural).
    """
    def __init__(self, voice: str = "en-IN-PrabhatNeural", sample_rate: int = 24000, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._voice = voice
        self._sample_rate = sample_rate

    async def run_tts(self, text: str):
        logger.info(f"Agent Speaking: '{text}'")
        yield BotStartedSpeakingFrame()
        yield TTSStartedFrame()
        try:
            comm = edge_tts.Communicate(text, self._voice)
            chunks = []
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            mp3_data = b"".join(chunks)
            if mp3_data:
                decoded = miniaudio.decode(mp3_data, nchannels=1, sample_rate=self._sample_rate)
                pcm_bytes = decoded.samples.tobytes()
                # 20ms chunks at 24kHz 16-bit PCM = 960 bytes
                chunk_size = 960
                for i in range(0, len(pcm_bytes), chunk_size):
                    piece = pcm_bytes[i:i + chunk_size]
                    yield TTSAudioRawFrame(piece, self._sample_rate, 1)
        except Exception as e:
            logger.error(f"TTS Synthesis error: {e}")
        yield TTSStoppedFrame()
        yield BotStoppedSpeakingFrame()

# -------------------------------------------------------------
# 2. Complete RAG Knowledge Grounding from airborneaviation.in
# -------------------------------------------------------------
def get_full_rag_context() -> str:
    """Compiles the entire airborneaviation.in knowledge corpus into the system prompt."""
    sections = []
    for item in rag.AIRBORNE_KNOWLEDGE_BASE:
        sections.append(f"[{item['title'].upper()}]\n{item['content'].strip()}")
    return "\n\n".join(sections)

FULL_WEBSITE_KNOWLEDGE = get_full_rag_context()

SYSTEM_INSTRUCTIONS = f"""
You are Capt. Modassir, a senior pilot mentor and admissions advisor at Airborne Aviation Academy, located at Ramphal Chowk, Sector 7, Dwarka, New Delhi.
You are on a live phone call with an aspiring pilot or parent.

Persona & Conversational Style:
- Warm, polite, confident, and encouraging pilot mentor.
- Fluent Bilingual: You speak both English and natural conversational Hinglish.
  * If the caller speaks English, respond in fluent, professional English.
  * If the caller speaks Hindi or Hinglish, respond in warm, natural Hinglish.
- Spoken Phone Call Format: KEEP RESPONSES VERY SHORT AND PUNCHY (1 to 2 short sentences per turn). Never lecture or give monologues. Let the caller respond!
- Never pushy or salesy. Act as a trusted flight advisor.

=======================================================
CRITICAL REALITIES & FACTS (MUST FOLLOW):
=======================================================
1. CPL = Commercial Pilot License course.
2. FTO REALITY (VERY IMPORTANT):
   - Airborne Aviation Academy does NOT have its own FTO (Flying Training Organisation) yet.
   - We are an elite DGCA ground academy and simulator training center.
   - For the mandatory 200 hours flight training, we have PARTNERED with top DGCA-approved flying schools (FTOs) in India and premier flight academies abroad (USA, South Africa, New Zealand).
   - If asked about flying: Explain that ground school & DGCA exam prep happens with us in Dwarka, and flying training is completed through our partnered DGCA-approved flying schools.

=======================================================
LEAD FILTERING & CONVERSATION GOAL:
=======================================================
Your primary goal on this call is to filter and qualify the lead, then guide them to schedule a campus visit or follow-up counseling call:
1. Filter Eligibility:
   - Ask or verify if they have completed 10+2 with Physics and Maths (or if they are planning to do it through NIOS open schooling, which DGCA accepts 100%).
   - Minimum age: 17 years for ground classes; 18 years for commercial pilot license issuance.
2. Close with an Actionable CTA:
   - Invite them to visit our Dwarka campus at Ramphal Chowk for an A320 flight simulator walkthrough and a 1-on-1 counseling session with Capt. Navrang Singh.
   - Or offer to schedule a follow-up counseling call if they are from outside Delhi.

=======================================================
COMPLETE OFFICIAL KNOWLEDGE BASE (airborneaviation.in):
=======================================================
{FULL_WEBSITE_KNOWLEDGE}
=======================================================

Fee Reference (Strict Rule - State amounts clearly without currency symbols):
- DGCA CPL Ground Classes: 2 Lakhs 70 Thousand Rupees (Rs. 2,70,000) for all 5 DGCA theory papers + WPC RTR (Aero). Duration: 3 to 6 months. Capped at 25 students per batch. Taught directly in-person by Captain Navrang Singh!
- Full CPL (Ground + 200 Flying Hours with partnered FTOs): 55 to 65 Lakh Rupees (Rs. 55-65 Lakhs).
- A320 Simulator (FBS Level 5): 12 Thousand Rupees (Rs. 12,000) per session onsite at Dwarka campus.
- Cadet Prep: 50 Thousand Rupees (Rs. 50,000) | Comprehensive Airline GD-PI Prep: 1 Lakh 25 Thousand Rupees (Rs. 1,25,000).
- Currency Rule: ALWAYS pronounce currency as "Rupees" or "Lakhs". Never use symbol characters.
"""

GREETING_MESSAGE = "Hello! This is Capt. Modassir from Airborne Aviation Academy, Dwarka. How may I guide your pilot training journey today?"

print("==================================================================")
print(f"Initializing Airborne Voice Agent Worker for Agent ID: {AGENT_ID}")
print("Pre-warming Whisper STT model (Model.TINY, CPU int8) and Silero VAD...")
from piopiy.services.whisper.stt import Model
shared_stt = WhisperSTTService(model=Model.TINY, device="cpu", compute_type="int8")
shared_vad = SileroVADAnalyzer()
print("Whisper STT (TINY) and Silero VAD ready for ultra-low latency!")

async def create_session(**kwargs):
    """
    Invoked automatically when a call connects to this agent.
    """
    call_id = kwargs.get("call_id", "unknown")
    caller = kwargs.get("from_number", kwargs.get("to_number", "caller"))
    logger.info(f"Incoming call connected! call_id={call_id}, caller={caller}")

    voice_agent = VoiceAgent(
        instructions=SYSTEM_INSTRUCTIONS,
        greeting=GREETING_MESSAGE,
        idle_timeout_secs=60,
    )

    llm = GoogleLLMService(
        api_key=config.GEMINI_API_KEY,
        model="gemini-3.8-flash",
    )

    tts = FastEdgeTTSService(
        voice="en-IN-PrabhatNeural",
        sample_rate=24000,
    )

    # Enable Silero VAD so the pipeline actively captures and segments user speech
    await voice_agent.Action(
        stt=shared_stt,
        llm=llm,
        tts=tts,
        vad=shared_vad,
        allow_interruptions=True,
    )

    logger.info(f"VoiceAgent pipeline active. Waiting for conversation turns...")
    await voice_agent.start()
    logger.info(f"Call session finished for call_id={call_id}")

agent = Agent(
    agent_id=AGENT_ID,
    agent_token=AGENT_TOKEN,
    create_session=create_session,
    debug=True,
)

async def run_worker():
    print(f"Connecting to Piopiy signaling server for Agent ID: {AGENT_ID}...")
    await agent.sio.connect(
        agent.signaling_url,
        auth={"agent_id": agent.agent_id, "token": agent.agent_token},
    )
    print("==================================================================")
    print("Airborne Aviation AI Agent Worker is ONLINE and waiting for live calls!")
    print(f"Active Agent ID: {AGENT_ID}")
    print("Knowledge Loaded: 100% of airborneaviation.in Ground Truth")
    print("Voice Engine: Fast Neural Speech (en-IN-PrabhatNeural)")
    print("STT & VAD: Faster-Whisper + Silero VAD (Active Speech Detection)")
    print("LLM Engine: Gemini 3.8 Flash")
    print("==================================================================")
    try:
        await agent.sio.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("Shutting down worker...")
        await agent.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("Stopped by user.")
