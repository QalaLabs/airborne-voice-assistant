import requests
try:
    import speech_recognition as sr
except ImportError:
    sr = None
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None
import os, tempfile
import config

def listen(recording_url: str) -> str:
    """
    Downloads recording from TeleCMI / Twilio / local audio, converts to WAV if needed,
    and transcribes using SpeechRecognition with Google Speech recognition (en-IN).
    """
    if not recording_url:
        return ""

    tmp_files_to_clean = []
    tmp_wav_path = None

    try:
        # 1. Handle local file paths directly
        if os.path.exists(recording_url):
            source_path = recording_url
        else:
            fetch_url = recording_url
            if (fetch_url.startswith("http://") or fetch_url.startswith("https://")) and "twilio" in fetch_url.lower():
                if not fetch_url.endswith(".wav") and not fetch_url.endswith(".mp3"):
                    fetch_url += ".wav"

            print(f"STT: Downloading recording from {fetch_url}...")
            
            auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN) if ("twilio" in fetch_url and config.TWILIO_ACCOUNT_SID) else None
            try:
                response = requests.get(fetch_url, auth=auth, timeout=15)
                if response.status_code != 200:
                    response = requests.get(fetch_url, timeout=15)
                    if response.status_code != 200:
                        print(f"STT: Failed to download audio. Status: {response.status_code}")
                        return ""
            except Exception as e:
                print(f"STT: Failed to fetch audio ({e})")
                return ""

            suffix = ".mp3" if (".mp3" in fetch_url.lower() or response.content.startswith(b"ID3") or response.content[:2] == b"\xff\xfb") else ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                tmp_file.write(response.content)
                source_path = tmp_file.name
                tmp_files_to_clean.append(source_path)

        # 2. Convert MP3 to WAV if necessary
        if source_path.lower().endswith(".mp3") or (open(source_path, "rb").read(3) == b"ID3"):
            if AudioSegment:
                wav_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                wav_temp.close()
                tmp_wav_path = wav_temp.name
                tmp_files_to_clean.append(tmp_wav_path)
                audio_seg = AudioSegment.from_file(source_path)
                audio_seg.export(tmp_wav_path, format="wav")
            else:
                tmp_wav_path = source_path
        else:
            tmp_wav_path = source_path

        if not sr:
            print("STT: SpeechRecognition library not available.")
            return ""

        recognizer = sr.Recognizer()
        with sr.AudioFile(tmp_wav_path) as source:
            # Do NOT discard the first 200ms with adjust_for_ambient_noise;
            # telephony carrier audio is already isolated.
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language="en-IN")
        print("User said (STT):", text)
        return text

    except sr.UnknownValueError:
        print("STT: Speech Recognition could not understand the audio.")
        return ""
    except sr.RequestError as e:
        print(f"STT Error: Could not request results from STT service: {e}")
        return ""
    except Exception as e:
        print(f"STT Processing Error: {e}")
        return ""
    finally:
        for f in tmp_files_to_clean:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
