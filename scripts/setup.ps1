$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
uv venv --python 3.12 .venv
uv sync
pnpm -C frontend install
& (Join-Path $PSScriptRoot "build-downloader.ps1")
& (Join-Path $PSScriptRoot "setup-separator.ps1")
Write-Output "脚手架已就绪。"
