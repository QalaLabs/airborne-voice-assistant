#!/bin/bash
# =========================================================
# 🚀 Google Cloud Run Automated Deployment Script (Linux/macOS)
# Airborne Aviation AI Voice Assistant
# =========================================================

set -e

SERVICE_NAME="airborne-voice-assistant"
REGION="asia-south1"

echo "================================================="
echo "Starting Cloud Run Deployment for $SERVICE_NAME"
echo "================================================="

# 1. Enable required GCP Services
echo "📌 Step 1: Enabling GCP Cloud Run & Container Registry APIs..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 2. Build and Deploy to Cloud Run directly from source
echo "📌 Step 2: Building and deploying container to Cloud Run ($REGION)..."
gcloud run deploy $SERVICE_NAME \
    --source . \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --port 8000 \
    --memory 1Gi \
    --cpu 1

# 3. Retrieve live service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')

echo ""
echo "================================================="
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "Service URL: $SERVICE_URL"
echo "================================================="
echo ""
echo "👉 Webhook Endpoints to configure in TeleCMI & Lead Forms:"
echo "   - Inbound TeleCMI Webhook:  $SERVICE_URL/answer-call"
echo "   - Outbound Campaign Lead:   $SERVICE_URL/webhooks/new-lead"
echo "   - Process Audio Webhook:    $SERVICE_URL/process-recording"
echo ""
