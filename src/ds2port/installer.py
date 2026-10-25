import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import tarfile
import tempfile
import uuid
from .profiles import digest, game_executable, patch_executable
from .resources import root


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def windows_font(explicit=None):
    path = Path(explicit) if explicit else Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msgothic.ttc"
    if not path.is_file():
        raise ValueError("実行PCのMSゴシック（msgothic.ttc）が見つかりません。フォントファイルを指定してください。")
    with path.open("rb") as source:
        if source.read(4) != b"ttcf":
            raise ValueError("MSゴシックのTTCファイルを指定してください。")
    return path


def font_shim():
    for path in (root() / 'runtime/win32/dsfont.dll', root() / 'bld/win32/dsfont.dll'):
        if path.is_file():
            return path
    raise ValueError('dsfont.dllがありません。scripts/build-font-shim.ps1で互換DLLを作成してください。')


def validate_bundle(path):
    path = Path(path)
    checksum = path.with_name(path.name + ".sha256")
    if not path.is_file() or not checksum.is_file():
        raise ValueError("runtime.tar.gz と runtime.tar.gz.sha256 を同じフォルダーに配置してください。")
    actual = file_hash(path)
    if actual != checksum.read_text(encoding="utf-8").split()[0].lower():
        raise ValueError("ランタイムのSHA-256が一致しません。")
    with tarfile.open(path) as tf:
        metadata = json.load(tf.extractfile("bundle.json"))
    if metadata.get("schema") != 1 or metadata.get("architecture") != "aarch64":
        raise ValueError("対応していないランタイムです。")
    return actual, metadata


