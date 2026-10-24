$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force bld/win32 | Out-Null
$mount = (Get-Location).Path.Replace('\', '/') + ':/work'
docker run --rm --platform linux/arm64 -v $mount -w /work ds2port-v90s-sdk:bookworm i686-w64-mingw32-gcc -std=c11 -Wall -Wextra -O2 -shared -static-libgcc '-Wl,--kill-at' -s runtime/native/dsfont.c -o bld/win32/dsfont.dll -lgdi32
if ($LASTEXITCODE -ne 0) { throw 'Font compatibility DLL build failed' }
