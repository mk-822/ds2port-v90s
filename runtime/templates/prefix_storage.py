"""Share Wine's builtin PE files through private copy-on-write overlays."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.digest()


def attributes(path):
    if not hasattr(os, 'listxattr'):
        return {}
    return {key: os.getxattr(path, key) for key in os.listxattr(path)
            if not key.startswith('trusted.overlay.')}


def identical(left, right):
    if left.is_symlink() or right.is_symlink():
        return False
    if not left.is_file() or not right.is_file():
        return False
    a, b = left.stat(), right.stat()
    properties = lambda s: (s.st_size, stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid)
    return properties(a) == properties(b) and attributes(left) == attributes(right) and digest(left) == digest(right)


def compact(upper, lower):
    """Only call while unmounted. Private replacements/whiteouts remain intact."""
    removed = total = 0
    for directory, children, files in os.walk(upper, followlinks=False):
        directory = Path(directory)
        try:
            opaque = os.getxattr(directory, 'trusted.overlay.opaque') == b'y'
        except (AttributeError, OSError):
            opaque = False
        if opaque:
            children[:] = []
            continue
        children[:] = [name for name in children if not (directory / name).is_symlink()]
        for name in files:
            path = directory / name
            other = lower / path.relative_to(upper)
            if not other.resolve().is_relative_to(lower.resolve()):
                continue
            if identical(path, other):
                total += path.stat().st_size
                path.unlink()
                removed += 1
    return removed, total


def mount_record(target):
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        left, right = line.split(' - ', 1)
        # Managed paths contain no spaces/backslashes, but mountinfo is escaped.
        path = left.split()[4].replace('\\040', ' ').replace('\\134', '\\')
        if path == str(target):
            return right.split()
    return None


def layout(runtime):
    runtimes = runtime.parent.parent if runtime.parent.name == '.shared' else runtime.parent
    state = runtime / 'prefix-storage.json'
    if state.exists():
        value = json.loads(state.read_text())
        if value.get('schema') != 1:
            raise RuntimeError('Unsupported prefix storage layout')
        lower = Path(value['wine'])
    else:
        shared = runtime / 'shared-runtime.json'
        if shared.exists():
            cache = Path(json.loads(shared.read_text())['path'])
            if cache.parent != runtimes / '.shared' or not re.fullmatch('runtime-[0-9a-f]{64}', cache.name):
                raise RuntimeError('Invalid shared runtime path')
            lower = cache / 'wine-10.0-amd64-wow64'
        else:
            lower = runtime / 'wine-10.0-amd64-wow64'
        # Write before renaming directories, so an interrupted migration resumes.
        temporary = state.with_suffix('.new')
        temporary.write_text(json.dumps({'schema': 1, 'wine': str(lower)}))
        temporary.replace(state)
    allowed = (lower == runtime / 'wine-10.0-amd64-wow64' or
               (lower.parent.parent == runtimes / '.shared' and
                re.fullmatch('runtime-[0-9a-f]{64}', lower.parent.name) and
                lower.name == 'wine-10.0-amd64-wow64'))
    if not allowed:
        raise RuntimeError('Prefix lower directory is outside managed runtimes')
    result = []
    for name, arch in [('system32', 'x86_64-windows'), ('syswow64', 'i386-windows')]:
        target = runtime / 'prefix/drive_c/windows' / name
        private = runtime / 'prefix-overlays' / name
        result.append((target, lower / 'lib/wine' / arch, private / 'upper', private / 'work'))
    return result


def ensure(runtime):
    if not (runtime / 'prefix-configured-v2').is_file() or not (runtime / 'prefix/system.reg').is_file():
        return
    if 'overlay' not in Path('/proc/filesystems').read_text().split():
        print('PREFIX_STORAGE_UNAVAILABLE overlay filesystem missing')
        return
    total = 0
    for target, lower, upper, work in layout(runtime):
        if not (lower / 'ntdll.dll').is_file() or not (lower / 'kernel32.dll').is_file():
            raise RuntimeError('Wine lower directory is incomplete: ' + str(lower))
        record = mount_record(target)
        if record:
            if record[0] != 'overlay' or 'upperdir=' + str(upper) not in record[2].split(','):
                raise RuntimeError('Unexpected mount at ' + str(target))
            continue
        if target.is_symlink() or upper.is_symlink() or work.is_symlink():
            raise RuntimeError('Prefix storage directories must not be symlinks')
        upper.parent.mkdir(parents=True, exist_ok=True)
        if not upper.exists():
            if not target.is_dir():
                raise RuntimeError('Missing initialized prefix directory: ' + str(target))
            target.rename(upper)
        target.mkdir(parents=True, exist_ok=True)
        if any(target.iterdir()):
            raise RuntimeError('Unmounted overlay target is not empty: ' + str(target))
        work.mkdir(exist_ok=True)
        count, freed = compact(upper, lower)
        total += freed
        options = 'lowerdir=%s,upperdir=%s,workdir=%s' % (lower, upper, work)
        subprocess.run(['mount', '-t', 'overlay', 'overlay', '-o', options, str(target)], check=True)
        print('PREFIX_OVERLAY_READY %s shared=%d bytes=%d' % (target.name, count, freed), flush=True)
    print('PREFIX_STORAGE_READY reclaimed=%d' % total, flush=True)


def unmount(runtime):
    if not (runtime / 'prefix-storage.json').is_file():
        return
    for target, lower, upper, work in reversed(layout(runtime)):
        record = mount_record(target)
        if record:
            if record[0] != 'overlay' or 'upperdir=' + str(upper) not in record[2].split(','):
                raise RuntimeError('Unexpected prefix mount')
            subprocess.run(['umount', str(target)], check=True)


if __name__ == '__main__':
    runtime = Path(sys.argv[2])
    base = Path('/mnt/plumos/ports-runtime')
    if not (runtime == base / '.shared/wine10' or
            (runtime.parent == base and re.fullmatch('[a-z][a-z0-9-]{0,39}', runtime.name))):
        raise RuntimeError('Invalid managed runtime path')
    import fcntl
    with (runtime / 'prefix-storage.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if sys.argv[1] == 'ensure':
            ensure(runtime)
        elif sys.argv[1] == 'unmount':
            unmount(runtime)
        else:
            raise RuntimeError('Unknown storage operation')
