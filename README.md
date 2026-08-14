# Tokkun '99 Auto Logger

『特訓'99 -君よ、男避けに避けろ-』のゲーム画面を観測し、プレイ結果・ハイスコア動画・終了時メッセージを自動記録するWindows用ロガーです。ゲームへキー入力やEnterを送るコードはありません。

## 通常起動

1. ゲームを起動し、タイトル画面を表示する。
2. ゲーム画面を最小化せず、他のウィンドウで覆わない。
3. PowerShellでリポジトリの `scripts` フォルダへ移動する。
4. 次を実行する。

```powershell
.\run_logger.cmd
```

停止は `Ctrl+C`。通常の `records_only` モードでは、生存時間または弾数の新記録動画だけを保持します。非記録runもRESULT画像、スコア、メッセージ、DB行は保持します。認識に失敗したrunと途中終了runの動画は、再確認できるよう隔離保存します。

動作確認用の120秒収集は次のコマンドです。このモードは全動画を保持します。

```powershell
.\run_live_smoke.cmd
```

いずれのコマンドもゲーム入力は行いません。

## 表示条件

- Windows上で `tkkn.exe` のタイトル「特訓」を1つだけ起動する
- クライアント領域が `320×240` である
- ゲームを画面上に表示し、最小化・遮蔽しない
- RESULTとMESSAGEは、それぞれ約1秒表示する
- ウィンドウ移動には追従するが、サイズ変更には対応しない
- 複数の対象ウィンドウがある場合は自動選択せず停止する

キャプチャは `mss`、録画はFFmpeg H.264を使用します。既定のFFmpegは `C:\tools\ffmpeg\bin\ffmpeg.exe` です。

## 状態と保存方針

状態遷移は `TITLE → PLAYING → RESULT → MESSAGE → TITLE`。各状態は3フレーム連続確認後に確定します。RESULT状態が確定した後、信頼条件を満たすスコアを1フレーム読み取れれば値を確定します。状態側ですでに3フレーム確認しているため、静止しているRESULTに追加の複数フレーム合意は要求しません。低信頼値はハイスコアを更新しません。

動画モード:

- `records_only`: 新記録動画だけ保持する通常運用
- `collect_samples`: 新記録に加え、N完走ごとのサンプル動画を保持する
- `collect_all`: 全完走動画を保持するキャリブレーション／試験用

直接指定する例:

```powershell
cd "$env:USERPROFILE\src\tkkn-logger"
.\.venv\Scripts\python.exe scripts\run_live_logger.py --duration 0 --mode collect_samples --sample-every 10
```

空き容量が既定の2 GiBを下回ると、新しい録画を開始せず安全側で停止します。しきい値は `--min-free-gb` で変更できます。新記録動画を容量整理で自動削除することはありません。

## 統計とレビュー

リポジトリ直下から実行します。

```powershell
.\.venv\Scripts\python.exe scripts\tokkun99.py stats
.\.venv\Scripts\python.exe scripts\tokkun99.py review-scores
.\.venv\Scripts\python.exe scripts\tokkun99.py review-messages
```

人がRESULT画像を確認した後の訂正:

```powershell
.\.venv\Scripts\python.exe scripts\tokkun99.py correct-score RUN_ID 9408 51 --reason "RESULT画像を目視確認"
```

訂正前の記録履歴は削除せず無効履歴として残し、訂正イベントとレコード推移を再構築します。

メッセージのラベル付け:

```powershell
.\.venv\Scripts\python.exe scripts\tokkun99.py label-message 12 "メッセージ全文" --verified
```

終了時メッセージの期待総数は不明です。そのため、現時点では「完全制覇」と断定せず、`stats` と `review-messages` で観測数・確認数・生存時間範囲を追跡します。

## データ保存先

- `data/logger.sqlite3`: run、スコア、記録履歴、メッセージ、訂正イベント
- `data/videos/collection`: 保持対象の完走動画。ファイル名は生存時間・日付・時刻順
- `data/videos/incomplete`: 途中終了・異常終了動画
- `data/videos/incomplete/recovered`: 起動時に発見した放棄partial
- `data/runs/YYYY/MM/DD`: RESULT確認画像。ファイル名は生存時間・日付・時刻順
- `data/messages/clusters`: メッセージ代表画像
- `data/templates`: 状態・数字テンプレート
- `artifacts/calibration`: キャリブレーション結果

