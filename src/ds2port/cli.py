import argparse
import json
import os
from pathlib import Path
from .installer import MIDI_BACKENDS, install, inspect_device, launch, list_installed, uninstall
from .profiles import profiles, detect_game
from .resources import application_dir
from .ssh import Connection, UnknownHostKey, trust_host


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compile DiscStation → PlumOS V90S V2")
    parser.add_argument("action", choices=('inspect', 'install', 'list', 'uninstall'))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="root")
    parser.add_argument("--key")
    parser.add_argument("--password-env", default="DS2PORT_SSH_PASSWORD")
    parser.add_argument("--accept-new-host-key", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--runtime", type=Path, default=application_dir() / "runtime.tar.gz")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--profile", default="auto", help="通常はauto（既知の互換設定を自動認識）")
    parser.add_argument("--executable", help="ゲームフォルダー内の起動EXE名。複数ある場合に指定")
    parser.add_argument("--port-id", help="検証用の別配置ID。通常は省略")
    parser.add_argument('--ports-name', help='Ports での表示名。拡張子 .sh は自動で付加')
    parser.add_argument('--yes', action='store_true', help='アンインストール時にゲームと個別データの削除を確定')
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--input-mode", choices=('mouse','joypad','keyboard'), default='mouse', help='起動時の入力モード')
    parser.add_argument("--midi-backend", choices=MIDI_BACKENDS, default='opl3', help='MIDI音源')
    parser.add_argument("--display-mode", choices=('auto','16bit','windowed'), default='auto', help='描画モード。16bitとwindowedは対応版CJ16用')
    args = parser.parse_args(argv)
    if args.action == 'uninstall' and (not args.port_id or not args.yes):
        parser.error('uninstall には --port-id と --yes が必要です。')
    options = dict(host=args.host, username=args.user, password=os.environ.get(args.password_env, ""),
                   port=args.port, key_filename=args.key)
    try:
        connection = Connection(**options)
    except UnknownHostKey as error:
        if not args.accept_new_host_key:
            parser.error("未登録の接続先の鍵です: " + str(error) + "\n確認後 --accept-new-host-key を指定してください。")
        print("登録する接続先の鍵:", error)
        trust_host(error)
        connection = Connection(**options)
    try:
        if args.action == "inspect":
            print(json.dumps(inspect_device(connection), ensure_ascii=False, indent=2))
        elif args.action == 'list':
            print(json.dumps(list_installed(connection), ensure_ascii=False, indent=2))
        elif args.action == 'uninstall':
            uninstall(connection, args.port_id)
            print('アンインストールしました。')
        else:
            if args.source is None:
                parser.error("installには --source が必要です。")
            profile = detect_game(args.source, args.executable) if args.profile == 'auto' else next((p for p in profiles() if p["id"] == args.profile), None)
            if profile is None:
                parser.error("未対応のゲームです。")
            config = install(connection, args.source, args.runtime, profile, args.font, args.port_id,
                             input_mode=args.input_mode, ports_name=args.ports_name,
                             midi_backend=args.midi_backend, display_mode=args.display_mode)
            if args.launch:
                launch(connection, config)
    finally:
        connection.close()
    return 0
