Write-Host "Training Tracker - Setup" -ForegroundColor Green
Write-Host "=======================" -ForegroundColor Green
Write-Host ""

Write-Host "Installiere Abhaengigkeiten..." -ForegroundColor Yellow
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "Fehler bei pip install. Stelle sicher dass Python installiert ist." -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "Server gestartet!" -ForegroundColor Green
Write-Host "PIN: 1234" -ForegroundColor Cyan
Write-Host "Oeffne im Browser: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Fuer andere Geraete im Netzwerk: http://<DEINE-IP>:8000" -ForegroundColor Cyan
Write-Host ""

uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
