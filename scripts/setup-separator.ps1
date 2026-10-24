$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root "tools\audio-separator\.venv"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    uv venv --python 3.12 $Venv
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed" }
}
uv pip install --python $Python "audio-separator[gpu]"
if ($LASTEXITCODE -ne 0) { throw "audio-separator install failed" }
uv pip install --python $Python --reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw "torch cu128 install failed" }
uv pip install --python $Python audioread
if ($LASTEXITCODE -ne 0) { throw "audioread install failed" }

$UvrCkpt = "D:\Ultimate Vocal Remover\models\MDX_Net_Models"
$UvrYaml = Join-Path $UvrCkpt "model_data\mdx_c_configs"
$Models = Join-Path $Root "var\models"
New-Item -ItemType Directory -Force -Path $Models | Out-Null

function Link-File([string]$Source, [string]$Target) {
    if (Test-Path $Target) { return }
    New-Item -ItemType HardLink -Path $Target -Target $Source | Out-Null
}

Link-File (Join-Path $UvrCkpt "melband_roformer_inst_v2.ckpt") (Join-Path $Models "melband_roformer_inst_v2.ckpt")
Link-File (Join-Path $UvrCkpt "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt") (Join-Path $Models "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt")
Copy-Item (Join-Path $UvrYaml "config_melbandroformer_inst_v2.yaml") (Join-Path $Models "config_melbandroformer_inst_v2.yaml") -Force
Copy-Item (Join-Path $UvrYaml "config_mel_band_roformer_karaoke.yaml") (Join-Path $Models "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml") -Force
Copy-Item (Join-Path $UvrYaml "config_mel_band_roformer_karaoke.yaml") (Join-Path $Models "config_mel_band_roformer_karaoke.yaml") -Force
Write-Output "separator ready: $Models"
