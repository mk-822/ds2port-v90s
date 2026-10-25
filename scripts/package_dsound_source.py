"""Ship the exact upstream source, patch and build inputs with a release."""
from pathlib import Path
import hashlib
import json
import tarfile
import tomllib

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
spec = json.loads((root / 'runtime/audio-source.json').read_text())
archive = root / 'bld/cache' / spec['file']
assert hashlib.sha256(archive.read_bytes()).hexdigest() == spec['sha256']
files = ['.dockerignore', 'runtime/audio-source.json', 'runtime/Dockerfile.wine-module',
         'runtime/build_dsound.sh', 'runtime/patches/wine10-dsound-optimized.patch',
         'scripts/build_dsound.py', 'scripts/build-audio-shim.ps1',
         'tests/dsound-functional.c', 'tests/dsound-stress.c',
         'docs/AUDIO_OPTIMIZATION.md', 'bld/win32/dsound-licenses/COPYING.LIB',
         'bld/win32/dsound.json', 'bld/cache/' + spec['file']]
output = root / ('bld/dist/ds2port-v90s-' + version + '-dsound-source.tar.gz')
output.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(output, 'w:gz') as target:
    for name in files:
        target.add(root / name, arcname=name, recursive=False)
with tarfile.open(output) as result:
    assert set(result.getnames()) == set(files)
    for member in result.getmembers():
        assert hashlib.sha256(result.extractfile(member).read()).digest() == hashlib.sha256((root / member.name).read_bytes()).digest()
digest = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_name(output.name + '.sha256').write_text(digest + '  ' + output.name + '\n')
print('DSOUND_SOURCE_PACKAGE_OK', output.name, output.stat().st_size, digest)
