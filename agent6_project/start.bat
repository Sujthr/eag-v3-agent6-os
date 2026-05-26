@echo off
setlocal

title Agent6 Launcher

set "PROJECT_DIR=%~dp0"
set "GATEWAY_DIR=%PROJECT_DIR%..\5e4a8833-292d-4ce5-be97-749c7656bdbf\llm_gatewayV3"
set "ENV_FILE=%PROJECT_DIR%..\.env"
set "PID_FILE=%PROJECT_DIR%.pids"

echo.
echo =========================================
echo   Agent6 OS - Start Script
echo =========================================
echo.

REM Check .env exists
if not exist "%ENV_FILE%" (
    echo [WARNING] .env not found at: %ENV_FILE%
    echo           Copy .env.example to the Resubmission root and add your API keys.
    echo           Continuing anyway - gateway may fail without keys.
    echo.
)

REM Check gateway directory exists
if not exist "%GATEWAY_DIR%\main.py" (
    echo [ERROR] Gateway not found at: %GATEWAY_DIR%
    pause
    exit /b 1
)

REM Clean up any stale .pids file
if exist "%PID_FILE%" del /f /q "%PID_FILE%"

REM ── Kill any process already on port 8101 (gateway) ──────────────────────
echo Checking port 8101...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8101 " ^| findstr "LISTENING"') do (
    echo   Stopping old gateway on port 8101 ^(PID %%p^)...
    taskkill /PID %%p /F >nul 2>&1
)

REM ── Kill any process already on port 8501 (Streamlit) ────────────────────
echo Checking port 8501...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8501 " ^| findstr "LISTENING"') do (
    echo   Stopping old UI on port 8501 ^(PID %%p^)...
    taskkill /PID %%p /F >nul 2>&1
)
timeout /t 1 /nobreak > nul

REM ── Start LLM Gateway V3 ──────────────────────────────────────────────────
echo [1/2] Starting LLM Gateway V3...
start "LLM_GATEWAY_V3" /D "%GATEWAY_DIR%" cmd /k "echo LLM Gateway V3 - http://localhost:8101 && python main.py"

echo       Waiting 4 seconds for gateway to initialise...
timeout /t 4 /nobreak > nul

REM ── Start Streamlit UI ────────────────────────────────────────────────────
echo [2/2] Starting Streamlit UI...
start "AGENT6_UI" /D "%PROJECT_DIR%" cmd /k "echo Agent6 UI - http://localhost:8501 && streamlit run ui.py"

echo.
echo =========================================
echo   Both services are starting!
echo =========================================
echo.
echo   Gateway : http://localhost:8101
echo   UI      : http://localhost:8501
echo             (opens in browser automatically)
echo.
echo   To stop: run stop.bat
echo.
echo =========================================
echo.

REM ── Save window titles to .pids for stop.bat ─────────────────────────────
echo LLM_GATEWAY_V3 > "%PID_FILE%"
echo AGENT6_UI >> "%PID_FILE%"

endlocal
