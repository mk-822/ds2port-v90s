"""Verify and stage the Win32 DirectDraw wrapper for the Windows build."""
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / "scripts/fetch_dependencies.py"), "cnc-ddraw"], check=True)
destination = root / "bld/win32/ddraw.dll"
destination.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(root / "bld/cache/cnc-ddraw.zip") as archive:
    destination.write_bytes(archive.read("ddraw.dll"))
