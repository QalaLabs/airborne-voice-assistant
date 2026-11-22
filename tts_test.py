import requests
import os
import time
import uuid
import base64
import config
import storage_service

try:
    from google.cloud import texttospeech as google_tts
except ImportError:
    google_tts = None

# Persistent session for low-latency keep-alive connections to ElevenLabs
_tts_session = requests.Session()
_google_tts_client = None

def get_google_tts_client():
    global _google_tts_client
    if _google_tts_client is None and google_tts:
        try:
            _google_tts_client = google_tts.TextToSpeechClient()
        except Exception as e:
            print(f"Notice: Google Cloud TTS Client Init: {e}")
            _google_tts_client = None
    return _google_tts_client

def cleanup_old_audio_files(max_age_seconds: int = 3600):
    """
    Cleans up cached response MP3 files in the static directory older than max_age_seconds
    to prevent disk leaks on container deployments.
    """
    try:
        static_dir = "static"
        if not os.path.exists(static_dir):
            return
        now = time.time()
        for fname in os.listdir(static_dir):
            if fname.startswith("resp_") and fname.endswith(".mp3"):
                fpath = os.path.join(static_dir, fname)
                try:
                    if now - os.path.getmtime(fpath) > max_age_seconds:
                        os.remove(fpath)
                except Exception:
                    pass
    except Exception:
        pass

def synthesize_with_google_tts(text: str) -> bytes:
    """
    Synthesizes speech using Google Cloud Text-to-Speech (Neural2 / Wavenet).
    Works natively on Google Cloud Run with service account / ADC, or via REST API with GEMINI_API_KEY.
    """
    # 1. Try google-cloud-texttospeech client (ADC / Service Account / Cloud Run native)
    client = get_google_tts_client()
    if client:
        try:
            s_input = google_tts.SynthesisInput(text=text)
            voice_name = getattr(config, "GOOGLE_TTS_VOICE", "en-IN-Neural2-B")
            language_code = getattr(config, "GOOGLE_TTS_LANG", "en-IN")
            voice = google_tts.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name
            )
            audio_config = google_tts.AudioConfig(
                audio_encoding=google_tts.AudioEncoding.MP3,
                speaking_rate=getattr(config, "GOOGLE_TTS_SPEED", 1.0)
            )
            response = client.synthesize_speech(input=s_input, voice=voice, audio_config=audio_config)
            return response.audio_content
        except Exception as e:
            print(f"Google Cloud TTS SDK synthesis failed ({e}). Trying REST endpoint...")

    # 2. Try REST API with GEMINI_API_KEY if client was unavailable
    gemini_key = getattr(config, "GEMINI_API_KEY", "")
    if gemini_key:
        try:
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={gemini_key}"
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": getattr(config, "GOOGLE_TTS_LANG", "en-IN"),
                    "name": getattr(config, "GOOGLE_TTS_VOICE", "en-IN-Neural2-B")
                },
                "audioConfig": {"audioEncoding": "MP3"}
            }
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
            if resp.status_code == 200:
                audio_b64 = resp.json().get("audioContent", "")
                if audio_b64:
                    return base64.b64decode(audio_b64)
        except Exception as e:
            print(f"Google Cloud TTS REST synthesis failed: {e}")

    return None

def speak_and_get_url(text: str) -> str:
    """
    Synthesizes text to speech:
    1. Primary: ElevenLabs API (custom trained voice)
    2. Secondary: Google Cloud Text-to-Speech (Neural2 Indian English)
    3. Tertiary: Mock silent audio frame
    Uploads the MP3 file to Google Cloud Storage (or falls back to local static URL)
    and returns a public, streamable audio URL.
    """
    cleanup_old_audio_files()
    fname = f"resp_{uuid.uuid4().hex}.mp3"
    blob_name = f"tts-audio/{fname}"
    
    # 1. PRIMARY: ElevenLabs
    api_key = (getattr(config, "ELEVENLABS_API_KEY", "") or "").strip()
    voice_id = (getattr(config, "ELEVENLABS_VOICE_ID", "") or "").strip()
    if api_key and voice_id:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?optimize_streaming_latency=4"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": getattr(config, "ELEVENLABS_MODEL_ID", "eleven_multilingual_v2") or "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.8}
        }
        try:
            resp = _tts_session.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            return storage_service.upload_audio_bytes(resp.content, blob_name)
        except Exception as e:
            print(f"TTS Notice: ElevenLabs failed or unavailable ({e}). Falling back to secondary (Google Cloud TTS).")
            
    # 2. SECONDARY: Google Cloud Text-to-Speech (Cloud Run native)
    try:
        google_audio = synthesize_with_google_tts(text)
        if google_audio:
            print("TTS: Synthesized successfully via Google Cloud Text-to-Speech.")
            return storage_service.upload_audio_bytes(google_audio, blob_name)
    except Exception as e:
        print(f"TTS Notice: Google Cloud TTS failed ({e}).")

    # 3. TERTIARY: Mock audio response (valid MPEG 1 Layer III frame)
    try:
        silent_frame = b"\xff\xfb\x90\x00" + b"\x00" * 32 + b"\x55" * 381
        return storage_service.upload_audio_bytes(silent_frame * 38, blob_name)
    except Exception as e:
        print(f"TTS Fallback failed: {e}")
        return ""
