# Tokkun '99 Logger GUI化・ポータブルEXE化・GitHub Release化 実装指示

## 1. この文書の目的

本書は、現在の『特訓'99』自動ロガーを次の3段階でWindows向けアプリケーションとして公開するための、Codex向け実装指示である。

1. **GUI化**: 既存ロガーを再利用可能なサービスへ整理し、Tkinter/ttkの簡素なGUIから開始・停止・状態確認できるようにする。
2. **ポータブルEXE化**: PyInstallerの`onedir`形式で、Python未導入環境でも動くWindows x64向けフォルダを作る。
3. **GitHub Release化**: ポータブルフォルダをZIPにし、バージョンタグとともにGitHub Releasesで配布する。安定後はGitHub Actionsで自動化する。

```text
既存のCLIロガー
  -> GUI付きPython版
  -> ポータブルWindows版
  -> GitHub Releasesで公開
```

第1段階のGUI化はコミット`868e380`で完了した。**次に実装するのは第2段階のPyInstaller `onedir`化である。** そのローカル成果物を検証した後、第3段階としてGitHub Actions上で同じビルドを再現し、GitHub Releaseへ公開する。

## 2. 調査時点のリポジトリ状態

2026-08-15の調査時点:

- リポジトリ: `https://github.com/piyohogeo/tkkn-logger.git`
- ブランチ: `agent/sortable-artifact-filenames`
- HEAD: `3817f27` (`Add automatic game monitoring`)
- ローカルブランチは`origin/agent/sortable-artifact-filenames`を追跡しており、調査時の作業ツリーはクリーンだった。
- テスト結果: ローカル実データを使うテストを除き **74 passed**。ローカルlive-smokeテストは、実装開始時に書き込み可能な通常環境で別途確認する。
- Python: `>=3.10,<3.11`
- 主要依存: NumPy 1.26.4、OpenCV 4.11.0.86、MSS 10.2.0、windows-capture 2.0.0、pywin32 312
- 既定キャプチャ: Windows Graphics Capture (WGC)
- 代替キャプチャ: MSS
- 録画: 外部FFmpegプロセス、既定パスは`C:\tools\ffmpeg\bin\ffmpeg.exe`
- データ: `DataLayout`により`data/collection`、`data/log`、`data/template`へ分離済み

Codexは実装開始時に、必ず改めて`git status`、現在のブランチ、HEAD、README、テスト結果を確認すること。本節のコミット番号を盲目的に前提にせず、ユーザーの未コミット変更がある場合は保存し、無関係な変更を上書きしない。

## 3. 現在できていること

既存機能をEXE化・配布自動化の過程で退行させないこと。

- ゲームへのキー入力、Enter送信、操作注入を一切行わない。
- `TITLE -> PLAYING -> RESULT -> MESSAGE -> TITLE`を3フレームのデバウンス付きで観測する。
- RESULTから生存時間と弾数をテンプレートベースで取得する。
- 生存時間と弾数の2系統の歴代記録を管理する。
- `records_only`、`collect_samples`、`collect_all`の保持モードがある。
- MESSAGEを収集し、クラスタ、代表画像、フル画面画像、観測回数を保存する。
- SQLiteにrun、記録履歴、訂正、メッセージを保存する。
- WGCを通常運用の既定とし、MSSも明示的に選べる。
- ウィンドウ移動へ追従する。
- 対象ウィンドウが0個または複数の場合は安全側で停止する。
- 320x240以外のクライアント領域を拒否する。
- 二重起動をロックで防ぐ。
- ディスク空き容量を確認する。
- 録画途中のファイルは`.mp4.incomplete`とし、正常確定時だけ`.mp4`へ変える。
- 異常終了動画や放棄partialを削除せず隔離・回収する。
- RESULT長時間表示時の録画一時停止、MESSAGE末尾のホールドがある。
- CLIで統計、スコアレビュー、スコア訂正、メッセージレビュー、ラベル付けができる。
- 実機由来の素材を公開リポジトリへ自動追加しない。

## 4. 変更してはいけない製品要件

