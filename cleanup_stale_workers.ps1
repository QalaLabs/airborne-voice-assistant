# ==============================================================================
# Rule 1 Guardrail: Terminate Stale Piopiy Background Workers
# Prevents LiveKit DuplicateIdentity call drops
# ==============================================================================

Write-Host "🔍 Scanning for stale piopiy_agent_worker processes..." -ForegroundColor Cyan

$terminated = 0

# 1. Check PID lock file
$lockFile = Join-Path $PSScriptRoot ".piopiy_worker.lock"
if (Test-Path $lockFile) {
    try {
        $pidText = (Get-Content $lockFile -Raw).Trim()
        if ($pidText -match "^\d+$") {
            $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "Terminating worker from lockfile (PID: $pidText)..." -ForegroundColor Yellow
                Stop-Process -Id ([int]$pidText) -Force
                $terminated++
            }
        }
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warning "Could not clean lockfile: $_"
    }
}

# 2. Terminate any python processes running piopiy_agent_worker
try {
    $workers = Get-CimInstance Win32_Process | Where-Object { 
        $_.CommandLine -like "*piopiy_agent_worker*" -and $_.ProcessId -ne $PID 
    }
    foreach ($w in $workers) {
        Write-Host "Terminating background worker (PID: $($w.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $w.ProcessId -Force
        $terminated++
    }
} catch {
    Write-Warning "Process query notice: $_"
}

if ($terminated -gt 0) {
    Write-Host "✅ Successfully terminated $terminated stale worker process(es). Ready to launch clean worker." -ForegroundColor Green
} else {
    Write-Host "✅ No stale workers found. Clean environment." -ForegroundColor Green
}
