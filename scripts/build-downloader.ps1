$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root "tools\amd"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Source = "D:\Download\apple-music-downloader-main"
if (-not $env:GOPROXY) {
    $env:GOPROXY = "https://goproxy.cn,direct"
}
Push-Location $Source
try {
    go build -o (Join-Path $OutDir "amd.exe") .
    if ($LASTEXITCODE -ne 0) { throw "go build failed with exit $LASTEXITCODE" }
}
finally {
    Pop-Location
}
Write-Output "amd.exe -> $OutDir\amd.exe"
