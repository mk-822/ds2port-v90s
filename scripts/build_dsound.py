"""Build the patched Wine 10 i386 DirectSound module, with a checked cache."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'bld/win32/dsound.dll'
METADATA = OUTPUT.with_suffix('.json')
SOURCE = json.loads((ROOT / 'runtime/audio-source.json').read_text())
INPUTS = ['runtime/audio-source.json', 'runtime/patches/wine10-dsound-optimized.patch',
          'runtime/build_dsound.sh', 'runtime/Dockerfile.wine-module', 'scripts/build_dsound.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    fingerprint = {name: sha(ROOT / name) for name in INPUTS}
    if OUTPUT.is_file() and METADATA.is_file():
        data = json.loads(METADATA.read_text())
        if data.get('inputs') == fingerprint and data.get('dll_sha256') == sha(OUTPUT):
            print('DSOUND_BUILD_CACHE_OK', flush=True)
            return
    archive = ROOT / 'bld/cache' / SOURCE['file']
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        request = urllib.request.Request(SOURCE['url'], headers={'User-Agent': 'DS2Port-build'})
        with urllib.request.urlopen(request, timeout=120) as stream, archive.with_suffix('.part').open('wb') as target:
            while chunk := stream.read(1024 * 1024):
                target.write(chunk)
        archive.with_suffix('.part').replace(archive)
    if sha(archive) != SOURCE['sha256']:
        raise ValueError('Wine source SHA-256 mismatch')
    image = 'ds2port-wine-module-sdk:bookworm'
    subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-t', image,
                    '-f', 'runtime/Dockerfile.wine-module', '.'], cwd=ROOT, check=True)
    subprocess.run(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                    '-v', ROOT.as_posix() + ':/work', '-w', '/work', image,
                    'sh', 'runtime/build_dsound.sh'], cwd=ROOT, check=True)
    if OUTPUT.read_bytes()[64:80] != b'DS2Port Wine DLL':
        raise ValueError('DirectSound module marker mismatch')
    data = {'inputs': fingerprint, 'dll_sha256': sha(OUTPUT), 'source': SOURCE,
            'pe_cflags': '-O3 -msse2 -mfpmath=sse', 'license': 'LGPL-2.1-or-later'}
    METADATA.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('DSOUND_BUILT', data['dll_sha256'], flush=True)


if __name__ == '__main__':
    build()
