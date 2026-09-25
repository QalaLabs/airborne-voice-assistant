# =========================================================
# 🚀 Google Cloud Run Automated Deployment Script (Windows PowerShell)
# Airborne Aviation AI Voice Assistant
# =========================================================

$ErrorActionPreference = "Stop"

$ServiceName = "airborne-voice-assistant"
$ProjectId = "airborne-aviation-505100"
$Region = "asia-south1"
$CloudSqlInstance = "airborne-aviation-505100:asia-south1:airborne-db"
$BucketName = "airborne-aviation-media-prod"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Starting Cloud Run Deployment for $ServiceName" -ForegroundColor Cyan
Write-Host "Project: $ProjectId | Region: $Region" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Enable required GCP Services
Write-Host "📌 Step 1: Ensuring GCP APIs are enabled..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com sqladmin.googleapis.com --project $ProjectId

# 2. Build and Deploy to Cloud Run directly from source
Write-Host "📌 Step 2: Building container and deploying to Cloud Run ($Region)..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --source . `
    --project $ProjectId `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 1 `
    --max-instances 10 `
    --no-cpu-throttling `
    --add-cloudsql-instances $CloudSqlInstance `
    --set-env-vars "APP_URL=https://airborne-voice-assistant-368523757732.asia-south1.run.app,GCS_BUCKET_NAME=$BucketName,GCP_PROJECT=$ProjectId,GEMINI_MODEL=gemini-flash-latest,OPENAI_MODEL=gpt-4o-mini,ELEVENLABS_MODEL_ID=eleven_multilingual_v2,ELEVENLABS_VOICE_ID=eJTrVjiaPKqBMpMujQdM,TELECMI_SIP_USER=airborneaviation,TELECMI_NAMESPACE_URL=qalalabs_airborne.piopiy.io,CAMPUS_BOOKING_URL=https://calendly.com/airborne-aviation/campus-visit" `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,TELECMI_APP_ID=TELECMI_APP_ID:latest,TELECMI_APP_SECRET=TELECMI_APP_SECRET:latest,TELECMI_TOKEN=TELECMI_TOKEN:latest,TELECMI_SIP_PASS=TELECMI_SIP_PASS:latest,ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest"

# 3. Retrieve live service URL
$ServiceUrl = (gcloud run services describe $ServiceName --project $ProjectId --platform managed --region $Region --format 'value(status.url)').Trim()

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "🎉 DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "👉 TeleCMI & CRM Webhook Endpoints:" -ForegroundColor Cyan
Write-Host "   - Inbound TeleCMI Answer:   $ServiceUrl/telecmi/answer" -ForegroundColor White
Write-Host "   - TeleCMI Events / Hangup:  $ServiceUrl/telecmi/events" -ForegroundColor White
Write-Host "   - New Lead Intake Webhook:  $ServiceUrl/webhooks/new-lead" -ForegroundColor White
Write-Host "   - Twilio Voice Entrypoint:  $ServiceUrl/answer-call" -ForegroundColor White
Write-Host ""
