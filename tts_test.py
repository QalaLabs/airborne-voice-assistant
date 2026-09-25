import requests
import os
import time
import uuid
import config
import storage_service

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

def speak_and_get_url(text: str) -> str:
    """
    Synthesizes the text to speech using ElevenLabs API or edge-tts.
    Uploads the MP3 file to Google Cloud Storage (or falls back to local static URL)
    and returns a public, streamable audio URL.
    """
    cleanup_old_audio_files()
    fname = f"resp_{uuid.uuid4().hex}.mp3"
    blob_name = f"tts-audio/{fname}"
    
    # Check if ElevenLabs is configured
    api_key = (config.ELEVENLABS_API_KEY or "").strip()
    voice_id = (config.ELEVENLABS_VOICE_ID or "").strip() or "eJTrVjiaPKqBMpMujQdM"
    if api_key and voice_id:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": config.ELEVENLABS_MODEL_ID or "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            return storage_service.upload_audio_bytes(resp.content, blob_name)
        except Exception as e:
            print(f"TTS Error: ElevenLabs failed ({e}). Falling back to free Indian neural voice.")
            
    # Free Indian Neural Voice via edge-tts
    os.makedirs("static", exist_ok=True)
    local_path = os.path.join("static", fname)
    try:
        import asyncio
        import edge_tts
        indian_voice = getattr(config, "TTS_VOICE", "en-IN-PrabhatNeural")
        
        async def _synthesize():
            communicate = edge_tts.Communicate(text, indian_voice)
            await communicate.save(local_path)
            
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_synthesize())).result()
            else:
                loop.run_until_complete(_synthesize())
        except RuntimeError:
            asyncio.run(_synthesize())
            
        return storage_service.upload_audio_file(local_path, blob_name)
    except Exception as e:
        print(f"TTS Error (edge-tts): {e}")

    # Fallback / Mock audio response (valid MPEG 1 Layer III silent frame header)
    try:
        silent_frame = b"\xff\xfb\x90\x64" + b"\x00" * 140
        return storage_service.upload_audio_bytes(silent_frame * 10, blob_name)
    except Exception as e:
        print(f"TTS Fallback failed: {e}")
        return ""
