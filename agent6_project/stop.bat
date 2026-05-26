@echo off
setlocal

title Agent6 Stop

set "PROJECT_DIR=%~dp0"
set "PID_FILE=%PROJECT_DIR%.pids"

echo.
echo =========================================
echo   Agent6 OS - Stop Script
echo =========================================
echo.

REM ── Kill by window title ──────────────────────────────────────────────────
echo Stopping LLM Gateway V3...
taskkill /FI "WINDOWTITLE eq LLM_GATEWAY_V3" /T /F 2>nul
if %ERRORLEVEL% EQU 0 (
    echo   Gateway stopped.
) else (
    echo   Gateway was not running (or already stopped).
)

echo Stopping Streamlit UI...
taskkill /FI "WINDOWTITLE eq AGENT6_UI" /T /F 2>nul
if %ERRORLEVEL% EQU 0 (
    echo   Streamlit UI stopped.
) else (
    echo   Streamlit UI was not running (or already stopped).
)

REM ── Also kill lingering python/streamlit processes on the ports ───────────
echo Cleaning up port 8101 (Gateway)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8101 " ^| findstr "LISTENING" 2^>nul') do (
    echo   Killing PID %%p on port 8101
    taskkill /PID %%p /F 2>nul
)

echo Cleaning up port 8501 (Streamlit)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501 " ^| findstr "LISTENING" 2^>nul') do (
    echo   Killing PID %%p on port 8501
    taskkill /PID %%p /F 2>nul
)

REM ── Clean up .pids file ───────────────────────────────────────────────────
if exist "%PID_FILE%" (
    del /f /q "%PID_FILE%"
)

echo.
echo =========================================
echo   All Agent6 services stopped.
echo =========================================
echo.
timeout /t 2 /nobreak > nul

endlocal
