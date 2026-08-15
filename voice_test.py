import requests
import speech_recognition as sr
import os, tempfile
import config

def listen(recording_url):
    """
    Downloads recording from Twilio, converts it using SpeechRecognition,
    and returns the transcribed text.
    """
    if not recording_url:
        return ""
        
    if not recording_url.endswith(".wav"):
        recording_url += ".wav"
        
    print(f"STT: Downloading recording from {recording_url}...")
    
    # Download the WAV file using Twilio Credentials
    try:
        response = requests.get(
            recording_url, 
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN) if config.TWILIO_ACCOUNT_SID else None
        )
        if response.status_code != 200:
            print("Error downloading recording:", response.text)
            # Try downloading without authentication in case of public access/local test
            response = requests.get(recording_url)
            if response.status_code != 200:
                return ""
    except Exception as e:
        print(f"Failed to fetch audio: {e}")
        return ""
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(response.content)
        tmp_file_path = tmp_file.name

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(tmp_file_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio_data = recognizer.record(source)
            
        # Transcribe using Google Speech Recognition
        # Set language="hi-IN" or default to recognize Hindi/English mixture
        text = recognizer.recognize_google(audio_data, language="en-IN")
        print("User said (STT):", text)
        return text
    except sr.UnknownValueError:
        print("STT: Speech Recognition could not understand the audio.")
        return ""
    except sr.RequestError as e:
        print(f"STT Error: Could not request results; {e}")
        return ""
    finally:
        try:
            os.remove(tmp_file_path)
        except Exception:
            pass
