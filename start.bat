@echo off
echo Training Tracker - Setup
echo =======================
echo.

REM Install dependencies
echo Installiere Abhaengigkeiten...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Fehler bei pip install. Stelle sicher dass Python installiert ist.
    pause
    exit /b 1
)

echo.
echo Starte Server...
echo PIN: 1234
echo Oeffne im Browser: http://localhost:8000
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