ロガーは二重起動を拒否します。突然終了後に残った `.partial.mp4` は、次回起動時に削除せず `recovered` へ移動します。

完走ファイル名の例は `000000040624ms_2026-08-13_15-40-35+0900_<run-id>.mp4`。先頭12桁は生存ミリ秒なので、エクスプローラーの名前順で生存時間順に並びます。日時はプレイ開始時刻とUTCオフセットです。RESULT画像は同じ名前の末尾に `_result.png` が付きます。生存時間未確定の途中終了動画は `unknown_日時_<run-id>.mp4` になります。

RESULTを表示したままにすると、既定では10秒後に録画だけを一時停止します。状態検出とスコア認識は継続し、MESSAGEへ進むと録画を再開してMESSAGE画面を含めた後に確定終了します。時間は `--result-record-seconds 15` のように変更できます。

録画末尾のMESSAGEは、確定したフレームを複製して既定で約2秒間表示します。実時間の待機は行いません。長さは `--message-hold-seconds 3` のように変更できます。

数字認識の回帰評価用にRESULTフレームを収集する実験オプションがあります。`--log-result-frames` を付けると、RESULT状態アンカーと一致し、かつ画素が異なるフレームだけを可逆圧縮PNGとして `data/regression/results/YYYY/MM/DD/<run-id>` に保存します。静止画は重複保存しないため通常は1枚です。容量を制限するため1runあたり既定で最大300枚とし、上限は `--result-frame-log-limit 100` のように変更できます。通常起動では無効です。

```powershell
cd scripts
.\run_logger_regression.cmd
```

収集したフレームを通常のRESULT画像と一緒に評価するには、次を実行します。

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_result_reader.py --include-frame-log
```

RESULTの数値欄は中央揃えの可変長として解析します。生存時間の整数部と弾数は1～4桁に対応し、生存時間の小数部は常に3桁として扱います。未対応の5桁以上や配置が一致しない画面は、誤った値を確定せずレビュー対象にします。

## バックアップ

ロガーを停止してから、`data` フォルダ全体を別ドライブ等へコピーしてください。SQLiteだけでなく動画・RESULT画像・メッセージ画像を一緒に保存することで参照関係を維持できます。

```powershell
Copy-Item -Recurse data "D:\backup\tkkn-logger-data-20260813"
```

復元時もロガーを停止し、`data` フォルダ全体をセットで戻します。

## 環境の再作成

既存のConda環境は変更せず、専用 `.venv` を使用します。Python 3.10で次を実行します。

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

依存バージョンは [requirements-lock.txt](requirements-lock.txt)、環境選定理由は [environment_decision.md](artifacts/env_audit/environment_decision.md) にあります。

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

実機から保存したRESULT画像はローカル専用ゴールデンデータとして回帰テストされます。ゲーム素材は公開リポジトリへ自動追加しません。

## 既知の制約

- 固定の `320×240` クライアント専用
- 前面表示に近い、遮蔽されない運用が必要
- ゲーム側の未知のRESULT配置・未知数字字形はレビュー対象になる
- MESSAGEの近似ハッシュは候補提示だけに使い、自動統合しない
- ディスク枯渇試験は安全なしきい値模擬で行い、実際にディスクを満杯にはしない

## 実験的Windows Graphics Capture

通常の `run_logger.cmd` は実績のあるMSSバックエンドを使用します。録画を30 FPSに維持したままWindows Graphics Captureを試す場合は、ゲームを起動して次を実行します。

```powershell
cd scripts
.\run_logger_wgc.cmd
```

WGCは対象ウィンドウの最新フレームをイベントで受け取り、ロガーの30 FPS出力時計に合わせて使用します。ウィンドウ内容が更新されない間は同じフレームを再利用するため、動画のフレームレートは30 FPSのままです。WGCが利用できない場合にMSSへ暗黙に切り替えることはありません。

MSSとWGCの負荷を同条件で比較するには、ゲームを静止したタイトル画面にして次を実行します。約75秒かかり、ゲーム入力や動画保存は行いません。

```powershell
cd scripts
.\run_capture_ab.cmd
```

結果は `artifacts/performance/capture_ab` にJSONで保存されます。DWM CPU、測定プロセスCPU、実効出力FPSを比較できます。
