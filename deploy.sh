#!/bin/bash
# =========================================================
# 🚀 Google Cloud Run Automated Deployment Script (Linux/macOS)
# Airborne Aviation AI Voice Assistant
# =========================================================

set -e

SERVICE_NAME="airborne-voice-assistant"
PROJECT_ID="airborne-aviation-505100"
REGION="asia-south1"
CLOUD_SQL_INSTANCE="airborne-aviation-505100:asia-south1:airborne-db"
BUCKET_NAME="airborne-aviation-media-prod"

# Requires Secret Manager secrets:
#   INTERNAL_RAG_SHARED_SECRET — auth for /internal/rag/query (X-Internal-Secret)
#   API_SHARED_SECRET — guards /api/calls/* and /webhooks/new-lead (X-API-Key)
# Create once with:
#   echo -n "<random-secret>" | gcloud secrets create INTERNAL_RAG_SHARED_SECRET --data-file=- --project $PROJECT_ID
# ADK / Agent Engine assets were archived under ../adk-archive/

echo "================================================="
echo "Starting Cloud Run Deployment for $SERVICE_NAME"
echo "Project: $PROJECT_ID | Region: $REGION"
echo "================================================="

# 1. Enable required GCP Services
echo "📌 Step 1: Ensuring GCP Cloud Run, Cloud Build & Storage APIs are enabled..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com sqladmin.googleapis.com --project $PROJECT_ID

# 2. Build and Deploy to Cloud Run directly from source
echo "📌 Step 2: Building container and deploying to Cloud Run ($REGION)..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --project $PROJECT_ID \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 1 \
    --no-cpu-throttling \
    --add-cloudsql-instances $CLOUD_SQL_INSTANCE \
    --set-env-vars "APP_URL=https://airborne-voice-assistant-368523757732.asia-south1.run.app,GCS_BUCKET_NAME=$BUCKET_NAME,GCP_PROJECT=$PROJECT_ID,GCP_LOCATION=$REGION,GEMINI_MODEL=gemini-3.1-flash-lite,OPENAI_MODEL=gpt-4o-mini,ELEVENLABS_MODEL_ID=eleven_flash_v2_5,ELEVENLABS_VOICE_ID=eJTrVjiaPKqBMpMujQdM,AGENT_ID=edc5b96c-9e10-4b1f-b2b0-528da3c30978,TELECMI_PIOPIY_APP_ID=edc5b96c-9e10-4b1f-b2b0-528da3c30978,TELECMI_PHONE_NUMBER=917948568600,PIOPIY_SIP_URL=qalalabs_airborne.piopiy.io,PIOPIY_TOKEN_NAME=AAA_V4_Nov14,CAMPUS_BOOKING_URL=https://calendly.com/airborne-aviation/campus-visit,CALL_VERIFICATION_TIMEOUT_SECS=35.0,FORCE_PCMO_OUTBOUND=false,MAX_CONCURRENT_CALLS=4" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,TELECMI_APP_ID=TELECMI_APP_ID:latest,TELECMI_APP_SECRET=TELECMI_APP_SECRET:latest,TELECMI_TOKEN=TELECMI_TOKEN:latest,ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,INTERNAL_RAG_SHARED_SECRET=INTERNAL_RAG_SHARED_SECRET:latest,API_SHARED_SECRET=API_SHARED_SECRET:latest"

# 3. Retrieve live service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --project $PROJECT_ID --platform managed --region $REGION --format 'value(status.url)')

echo ""
echo "================================================="
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "Service URL: $SERVICE_URL"
echo "================================================="
echo ""
echo "👉 TeleCMI & CRM Webhook Endpoints:"
echo "   - Inbound TeleCMI Answer:   $SERVICE_URL/telecmi/answer"
echo "   - TeleCMI Events / Hangup:  $SERVICE_URL/telecmi/events"
echo "   - New Lead Intake Webhook:  $SERVICE_URL/webhooks/new-lead"
echo "   - Twilio Voice Entrypoint:  $SERVICE_URL/answer-call"
echo ""
