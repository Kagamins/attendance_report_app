@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] Creating virtual environment...
python -m venv .venv || (echo Python 3.10-3.12 is required: https://www.python.org/downloads/ & pause & exit /b 1)
call .venv\Scripts\activate
echo [2/3] Installing packages...
python -m pip install --upgrade pip
pip install -r requirements.txt || (pause & exit /b 1)
echo [3/3] Installing the PDF renderer (Chromium)...
python -m playwright install chromium
echo.
echo Setup complete. Double-click run_windows.bat to start the app.
pause
