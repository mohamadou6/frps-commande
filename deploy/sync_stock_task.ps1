# Script exécuté par la tâche planifiée Windows "FRPS-SyncStock".
# Lance la synchro du stock Sage et journalise le résultat.

$ProjectDir = "C:\FRPS\commande-frps"
$PythonExe = "$ProjectDir\venv\Scripts\python.exe"
$LogDir = "$ProjectDir\deploy\logs"
$LogFile = "$LogDir\sync_stock.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Set-Location $ProjectDir
$env:PYTHONIOENCODING = "utf-8"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogFile -Encoding utf8 -Value "[$timestamp] Démarrage sync_stock"
$output = & $PythonExe manage.py sync_stock 2>&1 | Out-String
Add-Content -Path $LogFile -Encoding utf8 -Value $output
Add-Content -Path $LogFile -Encoding utf8 -Value "[$timestamp] Fin (exit code $LASTEXITCODE)"
