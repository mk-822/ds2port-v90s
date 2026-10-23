import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .installer import install, inspect_device, launch, windows_font
from .profiles import detect_game, executables
from .resources import application_dir
from .ssh import Connection, UnknownHostKey, trust_host


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=18)
        self.pack(fill="both", expand=True)
        master.title("DS2Port V90S — DiscStation 転送ツール")
        master.minsize(780, 760)
        self.events, self.busy = queue.Queue(), False
        self.values = {name: tk.StringVar(value=value) for name, value in {
            "executable": "", "source": "", "host": "", "username": "root",
            "input_mode": "マウス",
            "password": "", "key": "", "runtime": str(application_dir() / "runtime.tar.gz"),
            "font": str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msgothic.ttc"),
        }.items()}
        self.start_after = tk.BooleanVar(value=False)
        self._build()
        self.values['source'].trace_add('write', self._source_changed)
        self.after(80, self._poll)
        master.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        game = ttk.LabelFrame(self, text="転送するゲーム", padding=12)
        game.pack(fill="x")
        game.columnconfigure(1, weight=1)
        self._path_row(game, 0, "ゲームフォルダー", "source", True)
        ttk.Label(game, text="起動EXE").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
        self.exe_picker = ttk.Combobox(game, textvariable=self.values["executable"], state="readonly")
        self.exe_picker.grid(row=1, column=1, columnspan=2, sticky="ew")
        self._path_row(game, 2, "ランタイム", "runtime", False)
        self._path_row(game, 3, "MSゴシック（このPC）", "font", False)
        try:
            windows_font()
            font_text = "MSゴシックはこのPCのWindowsから取得し、本体へ転送します。"
        except ValueError:
            font_text = "このPCでMSゴシックを検出できません。転送にはmsgothic.ttcが必要です。"
        ttk.Label(game, text=font_text, foreground="#555555").grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(game, text="起動時モード").grid(row=5, column=0, sticky="w", pady=(10,0))
        ttk.Combobox(game, textvariable=self.values['input_mode'], values=('マウス','Joypad'), state='readonly').grid(row=5, column=1, columnspan=2, sticky='ew', pady=(10,0))
        device = ttk.LabelFrame(self, text="接続先の本体（Wi-FiとSSHを有効にしてください）", padding=12)
        device.pack(fill="x", pady=12)
        device.columnconfigure(1, weight=1)
        for row, (name, title) in enumerate((("host", "IPアドレス"), ("username", "SSHユーザー"), ("password", "パスワード"))):
            ttk.Label(device, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            ttk.Entry(device, textvariable=self.values[name], show="•" if name == "password" else "").grid(row=row, column=1, columnspan=2, sticky="ew")
        self._path_row(device, 3, "秘密鍵（任意）", "key", False)
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(actions, text="転送完了後に本体で起動する", variable=self.start_after).pack(side="left")
        self.inspect_button = ttk.Button(actions, text="接続を確認", command=lambda: self._begin(False))
        self.inspect_button.pack(side="right", padx=(8, 0))
        self.install_button = ttk.Button(actions, text="ゲームを転送", command=lambda: self._begin(True))
        self.install_button.pack(side="right")
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill="x")
        self.status = ttk.Label(self, text="準備できました。パスワードは保存しません。", anchor="w")
        self.status.pack(fill="x", pady=7)
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=10, wrap="word", state="disabled", font=("Yu Gothic UI", 9))
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _source_changed(self, *_):
        try:
            names = [p.name for p in executables(Path(self.values['source'].get()))] if self.values['source'].get() else []
        except (OSError, ValueError):
            names = []
        self.exe_picker.configure(values=names)
        if self.values['executable'].get() not in names:
            self.values['executable'].set(names[0] if len(names) == 1 else '')

    def _path_row(self, parent, row, label, name, folder):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(parent, textvariable=self.values[name]).grid(row=row, column=1, sticky="ew")
        def browse():
            path = filedialog.askdirectory(parent=self) if folder else filedialog.askopenfilename(parent=self)
            if path:
                self.values[name].set(path)
        ttk.Button(parent, text="参照…", command=browse, width=9).grid(row=row, column=2, padx=(8, 0))

    def _begin(self, transfer):
        values = {key: value.get().strip() if key != "password" else value.get() for key, value in self.values.items()}
        if not values["host"] or not values["username"]:
            messagebox.showinfo("接続先", "本体のIPアドレスとSSHユーザーを入力してください。", parent=self)
            return
        if transfer and not values["source"]:
            messagebox.showinfo("ゲームフォルダー", "ゲームのフォルダーを指定してください。", parent=self)
            return
        self.busy = True
        self.progress["value"] = 0
        self.install_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        start_after = self.start_after.get()
        threading.Thread(target=self._work, args=(values, transfer, start_after), daemon=True).start()

    def _work(self, values, transfer, start_after):
        connection = None
        log = lambda text: self.events.put(("log", text))
        try:
            options = dict(host=values["host"], username=values["username"], password=values["password"], key_filename=values["key"] or None)
            log("本体へ接続しています。")
            try:
                connection = Connection(**options)
            except UnknownHostKey as error:
                answer, ready = {}, threading.Event()
                self.events.put(("hostkey", (error, answer, ready)))
                ready.wait()
                if not answer.get("yes"):
                    raise ValueError("接続先の鍵が未確認のため中止しました。")
                trust_host(error)
                connection = Connection(**options)
            if transfer:
                profile = detect_game(Path(values['source']), values['executable'] or None)
                log('起動EXE: ' + profile['executable'] + ' / ' + profile['status'])
                result = install(connection, Path(values["source"]), Path(values["runtime"]), profile, font=values["font"] or None,
                                 log=log, progress=lambda value: self.events.put(("progress", value)),
                                 input_mode='joypad' if values['input_mode']=='Joypad' else 'mouse')
                if start_after:
                    launch(connection, result)
                log("転送が完了しました。Portsから「" + profile["launcher"] + "」を選択できます。")
            else:
                status = inspect_device(connection)
                log("接続できました。CPU: " + status["arch"])
                for path, data in status["roots"].items():
                    log(f"{path}: 空き {data['free'] / 1024**3:.2f} GiB / " + ("読み取り専用" if data["readonly"] else "書き込み可能"))
            self.events.put(("done", None))
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            if connection:
                connection.close()

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "hostkey":
                    error, answer, ready = value
                    answer["yes"] = messagebox.askyesno("初回接続：本体の鍵を確認", f"接続先: {error.hostname}\n\n{error.fingerprint}\n\nこの本体の鍵として登録しますか？", parent=self)
                    ready.set()
                elif kind == "progress":
                    self.progress["value"] = value
                elif kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", value + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                    self.status.configure(text=value.splitlines()[0])
                elif kind in ("done", "error"):
                    self.busy = False
                    self.install_button.configure(state="normal")
                    self.inspect_button.configure(state="normal")
                    self.status.configure(text="完了しました。" if kind == "done" else "処理を中止しました。")
                    if kind == "error":
                        messagebox.showerror("転送ツール", value, parent=self)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _close(self):
        if self.busy:
            messagebox.showinfo("処理中", "転送・配置処理が完了してから閉じてください。", parent=self)
        else:
            self.master.destroy()


def main():
    window = tk.Tk()
    App(window)
    window.mainloop()
