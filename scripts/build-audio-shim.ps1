$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python scripts/build_dsound.py
if ($LASTEXITCODE -ne 0) { throw 'DirectSound module build failed' }
