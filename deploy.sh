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
    --memory 1Gi \
    --cpu 1 \
    --min-instances 1 \
    --max-instances 10 \
    --no-cpu-throttling \
    --add-cloudsql-instances $CLOUD_SQL_INSTANCE \
    --set-env-vars "APP_URL=https://airborne-voice-assistant-368523757732.asia-south1.run.app,GCS_BUCKET_NAME=$BUCKET_NAME,GCP_PROJECT=$PROJECT_ID,GEMINI_MODEL=gemini-2.0-flash,OPENAI_MODEL=gpt-4o-mini,ELEVENLABS_MODEL_ID=eleven_multilingual_v2,CAMPUS_BOOKING_URL=https://calendly.com/airborne-aviation/campus-visit" \
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,TELECMI_APP_ID=TELECMI_APP_ID:latest,TELECMI_APP_SECRET=TELECMI_APP_SECRET:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest"

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
