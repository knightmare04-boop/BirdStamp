@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Bird Stamp Collection - Initializing Application
echo ===================================================

:: 1. Update Frontend Dependencies & Build
echo [1/3] Checking Frontend Dependencies...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo Installing npm packages...
    call npm install
) else (
    echo Updating npm packages...
    call npm install --no-audit --no-fund
)

echo [2/3] Building React Frontend...
call npm run build

:: 2. Update Backend Dependencies
echo.
echo [3/3] Checking Backend Python Environment & Dependencies...
cd /d "%~dp0backend"
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

call .\venv\Scripts\activate

if exist "requirements.txt" (
    echo Installing/updating Python dependencies from requirements.txt...
    pip install -r requirements.txt --quiet
)

echo.
echo ===================================================
echo   Starting Bird Stamp Desktop App...
echo ===================================================
python desktop.py

endlocal
