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
                result[relative] = ('file', sha(item), item.stat().st_mode & 0o777)
            elif item.is_dir():
                result[relative] = ('directory',)
            else:
                return None
        return result
    expected = entries(source)
    return expected is not None and expected == entries(destination)


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


def main(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    ident = config["port_id"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", ident):
        raise ValueError("Invalid port ID")
    p = Path("/mnt/plumos/roms/ports") / ident
    r = Path("/mnt/plumos/ports-runtime") / ident
    stage = config_path.parent
    if stage.parent != r or not stage.name.startswith(".incoming-"):
        raise ValueError("Invalid staging path")
    if platform.machine() != "aarch64":
        raise ValueError("This runtime requires aarch64")
    if p.is_symlink() or r.is_symlink():
        raise ValueError("Port root must not be a symbolic link")
    if Path("/tmp/.X11-unix/X93").exists():
        raise ValueError("先に起動中のゲームを終了してください。")
    for root in (Path("/mnt/plumos/roms/ports"), r):
        if os.statvfs(root).f_flag & os.ST_RDONLY:
            raise ValueError("転送先が読み取り専用です。SDの状態を確認してください。")
    for name in ("runtime", "payload"):
        if sha(stage / (name + ".tar.gz")) != config[name + "_sha256"]:
            raise ValueError(name + " archive checksum mismatch")
    unpacked = stage / "unpacked"
    runtime, payload = unpacked / "runtime", unpacked / "payload"
    runtime.mkdir(parents=True)
    payload.mkdir()
    print("アーカイブを検証・展開しています。", flush=True)
    safe_extract(stage / "runtime.tar.gz", runtime)
    safe_extract(stage / "payload.tar.gz", payload)
    manifest = json.loads((runtime / "bundle.json").read_text())
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported runtime bundle")
    for name, expected in manifest["files"].items():
        path = runtime / name
        if not path.resolve().is_relative_to(runtime.resolve()) or sha(path) != expected:
            raise ValueError("Runtime file mismatch: " + name)
    launcher = config["launcher"]
    if "/" in launcher or "\\" in launcher or not launcher.endswith(".sh"):
        raise ValueError("Invalid launcher name")
    if sha(payload / "game" / config["executable"]) != config["game_sha256"]:
        raise ValueError("Game executable mismatch")
    backup = r / "backups" / (time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + stage.name[-8:])
    backup.mkdir(parents=True)
    changes = []

    def install_file(source, dest):
        if dest.is_symlink() or any(x.is_symlink() for x in dest.parents if x not in (Path('/'),)):
            # /mnt/plumos/roms may itself be a normal system symlink; roots were
            # checked above. Only descendants of the per-port roots are restricted.
            for root in (p, r):
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
        shutil.copy2(source, tmp)
        changes.append(("file", dest, old))
        os.replace(tmp, dest)

    try:
        print("バックアップを保存して配置しています。", flush=True)
        p.mkdir(parents=True, exist_ok=True)
        existing_game = (p / "game").exists()
        existing_roots = {child.name.casefold() for child in (p / "game").iterdir()} if existing_game else set()
        for name in ("native", "wine-10.0-amd64-wow64", "licenses"):
            dest = r / name
            if same_tree(runtime / name, dest):
                print('既存ランタイムを再利用: ' + name, flush=True)
                shutil.rmtree(runtime / name)
                continue
            if name=='wine-10.0-amd64-wow64':
                candidates=[other/name for other in sorted(r.parent.iterdir())
                            if other!=r and not other.is_symlink()
                            and (p.parent/other.name/'ds2port-installed.json').is_file()]
                linked=share_wine_files(runtime/name,candidates)
                print('他のゲームと同一のWineファイルを共有: '+str(linked),flush=True)
            old = backup / name if dest.exists() else None
            if old:
                os.replace(dest, old)
            changes.append(("directory", dest, old))
            os.replace(runtime / name, dest)
        for subtree in (runtime / "shared", payload / "port"):
            for source in sorted(subtree.rglob("*")):
                if source.is_file():
                    install_file(source, p / source.relative_to(subtree))
        preserve = {x.casefold() for x in config["preserve"]}
        for source in sorted((payload / "game").rglob("*")):
            relative = source.relative_to(payload / "game")
            if relative.parts[0].casefold() in preserve & existing_roots:
                continue
            if source.is_file():
                install_file(source, p / "game" / relative)
        install_file(payload / "wineserver-wrapper", r / "wineserver-wrapper")
        install_file(payload / "launcher.sh", p.parent / launcher)
        # Existing Japanese Noto replacements must be cleared with Wine stopped.
        user_reg = r / "prefix/user.reg"
        if user_reg.exists():
            content = user_reg.read_text()
            for face in ("MS Gothic", "MS PGothic", "MS UI Gothic"):
                content = content.replace('"' + face + '"="Noto Sans CJK JP"\n', "")
            edited = stage / "user.reg"
            edited.write_text(content)
            install_file(edited, user_reg)
        result = subprocess.run(["sh", str(p / "launch.sh"), "--check"], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = str(r / "native/lib") + ":/mnt/plumos/lib"
        result = subprocess.run([str(p / "runtime/box64"), str(r / "native/tests/linux-probe")], env=env, text=True, capture_output=True)
        if result.returncode or "BOX64_LINUX_OK" not in result.stdout:
            raise RuntimeError("Box64動作検査に失敗しました: " + result.stdout + result.stderr)
        (p / "ds2port-installed.json").write_text(json.dumps({"version": "0.1.0", "profile": config["profile"], "backup": str(backup)}, indent=2))
        print(result.stdout.strip(), flush=True)
        print("DS2PORT_INSTALL_OK backup=" + str(backup), flush=True)
    except BaseException:
        for kind, dest, old in reversed(changes):
            if kind == "directory":
                if dest.exists():
                    shutil.rmtree(dest)
                if old:
                    os.replace(old, dest)
            elif old:
                shutil.copy2(old, dest)
            else:
                dest.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main(sys.argv[1])