- GUIを追加してもゲーム操作の自動化を実装しない。
- Enterキーを含む入力送信機能を追加しない。
- ゲーム本体を起動する機能を追加しない。
- ハイスコアは生存時間と弾数の2系統だけとする。
- 低信頼スコアでハイスコアを更新しない。
- 新記録動画、異常終了動画、レビューに必要な証拠を安全に扱う。
- ユーザーの既存`data`を移動、初期化、削除しない。
- GUI終了時に録画中のrunを無言で破棄しない。
- MSSをWGCの暗黙フォールバックにしない。選択したバックエンドが失敗した場合は明示的にエラー表示する。
- GUIの都合で既存CLIとテストを壊さない。

## 5. 三段階の全体像

### 第1段階: GUI化（完了）

- Tkinter/ttkを使用する。
- 既存ロガーのメインループを`LoggerService`へ抽出する。
- CLIとGUIが同じサービスを呼ぶようにする。
- GUIはPython環境から起動し、現在の外部FFmpegを使用する。
- GUIスレッドとロガーワーカーを分離する。
- 開始、停止、状態、録画時間、記録、メッセージ数、保持モード、データフォルダを扱う。
- 既存CLI機能は残す。

### 第2段階: ポータブルEXE化（次の実装対象）

- PyInstaller `onedir`を使用する。
- Python、NumPy、OpenCV、windows-capture、MSS、pywin32、Tcl/Tk、FFmpeg、固定テンプレートを同梱する。
- 配布リソースと書き込み可能なユーザーデータを分離する。
- ZIPを展開してEXEを起動するだけで動く形にする。
- Python、Conda、FFmpeg未導入のWindows環境またはWindows Sandboxで検証する。
- 最初から`onefile`を目指さない。

### 第3段階: GitHub Release化（第2段階の検証後）

- `Tokkun99Logger-vX.Y.Z-windows-x64.zip`をRelease assetとして添付する。
- `SHA256SUMS.txt`を添付する。
- 最初にローカルで`onedir`ビルドを成立させるが、そのローカル成果物を正式配布物にはしない。
- GitHub Actionsの手動実行で同じビルドを再現し、最初のプレリリースを作る。
- 最終的に`v*`タグを契機にテスト、ビルド、ZIP、ハッシュ、Release添付を自動化する。
- GitHubが自動生成する「Source code (zip)」をアプリ本体と誤解させないREADMEにする。

### 配布形式についての確定事項

- 一般配布物は**PyInstaller `onedir`版のZIPだけ**とする。
- ポータブルPythonランタイム＋BAT版は作らない。
- `.venv`をコピーして配布しない。
- PyInstaller `onefile`版は作らない。
- 初期段階ではインストーラーや自動アップデーターを作らない。
- 配布物は公開されたソース、PyInstaller spec、固定依存、GitHub Actions workflowから再現できるようにする。
- Release assetにはSHA-256を添付し、ビルド元のGitタグとコミットをRelease notesへ記載する。
- GitHub Actionsで作ったこと自体はコード署名ではない。未署名EXEに対するSmartScreen警告の可能性は別途明記する。

## 6. 第1段階の設計原則

### 6.1 GUIとロガー本体を分離する

Tkinterのイベントハンドラから`run_live_logger.main()`を直接呼んではならない。現在の`scripts/run_live_logger.py`には、設定解析、ウィンドウ探索、キャプチャ、状態機械、録画、run確定、コンソール表示、終了処理が一体化している。これをGUIへ複製せず、再利用可能なアプリケーションサービスへ抽出する。

目標構造の例:

```text
src/tokkun99_logger/
  app.py                 # アプリケーション入口、必要なら公開main
  gui.py                 # Tkinter/ttk画面
  logger_service.py      # 既存ライブ監視ループ
  logger_events.py       # GUI/CLIへ渡す構造化イベント
  config.py              # LoggerConfigと検証
  app_paths.py           # リソースと書き込みデータのパス解決
  capture.py             # ウィンドウ探索、MSS/WGC実装
  dashboard.py           # 統計の読み取りモデル、必要なら
  __main__.py            # python -m tokkun99_logger
```

ファイル名は既存設計に合わせて調整してよいが、責務分離は維持する。

### 6.2 `scripts`をライブラリとして扱わない

