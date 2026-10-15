import os
import requests
from io import BytesIO
import config

try:
    from google.cloud import storage
except ImportError:
    storage = None

GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "airborne-aviation-media-prod")
GCP_PROJECT = os.environ.get("GCP_PROJECT", "airborne-aviation-505100")

_client = None

def get_storage_client():
    global _client
    if _client is None and storage:
        try:
            _client = storage.Client(project=GCP_PROJECT)
        except Exception as e:
            print(f"GCS Client Init Error: {e}")
            _client = None
    return _client

def upload_audio_bytes(audio_bytes: bytes, destination_blob_name: str, content_type: str = "audio/mpeg") -> str:
    """
    Uploads audio bytes to Google Cloud Storage bucket.
    Returns the permanent public HTTPS URL, or falls back to local static URL.
    """
    client = get_storage_client()
    if client and GCS_BUCKET_NAME:
        try:
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_string(audio_bytes, content_type=content_type)
            public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
            return public_url
        except Exception as e:
            print(f"GCS Upload Error (bytes): {e}")

    # Local fallback
    os.makedirs("static", exist_ok=True)
    local_filename = os.path.basename(destination_blob_name)
    local_path = os.path.join("static", local_filename)
    with open(local_path, "wb") as f:
        f.write(audio_bytes)

    base_url = config.NGROK_URL.rstrip("/") if config.NGROK_URL else ""
    return f"{base_url}/static/{local_filename}"

def upload_audio_file(local_path: str, destination_blob_name: str, content_type: str = "audio/mpeg") -> str:
    """
    Uploads a local audio file to Google Cloud Storage bucket.
    Returns the permanent public HTTPS URL.
    """
    client = get_storage_client()
    if client and GCS_BUCKET_NAME and os.path.exists(local_path):
        try:
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(local_path, content_type=content_type)
            public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
            return public_url
        except Exception as e:
            print(f"GCS Upload Error (file): {e}")

    base_url = config.NGROK_URL.rstrip("/") if config.NGROK_URL else ""
    filename = os.path.basename(local_path)
    return f"{base_url}/static/{filename}"

# Hosts (and their subdomains) recordings may be downloaded from. Extend via the
# RECORDING_HOST_ALLOWLIST env var (comma-separated) if the carrier uses another domain.
_DEFAULT_RECORDING_HOSTS = ("telecmi.com", "piopiy.com", "twilio.com", "storage.googleapis.com")

def _recording_hosts():
    extra = [h.strip().lower() for h in os.environ.get("RECORDING_HOST_ALLOWLIST", "").split(",") if h.strip()]
    return tuple(_DEFAULT_RECORDING_HOSTS) + tuple(extra)

def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)

def is_safe_recording_url(url: str) -> bool:
    """
    Guards the server-side download of a caller-supplied recording URL (SSRF defence):
    https only, hostname on the allowlist, and every resolved address must be public.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            return False
        if not any(_host_matches(host, d) for d in _recording_hosts()):
            return False
        for info in socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False

def upload_call_recording_from_url(recording_url: str, call_identifier: str) -> str:
    """
    Downloads call recording from TeleCMI / Twilio and archives it to GCS.
    Uses unique timestamp and random identifier to prevent overwriting repeat calls.
    Returns the permanent Cloud Storage public URL.
    """
    if not recording_url:
        return ""

    if not is_safe_recording_url(recording_url):
        print(f"Recording URL rejected (not https / not an allowed carrier host / non-public address): {recording_url}")
        return recording_url

    import time
    import uuid
    timestamp = int(time.time())
    rand_suffix = uuid.uuid4().hex[:6]
    blob_name = f"call-recordings/call_{call_identifier}_{timestamp}_{rand_suffix}.mp3"
    client = get_storage_client()
    if client and GCS_BUCKET_NAME:
        try:
            print(f"Downloading call recording from {recording_url}...")
            from urllib.parse import urlparse
            host = (urlparse(recording_url).hostname or "").lower()
            # Twilio credentials go only to Twilio's own domain, never to any URL that merely contains "twilio".
            auth = (config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN) if (_host_matches(host, "twilio.com") and config.TWILIO_ACCOUNT_SID) else None
            resp = requests.get(recording_url, auth=auth, timeout=30, allow_redirects=False)
            if resp.is_redirect:
                # Follow a single redirect, but only to another safe host and without credentials.
                target = requests.compat.urljoin(recording_url, resp.headers.get("Location", ""))
                if not is_safe_recording_url(target):
                    raise ValueError(f"redirect to disallowed URL {target}")
                resp = requests.get(target, timeout=30, allow_redirects=False)
            resp.raise_for_status()
            
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(blob_name)
            blob.upload_from_string(resp.content, content_type="audio/mpeg")
            public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"
            print(f"Recording archived to Cloud Storage: {public_url}")
            return public_url
        except Exception as e:
            print(f"Failed to archive call recording to GCS ({e}). Retaining original URL.")
            return recording_url

    return recording_url
