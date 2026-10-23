# 表示性能の測定

PlumOS V90S V2実機で、FLOATを実行しながら640×480・32bitの画面取得とフレームバッファ転送を測定しました（2026-10-23）。各方式8秒、通常のfbbridgeを一時停止し、同じ画面経路へ測定プログラムだけが書き込む条件です。

| 方式 | 画面転送fps | 取得時間/フレーム | コピー時間/フレーム |
| --- | ---: | ---: | ---: |
| 従来：XGetImage、コピー後に33ms待機 | 16.78 | 8.387ms | 17.054ms |
| XGetImage、コピー最適化、60Hz周期 | 59.66 | 7.875ms | 1.803ms |
| XShmGetImage、コピー最適化、60Hz周期 | 59.61 | 1.787ms | 1.703ms |

従来はmemcpy後、フレームバッファ上の画素を読み戻してアルファ値を付けていました。この領域の読み戻しが遅いため、CPU側の画像へアルファ値を付けながら一度だけ書き込む方式へ変更しました。待機も毎回33msを足す方式から、処理時間を含めた周期制御へ変更しています。

X11 MIT-SHMが利用できる場合は共有メモリーを再利用し、毎回の画像受信・確保を減らします。拡張が無い場合や利用できない場合はXGetImageへ自動で戻ります。

組み込み後の実ゲームでは転送約60fps、取得約1.9ms、コピー約1.9msを確認しました。ユーザーからも滑らかさの改善、Bクリック、Y/R2加速、電源メニューからの復帰に問題がないことを確認済みです。カーソル移動量は経過時間から計算し、表示速度が上がっても移動速度が比例して増えないようにしています。

ここでいうfpsは画面の取得・転送回数です。ゲーム内部の更新頻度を60fpsに変更するものではありません。ログの `sampled_changes_s` は画像の一部をサンプリングした変化回数で、ゲーム内部のfpsを厳密に計測する値でもありません。

## PowerVR

本体のドライバーで次を確認しました。

- EGL 1.4、Imagination Technologies
- PowerVR Rogue GE8300、OpenGL ES 3.2
- オフスクリーン描画とピクセル読み戻し成功、GLエラーなし

今回はCPU側の転送改善で約60fpsへ到達したため、ゲームの表示経路にEGL/GPUは追加していません。GPUによる最終表示やDirectDrawの処理変更は今後の別検証です。Box64上のゲーム処理は引き続きCPUで実行します。

## 再検査

SDK内で以下をビルドできます。

```sh
gcc -O2 -Iruntime/native tests/frame-benchmark.c -o bld/frame-benchmark -lX11 -lXext
gcc -O2 -Iruntime/native tests/capture-smoke.c -o bld/capture-smoke -lX11 -lXext
gcc -O2 tests/egl-probe.c -o bld/egl-probe -lEGL -lGLESv2
```

`frame-benchmark ximage legacy`、`frame-benchmark ximage deadline`、`frame-benchmark shm deadline` を本体の実行環境変数の下で実行します。測定中は通常のfbbridgeを停止し、終了時に必ず再開してください。フレームバッファへ書き込むため、電源メニューと同時実行しないでください。

`capture-smoke shm` と `capture-smoke ximage` は各64フレームの取得・解放を確認します。別のXvfbを `-extension MIT-SHM` 付きで起動した環境では `capture-smoke fallback` も確認できます。これらの取得検査はフレームバッファへ書き込みません。実機で3方式すべて成功し、二重解放の検査も通しています。

診断用の環境変数は `DS2PORT_CAPTURE=ximage` で共有メモリーを無効化、`DS2PORT_FPS` で転送周期（標準60、範囲10～120）、`DS2PORT_CURSOR_SPEED` で通常カーソル速度（標準120px/秒）を変更できます。Y/R2加速時はこの速度の2倍です。