def render_template(name, replacements):
    text = (root() / "runtime/templates" / name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("@@" + key + "@@", value)
    if "@@" in text:
        raise ValueError("未解決のテンプレート変数があります。")
    return text.encode("utf-8")


def prepare_payload(source, font, profile, port_id, output, input_mode="mouse"):
    """Read user files without changing the source, including the original EXE."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", port_id):
        raise ValueError("Invalid port ID")
    if input_mode not in ('mouse','joypad'):
        raise ValueError('起動時モードはmouseまたはjoypadを指定してください。')
    source = Path(source).resolve()
    executable = game_executable(source, profile)
    original = executable.read_bytes()
    patched = patch_executable(original, profile)
    font = windows_font(font)
    p, r = "/mnt/plumos/roms/ports/" + port_id, "/mnt/plumos/ports-runtime/" + port_id
    replacements = {"PORT": p, "RUNTIME": r, "EXE": shlex.quote(profile["executable"])}
    backup_name = executable.stem + '.original.exe'

    def add_bytes(tf, name, content, executable=False):
        item = tarfile.TarInfo(name)
        item.size, item.mode, item.mtime = len(content), 0o755 if executable else 0o644, 0
        tf.addfile(item, io.BytesIO(content))

    total = 0
    with tarfile.open(output, "w:gz") as tf:
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError("ゲームフォルダー内のシンボリックリンクは転送できません。")
            if path.is_file() and path != executable:
                name = "game/" + path.relative_to(source).as_posix()
                if name.casefold() == ('game/' + backup_name).casefold():
                    continue
                # Normalize modes; an NTFS readonly source must remain writable on SD.
                def mode(item):
                    item.mode, item.uid, item.gid = 0o644, 0, 0
                    return item
                tf.add(path, arcname=name, recursive=False, filter=mode)
                total += path.stat().st_size
        add_bytes(tf, "game/" + profile["executable"], patched)
        add_bytes(tf, "game/" + backup_name, original)
        add_bytes(tf, "port/assets/fonts/msgothic.ttc", font.read_bytes())
        add_bytes(tf, 'port/runtime/dsfont.dll', font_shim().read_bytes())
        for name in ("env.sh", "launch.sh", "fonts.conf", "asound.conf", "asound-core.conf", "asound-fm.conf"):
            add_bytes(tf, "port/" + name, render_template(name + ".in", replacements), name.endswith(".sh"))
        add_bytes(tf, "port/japanese.reg", (root() / "runtime/templates/japanese.reg").read_bytes())
        for name in ('configure_prefix.py', 'prefix_storage.py', 'common_prefix.py'):
            add_bytes(tf, 'port/' + name, (root() / 'runtime/templates' / name).read_bytes())
        add_bytes(tf, "port/midi-backend", b"opl3\n")
        add_bytes(tf, "port/input-mode", (input_mode+'\n').encode('ascii'))
        add_bytes(tf, "wineserver-wrapper", render_template("wineserver-wrapper.in", replacements), True)
        add_bytes(tf, "launcher.sh", render_template("port-launcher.sh.in", replacements), True)
    return {"port_id": port_id, "profile": profile["id"], "input_mode": input_mode, "executable": profile["executable"],
            "launcher": (profile["launcher"] if port_id == profile["id"] else profile["launcher"] + " (" + port_id + ")") + ".sh",
            "game_sha256": digest(patched), "preserve": profile.get("preserve", [item.name for item in source.iterdir() if item != executable]),
            "payload_sha256": file_hash(output), "game_bytes": total + len(patched) + len(original)}


def inspect_device(connection):
    script = """import json,os,platform,shutil
roots=['/mnt/plumos/roms/ports','/mnt/plumos']
from pathlib import Path
prefix_bytes={p.parent.name:sum(f.stat().st_size for f in p.rglob('*') if f.is_file() and not f.is_symlink()) for p in Path('/mnt/plumos/ports-runtime').glob('*/prefix')}
ready=[p.name for p in Path('/mnt/plumos/ports-runtime').iterdir() if (p/'prefix-configured-v2').is_file() and (p/'prefix/system.reg').is_file() and (p/'prefix/user.reg').is_file()]
common=Path('/mnt/plumos/ports-runtime/.shared/wine10')
shared_ready=(common/'prefix-configured-v2').is_file() and (common/'prefix/system.reg').is_file() and (common/'prefix/user.reg').is_file()
seed_bytes=max((prefix_bytes.get(name,0)+sum(f.stat().st_size for f in (Path('/mnt/plumos/ports-runtime')/name/'prefix-overlays').rglob('*') if f.is_file() and not f.is_symlink()) for name in ready),default=0)
shared_bytes=sum(f.stat().st_size for f in (common/'prefix').rglob('*') if f.is_file() and not f.is_symlink()) if (common/'prefix').exists() else 0
print(json.dumps({'arch':platform.machine(),'uid':os.geteuid(),'plumos':os.path.isfile('/mnt/plumos/bin/plumos-portmaster-port-launch'),'prefix_bytes':prefix_bytes,'prefix_ready':ready,'shared_prefix_ready':shared_ready,'shared_prefix_bytes':shared_bytes,'shared_environment_exists':common.exists(),'shared_prefix_seed_bytes':seed_bytes,'roots':{p:{'free':shutil.disk_usage(p).free,'readonly':bool(os.statvfs(p).f_flag & os.ST_RDONLY)} for p in roots}}))
"""
    return json.loads(connection.run("python3 -c " + shlex.quote(script)))


def required_ext4_bytes(unpacked, archive_bytes, game_bytes, existing_prefix_bytes=0, runtime_cached=False, prefix_ready=False, shared_prefix_seed_bytes=0):
    # Wineboot creates ~565 MiB on this runtime. Reserve it before transfer,
    # including the missing part of an initialization interrupted by ENOSPC.
    prefix_growth=0 if prefix_ready else max(0,640*1024**2-existing_prefix_bytes)
    runtime_growth=0 if runtime_cached else unpacked+archive_bytes
    # Seeding reuses immutable DLLs, while reserving private settings/font copies.
    seed_growth=max(0,shared_prefix_seed_bytes)
    return runtime_growth+game_bytes*3+prefix_growth+seed_growth+160*1024**2


def install(connection, source, runtime, profile, font=None, port_id=None, log=print, progress=lambda value: None, input_mode="mouse"):
    port_id = port_id or profile["id"]
    runtime_hash, metadata = validate_bundle(runtime)
    # Reject unsupported games before making any changes on the device.
    patch_executable(game_executable(Path(source), profile).read_bytes(), profile)
    windows_font(font)
    status = inspect_device(connection)
    if status["arch"] != "aarch64" or status["uid"] != 0 or not status["plumos"]:
        raise ValueError("PlumOS V90S V2のaarch64環境へ、rootで接続してください。")
    if any(x["readonly"] for x in status["roots"].values()):
        raise ValueError("本体の保存領域が読み取り専用です。転送を中止しました。")
    unpacked = metadata["unpacked_bytes"]
    game_size = sum(p.stat().st_size for p in Path(source).rglob("*") if p.is_file())
    if status["roots"]["/mnt/plumos/roms/ports"]["free"] < game_size * 2 + 32 * 1024**2:
        raise ValueError("共有領域の空き容量が不足しています。")
    with tempfile.TemporaryDirectory(prefix="ds2port-") as tmp:
        payload = Path(tmp) / "payload.tar.gz"
        log("ゲームを検証し、互換修正とMSゴシックを転送用に準備しています。")
        config = prepare_payload(source, font, profile, port_id, payload, input_mode)
        config["runtime_sha256"] = runtime_hash
        config['tool_version'] = '0.1.4'
        r = "/mnt/plumos/ports-runtime/" + port_id
        stage = r + "/.incoming-" + uuid.uuid4().hex
        lock = r + "/.ds2port-install.lock"
        q = shlex.quote
        connection.run("set -e; test ! -S /tmp/.X11-unix/X93 || { echo '先に起動中のゲームを終了してください。'; exit 1; }; mkdir -p " + q(r) + "; mkdir " + q(lock) + "; if test -d /run/plumos/ds2port-display93.lock; then rmdir " + q(lock) + "; echo '先に起動中のゲームを終了してください。'; exit 1; fi")
        try:
            connection.run("mkdir " + q(stage))
            connection.upload_bytes((root() / "runtime/install_remote.py").read_bytes(), stage + "/install.py")
            with tarfile.open(runtime) as archive:
                entries = [[m.name, 'file' if m.isfile() else 'directory' if m.isdir() else 'symlink' if m.issym() else 'hardlink', m.mode & 0o777, m.linkname, m.size] for m in archive.getmembers()]
            description = {'runtime_sha256': runtime_hash, 'bundle': metadata, 'entries': entries}
            connection.upload_bytes(json.dumps(description).encode(), stage + '/cache.json')
            log('本体の同一ランタイムを検証し、共有キャッシュを準備しています。')
            output = connection.run('python3 ' + q(stage + '/install.py') + ' --cache ' + q(stage + '/cache.json'), timeout=1200)
            cached = json.loads(next(line.split(' ', 1)[1] for line in output.splitlines() if line.startswith('DS2PORT_CACHE_RESULT ')))
            status = inspect_device(connection)
            legacy_ready=bool(status.get('prefix_ready')) and not status.get('shared_environment_exists',False)
            shared_ready=status.get('shared_prefix_ready',False)
            needed=required_ext4_bytes(unpacked,Path(runtime).stat().st_size,game_size,
                                      status.get('shared_prefix_bytes',0),cached['ready'],
                                      shared_ready or legacy_ready,status.get('shared_prefix_seed_bytes',0) if legacy_ready and not shared_ready else 0)
            if status['roots']['/mnt/plumos']['free'] < needed:
                raise ValueError(f'ext4領域の空き容量が不足しています。共有後の転送一時領域とWine初回起動分を含め、約{needed/1024**3:.2f}GiB必要です。')
            if cached['ready']:
                config['runtime_cache'] = cached['path']
                log('共有ランタイムを再利用します。ランタイムの転送・全量展開は省略します。')
                transfers = (("payload", payload, 0, 85),)
            else:
                transfers = (("runtime", Path(runtime), 0, 60), ("payload", payload, 60, 25))
            for name, path, start, span in transfers:
                log(("ランタイム" if name == "runtime" else "ゲームとフォント") + "を転送しています。")
                connection.upload(path, stage + "/" + name + ".tar.gz", lambda done, total, s=start, n=span: progress(s + int(n * done / max(total, 1))))
            connection.upload_bytes(json.dumps(config, ensure_ascii=False).encode(), stage + "/config.json")
            log("本体でハッシュ検証・バックアップ・配置・Box64動作確認を行っています。")
            output = connection.run("python3 " + q(stage + "/install.py") + " " + q(stage + "/config.json"), timeout=1200)
            if "DS2PORT_INSTALL_OK" not in output:
                raise RuntimeError(output)
            log(output.strip())
            progress(100)
            return config
        finally:
            # Only paths freshly generated above are removed. Existing backups,
            # prefixes and game data are never recursive-delete targets here.
            cleanup = "import shutil,pathlib; p=pathlib.Path(" + repr(stage) + "); shutil.rmtree(p,ignore_errors=True); pathlib.Path(" + repr(lock) + ").rmdir()"
            try:
                connection.run("python3 -c " + q(cleanup))
            except Exception as error:
                log("一時ファイルの後片付けが必要です: " + str(error))


def launch(connection, config):
    launcher = "/mnt/plumos/roms/ports/" + config["launcher"]
    log_path = "/mnt/plumos/ports-runtime/" + config["port_id"] + "/logs"
    command = "mkdir -p " + shlex.quote(log_path) + "; nohup /mnt/plumos/bin/plumos-portmaster-port-launch " + shlex.quote(launcher)
    command += " >> " + shlex.quote(log_path + "/ports-wrapper.log") + " 2>&1 < /dev/null &"
    connection.run(command)
