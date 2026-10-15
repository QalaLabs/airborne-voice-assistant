# Use official Python 3.11 image (lightweight)
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app

# Set working directory
WORKDIR $APP_HOME

# Install system dependencies (needed for audio processing libraries like pydub/librosa)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    portaudio19-dev \
    gcc \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Bake the Faster-Whisper 'base' model into the image so cold starts do not wait on (or fail
# against) Hugging Face. The second command fails the build if the model can't load offline.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"     && HF_HUB_OFFLINE=1 python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
ENV HF_HUB_OFFLINE=1

# Copy application source code
COPY . .

# Expose port
EXPOSE 8000

# Run FastAPI app with Uvicorn on dynamic PORT (default 8000)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
