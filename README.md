# DS2Port V90S

所有するCompile DiscStation収録の32bit Windowsゲームを **PlumOS V90S V2** へ転送するWindows用ツールです。ゲームフォルダー内のEXEを選択して、共通のBox64・Wine・表示・入力・MIDI環境で起動します。

ゲームのファイルとWindowsのMSゴシックは、利用者のPCから本体へ転送します。リポジトリ・配布パッケージには含みません。タイトルの登録は転送の条件ではありません。確認済み原本はハッシュで認識し、対応する旧エンジンには共通の互換修正を適用します。ゲームごとの動作確認状況は [検証記録](docs/VALIDATION.md) を参照してください。

[v0.1.2 プレリリースをダウンロード](https://github.com/mk-822/ds2port-v90s/releases/tag/v0.1.2)。Windows用ZIPを展開し、転送ツールを起動してください。

| Windowsの転送ツール | V90Sでの動作例（FLOAT） |
| --- | --- |
| ![ゲームと起動モード、SSH接続先を指定する転送ツール](docs/images/transfer-tool.jpg) | ![PlumOS V90Sでフロートランドのおとぎばなしが起動した実機写真](docs/images/float-on-v90s.png) |

実機写真は利用者提供です。ゲーム画面の権利は各権利者に帰属します。ゲームデータの配布は行いません。

## 使い方

1. PlumOS V90S V2でWi-FiとSSHを起動します。
2. 配布フォルダーの `DS2PortV90S.exe` を起動します。`runtime.tar.gz` とその `.sha256` は同じ場所に置きます。
3. 所有するゲームのフォルダーと起動EXE、起動時モード（マウス／Joypad）、接続先IP、SSHユーザー・パスワードまたは秘密鍵を指定します。EXEが1つなら自動選択します。今回の本体ではrootでの接続を使用しています。
4. 「接続を確認」で保存領域を確認し、「ゲームを転送」を押します。初回は接続先SSH鍵のフィンガープリントを確認して登録します。
5. 本体のPortsからゲーム名の項目を起動します（例：**FLOAT**、**JUMPHERO Gaiden 3**）。初回のWine環境作成には数分かかる場合があります。

本体で起動中のゲームは、転送前に終了してください。PC側のゲーム原本は変更しません。既知のEXEにはハッシュ照合した固有修正を、それ以外にはPEのインポートと命令列が一致する場合だけ共通マウスフック・フォント互換修正を適用します。該当しないEXEは無変更で転送します。共通環境での全タイトルの動作を保証するものではありません。

MSゴシックは、実行PCの `%WINDIR%\Fonts\msgothic.ttc` を読み取ります。パスワード・秘密鍵・ゲーム原本を本ツールの設定ファイルへ保存しません。初回に確認したSSHホスト鍵は `%LOCALAPPDATA%\ds2port-v90s\known_hosts` に保存します。

## 共通環境と操作

- Box64 + Wine 10.0 WoW64、Xvfbによる640×480のDirectDraw表示。
- X11共有メモリーとコピー処理の最適化により、画面転送は60Hzを目標に動作。ゲーム内部の更新頻度とは別です。[性能測定](docs/PERFORMANCE.md)
- 対応するフレームバッファでは裏画面へ描画し、垂直帰線時のページ切替で表示。V90S実機では約59fpsで動作します。
- 実行PCのMSゴシックと日本語コードページ932。
- 同じ命令形式のWin95マウスフックをゲーム自身のスレッド対象へ変更。EXEごとの固定アドレスには依存しません。
- 対応する旧エンジンのフォント要求と実際の平均文字幅を照合し、全角文字の実測幅で文字送りを補正。タイトル別の固定縮小率を使わず、ANGLERの文字送り・狭幅表示にも対応。
- OPL3 FM MIDI音源（SB16のYMF262に相当する部分）。曲終了・リセットの消音処理。
- 本体の音量をBGM・効果音の両方へ反映。PCMは従来の70%、FMのBGMは従来音量を維持。
- 本体出力を48kHzへ統一し、44.1kHzなどの音はALSAで変換。V90Sの44.1kHz経路で起きた音程の上ずりを回避。

L2でマウスモードとJoypadモードを切り替えます。切替直後は左上へモードを2秒間表示し、その後1フレームに1ピクセルずつ上へ移動して消えます。切替時には押下状態を解放します。

マウスモード：

| 操作 | ボタン |
| --- | --- |
| カーソル移動 | 十字キー |
| 左クリック / 右クリック | B / A |
| カーソル2倍速 | YまたはR2を押している間 |
| Enter / Escape | START / SELECT |
| 終了してPortsへ戻る | START + SELECT |

JoypadモードではWindowsへ4ボタン・2軸の仮想Joypadを渡します。

| Joypad入力 | 本体ボタン |
| --- | --- |
| X軸・Y軸 | 十字キー |
| ボタン1 | Y（左） |
| ボタン2 | B（下） |
| ボタン3 | A（右） |
| ボタン4 | X（上） |

STARTのEnter、SELECTのEscape、START＋SELECTでの終了は両モード共通です。Joypadモードではマウス移動・クリックを送りません。

起動時の既定はマウスです。転送ツールでゲームごとに選択でき、CLIでは `--input-mode mouse` または `--input-mode joypad` を指定します。本体では `/mnt/plumos/ports-runtime/<ID>/port/input-mode` に保存します。L2による一時切替は次回起動時の設定を変更しません。JUMP3・FLOATはマウスで起動します。

L1/R1は割り当てなし。ゲームのカーソルだけを表示します。クリックの押下・解放はユーザーの操作どおりに送信します。

本体の電源メニューも利用できます。メニュー表示中はゲームへの入力・画面転送を止め、復帰時には溜まった入力とボタン状態をリセットします。

フォント互換修正は認識した初期化処理に限定します。JUMP3の固定アドレス補正とDF3の固定90%補正は共通処理へ統合しました。

## 配置と更新

| 配置先 | 内容 |
| --- | --- |
| `/mnt/plumos/roms/ports/jump3` | ゲーム、セーブ |
| `/mnt/plumos/ports-runtime/jump3` | ゲーム別設定・ログ・Wine環境・変更差分・更新バックアップ |
| `/mnt/plumos/ports-runtime/.shared/runtime-<SHA256>` | 共有ランタイム（Wine・native・Box64など） |
| `/mnt/plumos/roms/ports/JUMPHERO Gaiden 3.sh` | Ports起動項目 |

上表はJUMP3の例です。汎用転送ではEXE名から配置IDとPorts項目名を作り、各ゲームのWine prefixも分けます。

Wineのシンボリックリンクを保持するため、実行環境にはext4領域も必要です。JUMP3更新時は本体の `game/SaveData` を上書きしません。汎用転送では保存形式を決めつけず、起動EXE以外の既存ファイル・フォルダーを保持します（FLOATの `SAVE_D*.DAT` などを含みます）。既存データを差し替える場合は別の配置IDへ転送してください。変更する既存ファイルは実行環境側の `backups/` へ保存します。処理中のエラーでは配置変更を戻します。電源断に対する完全なトランザクションは保証しません。

ランタイムはSHA-256ごとの共有キャッシュから利用します。同じ版が本体にあれば、約170MiBのアーカイブの再転送と全量展開を省略します。旧配置からも、全ファイルを照合してキャッシュを作成できます。

Wine環境内のsystem32・syswow64はOverlayFSで共有DLLを読み取り、変更されたファイルだけゲーム別の `prefix-overlays` に保存します。レジストリ・セーブ・独自DLLは共有しません。既存4ゲームでは約1.67GiBを回復しました。初回Wine作成時の一時的な増加分は引き続き予約し、容量不足や読み取り専用の領域では転送を止めます。OverlayFS非対応の本体ではDLL共有を行いません。

設定・ログ・Box64などの補助ファイルもext4側へ配置します。FAT側は主にゲームとセーブ、Portsの起動項目です。既存ゲームは新版ツールで同じ配置IDへ再転送すると更新できます。

Wine環境をバックアップする場合は、`prefix`だけでなく、そのゲームの実行環境ディレクトリ全体（`prefix-overlays`・`prefix-storage.json`を含む）と参照中の共有キャッシュも対象にしてください。DLLの表示用ディレクトリは停止中には空ですが、通常のPorts起動でマウントされます。

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
| `bld/dist/ds2port-v90s-0.1.2-windows-x64.zip` | ローカルの配布候補 |

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
