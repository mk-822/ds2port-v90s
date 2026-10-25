"""A single Wine prefix for DiscStation games; migrate legacy data once."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid


REGISTRIES = ('system.reg', 'user.reg', 'userdef.reg')


def common_runtime(runtime):
    return runtime.parent / '.shared/wine10'


def initialized(runtime):
    prefix = runtime / 'prefix'
    return (not prefix.is_symlink() and (runtime / 'prefix-configured-v2').is_file()
            and all((prefix / name).is_file() for name in ('system.reg', 'user.reg')))


def same_file(left, right):
    if not left.is_file() or not right.is_file() or left.is_symlink() or right.is_symlink():
        return False
    if left.stat().st_size != right.stat().st_size:
        return False
    def digest(path):
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for data in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(data)
        return h.digest()
    return os.path.samefile(left, right) or digest(left) == digest(right)


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.ds2port-common-new')
    shutil.copy2(source, temporary)
    os.replace(temporary, target)


def registry_sections(text):
    result = {}
    matches = list(re.finditer(r'^\[([^\n]+)\][^\n]*\n', text, re.MULTILINE))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[match.group(1).casefold()] = text[match.start():end]
    return result


def registry_values(section):
    matches = list(re.finditer(r'^("(?:[^"\\]|\\.)*"|@)=', section, re.MULTILINE))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        # Section metadata is not part of the value (including continued hex data).
        lines = section[match.start():end].splitlines(keepends=True)
        result[match.group(1).casefold()] = ''.join(line for line in lines if not line.startswith('#'))
    return result


def merge_registry(destination, source):
    """Keep the common configuration and import missing application values."""
    if not destination.startswith('WINE REGISTRY Version 2') or not source.startswith('WINE REGISTRY Version 2'):
        raise ValueError('Invalid Wine registry')
    existing = registry_sections(destination)
    for key, section in registry_sections(source).items():
        if key not in existing:
            destination = destination.rstrip() + '\n\n' + section.rstrip() + '\n'
            continue
        target = existing[key]
        values = registry_values(target)
        additions = [value for name, value in registry_values(section).items() if name not in values]
        if additions:
            replacement = target.rstrip() + '\n' + ''.join(additions).rstrip() + '\n\n'
            destination = destination.replace(target, replacement, 1)
    return destination


def merge_files(source, destination, backup, lower=None, exclude=()):
    """Preserve old saves; explicit private DLLs take precedence over builtins."""
    copied = conflicts = 0
    if not source.is_dir():
        return copied, conflicts
    for directory, children, files in os.walk(source, followlinks=False):
        directory = Path(directory)
        relative = directory.relative_to(source)
        for name in list(children):
            if (directory / name).is_symlink():
                files.append(name)
                children.remove(name)
        for name in files:
            item = directory / name
            rel = relative / name
            if rel.as_posix() in exclude:
                continue
            target = destination / rel
            if any((destination / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts))):
                raise ValueError('Common prefix destination traverses a symlink')
            if item.is_symlink():
                if not target.exists() and not target.is_symlink():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(os.readlink(item), target, target_is_directory=item.is_dir())
                    copied += 1
                elif not target.is_symlink() or os.readlink(item) != os.readlink(target):
                    saved = backup / rel
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    if not saved.exists() and not saved.is_symlink():
                        os.symlink(os.readlink(item), saved, target_is_directory=item.is_dir())
                    conflicts += 1
            elif item.is_file():
                if not target.exists() and not target.is_symlink():
                    if lower is None or not same_file(item, lower / rel):
                        atomic_copy(item, target)
                        copied += 1
                elif not same_file(item, target):
                    if lower is not None and same_file(target, lower / rel):
                        atomic_copy(item, target)
                        copied += 1
                    else:
                        atomic_copy(item, backup / rel)
                        conflicts += 1
    return copied, conflicts


def storage_module():
    spec = importlib.util.spec_from_file_location('ds2port_prefix_storage', Path(__file__).with_name('prefix_storage.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(runtime, storage=None):
    shared = common_runtime(runtime)
    for path in (runtime, runtime.parent / '.shared', shared, shared / 'prefix'):
        if path.is_symlink():
            raise ValueError('Managed Wine environment must not be a symbolic link')
    storage = storage or storage_module()
    reference = json.loads((runtime / 'shared-runtime.json').read_text(encoding='utf-8'))
    cache = Path(reference['path'])
    if cache.parent != runtime.parent / '.shared' or not re.fullmatch('runtime-[0-9a-f]{64}', cache.name):
        raise ValueError('Invalid shared runtime reference')
    shared.parent.mkdir(exist_ok=True)
    if not shared.exists():
        candidates = [runtime] + sorted(p for p in runtime.parent.iterdir()
                                        if p != runtime and re.fullmatch('[a-z][a-z0-9-]{0,39}', p.name))
        donor = next((p for p in candidates if initialized(p)), None)
        temporary = shared.parent / ('.wine10-new-' + uuid.uuid4().hex)
        temporary.mkdir()
        try:
            (temporary / 'shared-runtime.json').write_text(json.dumps(reference), encoding='utf-8')
            if donor is not None:
                storage.ensure(donor)
                try:
                    private_bytes = sum(p.stat().st_size for p in (donor / 'prefix').rglob('*')
                                        if p.is_file() and not p.is_symlink()
                                        and p.relative_to(donor / 'prefix').parts[:3] not in
                                        (('drive_c', 'windows', 'system32'), ('drive_c', 'windows', 'syswow64')))
                    private_bytes += sum(p.stat().st_size for p in (donor / 'prefix-overlays').rglob('*')
                                         if p.is_file() and not p.is_symlink())
                    if shutil.disk_usage(shared.parent).free < private_bytes + 128 * 1024 ** 2:
                        raise ValueError('Insufficient space to migrate the common Wine environment')
                    # Builtin DLLs are immutable and will be removed by compact().
                    lowers = {name: lower for target, lower, upper, work in storage.layout(donor)
                              for name in (target.name,)}
                    def copy(source, target):
                        relative = Path(source).relative_to(donor / 'prefix')
                        if len(relative.parts) >= 4 and relative.parts[:2] == ('drive_c', 'windows'):
                            lower = lowers.get(relative.parts[2])
                            builtin = lower / Path(*relative.parts[3:]) if lower else None
                            identical = getattr(storage, 'identical', same_file)
                            if builtin is not None and identical(Path(source), builtin):
                                os.link(builtin, target)
                                return target
                        return shutil.copy2(source, target)
                    shutil.copytree(donor / 'prefix', temporary / 'prefix', symlinks=True, copy_function=copy)
                finally:
                    storage.unmount(donor)
                (temporary / 'prefix-configured-v2').touch()
            temporary.rename(shared)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if initialized(shared):
        # Convert a seeded flat prefix before importing other private layers.
        if not (shared / 'prefix-storage.json').exists():
            storage.ensure(shared)
        storage.unmount(shared)
    marker = shared / 'migrated' / (runtime.name + '.json')
    if not marker.exists() and initialized(runtime) and initialized(shared):
        storage.unmount(runtime)
        backup = shared / 'migration-backups' / runtime.name
        backup.mkdir(parents=True, exist_ok=True)
        for name in REGISTRIES:
            source, target = runtime / 'prefix' / name, shared / 'prefix' / name
            if source.exists():
                atomic_copy(source, backup / name)
                merged = merge_registry(target.read_text(encoding='utf-8'), source.read_text(encoding='utf-8')) if target.exists() else source.read_text(encoding='utf-8')
                temporary = target.with_suffix('.common-new')
                temporary.write_text(merged, encoding='utf-8')
                os.replace(temporary, target)
        copied, conflicts = merge_files(runtime / 'prefix', shared / 'prefix', backup / 'files', exclude=REGISTRIES)
        for target, lower, upper, work in storage.layout(shared):
            legacy = runtime / 'prefix-overlays' / target.name / 'upper'
            count, archived = merge_files(legacy, upper, backup / 'overlays' / target.name, lower=lower)
            copied += count
            conflicts += archived
        marker.parent.mkdir(exist_ok=True)
        marker.write_text(json.dumps({'files_imported': copied, 'conflicts_preserved': conflicts}), encoding='utf-8')
        print('COMMON_PREFIX_IMPORTED ' + runtime.name, flush=True)
    print('COMMON_PREFIX_READY ' + str(shared / 'prefix'), flush=True)
    return shared


if __name__ == '__main__':
    runtime = Path(sys.argv[1])
    if runtime.parent != Path('/mnt/plumos/ports-runtime') or not re.fullmatch('[a-z][a-z0-9-]{0,39}', runtime.name):
        raise ValueError('Invalid game runtime')
    import fcntl
    shared = common_runtime(runtime)
    if shared.parent.is_symlink():
        raise ValueError('Shared runtime root must not be a symlink')
    shared.parent.mkdir(exist_ok=True)
    with (shared.parent / 'wine10.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepare(runtime)
