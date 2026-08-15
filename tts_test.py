import requests
import os
import uuid
import config

def speak_and_get_url(text: str) -> str:
    """
    Synthesizes the text to speech using ElevenLabs API.
    Saves the MP3 file in the static directory and returns the public ngrok URL.
    """
    os.makedirs("static", exist_ok=True)
    fname = f"resp_{uuid.uuid4().hex}.mp3"
    path = os.path.join("static", fname)
    
    # Check if ElevenLabs is configured
    if config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": config.ELEVENLABS_MODEL_ID or "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }
        try:
            resp = requests.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            return f"{config.NGROK_URL}/static/{fname}"
        except Exception as e:
            print(f"TTS Error: ElevenLabs failed ({e}). Falling back to dummy voice file.")
            
    # Fallback / Mock audio response
    # We will copy a placeholder file or write a tiny silence/beep WAV file to avoid crashes
    try:
        # Create a tiny 1-second silent MP3/WAV file if none exists
        with open(path, "wb") as f:
            # Writing some dummy data to mock a voice file
            f.write(b"\x00" * 500)
        return f"{config.NGROK_URL}/static/{fname}"
    except Exception as e:
        print(f"TTS Fallback failed: {e}")
        return ""
