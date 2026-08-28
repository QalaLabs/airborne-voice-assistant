import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# App Settings
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("PORT", os.environ.get("APP_PORT", 8000)))
# Cloud Run Public Service URL or NGROK fallback
NGROK_URL = os.environ.get("APP_URL", os.environ.get("NGROK_URL", ""))

# OpenAI Settings
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview")

# Gemini Settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

# ElevenLabs Settings
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

# Twilio Credentials (fallback telephony carrier)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")

# Supabase Credentials
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# TeleCRM Credentials
TELECRM_API_KEY = os.environ.get("TELECRM_API_KEY", "")

# TeleCMI / PIOPIY Voice API & SIP Trunk
TELECMI_APP_ID = os.environ.get("TELECMI_APP_ID", "6eaa00e8-10e8-4dd6-afb1-0a0e200d2b0b")
TELECMI_APP_SECRET = os.environ.get("TELECMI_APP_SECRET", "e65072de-7571-4930-a51b-181fba552e7d")
TELECMI_TOKEN = os.environ.get("TELECMI_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJvcmdfaWQiOiIzYTNhNGM0ZC00OTUzLTRiYjEtOTg5MS0xMjhiNjlmY2FhOGYiLCJlbWFpbF9pZCI6ImFiQHFhbGFsYWJzLmNvbSIsImlhdCI6MTc4NzkxOTYwNn0.zwST5Rc3qgXioCj2xInm_Dql148Crfcs8ewX1XuQ0wI")
TELECMI_SIP_USER = os.environ.get("TELECMI_SIP_USER", "airborneaviation")
TELECMI_SIP_PASS = os.environ.get("TELECMI_SIP_PASS", "Qalalabs@212")
TELECMI_PHONE_NUMBER = os.environ.get("TELECMI_PHONE_NUMBER", "")


# Booking & Automations Settings
CAMPUS_BOOKING_URL = os.environ.get("CAMPUS_BOOKING_URL", "https://calendly.com/airborne-aviation/campus-visit")
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "")
WHATSAPP_API_KEY = os.environ.get("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

