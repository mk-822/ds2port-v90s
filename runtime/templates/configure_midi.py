"""Expose PlumOS's versioned FluidSynth dependencies by their SONAMEs."""
import os
from pathlib import Path
import re
import subprocess
import sys


FIRMWARE_LIB = Path('/mnt/plumos/lib')
FLUIDSYNTH = FIRMWARE_LIB / 'libfluidsynth.so.3.1.4'


def configure(aliases, firmware=FIRMWARE_LIB, library=FLUIDSYNTH):
    if not library.is_file():
        raise ValueError(f'FluidSynth が見つかりません: {library}')
    search_path = str(aliases)
    if existing := os.environ.get('LD_LIBRARY_PATH'):
        search_path += ':' + existing
    env = os.environ | {'LD_LIBRARY_PATH': search_path, 'LC_ALL': 'C'}
    while True:
        result = subprocess.run(['ldd', str(library)], env=env, text=True,
                                capture_output=True, timeout=5, check=True)
        missing = re.findall(r'^\s*(\S+)\s+=>\s+not found\s*$', result.stdout, re.MULTILINE)
        if not missing:
            return
        for soname in missing:
            if re.fullmatch(r'lib[\w.+-]+\.so\.[0-9]+(?:\.[0-9]+)*', soname):
                alias = aliases / soname
                versions = [
                    path for path in firmware.glob(soname + '.*')
                    if path.is_file() and re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', path.name[len(soname) + 1:])
                ]
                if versions and not alias.is_symlink():
                    alias.symlink_to(max(versions, key=lambda path: tuple(map(int, path.name[len(soname) + 1:].split('.')))))
                    continue
            raise ValueError(f'FluidSynth の依存ライブラリが見つかりません: {soname}')


if __name__ == '__main__':
    try:
        configure(Path(sys.argv[1]))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