現在の`scripts/run_live_logger.py`は`scripts/probe_capture.py`からキャプチャ機能をimportしている。GUIと後のPyInstallerでは不安定なため、ライブ運用に必要な次を`src/tokkun99_logger/capture.py`等へ移す。

- `TargetWindow`
- DPI awareness設定
- 対象プロセス・ウィンドウ列挙
- キャプチャ対象の選択
- `MssCapture`
- `WgcCapture`
- ライブ運用で必要な座標・crop補助

`scripts/probe_capture.py`は、パッケージ側の機能を使う診断用ラッパーへ変更する。プローブ専用の統計・PPM保存・CLI解析はスクリプト側に残してよい。

### 6.3 設定を型付きオブジェクトにする

現在の`argparse.Namespace`をサービスへ直接渡さない。例えば次の`LoggerConfig`を作る。

```python
@dataclass(frozen=True)
class LoggerConfig:
    fps: int = 30
    capture_backend: Literal["wgc", "mss"] = "wgc"
    ffmpeg_path: Path = Path(r"C:\tools\ffmpeg\bin\ffmpeg.exe")
    retention_mode: Literal["records_only", "collect_samples", "collect_all"] = "records_only"
    sample_every: int = 10
    min_free_gb: float = 2.0
    result_record_seconds: float = 10.0
    message_hold_seconds: float = 2.0
    save_run_images: bool = False
    log_result_frames: bool = False
    result_frame_log_limit: int = 300
    duration_seconds: float | None = None
```

- 検証を1か所にまとめる。
- CLIとGUIで同じ既定値と検証を使う。
- `duration_seconds=None`を無期限運用としてよい。
- GUI実行中に変更できない項目は開始時にスナップショット化する。

### 6.4 パスを注入可能にする

現状の`PROJECT_ROOT / "data"`と`data/template`は開発時には動くが、EXE化すると配布リソースと書き込みデータの場所が異なる。第1段階で、最低限次をサービスへ注入できるようにする。

```text
resource_root
  固定の状態テンプレート、数字テンプレート

data_root
  SQLite、動画、メッセージ、ログ、ユーザー設定

ffmpeg_path
  第1段階では既存パス、第2段階では同梱バイナリ
```

第1段階の既定値は既存互換とする。

```text
resource_root = <repository>/data/template
data_root     = <repository>/data
ffmpeg_path   = C:\tools\ffmpeg\bin\ffmpeg.exe
```

`DataLayout.template`に依存している認識器は、固定リソースのパスを明示的に受け取れるようにする。既存`data`のレイアウトとDB内相対パスは変更しない。

### 6.5 サービス停止を明示的に扱う

`LoggerService`は少なくとも次を受け取る。

- 検証済み`LoggerConfig`
- パス設定
- `threading.Event`等の停止要求
- 構造化イベントを受け取るcallbackまたはqueue

監視ループはフレーム単位で停止要求を確認する。停止時は現在と同等以上に安全に終了する。

- 録画中ならincompleteとして確定・隔離する。
- runを`incomplete`としてDBへ保存する。
- FFmpegのstdinとプロセスを閉じる。
- キャプチャを閉じる。
- インスタンスロックを解放する。
- `stopped`イベントを通知する。

GUIを閉じる際にワーカースレッドが終了していない状態でプロセスを強制終了しない。停止要求後、UIを「停止中」にし、終了を監視する。長時間応答がない場合はユーザーへ状態を示すが、データを壊す強制終了を既定動作にしない。

### 6.6 構造化イベントを使う

既存の`print()`だけをGUIへ取り込む設計にしない。例えば以下のイベントを定義する。

```text
service_starting
target_found
state_changed
recording_started
recording_paused
recording_resumed
run_completed
run_needs_review
recovery_completed
warning
error
service_stopped
```

イベントには必要に応じて次を含める。

- timestamp
- message
- game state
- elapsed seconds
- target size
- capture backend
- run ID
- survival time
- bullet count
- 生存時間記録更新フラグ
- 弾数記録更新フラグ
- 動画保持フラグ
- message cluster ID
- error type

CLIはイベントを人間向けテキストへ変換して表示し、GUIは表示モデルを更新する。`print()`を完全に禁止する必要はないが、製品動作の判定を文字列解析へ依存させない。

