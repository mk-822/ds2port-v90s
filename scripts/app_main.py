import json
from pathlib import Path
import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    if Path(sys.executable).stem.casefold() == "ds2portcli":
        from ds2port.cli import main as cli
        try:
            return cli(sys.argv[1:])
        except Exception as error:
            print(str(error), file=sys.stderr)
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from ds2port.cli import main as cli
        try:
            return cli(sys.argv[2:])
        except Exception as error:
            print(str(error), file=sys.stderr)
            return 1
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        import tkinter as tk
        from ds2port.gui import App
        from ds2port.profiles import profiles
        from ds2port.installer import windows_font
        window = tk.Tk()
        window.withdraw()
        app = App(window)
        window.geometry("800x760")
        window.update()
        result = {"gui": True, "profiles": len(profiles()), "windows_font": windows_font().name,
                  "requested_width": app.winfo_reqwidth(), "requested_height": app.winfo_reqheight()}
        window.destroy()
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(json.dumps(result), encoding="utf-8")
        return 0
    from ds2port.gui import main as gui
    gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
