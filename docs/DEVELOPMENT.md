# 開発構成

```text
src/ds2port/      GUI・SSH・転送・プロファイル互換修正
profiles/        対応ゲーム、原本/修正後のSHA-256、保持するセーブフォルダー
runtime/native/ AArch64の画面・入力・MIDI・音量処理
runtime/templates/ ゲームごとに配置先を埋める設定
runtime/install_remote.py  本体上の検証・バックアップ・配置・ロールバック
scripts/        依存取得、ビルド、配布候補の作成
tests/          アーカイブ安全性・互換修正・原本保持とWin32検証ソース
bld/            キャッシュ・生成バイナリ・検証ログ（Git対象外）
```

## タイトルの追加

通常はプロファイル追加なしでゲームフォルダーとEXEを指定します。`detect_game` が32bit PEを検証し、既知の原本は固有プロファイル、それ以外は共通ランタイムの設定を生成します。EXEが複数ある場合は明示選択が必要です。

共通マウス修正はPEのSetWindowsHookExAインポートを解決し、`hMod=NULL / callback / WH_MOUSE / call` の命令列と実行セクション内のcallbackを照合します。実行セクション末尾のゼロ埋め領域に、元のthread-IDスタックスロットを現在のスレッドIDへ置き換えるコードを追加します。空きが不足する場合は転送を止めます。JUMP3の固定アドレスを別ゲームへ流用しません。

固有の修正が必要な場合だけプロファイルを追加し、対象版の原本ハッシュ、実行ファイル名、保持するセーブを指定します。修正後ハッシュも照合します。

画面・文字・音・操作・保存を実機で確認してから対応表へ追加します。Win95ゲームがすべて同じランタイム設定で動くという前提は置いていません。

## CLI

パスワードは `DS2PORT_SSH_PASSWORD` 環境変数、または秘密鍵で渡します。引数やログへ平文で記録しません。

```powershell
DS2PortCLI.exe inspect --host 192.0.2.10 --user root --key C:\Keys\device_key
DS2PortCLI.exe install --host 192.0.2.10 --source D:\JUMP3 --runtime runtime.tar.gz --key C:\Keys\device_key
DS2PortCLI.exe install --host 192.0.2.10 --source D:\FLOAT --executable FLOAT.EXE --runtime runtime.tar.gz --key C:\Keys\device_key
```

初回接続は表示されたフィンガープリントを確認し、`--accept-new-host-key` を付けて鍵を登録します。登録済み鍵の不一致は自動承認しません。

`--port-id jump3-tool-test` で既存のjump3とは別の場所へ検証用配置を作れます。起動には同じdisplay 93と本体入力を使用するため、同時実行はできません。テスト完了後はその配置だけを明示的に削除します。

## 実装上の注意

- SFTP非搭載の本体に対応するため、転送はSSHのファイルストリームを使用します。
- FAT領域にWineを展開せず、リンクを保持できるext4で展開・検証します。
- 保存領域が読み取り専用の場合は配置を開始しません。
- 更新時、Wine・native・licensesは既存ツリーとファイル内容・モード・リンク先・構成が一致すれば再利用します。変更があるツリーだけをバックアップして置換します。
- ダウンロード・転送後にハッシュを検証し、未知のEXEには修正を適用しません。
- インストール中は別プロセスからの同時転送をロックします。
- Win32検証プログラムは処理を完了してもUnixに137を返すことがあるため、マーカー出力も照合します。
- 入力は通常の押下・解放です。Win95のDLLなしグローバルWH_MOUSE登録は、Wineで失敗するためゲームスレッドへ限定します。
- fbbridgeはevdevを排他取得しません。PlumOSの電源メニューはfb0を開くプロセスをSIGSTOPするため、排他取得すると停止中もコントローラーを保持し、メニュー操作を妨げます。power-menu-overlay.lockとSIGCONTを監視し、メニュー中の入力・描画を抑止し、復帰時に溜まったイベントとマウス・キー・移動状態をリセットします。
- 初回はwinebootでprefixを作成した後、wineserverを停止してから専用prefixの日本語設定を更新します。Box64上のregeditの終了コードやレジストリ保存時刻へ依存しません。無関係な設定を保持し、変更前のレジストリもprefix内へ保存します。PCのWindowsレジストリは変更しません。
- `LC_ALL=ja_JP.UTF-8` を本ゲームの起動環境へ設定します。Wine 10の[ロケール初期化](https://github.com/wine-mirror/wine/blob/wine-10.0/dlls/ntdll/unix/env.c)はCロケール時にLC_ALLを参照します。本体に日本語glibcロケールがない構成でも、Win32検査でGetACP=932、システム・ユーザーLCID=1041を確認しています。