## 7. GUI仕様

### 7.1 技術

- Python標準のTkinterと`tkinter.ttk`を使用する。
- 新しいGUIフレームワーク依存を追加しない。
- GUIの表示言語は日本語を基本とする。
- Tkメインスレッド以外からWidgetを操作しない。
- ロガーはバックグラウンドのワーカースレッドで実行する。
- ワーカーからのイベントは`queue.Queue`へ入れ、`root.after(...)`で定期取得する。
- ワーカースレッドは同時に1本だけ許可する。既存`InstanceLock`も維持する。

### 7.2 最小画面

```text
┌ 特訓'99 Logger ───────────────────────┐
│ ゲーム: 検出済み / 320x240             │
│ 状態: PLAYING                          │
│ 録画: ● 00:34                          │
│                                        │
│ 生存時間記録: 40.624秒                 │
│ 弾数記録: 812発                        │
│ メッセージ: 7種類 / 確認済み5種類      │
│                                        │
│ 保持モード: records_only        [▼]    │
│ キャプチャ: WGC（既定）         [▼]    │
│                                        │
│ [監視開始] [停止] [データを開く]       │
│                                        │
│ 状態・警告・直近runの短いログ           │
└────────────────────────────────────────┘
```

見栄えよりも、状態が分かり、誤操作しにくく、停止が安全であることを優先する。

### 7.3 表示項目

- ゲーム検出状態: 未検出、検出済み、複数検出、サイズ不一致、キャプチャ失敗
- 現在状態: `UNKNOWN`、`TITLE`、`PLAYING`、`RESULT`、`MESSAGE`
- 録画状態: 待機、録画中、一時停止、停止中
- 現在runの録画経過時間
- 生存時間の歴代最高
- 弾数の歴代最高
- メッセージクラスタ数
- ラベル済み数または確認済み数
- 現在の保持モード
- 現在のキャプチャバックエンド
- 直近の警告・エラー

統計がない初回起動では`—`または`記録なし`を表示し、例外にしない。

### 7.4 ボタンと状態遷移

#### 監視開始

- 停止中のみ有効。
- 設定を検証する。
- FFmpeg、テンプレート、データ書き込み先の事前確認を行う。
- ワーカーを起動する。
- 起動後は設定コンボを無効にし、停止ボタンを有効にする。
- ゲーム未起動、複数起動、320x240不一致等はダイアログまたは画面内エラーで知らせる。
- 起動失敗後は停止状態へ戻り、修正後に再試行できる。

#### 停止

- 実行中と停止処理中だけ有効。
- 多重クリックしても複数停止処理を起こさない。
- 停止要求をワーカーへ送り、画面を`停止中...`にする。
- 安全な終了イベント後に開始ボタンを再び有効にする。

#### データを開く

- `data_root`をWindows Explorerで開く。
- `os.startfile`等を使う場合も、解決済みの`data_root`だけを対象にする。
- ディレクトリがなければ安全に作成するか、明確なエラーを表示する。

### 7.5 ウィンドウを閉じる操作

- 停止中なら通常終了する。
- 実行中なら停止要求を出し、安全終了を待つ。
- 録画中であることが分かる表示を行う。
- 終了処理が終わるまで二重操作を無効にする。
- タスクトレイ常駐は第1段階の必須要件ではない。

### 7.6 第1段階でGUI化しない機能

次は既存CLIのままでよい。

- スコアの人手訂正
- 未確認スコア一覧の詳細レビュー
- メッセージ本文のラベル付け
- クラスタ統合
- キャリブレーション
- 回帰素材収集・評価
- MSS/WGCベンチマーク

GUIには必要なら「コマンドライン機能はREADME参照」と表示する。第1段階の範囲を広げて既存ロジックを不安定にしない。

## 8. CLI互換性

GUI追加後も以下を維持する。

```powershell
.\scripts\run_logger.cmd
.\scripts\run_live_smoke.cmd
.\.venv\Scripts\python.exe scripts\run_live_logger.py ...
.\.venv\Scripts\python.exe scripts\tokkun99.py stats
.\.venv\Scripts\python.exe scripts\tokkun99.py review-scores
.\.venv\Scripts\python.exe scripts\tokkun99.py review-messages
```

