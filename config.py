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
NGROK_URL = _clean_env("NGROK_URL", APP_URL)

# OpenAI Settings
OPENAI_API_KEY = _clean_env("OPENAI_API_KEY", "")
OPENAI_MODEL = _clean_env("OPENAI_MODEL", "gpt-4-turbo-preview")

# Gemini Settings
GEMINI_API_KEY = _clean_env("GEMINI_API_KEY", "")
GEMINI_MODEL = _clean_env("GEMINI_MODEL", "gemini-3.8-flash")

# ElevenLabs Settings
USE_ELEVENLABS = _clean_env("USE_ELEVENLABS", "true").lower() == "true"
ELEVENLABS_API_KEY = _clean_env("ELEVENLABS_API_KEY", "")
ELEVENLABS_KEY_ID = _clean_env("ELEVENLABS_KEY_ID", "")
ELEVENLABS_VOICE_ID = _clean_env("ELEVENLABS_VOICE_ID", "eJTrVjiaPKqBMpMujQdM")
ELEVENLABS_MODEL_ID = _clean_env("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
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
AGENT_ID = _clean_env("AGENT_ID", _clean_env("TELECMI_PIOPIY_APP_ID", ""))
AGENT_TOKEN = _clean_env("AGENT_TOKEN", _clean_env("TELECMI_TOKEN", ""))
PIOPIY_TOKEN_NAME = _clean_env("PIOPIY_TOKEN_NAME", "Airborne_Voice_Agent")

# TeleCMI / PIOPIY Voice API & Settings
TELECMI_APP_ID = _clean_env("TELECMI_APP_ID", "")
TELECMI_APP_SECRET = _clean_env("TELECMI_APP_SECRET", "")
TELECMI_TOKEN = _clean_env("TELECMI_TOKEN", "")
TELECMI_PHONE_NUMBER = _clean_env("TELECMI_PHONE_NUMBER", "")
# Custom SIP namespace URL for this Piopiy project (SIP endpoints)
PIOPIY_SIP_URL = _clean_env("PIOPIY_SIP_URL", "")
TELECMI_PIOPIY_APP_ID = _clean_env("TELECMI_PIOPIY_APP_ID", "")
# Shared secret appended as ?token=... on the TeleCMI Debug/Event webhook URL to verify
# incoming requests actually originate from TeleCMI. Leave unset to disable verification.
TELECMI_WEBHOOK_TOKEN = _clean_env("TELECMI_WEBHOOK_TOKEN", "")

# Outbound Telephony Queue Recovery & PCMO Override
CALL_VERIFICATION_TIMEOUT_SECS = float(_clean_env("CALL_VERIFICATION_TIMEOUT_SECS", "35.0"))
FORCE_PCMO_OUTBOUND = _clean_env("FORCE_PCMO_OUTBOUND", "false").lower() in ("1", "true", "yes")
MAX_CONCURRENT_CALLS = int(_clean_env("MAX_CONCURRENT_CALLS", "4"))


# Booking & Automations Settings
CAMPUS_BOOKING_URL = _clean_env("CAMPUS_BOOKING_URL", "https://calendly.com/airborne-aviation/campus-visit")
WHATSAPP_API_URL = _clean_env("WHATSAPP_API_URL", "")
WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

# Google Cloud Settings (Cloud SQL / Cloud Run / optional Vertex helpers)
GCP_PROJECT = _clean_env("GCP_PROJECT", "")
GCP_LOCATION = _clean_env("GCP_LOCATION", "asia-south1")

# Shared secret validated by the internal /internal/rag/query endpoint (main.py).
# ADK Agent Engine integration was archived under ../adk-archive/.
INTERNAL_RAG_SHARED_SECRET = _clean_env("INTERNAL_RAG_SHARED_SECRET", "")

# Shared secret required (X-API-Key header or Bearer token) by the call-dispatch,
# pre-feed and new-lead endpoints in main.py. Unset => those endpoints refuse all requests.
API_SHARED_SECRET = _clean_env("API_SHARED_SECRET", "")


# =====================================================================
# 🛡️  ENVIRONMENT VARIABLE VALIDATION
# =====================================================================

_REQUIRED_PRODUCTION_KEYS = [
    "GEMINI_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
]

_RECOMMENDED_KEYS = [
    "DATABASE_URL",
    "GCS_BUCKET_NAME",
    "TELECRM_API_KEY",
    "WHATSAPP_API_KEY",
]

_MOCK_MODE = not bool(os.environ.get("DATABASE_URL", os.environ.get("POSTGRES_URL", "")))


def validate_env(strict: bool = False):
    """
    Checks that all required environment variables are set.
    In strict mode (production), raises RuntimeError on missing required keys.
    In non-strict mode (local dev), prints warnings only.
    """
    missing_required = [k for k in _REQUIRED_PRODUCTION_KEYS if not _clean_env(k)]
    missing_recommended = [k for k in _RECOMMENDED_KEYS if not _clean_env(k)]

    if missing_required:
        msg = f"Missing required environment variables: {', '.join(missing_required)}"
        if strict and not _MOCK_MODE:
            raise RuntimeError(msg + ". Set these in your .env or Secret Manager before deploying.")
        else:
            for k in missing_required:
                print(f"⚠️  Warning: {k} is not set. Feature will use mock/fallback mode.")

    if missing_recommended:
        for k in missing_recommended:
            print(f"ℹ️  Notice: {k} is not set. Related feature may be limited.")


validate_env(strict=False)

