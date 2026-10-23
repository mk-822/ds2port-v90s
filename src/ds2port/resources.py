from pathlib import Path
import sys


def root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def application_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else root() / "bld"
