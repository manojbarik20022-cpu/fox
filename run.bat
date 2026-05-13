@echo off
REM Fox2-clone launcher for Windows. Double-click to run.
REM First launch creates .venv and installs dependencies (takes a few minutes).
REM Subsequent launches start the GUI in ~1 second.

setlocal enableextensions
cd /d "%~dp0"

REM ---- Check Python is available ----
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo and check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM ---- Check ffmpeg ----
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg not found in PATH.
    echo Video assembly and Ken Burns animations will not work without ffmpeg.
    echo Install: winget install Gyan.FFmpeg
    echo Or download from https://www.gyan.dev/ffmpeg/builds/ and add to PATH.
    echo.
    timeout /t 3 >nul
)

REM ---- Create venv if missing ----
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
    echo [setup] Installing dependencies ^(may take a few minutes^) ...
    call ".venv\Scripts\python.exe" -m pip install --upgrade pip
    call ".venv\Scripts\python.exe" -m pip install -e ".[browser]"
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
)

REM ---- Install Playwright Chromium (one-time, ~200MB) ----
REM Marker file lets us skip this step on subsequent launches.
if not exist ".venv\.playwright-chromium-installed" (
    echo [setup] Installing Chromium for browser automation ^(Flow, Grok, Nano Banana^) ...
    echo [setup] This is a one-time ~200MB download.
    call ".venv\Scripts\python.exe" -m pip install -e ".[browser]" >nul 2>&1
    call ".venv\Scripts\python.exe" -m playwright install chromium
    if errorlevel 1 (
        echo [WARNING] Chromium installation failed. Browser providers ^(Flow/Grok/Nano Banana^) will not work.
        echo You can retry later with: .venv\Scripts\python.exe -m playwright install chromium
        timeout /t 4 >nul
    ) else (
        type nul > ".venv\.playwright-chromium-installed"
        echo [setup] Chromium installed.
    )
)

REM ---- Ensure playwright-stealth is installed (cheap pip check, no-op if already there) ----
REM Without it Google login detects automation and blocks the sign-in dialog.
call ".venv\Scripts\python.exe" -c "import playwright_stealth" >nul 2>&1
if errorlevel 1 (
    echo [setup] Installing playwright-stealth ^(stealth patches for Google login^) ...
    call ".venv\Scripts\python.exe" -m pip install --quiet "playwright-stealth>=2.0.0"
)

REM ---- Launch GUI ----
call ".venv\Scripts\python.exe" -m fox2
if errorlevel 1 (
    echo.
    echo [ERROR] Fox2 exited with an error.
    pause
)

endlocal
