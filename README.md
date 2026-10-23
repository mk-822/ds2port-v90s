# DS2Port V90S

所有するCompile DiscStation収録ゲームを **PlumOS V90S V2** へ転送するWindows用ツールです。現在の対応ゲームは **JUMPHERO 外伝3 ～トビッきりアドベンチャー～** です。

ゲームのファイルとWindowsのMSゴシックは、利用者のPCから本体へ転送します。リポジトリ・配布パッケージには含みません。他のDiscStationタイトルは、ゲーム別プロファイルと実機確認を追加して対応していく構成です。

## 使い方

1. PlumOS V90S V2でWi-FiとSSHを起動します。
2. 配布フォルダーの `DS2PortV90S.exe` を起動します。`runtime.tar.gz` とその `.sha256` は同じ場所に置きます。
3. 所有するゲームのフォルダー、接続先IP、SSHユーザー・パスワードまたは秘密鍵を指定します。今回の本体ではrootでの接続を使用しています。
4. 「接続を確認」で保存領域を確認し、「ゲームを転送」を押します。初回は接続先SSH鍵のフィンガープリントを確認して登録します。
5. 本体のPortsから **JUMPHERO Gaiden 3** を起動します。初回のWine環境作成には数分かかる場合があります。

本体で起動中のゲームは、転送前に終了してください。PC側のゲーム原本は変更しません。対応する原本EXEのハッシュが一致した場合だけ、転送用コピーへ互換修正を適用します。

MSゴシックは、実行PCの `%WINDIR%\Fonts\msgothic.ttc` を読み取ります。パスワード・秘密鍵・ゲーム原本を本ツールの設定ファイルへ保存しません。初回に確認したSSHホスト鍵は `%LOCALAPPDATA%\ds2port-v90s\known_hosts` に保存します。

## JUMP3の動作と操作

- Box64 + Wine 10.0 WoW64、Xvfbによる640×480のDirectDraw表示。
- MSゴシックによる縦長の会話文字、4行表示。Wineの最大文字幅による字間のずれを補正。
- Win95方式のマウスフックをゲーム自身のスレッド対象へ変更。
- OPL3 FM MIDI音源（SB16のYMF262に相当する部分）。曲終了・リセットの消音処理。
- 本体の音量をBGM・効果音の両方へ反映。

| 操作 | ボタン |
| --- | --- |
| カーソル移動 | 十字キー |
| 左クリック / 右クリック | A / B |
| カーソル2倍速 | R2を押している間 |
| Enter / Escape | START / SELECT |
| 終了してPortsへ戻る | START + SELECT |

L1/R1は割り当てなし。ゲームのカーソルだけを表示します。クリックの押下・解放はユーザーの操作どおりに送信します。

## 配置と更新

| 配置先 | 内容 |
| --- | --- |
| `/mnt/plumos/roms/ports/jump3` | ゲーム、設定、Box64、音源、ログ |
| `/mnt/plumos/ports-runtime/jump3` | Wine、prefix、Xvfb、補助プログラム、更新バックアップ |
| `/mnt/plumos/roms/ports/JUMPHERO Gaiden 3.sh` | Ports起動項目 |

Wineのシンボリックリンクを保持するため、実行環境にはext4領域も必要です。更新時は本体の `game/SaveData` を上書きせず、変更する既存ファイルを実行環境側の `backups/` へ保存します。処理中のエラーでは配置変更を戻します。電源断に対する完全なトランザクションは保証しません。

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
| `bld/dist/ds2port-v90s-0.1.0-windows-x64.zip` | ローカルの配布候補 |

依存アーカイブは `runtime/dependencies.json` のSHA-256で照合します。ゲーム・フォント・資格情報・ビルド環境・生成バイナリをGitへ追加しないでください。

## テスト

```powershell
$env:PYTHONPATH = 'src'
bld/venv/Scripts/python.exe -m unittest discover -s tests -v
# 所有するゲームでパッチと原本保持も検査する場合
$env:DS2PORT_TEST_GAME = 'D:\DiscStation\JUMP3'
bld/venv/Scripts/python.exe -m unittest discover -s tests -v
```

ゲームのファイルはテスト用fixtureとしてコミットしません。検証の詳細は [docs/VALIDATION.md](docs/VALIDATION.md)、構成と対応追加は [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) を参照してください。

本プロジェクトはGPL-3.0-or-laterです。依存物のライセンス・ソース参照先は [THIRD_PARTY.md](THIRD_PARTY.md) にまとめています。
