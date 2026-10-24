param([switch]$SkipDependencies, [switch]$ExecutablesOnly)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path bld/venv/Scripts/python.exe)) { python -m venv bld/venv }
$python = (Resolve-Path bld/venv/Scripts/python.exe).Path
if (-not $SkipDependencies) {
    & $python -m pip install -r requirements-build.lock
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
& (Join-Path $PSScriptRoot 'build-font-shim.ps1')
$repoRoot = (Get-Location).Path
$profilesData = (Join-Path $repoRoot 'profiles') + ';profiles'
$templatesData = (Join-Path $repoRoot 'runtime/templates') + ';runtime/templates'
$installerData = (Join-Path $repoRoot 'runtime/install_remote.py') + ';runtime'
$fontData = (Join-Path $repoRoot 'bld/win32/dsfont.dll') + ';runtime/win32'
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name DS2PortV90S --distpath bld/dist/DS2PortV90S --workpath bld/pyinstaller --specpath bld --paths src --add-data $profilesData --add-data $templatesData --add-data $installerData --add-data $fontData scripts/app_main.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
& $python -m PyInstaller --noconfirm --clean --onefile --console --name DS2PortCLI --distpath bld/dist/DS2PortV90S --workpath bld/pyinstaller-cli --specpath bld --paths src --add-data $profilesData --add-data $templatesData --add-data $installerData --add-data $fontData scripts/app_main.py
if ($LASTEXITCODE -ne 0) { throw 'CLI build failed' }
if ($ExecutablesOnly) { Write-Output 'Windows executables built'; return }
$destination = 'bld/dist/DS2PortV90S'
Copy-Item bld/runtime.tar.gz,bld/runtime.tar.gz.sha256,README.md,THIRD_PARTY.md,LICENSE,NOTICE -Destination $destination
& $python scripts/package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed' }
