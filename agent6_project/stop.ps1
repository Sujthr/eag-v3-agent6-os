#Requires -Version 5.1
<#
.SYNOPSIS
    Stop Agent6 OS — kills LLM Gateway V3 and Streamlit UI.
.EXAMPLE
    .\stop.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

$ProjectDir = $PSScriptRoot
$PidFile    = Join-Path $ProjectDir ".pids.json"

function Write-Step([string]$msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }

Write-Host ""
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host "  Agent6 OS — Stop Script" -ForegroundColor Magenta
Write-Host "=========================================" -ForegroundColor Magenta
Write-Host ""

$stopped = $false

# ── Stop by saved PIDs ────────────────────────────────────────────────────
if (Test-Path $PidFile) {
    Write-Step "Reading PIDs from .pids.json..."
    try {
        $pidData = Get-Content $PidFile -Raw | ConvertFrom-Json

        foreach ($label in @("gateway", "streamlit")) {
            $pid_ = $pidData.$label
            if ($pid_) {
                $proc = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Step "Stopping $label (PID $pid_)..."
                    Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
                    Write-OK "$label stopped."
                } else {
                    Write-Warn "$label PID $pid_ is not running (already stopped?)."
                }
            }
        }
        $stopped = $true
    } catch {
        Write-Warn "Could not parse .pids.json: $_"
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# ── Fallback: kill by window title ────────────────────────────────────────
if (-not $stopped) {
    Write-Step "No .pids.json found — killing by window title..."
    $titles = @("LLM_GATEWAY_V3", "AGENT6_UI")
    foreach ($title in $titles) {
        Get-Process | Where-Object { $_.MainWindowTitle -like "*$title*" } | ForEach-Object {
            Write-Step "Stopping PID $($_.Id) ($title)..."
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-OK "Stopped."
        }
    }
}

# ── Port-based cleanup ────────────────────────────────────────────────────
Write-Step "Cleaning up ports 8101 and 8501..."
foreach ($port in @(8101, 8501)) {
    $netOutput = netstat -ano 2>$null | Select-String ":$port\s.*LISTENING"
    if ($netOutput) {
        $pid_ = ($netOutput.ToString().Trim() -split '\s+')[-1]
        if ($pid_ -match '^\d+$' -and [int]$pid_ -gt 0) {
            Write-Step "  Port $port → killing PID $pid_"
            Stop-Process -Id ([int]$pid_) -Force -ErrorAction SilentlyContinue
            Write-OK "  Port $port freed."
        }
    }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  All Agent6 services stopped." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
