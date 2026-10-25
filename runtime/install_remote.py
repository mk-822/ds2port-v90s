"""Run on PlumOS with its Python 3; all destinations are fixed beneath this port."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
from contextlib import contextmanager


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def same_tree(source, destination):
    """Reuse identical runtime trees so an update need not keep a second Wine."""
    if not destination.is_dir() or destination.is_symlink():
        return False
    def entries(root):
        result = {}
        for item in root.rglob('*'):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                result[relative] = ('link', os.readlink(item))
            elif item.is_file():
                result[relative] = ('file', item, item.stat().st_mode & 0o777)
            elif item.is_dir():
                result[relative] = ('directory',)
            else:
                return None
        return result
    expected, actual = entries(source), entries(destination)
    if expected is None or actual is None or expected.keys() != actual.keys():
        return False
    for name, value in expected.items():
        other = actual[name]
        if value[0] != other[0]:
            return False
        if value[0] == 'file':
            if value[2] != other[2] or not (os.path.samefile(value[1], other[1]) or sha(value[1]) == sha(other[1])):
                return False
        elif value != other:
            return False
    return True


def share_wine_files(source, candidates):
    """Share immutable Wine binaries only; game data and prefixes stay private.

    Managed runtime upgrades replace files/directories, never edit shared
    binaries in place. An old installation therefore retains its own version.
    """
    count=0
    candidates=[p for p in candidates if p.is_dir() and not p.is_symlink()]
    for dest in source.rglob('*'):
        if dest.is_symlink() or not dest.is_file():continue
        relative=dest.relative_to(source)
        current=dest.stat();expected=None
        for root in candidates:
            other=root/relative
            if other.is_symlink() or not other.is_file() or not other.resolve().is_relative_to(root.resolve()):continue
            previous=other.stat()
            properties=lambda s:(s.st_dev,s.st_size,stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)
            if properties(current)!=properties(previous):continue
            if current.st_ino==previous.st_ino:break
            if expected is None:expected=sha(dest)
            if sha(other)!=expected:continue
            temporary=dest.with_name(dest.name+'.ds2port-link')
            if temporary.exists() or temporary.is_symlink():continue
            try:
                os.link(other,temporary)
                os.replace(temporary,dest)
            except OSError:
                temporary.unlink(missing_ok=True)
                continue
            count+=1;break
    return count


def safe_extract(archive, destination):
    """Validate paths and link targets before creating any archive member."""
    with tarfile.open(archive) as tf:
        seen = set()
        members = tf.getmembers()
        for m in members:
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts or p.as_posix() in seen:
                raise ValueError("Unsafe/duplicate archive path: " + m.name)
            seen.add(p.as_posix())
            if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                raise ValueError("Special archive entry: " + m.name)
            if m.issym() or m.islnk():
                target = (destination / p.parent / m.linkname) if m.issym() else (destination / m.linkname)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("Escaping archive link: " + m.name)
        # Reject archives placing files below symlink members, independent of order.
        links = {PurePosixPath(m.name) for m in members if m.issym() or m.islnk()}
        if any(parent in links for m in members for parent in PurePosixPath(m.name).parents):
            raise ValueError("Archive writes through a link")
        # Python 3.11.2 on PlumOS predates tarfile's filter keyword. Validation
        # above covers every member and link before this compatibility call.
        tf.extractall(destination, members=members)


def cache_entries(description, destination):
    """Check the archive layout even when files come from installed runtimes."""
    entries = [[PurePosixPath(name).as_posix(), kind, mode, target, size]
               for name, kind, mode, target, size in description['entries']]
    seen, links = set(), set()
    for name, kind, mode, target, size in entries:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.as_posix() in seen or not path.parts:
            raise ValueError('Invalid cached runtime path')
        seen.add(path.as_posix())
        if kind not in ('file', 'directory', 'symlink', 'hardlink') or mode & ~0o777:
            raise ValueError('Invalid cached runtime entry')
        if kind in ('symlink', 'hardlink'):
            links.add(path)
            resolved = destination / path.parent / target if kind == 'symlink' else destination / target
            if not resolved.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Escaping cached runtime link')
    if any(parent in links for path in seen for parent in PurePosixPath(path).parents):
        raise ValueError('Cached runtime writes through a link')
    files = {name for name, kind, _, _, _ in entries if kind == 'file' and name != 'bundle.json'}
    if files != set(description['bundle']['files']):
        raise ValueError('Cached runtime manifest/layout mismatch')
    return entries


def cache_valid(cache, description, verify_hash=True):
    if cache.is_symlink() or not cache.is_dir():
        return False
    try:
        for name, kind, mode, target, size in cache_entries(description, cache):
            path = cache / name
            if kind == 'symlink':
                if not path.is_symlink() or os.readlink(path) != target:
                    return False
            elif kind == 'directory':
                if path.is_symlink() or not path.is_dir():
                    return False
            elif kind == 'file' and name != 'bundle.json':
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(cache.resolve()):
                    return False
                if path.stat().st_size != size or stat.S_IMODE(path.stat().st_mode) != mode or (verify_hash and sha(path) != description['bundle']['files'][name]):
                    return False
            elif kind == 'hardlink':
                if not path.is_file() or not os.path.samefile(path, cache / target):
                    return False
        return json.loads((cache / 'bundle.json').read_text()) == description['bundle']
    except (OSError, ValueError, KeyError):
        return False


def copy_cache_layout(description, destination, sources):
    entries = cache_entries(description, destination)
    destination.mkdir(parents=True)
    for name, kind, mode, target, size in entries:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if kind == 'directory':
            path.mkdir(exist_ok=True)
        elif kind == 'file':
            if name == 'bundle.json':
                path.write_text(json.dumps(description['bundle'], sort_keys=True))
            else:
                source = sources[name]
                # Never chmod an existing hardlink: it belongs to another port.
                if source.stat().st_dev == destination.stat().st_dev and stat.S_IMODE(source.stat().st_mode) == mode:
                    os.link(source, path)
                else:
                    shutil.copyfile(source, path)
            if stat.S_IMODE(path.stat().st_mode) != mode:
                path.chmod(mode)
    for name, kind, mode, target, size in entries:
        if kind == 'symlink':
            (destination / name).symlink_to(target)
        elif kind == 'hardlink':
            os.link(destination / target, destination / name)


def normalize_cache_owner(cache, description):
    # The archive's build-user uid is not a Windows file owner. Root-run Wine
    # creates prefix DLLs as root; match that metadata for lossless compaction.
    if os.name != 'posix' or os.geteuid() != 0:
        return
    for name, kind, mode, target, size in cache_entries(description, cache):
        if kind == 'file':
            path = cache / name
            if path.stat().st_uid != 0 or path.stat().st_gid != 0:
                os.chown(path, 0, 0)


def prepare_cache(description, runtimes=Path('/mnt/plumos/ports-runtime'), ports=Path('/mnt/plumos/roms/ports'), verified=None, verify_existing=True):
    identity = description['runtime_sha256']
    if not re.fullmatch('[0-9a-f]{64}', identity):
        raise ValueError('Invalid runtime cache identity')
    shared = runtimes / '.shared'
    if shared.is_symlink():
        raise ValueError('Shared runtime root must not be a symlink')
    cache = shared / ('runtime-' + identity)
    cache_entries(description, cache)
    if cache.exists():
        if not cache_valid(cache, description, verify_existing):
            raise ValueError('Shared runtime verification failed; refusing to reuse it')
        normalize_cache_owner(cache, description)
        return cache
    managed = [p for p in sorted(runtimes.iterdir()) if not p.is_symlink() and
               re.fullmatch('[a-z][a-z0-9-]{0,39}', p.name) and
               ((ports / p.name / 'ds2port-installed.json').is_file() or (p / 'installed.json').is_file())]
    sources = {}
    for name, kind, mode, target, size in cache_entries(description, cache):
        if kind != 'file' or name == 'bundle.json':
            continue
        candidates = []
        for runtime in managed:
            relative = PurePosixPath(name)
            if relative.parts[0] == 'shared':
                candidates.extend([runtime / 'port' / Path(*relative.parts[1:]), ports / runtime.name / Path(*relative.parts[1:])])
            else:
                candidates.append(runtime / name)
        if verified:
            candidates.append(verified / name)
        for candidate in candidates:
            root = verified if verified and candidate.is_relative_to(verified) else (ports if candidate.is_relative_to(ports) else runtimes)
            if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
                continue
            if candidate.stat().st_size == size and sha(candidate) == description['bundle']['files'][name]:
                sources[name] = candidate
                break
        else:
            return None
    modes = {name: mode for name, kind, mode, target, size in cache_entries(description, cache)}
    device = runtimes.stat().st_dev
    copied = sum(source.stat().st_size for name, source in sources.items()
                 if source.stat().st_dev != device or stat.S_IMODE(source.stat().st_mode) != modes[name])
    needed = copied + 128 * 1024 ** 2
    if shutil.disk_usage(runtimes).free < needed:
        raise ValueError('共有キャッシュの準備に約%.0fMiBの空き容量が必要です。' % (needed / 1024 ** 2))
    shared.mkdir(exist_ok=True)
    if shared.is_symlink():
        raise ValueError('Shared runtime root must not be a symlink')
    temporary = shared / ('.building-' + uuid.uuid4().hex)
    try:
        copy_cache_layout(description, temporary, sources)
        normalize_cache_owner(temporary, description)
        if not cache_valid(temporary, description):
            raise ValueError('New runtime cache verification failed')
        (temporary / '.ds2port-cache.json').write_text(json.dumps(description))
        try:
            temporary.rename(cache)
        except OSError:
            if not cache.is_dir() or not cache_valid(cache, description):
                raise
        return cache
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


@contextmanager
def shared_environment_lock(path=Path('/run/plumos/ds2port-display93.lock')):
    # Share the launcher's lock so no title can start while the common registry
    # is being changed. A failed acquisition must never remove someone else's lock.
    try:
        path.mkdir()
    except FileExistsError:
        raise ValueError('ゲームの起動または別の転送処理が進行中です。終了後に再実行してください。')
    try:
        yield
    finally:
        path.rmdir()


def main(config_path):
    with shared_environment_lock():
        install_files(config_path)


def install_files(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    ident = config["port_id"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", ident):
        raise ValueError("Invalid port ID")
    p = Path("/mnt/plumos/roms/ports") / ident
    r = Path("/mnt/plumos/ports-runtime") / ident
    common = r.parent / '.shared/wine10'
    stage = config_path.parent
    if stage.parent != r or not stage.name.startswith(".incoming-"):
        raise ValueError("Invalid staging path")
    if platform.machine() != "aarch64":
        raise ValueError("This runtime requires aarch64")
    if p.is_symlink() or r.is_symlink() or common.is_symlink() or (common / 'prefix').is_symlink():
        raise ValueError("Port root must not be a symbolic link")
    if Path("/tmp/.X11-unix/X93").exists():
        raise ValueError("先に起動中のゲームを終了してください。")
    for root in (Path("/mnt/plumos/roms/ports"), r):
        if os.statvfs(root).f_flag & os.ST_RDONLY:
            raise ValueError("転送先が読み取り専用です。SDの状態を確認してください。")
    for name in (("payload",) if config.get('runtime_cache') else ("runtime", "payload")):
        if sha(stage / (name + ".tar.gz")) != config[name + "_sha256"]:
            raise ValueError(name + " archive checksum mismatch")
    unpacked = stage / "unpacked"
    runtime, payload = unpacked / "runtime", unpacked / "payload"
    unpacked.mkdir(parents=True)
    payload.mkdir()
    print("アーカイブを検証・展開しています。", flush=True)
    cache = None
    if config.get('runtime_cache'):
        cache = r.parent / '.shared' / ('runtime-' + config['runtime_sha256'])
        if str(cache) != config['runtime_cache']:
            raise ValueError('Invalid shared runtime reference')
        description = json.loads((cache / '.ds2port-cache.json').read_text())
        if description['runtime_sha256'] != config['runtime_sha256'] or not cache_valid(cache, description):
            raise ValueError('Shared runtime checksum mismatch')
        sources = {name: cache / name for name in description['bundle']['files']}
        copy_cache_layout(description, runtime, sources)
    else:
        runtime.mkdir()
        safe_extract(stage / "runtime.tar.gz", runtime)
    safe_extract(stage / "payload.tar.gz", payload)
    manifest = json.loads((runtime / "bundle.json").read_text())
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported runtime bundle")
    # A cache has already been fully verified immediately before hardlinking.
    for name, expected in (() if cache else manifest["files"].items()):
        path = runtime / name
        if not path.resolve().is_relative_to(runtime.resolve()) or sha(path) != expected:
            raise ValueError("Runtime file mismatch: " + name)
    if cache is None:
        with tarfile.open(stage / 'runtime.tar.gz') as archive:
            entries = [[m.name, 'file' if m.isfile() else 'directory' if m.isdir() else 'symlink' if m.issym() else 'hardlink', m.mode & 0o777, m.linkname, m.size] for m in archive.getmembers()]
        description = {'runtime_sha256': config['runtime_sha256'], 'bundle': manifest, 'entries': entries}
        cache = prepare_cache(description, verified=runtime)
        if cache is None:
            raise ValueError('Unable to publish verified runtime cache')
    launcher = config["launcher"]
    if "/" in launcher or "\\" in launcher or not launcher.endswith(".sh"):
        raise ValueError("Invalid launcher name")
    if sha(payload / "game" / config["executable"]) != config["game_sha256"]:
        raise ValueError("Game executable mismatch")
    backup = r / "backups" / (time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + stage.name[-8:])
    backup.mkdir(parents=True)
    changes = []

    def install_file(source, dest, shared=False):
        if dest.is_symlink() or any(x.is_symlink() for x in dest.parents if x not in (Path('/'),)):
            # /mnt/plumos/roms may itself be a normal system symlink; roots were
            # checked above. Only descendants of the per-port roots are restricted.
            for root in (p, r, common):
                if dest.is_relative_to(root) and any((root / Path(*dest.relative_to(root).parts[:i])).is_symlink() for i in range(1, len(dest.relative_to(root).parts) + 1)):
                    raise ValueError("Managed destination contains a link: " + str(dest))
        if dest.is_file() and sha(dest) == sha(source):
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        old = backup / "files" / str(len(changes))
        if dest.exists():
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, old)
        else:
            old = None
        tmp = dest.with_name(dest.name + ".ds2port-new")
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        if shared and source.stat().st_dev == dest.parent.stat().st_dev:
            os.link(source, tmp)
        else:
            shutil.copy2(source, tmp)
        changes.append(("file", dest, old))
        os.replace(tmp, dest)

    try:
        print("バックアップを保存して配置しています。", flush=True)
        p.mkdir(parents=True, exist_ok=True)
        existing_game = (p / "game").exists()
        existing_roots = {child.name.casefold() for child in (p / "game").iterdir()} if existing_game else set()
        storage = payload / 'port/prefix_storage.py'
        if storage.is_file() and (r / 'prefix-storage.json').is_file():
            subprocess.run(['python3', str(storage), 'unmount', str(r)], check=True)
        if storage.is_file() and (common / 'prefix-storage.json').is_file():
            subprocess.run(['python3', str(storage), 'unmount', str(common)], check=True)
        for name in ("native", "wine-10.0-amd64-wow64", "licenses"):
            dest = r / name
            if same_tree(runtime / name, dest):
                # Old bundles carried the build user's uid. These are verified
                # immutable files, so normalize before deduplicating by inode.
                for item in dest.rglob('*'):
                    if item.is_file() and not item.is_symlink():
                        info = item.stat()
                        if info.st_uid != 0 or info.st_gid != 0:
                            os.chown(item, 0, 0)
                share_wine_files(dest, [cache / name])
                print('既存ランタイムを再利用: ' + name, flush=True)
                shutil.rmtree(runtime / name)
                continue
            share_wine_files(runtime/name,[cache/name])
            print('共有ランタイムから配置: '+name,flush=True)
            old = backup / name if dest.exists() else None
            if old:
                os.replace(dest, old)
            changes.append(("directory", dest, old))
            os.replace(runtime / name, dest)
        for subtree in (runtime / "shared", payload / "port"):
            for source in sorted(subtree.rglob("*")):
                if source.is_file():
                    install_file(source, r / 'port' / source.relative_to(subtree), subtree == runtime / 'shared')
        preserve = {x.casefold() for x in config["preserve"]}
        for source in sorted((payload / "game").rglob("*")):
            relative = source.relative_to(payload / "game")
            if relative.parts[0].casefold() in preserve & existing_roots:
                continue
            if source.is_file():
                install_file(source, p / "game" / relative)
        install_file(payload / "wineserver-wrapper", r / "wineserver-wrapper")
        cache_reference = stage / 'shared-runtime.json'
        cache_reference.write_text(json.dumps({'schema': 1, 'path': str(cache)}))
        install_file(cache_reference, r / 'shared-runtime.json')
        install_file(payload / "launcher.sh", p.parent / launcher)
        # Existing Japanese Noto replacements must be cleared with Wine stopped.
        user_reg = (common if (common / 'prefix/user.reg').is_file() else r) / "prefix/user.reg"
        if user_reg.exists():
            content = user_reg.read_text()
            for face in ("MS Gothic", "MS PGothic", "MS UI Gothic"):
                content = content.replace('"' + face + '"="Noto Sans CJK JP"\n', "")
            edited = stage / "user.reg"
            edited.write_text(content)
            install_file(edited, user_reg)
        result = subprocess.run(["sh", str(r / "port/launch.sh"), "--check"], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(r / "native/lib") + ":/mnt/plumos/lib"
        result = subprocess.run([str(r / "port/runtime/box64"), str(r / "native/tests/linux-probe")], env=env, text=True, capture_output=True)
        if result.returncode or "BOX64_LINUX_OK" not in result.stdout:
            raise RuntimeError("Box64動作検査に失敗しました: " + result.stdout + result.stderr)
        (r / "installed.json").write_text(json.dumps({"version": config.get('tool_version', '0.1.2'), "profile": config["profile"], "backup": str(backup), 'runtime_sha256': config['runtime_sha256'], 'game_sha256': config['game_sha256']}, indent=2))
        print(result.stdout.strip(), flush=True)
        print("DS2PORT_INSTALL_OK backup=" + str(backup), flush=True)
    except BaseException as failure:
        errors = []
        for kind, dest, old in reversed(changes):
            try:
                if kind == "directory":
                    if dest.exists():
                        shutil.rmtree(dest)
                    if old:
                        os.replace(old, dest)
                elif old:
                    temporary = dest.with_name(dest.name + '.ds2port-restore')
                    shutil.copy2(old, temporary)
                    os.replace(temporary, dest)
                else:
                    dest.unlink(missing_ok=True)
            except OSError as error:
                errors.append(str(dest) + ': ' + str(error))
        if errors:
            failure.add_note('Some changes could not be restored:\n' + '\n'.join(errors))
        raise


if __name__ == "__main__":
    if sys.argv[1] == '--cache':
        # Planning checks layout/size/modes; main() hashes all files before use.
        cache = prepare_cache(json.loads(Path(sys.argv[2]).read_text()), verify_existing=False)
        print('DS2PORT_CACHE_RESULT ' + json.dumps({'ready': cache is not None, 'path': str(cache) if cache else None}), flush=True)
    else:
        main(sys.argv[1])
