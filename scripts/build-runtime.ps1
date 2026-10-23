param([switch]$SkipImageBuild)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python scripts/prepare_cache.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed' }
if (-not $SkipImageBuild) {
    docker build --platform linux/arm64 -t ds2port-v90s-sdk:bookworm -f runtime/Dockerfile .
    if ($LASTEXITCODE -ne 0) { throw 'SDK build failed' }
}
$mount = (Get-Location).Path.Replace('\','/') + ':/work'
docker run --rm --platform linux/arm64 -v $mount -w /work ds2port-v90s-sdk:bookworm sh runtime/build_native.sh
if ($LASTEXITCODE -ne 0) { throw 'Runtime build failed' }
python scripts/pack_runtime.py bld/runtime-tree.tar bld/runtime.tar.gz
if ($LASTEXITCODE -ne 0) { throw 'Runtime packaging failed' }
