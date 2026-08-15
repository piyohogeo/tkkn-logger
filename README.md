# Tokkun '99 Auto Logger

『特訓'99 -君よ、男避けに避けろ-』のゲーム画面を観測し、プレイ結果・ハイスコア動画・終了時メッセージを自動記録するWindows用ロガーです。ゲームへキー入力やEnterを送るコードはありません。

実行用ポータブル版は[GitHub Releases](https://github.com/piyohogeo/tkkn-logger/releases)から取得します。`Tokkun99Logger-v0.1.0-windows-x64.zip`がWindows用実行ファイルです。GitHubが自動生成する`Source code (zip)`には実行環境やFFmpegが含まれません。

## 対象ゲーム

オリジナル版は、作者びい氏の[『特訓'99』配布ページ](https://bee.in.coocan.jp/tk)から入手できます。サイトのトップページは[「やればできる。」](https://bee.in.coocan.jp/)です。

このロガーの動作確認に使用したファイルのSHA-256は次のとおりです。

| ファイル | SHA-256 |
| --- | --- |
| `TKKN.LZH` | `A8AF1AC23238A7918764D2765CE78B8942FB5DB09A275EFF351102856D36537C` |
| `TKKN.EXE` | `A5345D731E3071A9A7C508AABEF7D600B9D358B853CB2EECA0A2305C262CD7DF` |

『特訓'99』を制作・公開され、今も遊べる形で残してくださっている作者のびい氏に、心より感謝いたします。

## GUI起動

ゲームを起動してタイトル画面を表示し、次を実行します。

```powershell
.\scripts\run_gui.cmd
```

GUIでは監視開始・安全停止・データフォルダ表示ができ、ゲーム状態、録画状態、2系統の記録、メッセージ進捗を確認できます。保持モードとキャプチャ方式は監視開始前に選択します。WGCが既定で、MSSは代替方式です。GUIを閉じる操作も停止要求として処理され、録画中のrunを無言で破棄しません。

「自動監視（ゲーム起動・終了に連動）」は既定でONです。停止中は1秒間隔で『特訓'99』のウィンドウを探し、対象が現れた時点で監視を開始します。ゲームを終了するなど対象を取得できなくなった場合は、録画とrunを安全に確定して監視を停止し、再び待機します。手動で開始したい場合は、待機中にチェックを外してください。

GUIはゲームの起動やキー入力を行いません。スコア訂正、メッセージレビュー、キャリブレーションは引き続きCLIを使用します。

Pythonから直接起動する場合:

```powershell
.\.venv\Scripts\python.exe scripts\run_gui.py
```

## ポータブルWindows版のローカルビルド

Windows x64向けの一般配布形式は、PyInstaller `onedir`版だけです。`onefile`版、ポータブルPython＋BAT版、インストーラーは作りません。ビルド成果物はGit管理せず、`dist/Tokkun99Logger`へ生成します。

専用`.venv`へビルド依存を導入します。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

既定では`packaging/ffmpeg-manifest.json`に固定したBtbN Windows x64 LGPL版FFmpegを`build/ffmpeg-lgpl`へ取得・検証し、テスト後に`onedir`を作ります。浮動するlatest URL、システムFFmpeg、Conda環境のFFmpegは使用しません。PowerShellの実行ポリシーを永続変更する必要はありません。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_portable.ps1
```

同じ固定ビルドを既に展開している場合は、そのルートに`bin/ffmpeg.exe`、`bin/ffprobe.exe`、`LICENSE.txt`が必要です。ZIPを省略しても、実行ファイルのSHA-256、x64、configure、標準`mpeg4`エンコーダ、LGPL本文を検証します。別バージョンや別ビルドへ暗黙には切り替えません。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_portable.ps1 `
  -FfmpegRoot "D:\Tools\ffmpeg"
```

生成物は次の構成です。

```text
dist/Tokkun99Logger/
  Tokkun99Logger.exe
  README.txt
  VERSION.txt
  LICENSES/
  _internal/
    ffmpeg.exe
    template/
    Python・OpenCV・Tcl/Tk等
```

空の`data`は同梱しません。初回起動時にEXEと同じフォルダへ作成し、固定テンプレートやFFmpegが入る`_internal`とは分離します。PythonとCondaをPATHから除外した起動・安全停止スモークは次で再実行できます。検証用に作成した`data`だけを安全停止後に削除します。既存`data`がある場合は保護のため実行を拒否します。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_portable.ps1
```

同梱FFmpegのLGPL v3本文、完全なconfigure情報、固定ソース参照、バイナリハッシュと、Python依存のライセンスは`LICENSES`に収集します。同梱するFFmpegはアプリへリンクせず、別プロセスとして起動します。対応する[FFmpegソース](https://github.com/FFmpeg/FFmpeg/tree/9b6c8969e05b4f0b29f0f85cd501be6b3e582e6b)と[BtbNビルド定義](https://github.com/BtbN/FFmpeg-Builds/tree/a99e8230eae00d1cee38f23076a7a1f55cd984e2)を固定しています。現在のローカルビルドは未署名であり、Windows SmartScreenの警告が表示される可能性があります。この段階のローカル成果物は正式配布物ではありません。

## CLI起動

1. ゲームを起動し、タイトル画面を表示する。
2. ゲーム画面を最小化せず、他のウィンドウで覆わない。
3. PowerShellでリポジトリの `scripts` フォルダへ移動する。
4. 次を実行する。

```powershell
.\run_logger.cmd
```

停止は `Ctrl+C`。通常の `records_only` モードでは、生存時間または弾数の新記録動画だけを保持します。非記録runもスコア、メッセージ、DB行は保持しますが、RESULT画像は既定では保存しません。認識に失敗したrunと途中終了runの動画は、再確認できるよう隔離保存します。

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

キャプチャは既定でWindows Graphics Capture（WGC）、代替としてMSSを選択できます。新規録画はLGPL版FFmpegの標準`mpeg4`エンコーダ（MPEG-4 Part 2）を`-q:v 1`で使用し、MP4へ保存します。この最高品質設定も数学的な可逆圧縮ではなく、H.264よりファイルサイズが増える場合があります。既存のH.264 MP4は変換・削除せず、そのまま利用できます。選択したキャプチャ方式や録画コーデックが失敗しても別方式へ暗黙に切り替えません。

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

人間が閲覧する収集データ:

- `data/collection/messages`: 新規MESSAGEのフル画面PNG。ファイル名は生存時間・日付・時刻順
- `data/collection/videos`: 保持対象の完走動画。ファイル名は生存時間・日付・時刻順
- `data/collection/videos/incomplete`: 途中終了・異常終了動画
- `data/collection/videos/incomplete/recovered`: 起動時に発見した放棄partial
- `data/collection/runs`: デバッグ用RESULT画像。`--save-run-images` 指定時のみ保存

プログラムが使用するログ:

- `data/log/logger.sqlite3`: run、スコア、記録履歴、メッセージ、訂正イベント
- `data/log/messages`: MESSAGE照合用の正規化画像
- `data/log/regression`: 数字認識の回帰評価ログ
- `data/log/logger.lock`: 二重起動防止ロック

配布固定データ:

- `data/template`: 状態・数字テンプレート
- `artifacts/calibration`: キャリブレーション結果

ロガーは二重起動を拒否します。録画中は `.mp4.incomplete` へ書き込み、FFmpegが正常終了した後にだけ `.mp4` へアトミックに改名します。突然終了後に残った未ファイナライズファイルは、次回起動時に拡張子を変えず `recovered` へ移動します。旧バージョンの `.partial.mp4` も同様に回収します。

完走ファイル名の例は `000000040624ms_2026-08-13_15-40-35+0900_<run-id>.mp4`。先頭12桁は生存ミリ秒なので、エクスプローラーの名前順で生存時間順に並びます。日時はプレイ開始時刻とUTCオフセットです。デバッグ保存するRESULT画像は同じ名前の末尾に `_result.png` が付きます。生存時間未確定の途中終了動画は `unknown_日時_<run-id>.mp4` になります。

通常起動ではRESULT画像を保存しません。デバッグ用に1runにつき1枚保存する場合は `--save-run-images` を付けます。

RESULTを表示したままにすると、既定では10秒後に録画だけを一時停止します。状態検出とスコア認識は継続し、MESSAGEへ進むと録画を再開してMESSAGE画面を含めた後に確定終了します。時間は `--result-record-seconds 15` のように変更できます。

録画末尾のMESSAGEは、確定したフレームを複製して既定で約2秒間表示します。実時間の待機は行いません。長さは `--message-hold-seconds 3` のように変更できます。

数字認識の回帰評価用にRESULTフレームを収集する実験オプションがあります。`--log-result-frames` を付けると、RESULT状態アンカーと一致し、かつ画素が異なるフレームだけを可逆圧縮PNGとして `data/log/regression/results/YYYY/MM/DD/<run-id>` に保存します。静止画は重複保存しないため通常は1枚です。容量を制限するため1runあたり既定で最大300枚とし、上限は `--result-frame-log-limit 100` のように変更できます。通常起動では無効です。

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
- 同梱FFmpegのrav1eは、公開元Actionsログの失効と未固定の`cargo-c`により実ビルドのCargo依存関係を完全には証明できない。再構成した依存関係とバイナリで確認できたRust標準ライブラリの通知を収録し、v0.1.0では既知の監査上の制約として扱う

## ライセンス

ロガー本体のソースコードは[MIT License](LICENSE)です。Copyright (c) 2026 piyohogeo.

同梱FFmpeg、Python依存パッケージ等にはそれぞれのライセンスが適用されます。`data/template/`に含まれるゲーム画面由来の小さな認識テンプレートを含め、第三者資産をMIT Licenseで再許諾するものではありません。詳細は[第三者資産の注記](THIRD_PARTY_ASSETS.md)とポータブル版の`LICENSES/`を参照してください。『特訓'99』本体はリポジトリにもReleaseにも含まれません。

ポータブル版のEXEと同梱FFmpegは未署名です。Windows SmartScreenやMicrosoft Defenderの警告が表示される可能性があります。

## キャプチャ方式

通常の `run_logger.cmd` とGUIはWGCバックエンドを使用します。WGCを明示した互換コマンドも利用できます。

```powershell
cd scripts
.\run_logger_wgc.cmd
```

WGCは対象ウィンドウの最新フレームをイベントで受け取り、ロガーの30 FPS出力時計に合わせて使用します。ウィンドウ内容が更新されない間は同じフレームを再利用するため、動画のフレームレートは30 FPSのままです。MSSを使う場合はGUIで選択するか、CLIへ `--capture-backend mss` を指定します。どちらかが利用できない場合も暗黙には切り替えません。

MSSとWGCの負荷を同条件で比較するには、ゲームを静止したタイトル画面にして次を実行します。約75秒かかり、ゲーム入力や動画保存は行いません。

```powershell
cd scripts
.\run_capture_ab.cmd
```

結果は `artifacts/performance/capture_ab` にJSONで保存されます。DWM CPU、測定プロセスCPU、実効出力FPSを比較できます。
