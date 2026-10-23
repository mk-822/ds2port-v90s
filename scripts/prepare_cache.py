"""Decode Wine's xz on the native host, preserving Unix entries in a tar."""
from pathlib import Path
import lzma
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'scripts/fetch_dependencies.py')],check=True)
cache=root/'bld/cache'
target=cache/'wine10.tar'
temporary=cache/'wine10.tar.building'
with lzma.open(cache/'wine10.tar.xz','rb') as source,temporary.open('wb') as dest:
    shutil.copyfileobj(source,dest,1024*1024)
temporary.replace(target)
print('WINE_TAR_READY',target.stat().st_size,flush=True)
