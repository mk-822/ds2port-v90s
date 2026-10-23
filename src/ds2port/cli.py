import argparse
import json
import os
from pathlib import Path
from .installer import install, inspect_device, launch
from .profiles import profiles
from .resources import application_dir
from .ssh import Connection, UnknownHostKey, trust_host


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compile DiscStation → PlumOS V90S V2")
    parser.add_argument("action", choices=("inspect", "install"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", default="root")
    parser.add_argument("--key")
    parser.add_argument("--password-env", default="DS2PORT_SSH_PASSWORD")
    parser.add_argument("--accept-new-host-key", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--runtime", type=Path, default=application_dir() / "runtime.tar.gz")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--profile", default="jump3")
    parser.add_argument("--port-id", help="検証用の別配置ID。通常は省略")
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args(argv)
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
        else:
            if args.source is None:
                parser.error("installには --source が必要です。")
            profile = next((p for p in profiles() if p["id"] == args.profile), None)
            if profile is None:
                parser.error("未対応のゲームです。")
            config = install(connection, args.source, args.runtime, profile, args.font, args.port_id)
            if args.launch:
                launch(connection, config)
    finally:
        connection.close()
    return 0
