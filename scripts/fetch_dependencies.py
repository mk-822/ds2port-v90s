import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "bld/cache"
CACHE.mkdir(parents=True, exist_ok=True)
for name, item in json.loads((ROOT / "runtime/dependencies.json").read_text()).items():
    path = CACHE / item["file"]
    if not path.exists():
        print("Downloading", name, flush=True)
        request = urllib.request.Request(item["url"], headers={"User-Agent": "ds2port-v90s/0.1.0"})
        with urllib.request.urlopen(request, timeout=120) as source, path.with_suffix(".part").open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
        path.with_suffix(".part").replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise SystemExit("SHA-256 mismatch: " + str(path))
    print("Verified", name, flush=True)
