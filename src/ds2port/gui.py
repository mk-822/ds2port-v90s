import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .installer import install, inspect_device, launch, list_installed, uninstall, windows_font
from .profiles import detect_game, executables
from .resources import application_dir
from .settings import load_connection_settings, save_connection_settings
from .ssh import Connection, UnknownHostKey, trust_host


CONNECTION_FIELDS = ('host', 'username', 'password', 'key')
MIDI_CHOICES = {'OPL3（FM音源）': 'opl3', 'TimGM6mb（軽量SoundFont）': 'timgm6mb',
                'GeneralUser GS（SoundFont）': 'generaluser-gs'}
DISPLAY_CHOICES = {'自動（推奨）': 'auto', '16ビット（仮想フルスクリーン）': '16bit',
                   '標準ウィンドウ（32ビット）': 'windowed'}


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=18)
        self.pack(fill="both", expand=True)
        master.title("DS2Port V90S — DiscStation 転送ツール")
        master.minsize(940, 760)
        self.events, self.busy = queue.Queue(), False
        self.ports = []
        self.values = {name: tk.StringVar(value=value) for name, value in {
            "executable": "", "source": "", "host": "", "username": "root",
            "input_mode": "マウス", "ports_name": "",
            "midi_backend": next(iter(MIDI_CHOICES)), "display_mode": next(iter(DISPLAY_CHOICES)),
            "password": "", "key": "", "runtime": str(application_dir() / "runtime.tar.gz"),
            "font": str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msgothic.ttc"),
        }.items()}
        saved = load_connection_settings()
        for name in ("host", "username", "password"):
            self.values[name].set(saved[name])
        self.save_password = tk.BooleanVar(value=saved["save_password"])
        self.start_after = tk.BooleanVar(value=False)
        self._build()
        self.values['source'].trace_add('write', self._source_changed)
        self.values['executable'].trace_add('write', self._display_choices_changed)
        for name in CONNECTION_FIELDS:
            self.values[name].trace_add('write', self._connection_changed)
        self.after(80, self._poll)
        master.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        transfer = ttk.Frame(self)
        transfer.pack(side="left", fill="both", expand=True, padx=(0, 12))
        game = ttk.LabelFrame(transfer, text="転送するゲーム", padding=12)
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
        ttk.Label(game, text=font_text, foreground="#555555", wraplength=460).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(game, text="起動時モード").grid(row=5, column=0, sticky="w", pady=(10,0))
        ttk.Combobox(game, textvariable=self.values['input_mode'], values=('マウス','Joypad','キーボード'), state='readonly').grid(row=5, column=1, columnspan=2, sticky='ew', pady=(10,0))
        ttk.Label(game, text='MIDI音源').grid(row=6, column=0, sticky='w', pady=5)
        ttk.Combobox(game, textvariable=self.values['midi_backend'], values=tuple(MIDI_CHOICES), state='readonly').grid(
            row=6, column=1, columnspan=2, sticky='ew')
        ttk.Label(game, text='描画モード').grid(row=7, column=0, sticky='w', pady=5)
        self.display_picker = ttk.Combobox(game, textvariable=self.values['display_mode'],
                                           values=(next(iter(DISPLAY_CHOICES)),), state='disabled')
        self.display_picker.grid(row=7, column=1, columnspan=2, sticky='ew')
        ttk.Label(game, text='Ports の表示名').grid(row=8, column=0, sticky='w', pady=5)
        ttk.Entry(game, textvariable=self.values['ports_name']).grid(row=8, column=1, sticky='ew')
        ttk.Label(game, text='空欄で既定名').grid(row=8, column=2, padx=(8, 0))
        device = ttk.LabelFrame(transfer, text="接続先の本体（Wi-FiとSSHを有効にしてください）", padding=12)
        device.pack(fill="x", pady=12)
        device.columnconfigure(1, weight=1)
        for row, (name, title) in enumerate((("host", "IPアドレス"), ("username", "SSHユーザー"), ("password", "パスワード"))):
            ttk.Label(device, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            ttk.Entry(device, textvariable=self.values[name], show="•" if name == "password" else "").grid(row=row, column=1, columnspan=2, sticky="ew")
        ttk.Checkbutton(device, text="SSHパスワードを保存する", variable=self.save_password).grid(
            row=3, column=1, columnspan=2, sticky="w", pady=(0, 5))
        self._path_row(device, 4, "秘密鍵（任意）", "key", False)
        actions = ttk.Frame(transfer)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(actions, text="転送完了後に本体で起動する", variable=self.start_after).pack(side="left")
        self.inspect_button = ttk.Button(actions, text="接続を確認", command=lambda: self._begin('inspect'))
        self.inspect_button.pack(side="right", padx=(8, 0))
        self.install_button = ttk.Button(actions, text="ゲームを転送", command=lambda: self._begin('install'))
        self.install_button.pack(side="right")
        self.progress = ttk.Progressbar(transfer, maximum=100)
        self.progress.pack(fill="x")
        self.status = ttk.Label(transfer, text="準備できました。", anchor="w")
        self.status.pack(fill="x", pady=7)
        log_frame = ttk.Frame(transfer)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=8, wrap="word", state="disabled", font=("Yu Gothic UI", 9))
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

        installed = ttk.LabelFrame(self, text="本体にインストール済みのゲーム", padding=12)
        installed.pack(side="right", fill="y")
        self.refresh_button = ttk.Button(installed, text="一覧を更新", command=lambda: self._begin('list'))
        self.refresh_button.pack(anchor="e")
        self.ports_status = ttk.Label(installed, text="「一覧を更新」で取得できます。")
        self.ports_status.pack(anchor="w", pady=8)
        entries = ttk.Frame(installed)
        entries.pack(fill="both", expand=True)
        entries.columnconfigure(0, weight=1)
        entries.rowconfigure(0, weight=1)
        self.port_list = tk.Listbox(entries, width=40, exportselection=False, activestyle="none")
        self.port_list.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(entries, command=self.port_list.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(entries, orient="horizontal", command=self.port_list.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.port_list.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.port_list.bind("<<ListboxSelect>>", self._update_uninstall_button)
        self.uninstall_button = ttk.Button(installed, text="選択したゲームをアンインストール…",
                                           command=lambda: self._begin('uninstall'), state="disabled")
        self.uninstall_button.pack(anchor="e", pady=(10, 0))

    def _connection_changed(self, *_):
        self._show_ports([], "「一覧を更新」で取得できます。")

    def _show_ports(self, ports, status):
        self.ports = ports
        self.port_list.delete(0, "end")
        for port in ports:
            ident = port['port_id']
            launcher = port['launcher']
            self.port_list.insert("end", f"{launcher.removesuffix('.sh')}  ({ident})" if launcher else ident)
        self.ports_status.configure(text=status)
        self._update_uninstall_button()

    def _update_uninstall_button(self, *_):
        self.uninstall_button.configure(state="normal" if not self.busy and self.port_list.curselection() else "disabled")

    def _source_changed(self, *_):
        try:
            names = [p.name for p in executables(Path(self.values['source'].get()))] if self.values['source'].get() else []
        except (OSError, ValueError):
            names = []
        self.exe_picker.configure(values=names)
        if self.values['executable'].get() not in names:
            self.values['executable'].set(names[0] if len(names) == 1 else '')
        else:
            self._display_choices_changed()

    def _display_choices_changed(self, *_):
        name = self.values['executable'].get()
        supports_modes = False
        if name.casefold() == 'cj16.exe':
            try:
                profile = detect_game(Path(self.values['source'].get()), name)
                supports_modes = bool(profile.get('windowed_sha256'))
            except (OSError, ValueError):
                pass
        if supports_modes:
            self.display_picker.configure(values=tuple(DISPLAY_CHOICES), state='readonly')
        else:
            auto = next(iter(DISPLAY_CHOICES))
            self.values['display_mode'].set(auto)
            self.display_picker.configure(values=(auto,), state='disabled')

    def _path_row(self, parent, row, label, name, folder):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        ttk.Entry(parent, textvariable=self.values[name]).grid(row=row, column=1, sticky="ew")
        def browse():
            path = filedialog.askdirectory(parent=self) if folder else filedialog.askopenfilename(parent=self)
            if path:
                self.values[name].set(path)
        ttk.Button(parent, text="参照…", command=browse, width=9).grid(row=row, column=2, padx=(8, 0))

    def _value(self, name):
        value = self.values[name].get()
        return value if name == 'password' else value.strip()

    def _begin(self, action):
        if self.busy:
            return
        values = {name: self._value(name) for name in self.values}
        if not values["host"] or not values["username"]:
            messagebox.showinfo("接続先", "本体のIPアドレスとSSHユーザーを入力してください。", parent=self)
            return
        if action == 'install' and not values["source"]:
            messagebox.showinfo("ゲームフォルダー", "ゲームのフォルダーを指定してください。", parent=self)
            return
        port = None
        if action == 'uninstall':
            selection = self.port_list.curselection()
            if not selection:
                return
            index = selection[0]
            title = self.port_list.get(index)
            if not messagebox.askyesno(
                "削除の確認",
                f"{values['host']} から「{title}」を削除しますか？\nゲームフォルダー内のセーブと個別バックアップも削除します。",
                parent=self, default="no",
            ):
                return
            port = self.ports[index]
        self.busy = True
        self.progress["value"] = 0
        self.install_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.ports_status.configure(text="本体で処理中です…")
        self._update_uninstall_button()
        start_after = self.start_after.get()
        threading.Thread(target=self._work, args=(values, action, start_after, port), daemon=True).start()

    def _work(self, values, action, start_after, port):
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
            if action == 'install':
                profile = detect_game(Path(values['source']), values['executable'] or None)
                log(f"起動EXE: {profile['executable']} / 描画: {values['display_mode']} / MIDI: {values['midi_backend']}")
                result = install(connection, Path(values["source"]), Path(values["runtime"]), profile, font=values["font"] or None,
                                 log=log, progress=lambda value: self.events.put(("progress", value)),
                                 input_mode={'マウス':'mouse','Joypad':'joypad','キーボード':'keyboard'}[values['input_mode']],
                                 ports_name=values['ports_name'], midi_backend=MIDI_CHOICES[values['midi_backend']],
                                 display_mode=DISPLAY_CHOICES[values['display_mode']])
                if start_after:
                    launch(connection, result)
                log('転送が完了しました。Ports から「' + result['launcher'][:-3] + '」を選べます。')
            elif action == 'uninstall':
                if port not in list_installed(connection):
                    raise ValueError('選択したゲームの情報が変わりました。一覧を更新してください。')
                uninstall(connection, port['port_id'])
                log('アンインストールしました。')
            elif action == 'inspect':
                status = inspect_device(connection)
                log("接続できました。CPU: " + status["arch"])
                for path, data in status["roots"].items():
                    log(f"{path}: 空き {data['free'] / 1024**3:.2f} GiB / " + ("読み取り専用" if data["readonly"] else "書き込み可能"))
            try:
                ports = list_installed(connection)
            except Exception as error:
                if action == 'list':
                    raise
                log('インストール済みのゲーム一覧を取得できませんでした。\n' + str(error))
                ports = None
            self.events.put(("done", (values, ports)))
        except Exception as error:
            self.events.put(("error", (values, str(error))))
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
                    values, result = value
                    self.busy = False
                    self.install_button.configure(state="normal")
                    self.inspect_button.configure(state="normal")
                    self.refresh_button.configure(state="normal")
                    if all(values[name] == self._value(name) for name in CONNECTION_FIELDS):
                        if kind == "done" and result is not None:
                            self._show_ports(result, f"{len(result)} 件" if result else "インストール済みのゲームはありません。")
                        else:
                            self._show_ports([], "「一覧を更新」で再取得してください。")
                    self.status.configure(text="完了しました。" if kind == "done" else "処理を中止しました。")
                    if kind == "error":
                        messagebox.showerror("転送ツール", result, parent=self)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _close(self):
        if self.busy:
            messagebox.showinfo("処理中", "転送・配置処理が完了してから閉じてください。", parent=self)
        else:
            try:
                save_connection_settings(self.values["host"].get(), self.values["username"].get(),
                                         self.values["password"].get(), self.save_password.get())
            except OSError as error:
                messagebox.showwarning("接続情報の保存", f"接続情報を保存できませんでした。\n{error}", parent=self)
            self.master.destroy()


def main():
    window = tk.Tk()
    App(window)
    window.mainloop()
