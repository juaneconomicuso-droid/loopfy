@echo off
setlocal
set "RAIZ=%~dp0"
set "LOOPFY_DEV=1"
set "LOOPFY_SERVER=http://localhost:3100"

rem sobe o servidor de licenca (modo teste) se ainda nao estiver no ar, escondido
powershell -NoProfile -Command "try { (Invoke-WebRequest http://localhost:3100/api/license/challenge -Method Post -ContentType application/json -Body '{}' -UseBasicParsing -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  start "" /min cmd /c "cd /d %RAIZ%app && npm run dev -- -p 3100"
  powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){ try { Invoke-WebRequest http://localhost:3100/api/license/challenge -Method Post -ContentType application/json -Body '{}' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep 1 } }; exit 1"
)

cd /d "%RAIZ%desktop"
start "" "%RAIZ%desktop\.venv\Scripts\pythonw.exe" -m loopfy