`scripts/run_live_logger.py`はargparseとイベントのコンソール表示を担当する薄いラッパーにする。ライブ監視の実装をCLIとGUIに二重に持たない。

GUIの開発時起動方法は、次のいずれかに統一する。

```powershell
.\.venv\Scripts\python.exe -m tokkun99_logger
```

必要なら互換用に`scripts/run_gui.py`または`scripts/run_gui.cmd`を用意してよいが、実装本体は`src/tokkun99_logger`内に置く。

## 9. ログとエラー表示

- Python標準`logging`を使用する。
- 画面には短い人間向けメッセージを表示する。
- 詳細は`data/log`配下のログファイルに残す。
- ログは無制限に増やさず、`RotatingFileHandler`等で上限を設ける。
- 例外型、時刻、スタックトレースを詳細ログに残す。
- 動画フレーム、個人環境変数、デスクトップ全体画像を通常ログへ入れない。
- `Tkinter callback`内の例外を握りつぶさない。
- ワーカー例外は`error`イベントに変換し、GUIを再試行可能な停止状態へ戻す。

代表的なユーザー向けエラー:

- 『特訓'99』が見つからない。
- 対象ウィンドウが複数ある。
- ゲーム画面が320x240ではない。
- FFmpegが見つからない、または起動できない。
- テンプレートがない、または読めない。
- データフォルダへ書き込めない。
- 空き容量が不足している。
- 別のロガーがすでに動いている。
- 選択したキャプチャ方式を利用できない。

## 10. 統計表示の実装

GUI内へSQLを散在させない。統計取得用の関数または小さなモデルを用意し、既存`scripts/tokkun99.py stats`も可能なら同じ集計処理を使う。

最低限取得する値:

- run総数
- 完了run数
- 要レビュー数
- 生存時間最高値とrun ID
- 弾数最高値とrun ID
- 有効メッセージクラスタ数
- ラベル済み数
- 確認済み数
- 観測総数

GUI起動時、run確定後、手動再表示時のいずれかで更新する。監視中に高頻度でSQLiteをポーリングしない。

## 11. テスト戦略

### 11.1 既存回帰テスト

GUI化前の基準は`58 passed, 1 skipped`だった。現在のテスト構成を基準に、EXE化後も全て通す。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### 11.2 新しい単体テスト

実ゲームを必要としないよう依存を注入し、最低限次をテストする。

- `LoggerConfig`の既定値と不正値拒否
- リソースルートとデータルートの分離
- サービス開始時の事前検査
- 停止要求が監視ループを終了させる
- 停止時にcapture、recorder、lockが解放される
- ワーカー例外が構造化`error`イベントになる
- 同じサービスの二重開始を拒否する
- 状態変更イベントの内容
- run完了イベントの2系統記録フラグ
- 空DBの統計表示
- データのあるDBの統計表示
- データフォルダを開く対象パスの解決

キャプチャ、時計、FFmpeg recorder、ウィンドウ探索、イベントsinkはfakeまたはstubへ差し替えられる構造にする。単体テストで実デスクトップをキャプチャしない。

### 11.3 GUIテスト

Tkinterは表示環境へ依存するため、ロジックの大部分をViewModel相当または純粋関数として試験する。最低限:

- GUIを構築して即座に破棄できるスモークテスト（環境でTkが使える場合）
- 停止時のボタン状態
- 起動中のボタン状態
- `state_changed`イベントで表示が更新される
- `error`イベント後に再試行できる
- 閉じる操作が停止要求を発行する

Tkが使えないCI環境では、理由が明確なskipにする。主要ロジックをGUIテストのskipへ依存させない。

### 11.4 手動テスト

