<#
.SYNOPSIS
    Rule 7 Guardrail: Safely uploads or updates secrets in GCP Secret Manager.
.DESCRIPTION
    PowerShell pipeline serializes byte arrays as newline-separated ASCII integers, corrupting JWT tokens,
    passwords, and API keys. This script enforces Rule 7 by writing the exact string payload to a clean
    temporary UTF-8 file (without BOM and without trailing newline), uploading it using --data-file, and
    immediately securely scrubbing and deleting the file.
.PARAMETER SecretName
    Name of the secret in GCP Secret Manager (e.g., AGENT_TOKEN, GEMINI_API_KEY).
.PARAMETER SecretValue
    Secret payload string. If omitted, prompts securely.
.PARAMETER ProjectId
    GCP Project ID (default: airborne-aviation-505100).
.PARAMETER Account
    GCP authenticated account (default: adminairborne@gmail.com).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$SecretName,

    [Parameter(Mandatory = $false, Position = 1)]
    [string]$SecretValue,

    [Parameter(Mandatory = $false)]
    [string]$ProjectId = "airborne-aviation-505100",

    [Parameter(Mandatory = $false)]
    [string]$Account = "adminairborne@gmail.com"
)

$ErrorActionPreference = "Stop"

if (-not $SecretValue) {
    Write-Host "Enter secret value for '$SecretName': " -NoNewline -ForegroundColor Yellow
    $SecretValue = Read-Host
}

if ([string]::IsNullOrEmpty($SecretValue)) {
    Write-Error "Secret value cannot be empty."
    exit 1
}

# Unique temp file path in local temp folder
$tempFile = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "gcp_sec_$([System.Guid]::NewGuid().ToString('N')).tmp")

try {
    # Rule 7 Invariant: UTF-8 without BOM and without trailing newline (\r\n)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempFile, $SecretValue, $utf8NoBom)

    Write-Host "🔐 Rule 7 Guardrail: Uploading '$SecretName' to Secret Manager (Project: $ProjectId)..." -ForegroundColor Cyan

    # Check if secret already exists
    $exists = $false
    try {
        & gcloud secrets describe $SecretName --project=$ProjectId --account=$Account --format="value(name)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $exists = $true
        }
    } catch {
        $exists = $false
    }

    if ($exists) {
        Write-Host "Adding new version to existing secret '$SecretName'..." -ForegroundColor Cyan
        & gcloud secrets versions add $SecretName --data-file="$tempFile" --project=$ProjectId --account=$Account
    } else {
        Write-Host "Creating new secret '$SecretName'..." -ForegroundColor Cyan
        & gcloud secrets create $SecretName --data-file="$tempFile" --project=$ProjectId --account=$Account --replication-policy="automatic"
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Successfully updated secret '$SecretName' with zero byte/encoding corruption!" -ForegroundColor Green
    } else {
        Write-Error "Failed to upload secret '$SecretName' (exit code: $LASTEXITCODE)."
    }
} finally {
    if (Test-Path $tempFile) {
        # Securely overwrite before removing
        try {
            [System.IO.File]::WriteAllText($tempFile, "0000000000000000", [System.Text.Encoding]::ASCII)
        } catch {}
        Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
    }
}
