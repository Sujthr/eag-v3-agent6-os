#Requires -Version 5.1
<#
.SYNOPSIS
    Start Agent6 OS — LLM Gateway V3 + Streamlit UI.
.EXAMPLE
    .\start.ps1
    .\start.ps1 -GatewayPort 8102 -UIPort 8502
#>
param(
    [int]$GatewayPort = 8101,
    [int]$UIPort      = 8501,
    [int]$WarmupSecs  = 4
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectDir = $PSScriptRoot
$GatewayDir = Join-Path $ProjectDir ".." "5e4a8833-292d-4ce5-be97-749c7656bdbf" "llm_gatewayV3"
$GatewayDir = (Resolve-Path $GatewayDir).Path
$EnvFile    = Join-Path $ProjectDir ".." ".env"
$PidFile    = Join-Path $ProjectDir ".pids.json"

function Write-Step([string]$msg) {
    Write-Host "  $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg) {
    Write-Host "  $msg" -ForegroundColor Green
}
function Write-Warn([string]$msg) {
    Write-Host "  [WARN] $msg" -ForegroundColor Yellow
}
function Write-Fail([string]$msg) {
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host "  Agent6 OS — Start Script" -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host ""

# ── Pre-flight checks ─────────────────────────────────────────────────────
if (-not (Test-Path (Join-Path $GatewayDir "main.py"))) {
    Write-Fail "Gateway main.py not found at: $GatewayDir"
    exit 1
}

if (-not (Test-Path $EnvFile)) {
    Write-Warn ".env not found at: $EnvFile"
    Write-Warn "Copy .env.example to the Resubmission root and add your API keys."
    Write-Host ""
}

# Check python available
try { $null = Get-Command python -ErrorAction Stop }
catch { Write-Fail "python not found in PATH"; exit 1 }

# Check streamlit available
try { $null = Get-Command streamlit -ErrorAction Stop }
catch { Write-Fail "streamlit not found. Run: pip install streamlit"; exit 1 }

# ── Kill anything already on the ports ────────────────────────────────────
foreach ($port in @($GatewayPort, $UIPort)) {
    # Where-Object returns plain strings; Select-String returns MatchInfo objects
    # which behave unexpectedly when split.
    $lines = netstat -ano 2>$null | Where-Object { $_ -match ":$port\s+\S+\s+LISTENING" }
    foreach ($line in $lines) {
        $parts = $line.Trim() -split '\s+'
        $pid_  = $parts[-1]
        if ($pid_ -match '^\d+$') {
            Write-Warn "Port $port in use by PID $pid_ — stopping it first."
            Stop-Process -Id ([int]$pid_) -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 800
        }
    }
}

# ── Start LLM Gateway V3 ─────────────────────────────────────────────────
Write-Step "Starting LLM Gateway V3 on port $GatewayPort..."

$gwEnv = @{"GATEWAY_V3_PORT" = "$GatewayPort"}
$gwProc = Start-Process python `
    -ArgumentList "main.py" `
    -WorkingDirectory $GatewayDir `
    -WindowStyle Normal `
    -PassThru

Write-OK "Gateway started (PID $($gwProc.Id))"
Write-Step "Waiting $WarmupSecs seconds for gateway to initialise..."
Start-Sleep -Seconds $WarmupSecs

# Verify gateway is up
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$GatewayPort/v1/providers" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
    Write-OK "Gateway responded OK"
} catch {
    Write-Warn "Gateway health check failed — it may still be starting."
}

# ── Start Streamlit UI ────────────────────────────────────────────────────
Write-Step "Starting Streamlit UI on port $UIPort..."

$uiProc = Start-Process streamlit `
    -ArgumentList "run", "ui.py", "--server.port", "$UIPort" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Normal `
    -PassThru

Write-OK "Streamlit started (PID $($uiProc.Id))"

# ── Save PIDs ─────────────────────────────────────────────────────────────
$pidData = @{
    gateway   = $gwProc.Id
    streamlit = $uiProc.Id
    started   = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    ports     = @{gateway = $GatewayPort; ui = $UIPort}
}
$pidData | ConvertTo-Json | Out-File $PidFile -Encoding utf8

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  Services running!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Gateway  : http://localhost:$GatewayPort" -ForegroundColor White
Write-Host "  UI       : http://localhost:$UIPort" -ForegroundColor White
Write-Host "  PIDs     : gateway=$($gwProc.Id) streamlit=$($uiProc.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "  To stop  : .\stop.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