1. Python版GUIを起動する。
2. ゲーム未起動で開始し、分かりやすいエラーと再試行を確認する。
3. ゲームを1つ起動し、320x240で監視開始する。
4. `TITLE -> PLAYING -> RESULT -> MESSAGE -> TITLE`が表示へ反映されることを確認する。
5. 動画、DB、メッセージ、記録更新がCLI版と同様であることを確認する。
6. プレイ中に停止し、incomplete動画とDB行が安全に残ることを確認する。
7. RESULT停止中、MESSAGE時、TITLE待機中にそれぞれ停止する。
8. GUIを閉じて同じ安全終了を確認する。
9. 再起動し、放棄partial回収と統計再読込を確認する。
10. GUI版停止後にCLI版、CLI版停止後にGUI版を起動し、ロックが正常解放されることを確認する。

## 12. 第1段階の実装順序（完了済み）

### Step 0: ベースライン確認

- `git status`、ブランチ、HEADを確認する。
- `AGENTS.md`があれば読む。
- README、依存、実行入口を再確認する。
- 全テストを実行する。
- ユーザーの無関係な変更に触れない。

### Step 1: 設定とパス境界

- `LoggerConfig`と検証を作る。
- リソース、データ、FFmpegのパスを明示する。
- 既存の開発時既定値を維持する。
- パスと設定の単体テストを書く。

### Step 2: キャプチャコードをパッケージへ移す

- ライブ運用部分を`src/tokkun99_logger`へ移す。
- `probe_capture.py`と既存テストのimportを調整する。
- MSSとWGCの挙動を変えない。
- プローブ・ベンチマークを壊さない。

### Step 3: `LoggerService`を抽出する

- `run_live_logger.py`の監視ループとrun確定をサービスへ移す。
- 停止イベントと構造化イベントを追加する。
- CLIを薄いラッパーへする。
- 既存CLIの引数と出力の意味を維持する。
- fake依存によるサービステストを書く。

### Step 4: 統計読取を共有化する

- GUI表示用の統計モデルを作る。
- 可能なら既存`stats`コマンドも再利用する。
- 空DBと既存DBをテストする。

### Step 5: Tkinter GUIを追加する

- 最小画面を作る。
- Queueと`root.after`でイベントを反映する。
- 開始、停止、データを開くを実装する。
- モードとキャプチャ選択を実装する。
- 二重開始と多重停止を防ぐ。
- 安全なウィンドウ終了を実装する。

### Step 6: 起動入口とREADME

- `python -m tokkun99_logger`等の起動入口を追加する。
- 必要なら開発者向け`.cmd`を追加する。
- READMEにGUI起動、CLI起動、制約、停止方法を追記する。
- GUIが入力注入をしないことを明記する。

### Step 7: 検証

- 全自動テストを実行する。
- GUIスモークを行う。
- 実ゲームによる手動チェックリストを実施する。
- `git diff`で意図しない変更や実データ混入がないことを確認する。

## 13. 第1段階の完了条件

- Tkinter/ttkのGUIがPython環境から起動する。
- GUIから監視開始・安全停止・データフォルダ表示ができる。
- ゲーム検出、状態、録画状態、記録、メッセージ進捗が表示される。
- 保持モードを選べる。
- WGCとMSSを明示的に選べる。WGCを既定とし、MSSは代替方式として表示される。
- GUIの応答が30 FPSのキャプチャ処理で固まらない。
- GUI終了時に録画、DB、FFmpeg、ロックを安全に処理する。
- 対象未検出、複数検出、サイズ不一致、FFmpeg欠落、容量不足を分かりやすく表示する。
- GUIとCLIが同一の監視サービスを使い、ロジックが二重化されていない。
- 既存CLIが引き続き動く。
- 現在のテスト構成を含め、全テストが通る。
- 実ゲームの最低1runで、動画・スコア・メッセージ・記録判定がGUI化前と一致する。
- ゲームへの入力送信コードが存在しない。
- 実データ、動画、SQLite、ユーザー固有ログがGit管理へ追加されていない。
- READMEが更新されている。

## 14. 第1段階で対象外とした項目

- PyInstallerビルド
- 単一EXE化
- FFmpegバイナリの取得・同梱
- インストーラー
- 自動アップデーター
- GitHub Actions
- Gitタグ作成
- GitHub Release公開
- コード署名
- タスクトレイ常駐
- メッセージやスコアレビューの完全GUI化
- UIデザインの作り込み
- ゲーム操作自動化

## 15. 第2段階へ渡す設計上の宿題

GUI化の時点で次が満たされていれば、EXE化が容易になる。

