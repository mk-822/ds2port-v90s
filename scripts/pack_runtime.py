"""Pack the Linux tar on the host; preserve links without creating NTFS links."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import io
import json
import sys
import tarfile

source, output = map(Path, sys.argv[1:])
files, unpacked = {}, 0
with tarfile.open(source, "r:") as original:
    members = original.getmembers()
    for member in members:
        if not member.isfile():
            continue
        name = PurePosixPath(member.name).as_posix()
        if PurePosixPath(name).name.casefold() in {"msgothic.ttc", "jump3.exe", "jump3.original.exe"}:
            raise SystemExit("Private file in runtime: " + name)
        h = hashlib.sha256()
        with original.extractfile(member) as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        files[name] = h.hexdigest()
        unpacked += member.size
    manifest = {"schema": 1, "version": "0.1.0", "architecture": "aarch64", "unpacked_bytes": unpacked, "files": files}
    content = json.dumps(manifest, sort_keys=True, indent=2).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".building")
    with tarfile.open(temporary, "w:gz", compresslevel=6) as packed:
        item = tarfile.TarInfo("bundle.json")
        item.size, item.mode = len(content), 0o644
        packed.addfile(item, io.BytesIO(content))
        for member in members:
            member = copy.copy(member)
            member.name = PurePosixPath(member.name).as_posix()
            if member.name == ".":
                continue
            packed.addfile(member, original.extractfile(member) if member.isfile() else None)
    temporary.replace(output)
h = hashlib.sha256(output.read_bytes()).hexdigest()
output.with_name(output.name + ".sha256").write_text(h + "  " + output.name + "\n")
print("RUNTIME_BUILT", output, output.stat().st_size, "sha256=" + h, flush=True)
