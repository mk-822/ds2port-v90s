"""Connection preferences for the desktop transfer tool."""
import json
import os
from pathlib import Path
import tempfile


def settings_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "ds2port-v90s" / "settings.json"


def load_connection_settings(path=None):
    settings = {"host": "", "username": "root", "save_password": False, "password": ""}
    try:
        data = json.loads((Path(path) if path is not None else settings_path()).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return settings
    if not isinstance(data, dict):
        return settings
    for name in ("host", "username"):
        if isinstance(data.get(name), str):
            settings[name] = data[name]
    settings["save_password"] = data.get("save_password") is True
    if settings["save_password"] and isinstance(data.get("password"), str):
        settings["password"] = data["password"]
    return settings


def save_connection_settings(host, username, password, save_password, path=None):
    path = Path(path) if path is not None else settings_path()
    data = {"host": host.strip(), "username": username.strip(), "save_password": bool(save_password)}
    if save_password:
        data["password"] = password
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