- `scripts`をimportしなくてもアプリが動く。
- すべての実行コードが`src/tokkun99_logger`にある。
- 固定リソースと書き込みデータのルートが分離されている。
- FFmpegパスがハードコードではなく解決・注入できる。
- GUIのエントリーポイントが1つに定まっている。
- subprocess、OpenCV、MSS、WGCの動的importが把握されている。
- 必要なテンプレート一覧が明確である。
- バージョン文字列を1か所から取得できる。
- アプリアイコンを後から指定できる。
- 例外時の詳細ログをファイルへ残せる。

第2段階では、PyInstaller用の専用ビルド依存を`requirements-build.txt`等へ分離し、通常実行依存へ混ぜない。最初は`onedir`で検証し、ZIP配布物には空の`data`を入れず、初回起動で作成する。テンプレートは読み取り専用の同梱リソース、SQLite・動画・メッセージは書き込み可能なポータブルデータとして扱う。

## 16. 第3段階へ渡す配布要件

GitHub Releaseの想定成果物:

```text
Tokkun99Logger-v0.1.0-windows-x64.zip
SHA256SUMS.txt
```

ZIP内部の想定:

```text
Tokkun99Logger/
  Tokkun99Logger.exe
  _internal/
    Python・OpenCV・Tcl/Tk等
    ffmpeg.exe
    template/
  LICENSES/
  README.txt
```

Release作業は次の順序で成熟させる。

1. ローカル`onedir`ビルドは成立性とWindows Sandbox等での検証だけに使う。
2. GitHub Actionsの`workflow_dispatch`でWindowsビルドを再現し、その成果物を最初のプレリリースへ添付する。
3. `v*`タグでテストとビルドを行い、Release assetとSHA-256を自動添付する。
4. 十分に安定した後だけ、自動で正式Releaseを公開する。

Actionsの短期Artifactを一般配布先にせず、正式成果物はGitHub Release assetにする。FFmpegの配布ライセンス、使用ビルド、チェックサム、第三者ライセンス表示を確定してから公開する。未署名EXEではWindows SmartScreen警告が出る可能性をREADMEとRelease notesに記載する。

## 17. Codexへの作業ルール

- GUI化は完了済みである。次は第2段階だけを実装し、承認なくRelease公開へ進まない。
- 既存のConda環境を変更しない。現在の専用`.venv`を使う。
- 新規依存が不要なTkinter/ttkを優先する。
- 不要なパッケージをインストールしない。
- ユーザーの未コミット変更を消さない。
- `data/collection`、`data/log`、`artifacts`の実データをGitへ追加しない。
- ゲーム本体やゲーム配布物をリポジトリへ追加しない。
- 大きな一括書き換えを避け、PyInstaller spec、ローカル`onedir`ビルド、クリーン環境検証、GitHub Actionsの順に小さく検証する。
- 各段階でテストを実行し、退行箇所を早く特定する。
- 実機確認が必要な項目は自動テスト済み項目と区別して報告する。
- EXE化完了時に、変更ファイル、テスト結果、Windows Sandbox等での検証結果、第3段階へ残した課題をまとめる。
- ユーザーから明示されない限り、commit、push、PR、タグ、Release公開を行わない。

## 18. 次工程開始時にCodexへ渡す短い指示

以下をそのまま実装開始指示として使用できる。

> `GUI_PORTABLE_RELEASE_PLAN.md`を最初から最後まで読み、最新のリポジトリ状態と既存テストを確認してください。GUI化は完了済みです。今回は第2段階としてPyInstaller `onedir`のポータブルWindows x64版を実装してください。ポータブルPython＋BAT版、`onefile`版、インストーラーは作らないでください。WGC既定/MSS代替、CLI互換性、既存データ形式、録画安全性、入力注入を行わない要件を維持してください。固定テンプレートとFFmpegを配布物へ含め、書き込みデータは配布リソースから分離してください。通常のPython環境がないWindows環境で起動・監視・安全停止を検証し、依存ライセンスと再現可能なビルド定義を整えてください。GitHub Actions、タグ、Release公開はまだ行わず、まずローカル`onedir`成果物を完成させて結果を報告してください。
