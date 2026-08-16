# =========================================================
# 🚀 Google Cloud Run Automated Deployment Script (Windows PowerShell)
# Airborne Aviation AI Voice Assistant
# =========================================================

$ErrorActionPreference = "Stop"

$ServiceName = "airborne-voice-assistant"
$Region = "asia-south1"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Starting Cloud Run Deployment for $ServiceName" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Enable required GCP Services
Write-Host "📌 Step 1: Enabling GCP Cloud Run & Container Registry APIs..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

# 2. Build and Deploy to Cloud Run directly from source
Write-Host "📌 Step 2: Building and deploying container to Cloud Run ($Region)..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --memory 1Gi `
    --cpu 1 `
    --min-instances 1 `
    --no-cpu-throttling

# 3. Retrieve live service URL
$ServiceUrl = (gcloud run services describe $ServiceName --platform managed --region $Region --format 'value(status.url)').Trim()

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "🎉 DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "👉 Webhook Endpoints to configure in TeleCMI & Lead Forms:" -ForegroundColor Cyan
Write-Host "   - Inbound TeleCMI Webhook:  $ServiceUrl/answer-call" -ForegroundColor White
Write-Host "   - Outbound Campaign Lead:   $ServiceUrl/webhooks/new-lead" -ForegroundColor White
Write-Host "   - Process Audio Webhook:    $ServiceUrl/process-recording" -ForegroundColor White
Write-Host ""
