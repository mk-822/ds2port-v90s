# 配置・更新と開発者向け手順

普段の転送と操作は [README](../README.md) を参照してください。

## ファイルの配置

| 配置先 | 内容 |
| --- | --- |
| `/mnt/plumos/roms/ports/jump3` | ゲーム、セーブ |
| `/mnt/plumos/ports-runtime/jump3` | ゲーム別設定・ログ・更新バックアップ |
| `/mnt/plumos/ports-runtime/.shared/wine10` | 共通Wine環境・設定・変更差分・移行バックアップ |
| `/mnt/plumos/ports-runtime/.shared/runtime-<SHA256>` | 共有ランタイム（Wine・native・Box64など） |
| `/mnt/plumos/roms/ports/JUMPHERO Gaiden 3.sh` | Ports起動項目 |

上表はJUMP3の例です。汎用転送ではEXE名から配置IDとPorts項目名を作り、Wine環境は全ゲームで共用します。

Wineのシンボリックリンクを保持するため、実行環境にはext4領域も必要です。JUMP3更新時は本体の `game/SaveData` を上書きしません。汎用転送では保存形式を決めつけず、起動EXE以外の既存ファイル・フォルダーを保持します（FLOATの `SAVE_D*.DAT` などを含みます）。既存データを差し替える場合は別の配置IDへ転送してください。変更する既存ファイルは実行環境側の `backups/` へ保存します。処理中のエラーでは配置変更を戻します。電源断に対する完全なトランザクションは保証しません。

ランタイムはSHA-256ごとの共有キャッシュから利用します。同じ版が本体にあれば、約170MiBのアーカイブの再転送と全量展開を省略します。旧配置からも、全ファイルを照合してキャッシュを作成できます。

Wine環境とレジストリは `.shared/wine10` に1つだけ作り、全ゲームで使います。system32・syswow64はOverlayFSで共有DLLを読み取り、変更分だけ共通の `prefix-overlays` に保存します。ゲーム本体と通常のセーブはゲーム別フォルダーに残します。旧版の個別Wine環境は初回利用時に設定・データを取り込み、競合するデータも `migration-backups` に退避します。旧環境は自動削除しません。初回Wine作成時の一時的な増加分は引き続き予約し、容量不足や読み取り専用の領域では転送を止めます。OverlayFS非対応の本体ではDLL共有を行いません。

設定・ログ・Box64などの補助ファイルもext4側へ配置します。FAT側は主にゲームとセーブ、Portsの起動項目です。既存ゲームは新版ツールで同じ配置IDへ再転送すると更新できます。

Wine環境をバックアップする場合は、ゲーム・セーブのフォルダーに加え、`.shared/wine10` 全体（`prefix-overlays`・`prefix-storage.json`を含む）、ゲーム別設定、参照中の共有キャッシュも対象にしてください。DLLの表示用ディレクトリは停止中には空ですが、通常のPorts起動でマウントされます。

## ソースからビルド

Windows x64、Python 3.11以上、Docker DesktopのLinuxコンテナー環境が必要です。ARM64コンテナーのエミュレーションを使用します。

```powershell
git clone https://github.com/mk-822/ds2port-v90s.git
cd ds2port-v90s
powershell -ExecutionPolicy Bypass -File scripts/build-runtime.ps1
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```

成果物はGit対象外の `bld/` に生成します。

| パス | 内容 |
| --- | --- |
| `bld/dist/DS2PortV90S/DS2PortV90S.exe` | Windows GUI |
| `bld/dist/DS2PortV90S/DS2PortCLI.exe` | コンソール版 |
| `bld/runtime.tar.gz` | 実機ランタイム |
| `bld/dist/ds2port-v90s-0.1.4-windows-x64.zip` | ローカルの配布候補 |

依存アーカイブは `runtime/dependencies.json` のSHA-256で照合します。ゲーム・フォント・資格情報・ビルド環境・生成バイナリをGitへ追加しないでください。

## テスト

```powershell
$env:PYTHONPATH = 'src'
bld/venv/Scripts/python.exe -m unittest discover -s tests -v
# 所有するゲームでパッチと原本保持も検査する場合
$env:DS2PORT_TEST_GAME = 'D:\DiscStation\JUMP3'
bld/venv/Scripts/python.exe -m unittest discover -s tests -v
```

ゲームのファイルはテスト用fixtureとしてコミットしません。検証の詳細は [検証記録](VALIDATION.md)、構成と対応追加は [開発構成](DEVELOPMENT.md) を参照してください。

本プロジェクトはGPL-3.0-or-laterです。依存物のライセンス・ソース参照先は [依存物のライセンス](../THIRD_PARTY.md) にまとめています。
