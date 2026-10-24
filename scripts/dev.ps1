$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:KATOCK_NO_BROWSER = "1"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","katock.web.app:app","--host","127.0.0.1","--port","8765","--reload" -WorkingDirectory $Root
pnpm -C frontend dev
