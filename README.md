# DS2Port V90S

所有するCompile DiscStation収録の32bit Windowsゲームを **PlumOS V90S V2** へ転送するWindows用ツールです。ゲームフォルダー内のEXEを選択して、共通のBox64・Wine・表示・入力・MIDI環境で起動します。

ゲームのファイルとWindowsのMSゴシックは、利用者のPCから本体へ転送します。リポジトリ・配布パッケージには含みません。タイトルの登録は転送の条件ではありません。JUMP3の文字表示など、確認済みのタイトル固有設定は原本のハッシュから自動認識します。ゲームごとの動作確認状況は [検証記録](docs/VALIDATION.md) を参照してください。

## 使い方

1. PlumOS V90S V2でWi-FiとSSHを起動します。
2. 配布フォルダーの `DS2PortV90S.exe` を起動します。`runtime.tar.gz` とその `.sha256` は同じ場所に置きます。
3. 所有するゲームのフォルダーと起動EXE、接続先IP、SSHユーザー・パスワードまたは秘密鍵を指定します。EXEが1つなら自動選択します。今回の本体ではrootでの接続を使用しています。
4. 「接続を確認」で保存領域を確認し、「ゲームを転送」を押します。初回は接続先SSH鍵のフィンガープリントを確認して登録します。
5. 本体のPortsからゲーム名の項目を起動します（例：**FLOAT**、**JUMPHERO Gaiden 3**）。初回のWine環境作成には数分かかる場合があります。

本体で起動中のゲームは、転送前に終了してください。PC側のゲーム原本は変更しません。既知のEXEにはハッシュ照合した固有修正を、それ以外にはPEのインポートと命令列が一致する場合だけ共通マウスフック修正を適用します。該当しないEXEは無変更で転送します。共通環境での全タイトルの動作を保証するものではありません。

MSゴシックは、実行PCの `%WINDIR%\Fonts\msgothic.ttc` を読み取ります。パスワード・秘密鍵・ゲーム原本を本ツールの設定ファイルへ保存しません。初回に確認したSSHホスト鍵は `%LOCALAPPDATA%\ds2port-v90s\known_hosts` に保存します。

## 共通環境と操作

- Box64 + Wine 10.0 WoW64、Xvfbによる640×480のDirectDraw表示。
- X11共有メモリーとコピー処理の最適化により、画面転送は60Hzを目標に動作。ゲーム内部の更新頻度とは別です。[性能測定](docs/PERFORMANCE.md)
- 対応するフレームバッファでは裏画面へ描画し、垂直帰線時のページ切替で表示。V90S実機では約59fpsで動作します。
- 実行PCのMSゴシックと日本語コードページ932。
- 同じ命令形式のWin95マウスフックをゲーム自身のスレッド対象へ変更。EXEごとの固定アドレスには依存しません。
- OPL3 FM MIDI音源（SB16のYMF262に相当する部分）。曲終了・リセットの消音処理。
- 本体の音量をBGM・効果音の両方へ反映。
- 本体出力を48kHzへ統一し、44.1kHzなどの音はALSAで変換。V90Sの44.1kHz経路で起きた音程の上ずりを回避。

| 操作 | ボタン |
| --- | --- |
| カーソル移動 | 十字キー |
| 左クリック / 右クリック | B / A |
| カーソル2倍速 | YまたはR2を押している間 |
| Enter / Escape | START / SELECT |
| 終了してPortsへ戻る | START + SELECT |

L1/R1は割り当てなし。ゲームのカーソルだけを表示します。クリックの押下・解放はユーザーの操作どおりに送信します。

本体の電源メニューも利用できます。メニュー表示中はゲームへの入力・画面転送を止め、復帰時には溜まった入力とボタン状態をリセットします。

JUMP3では追加で会話4行の文字幅・字間を補正します。この修正は一致するJUMP3原本だけに適用します。

## 配置と更新

| 配置先 | 内容 |
| --- | --- |
| `/mnt/plumos/roms/ports/jump3` | ゲーム、設定、Box64、音源、ログ |
| `/mnt/plumos/ports-runtime/jump3` | Wine、prefix、Xvfb、補助プログラム、更新バックアップ |
| `/mnt/plumos/roms/ports/JUMPHERO Gaiden 3.sh` | Ports起動項目 |

上表はJUMP3の例です。汎用転送ではEXE名から配置IDとPorts項目名を作り、各ゲームのWine prefixも分けます。

Wineのシンボリックリンクを保持するため、実行環境にはext4領域も必要です。JUMP3更新時は本体の `game/SaveData` を上書きしません。汎用転送では保存形式を決めつけず、起動EXE以外の既存ファイル・フォルダーを保持します（FLOATの `SAVE_D*.DAT` などを含みます）。既存データを差し替える場合は別の配置IDへ転送してください。変更する既存ファイルは実行環境側の `backups/` へ保存します。処理中のエラーでは配置変更を戻します。電源断に対する完全なトランザクションは保証しません。

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
