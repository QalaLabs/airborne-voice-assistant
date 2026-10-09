import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

def _clean_env(key: str, default: str = "") -> str:
    val = os.environ.get(key, default)
    return val.strip() if isinstance(val, str) else val

# App Settings
APP_HOST = _clean_env("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("PORT", os.environ.get("APP_PORT", 8000)))
APP_URL = _clean_env("APP_URL", "https://airborne-voice-assistant-368523757732.asia-south1.run.app")
NGROK_URL = _clean_env("APP_URL", _clean_env("NGROK_URL", APP_URL))

# OpenAI Settings
OPENAI_API_KEY = _clean_env("OPENAI_API_KEY", "")
OPENAI_MODEL = _clean_env("OPENAI_MODEL", "gpt-4-turbo-preview")

# Gemini Settings
GEMINI_API_KEY = _clean_env("GEMINI_API_KEY", "")
GEMINI_MODEL = _clean_env("GEMINI_MODEL", "gemini-3.8-flash")

# ElevenLabs Settings
USE_ELEVENLABS = _clean_env("USE_ELEVENLABS", "true").lower() == "true"
ELEVENLABS_API_KEY = _clean_env("ELEVENLABS_API_KEY", "")
ELEVENLABS_KEY_ID = _clean_env("ELEVENLABS_KEY_ID", "b69d20bc454b66daeb436c793d3edf9e6018690e472e192a08625fb596abe03e")
ELEVENLABS_VOICE_ID = _clean_env("ELEVENLABS_VOICE_ID", "eJTrVjiaPKqBMpMujQdM")
ELEVENLABS_MODEL_ID = _clean_env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
ELEVENLABS_AGENT_ID = _clean_env("ELEVENLABS_AGENT_ID", "agent_5701kztar977fxsb7nj7cxedcrgf")

# Twilio Credentials (fallback telephony carrier)
TWILIO_ACCOUNT_SID = _clean_env("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = _clean_env("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = _clean_env("TWILIO_PHONE_NUMBER", "")

# Supabase Credentials
SUPABASE_URL = _clean_env("SUPABASE_URL", "")
SUPABASE_KEY = _clean_env("SUPABASE_KEY", "")

# TeleCRM Credentials
TELECRM_API_KEY = _clean_env("TELECRM_API_KEY", "")

# Piopiy / TeleCMI Settings
AGENT_ID = _clean_env("AGENT_ID", _clean_env("TELECMI_PIOPIY_APP_ID", "edc5b96c-9e10-4b1f-b2b0-528da3c30978"))
AGENT_TOKEN = _clean_env("AGENT_TOKEN", _clean_env("TELECMI_TOKEN", ""))

# TeleCMI / PIOPIY Voice API & Settings
TELECMI_APP_ID = _clean_env("TELECMI_APP_ID", "edc5b96c-9e10-4b1f-b2b0-528da3c30978")
TELECMI_APP_SECRET = _clean_env("TELECMI_APP_SECRET", "")
TELECMI_TOKEN = _clean_env("TELECMI_TOKEN", "")
TELECMI_PHONE_NUMBER = _clean_env("TELECMI_PHONE_NUMBER", "917943446755")
TELECMI_PIOPIY_APP_ID = _clean_env("TELECMI_PIOPIY_APP_ID", "edc5b96c-9e10-4b1f-b2b0-528da3c30978")
# Shared secret appended as ?token=... on the TeleCMI Debug/Event webhook URL to verify
# incoming requests actually originate from TeleCMI. Leave unset to disable verification.
TELECMI_WEBHOOK_TOKEN = _clean_env("TELECMI_WEBHOOK_TOKEN", "")


# Booking & Automations Settings
CAMPUS_BOOKING_URL = _clean_env("CAMPUS_BOOKING_URL", "https://calendly.com/airborne-aviation/campus-visit")
WHATSAPP_API_URL = _clean_env("WHATSAPP_API_URL", "")
WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

# Google Cloud / Vertex AI Agent Engine Settings
GCP_PROJECT = _clean_env("GCP_PROJECT", "")
GCP_LOCATION = _clean_env("GCP_LOCATION", "asia-south1")
# Resource name of the deployed ADK agent on Vertex AI Agent Engine, e.g.
# "projects/<project>/locations/<location>/reasoningEngines/<id>" — populated
# after running agent/deploy_agent.sh once. Empty/unset keeps the feature off.
AGENT_ENGINE_RESOURCE_NAME = _clean_env("AGENT_ENGINE_RESOURCE_NAME", "")
# Feature flag: route the conversational turn through the deployed Agent Engine
# agent instead of the direct Gemini/OpenAI call in gpt_test.py. Defaults to
# off so this ships inert; flip only after the verification steps in
# agent/README.md pass. assistant.py always falls back to the direct LLM path
# per-turn if the Agent Engine call fails, regardless of this flag.
USE_AGENT_ENGINE = _clean_env("USE_AGENT_ENGINE", "false").lower() in ("1", "true", "yes")
# Optional comma-separated allowlist of phone numbers to route through the
# Agent Engine path even when USE_AGENT_ENGINE is false, for graduated
# rollout/testing without flipping the global flag.
AGENT_ENGINE_ROLLOUT_PHONES = {
    p.strip() for p in _clean_env("AGENT_ENGINE_ROLLOUT_PHONES", "").split(",") if p.strip()
}

# Shared secret validated by the internal /internal/rag/query endpoint
# (main.py), called by the ADK agent's search_knowledge tool (agent/rag_client.py).
INTERNAL_RAG_SHARED_SECRET = _clean_env("INTERNAL_RAG_SHARED_SECRET", "")

