# Tokkun '99 Logger: LGPL FFmpeg + MPEG-4移行 実装指示

## 1. この文書の目的

この文書は、`Tokkun '99 Logger`のポータブルWindows版で同梱しているGPL版FFmpegと`libx264`を、LGPL版FFmpegとFFmpeg標準`mpeg4`エンコーダへ置き換えるためのCodex向け実装指示である。

この工程はGitHub Release化の前に独立して完了させる。移行後にローカル実機プレイ、ポータブル版のクリーン起動、ライセンス収集を検証してから、別工程としてGitHub ActionsとReleaseを実装する。

本指示は、最新確認時点の開発ブランチ`agent/sortable-artifact-filenames`、コミット`a482163f26c6ed131c070246d91b9af4c3ba3f54`を基準とする。作業開始時には必ずリポジトリの最新状態、未コミット変更、現在のブランチを再確認すること。

## 2. 確定済みの方針

- Windows 10/11 x64向けPyInstaller `onedir`ポータブル版を維持する。
- FFmpegは外部インストールを要求せず、配布物へ同梱する。
- GPL専用ライブラリを含まないLGPL版FFmpegを使う。
- `libx264`、`libx265`、`libxvid`などGPL依存のエンコーダは使わない。
- 動画コンテナは従来どおりMP4、拡張子は`.mp4`とする。
- 映像エンコーダはFFmpeg標準の`mpeg4`（MPEG-4 Part 2）とする。
- 画質は最高設定の`-q:v 1`に固定する。
- `mpeg4`の最高品質設定は数学的な可逆圧縮ではないことをREADMEに明記する。
- 画質を優先し、H.264よりファイルサイズが増えることは許容する。
- 既存のH.264動画は変換・削除しない。新規録画だけをMPEG-4 Part 2へ切り替える。
- SQLite、JSONL、run ID、動画パス、保持モード等の既存データ形式は変更しない。
- ゲームへのキー入力、Enter送信、ゲーム起動などの入力自動化は追加しない。
- この工程ではタグ作成、GitHub Release公開、既存`main`へのマージを行わない。

## 3. 現状と変更理由

現状の`src/tokkun99_logger/recorder.py`は、FFmpegへ次の指定を渡している。

```text
-c:v libx264
-preset veryfast
-crf 18
-pix_fmt yuv420p
```

現在の`packaging/ffmpeg-manifest.json`は、GyanのGPL v3 full static buildを固定している。このビルドは`--enable-gpl`、`libx264`、`libx265`等を含む。

移行後は、GPL専用ライブラリを含まないLGPL版FFmpegを単独の外部プロセスとして起動し、FFmpeg自身に内蔵されている標準`mpeg4`エンコーダで録画する。

LGPL版に変更しても、FFmpegの著作権表示、ライセンス本文、対応ソース、ビルド情報の案内は必要である。「LGPLだから表示不要」と扱ってはならない。

## 4. 使用するFFmpeg候補

浮動する`latest` URLや無検証の最新nightlyは使わない。取得元、ファイル名、バージョン、ZIP全体のSHA-256を固定する。

初期候補は次とする。

```text
提供元:
  BtbN/FFmpeg-Builds

Release tag:
  autobuild-2026-07-31-14-10

Archive:
  ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-8.1.zip

Archive URL:
  https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-07-31-14-10/ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-8.1.zip

Archive SHA-256:
  089e4169e93b2b3f3acbfced3c0704d24276a225641bdda04d796d28b07a2a38
```

この候補はBtbNの`win64-lgpl` staticパッケージである。アプリはFFmpegライブラリへリンクせず、`ffmpeg.exe`をsubprocessとして起動する。staticパッケージを選ぶ理由は、PyInstaller配布物へ多数のFFmpeg DLLを個別収集する複雑さを避けるためである。

ただし、作業開始時に次を再確認すること。

1. URLが取得可能である。
2. ZIPのSHA-256が上記と一致する。
3. 展開物にライセンス、README、ビルド情報が含まれる。
4. `ffmpeg.exe -version`のconfigure情報に`--enable-gpl`と`--enable-nonfree`がない。
5. `ffmpeg.exe -encoders`にFFmpeg標準の`mpeg4`がある。
6. `libx264`、`libx265`、`libxvid`を必要としない。
7. Windows x64で単独起動できる。

上記を満たさない場合、黙って別ビルドへ切り替えない。調査結果と代替候補をユーザーへ提示して承認を得ること。

## 5. マニフェストの拡張

`packaging/ffmpeg-manifest.json`は、単一の`ffmpeg.exe`ハッシュだけでなく、取得から展開まで検証できる形式へ変更する。

想定例:

```json
{
  "provider": "BtbN/FFmpeg-Builds",
  "version": "n8.1.2-34-g9b6c8969e0",
  "variant": "win64-lgpl-8.1",
  "license": "LGPL-2.1-or-later",
  "archive_name": "ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-8.1.zip",
  "archive_url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-07-31-14-10/ffmpeg-n8.1.2-34-g9b6c8969e0-win64-lgpl-8.1.zip",
  "archive_sha256": "089e4169e93b2b3f3acbfced3c0704d24276a225641bdda04d796d28b07a2a38",
  "ffmpeg_sha256": "展開したffmpeg.exeの実測値",
  "ffmpeg_source_url": "正確なFFmpegソース参照先",
  "build_source_url": "対応するBtbNビルド定義の固定コミット参照先"
}
```

実装時には`ffmpeg_source_url`と`build_source_url`を、浮動ブランチではなく対応コミットへ固定する。`ffmpeg_sha256`は対象ZIPを検証・展開した後に実測して記録する。

## 6. 録画コマンドの変更

対象ファイル:

- `src/tokkun99_logger/recorder.py`
- `tests/test_recorder.py`
- 必要に応じて録画設定を渡す`logger_service.py`

現状のH.264固有指定を削除する。

```text
-c:v libx264
-preset veryfast
-crf 18
```

次の指定へ変更する。

```text
-c:v mpeg4
-q:v 1
-pix_fmt yuv420p
-movflags +faststart
-f mp4
```

主要コマンド配列の想定:

```python
command = [
    str(self.ffmpeg_path),
    "-hide_banner",
    "-loglevel",
    "error",
    "-f",
    "rawvideo",
    "-pixel_format",
    "bgr24",
    "-video_size",
    f"{self.width}x{self.height}",
    "-framerate",
    str(self.fps),
    "-i",
    "pipe:0",
    "-an",
    "-c:v",
    "mpeg4",
    "-q:v",
    "1",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    "-f",
    "mp4",
    str(partial_path),
]
```

画質はユーザー設定へ露出させず、当面`1`に固定する。既存の`crf`引数と`self.crf`は削除する。将来変更可能にする設計上の理由がある場合は、`quality: int = 1`へ名称変更し、`1 <= quality <= 31`を検証する。ただしGUIへ画質選択欄は追加しない。

以下の既存挙動を維持する。

- pre-roll
- pause/resume
- MESSAGE画面のhold追加
- `.incomplete`への一時記録
- FFmpeg終了成功後だけ正式`.mp4`へatomic rename
- 異常終了動画の隔離保存
- FFmpeg stderrを含むエラー報告
- 録画中の安全停止

## 7. FFmpeg入力検証の追加

ビルド処理へ、ライセンス種別と必要機能を機械的に検査する工程を追加する。

最低限、次を実行する。

```powershell
ffmpeg.exe -hide_banner -version
ffmpeg.exe -hide_banner -encoders
ffmpeg.exe -hide_banner -h encoder=mpeg4
```

ビルドを失敗させる条件:

- `-version`出力に`--enable-gpl`がある。
- `-version`出力に`--enable-nonfree`がある。
- `mpeg4`エンコーダがない。
- 対象が64 bit Windowsビルドではない。
- ZIPまたは`ffmpeg.exe`のSHA-256がマニフェストと一致しない。
- 必要なライセンス・ビルド情報ファイルがない。

`libx264`が存在しないこと自体を唯一の判定基準にしない。configure情報、variant、ハッシュ、標準`mpeg4`の有無を併せて検証する。

## 8. PyInstallerとポータブルビルド

対象ファイル:

- `packaging/Tokkun99Logger.spec`
- `scripts/build_portable.ps1`
- `scripts/verify_portable.ps1`
- `packaging/README_PORTABLE.txt`

要件:

1. LGPL版`ffmpeg.exe`を従来どおり`_internal/ffmpeg.exe`へ格納する。
2. FFmpegの一時ダウンロード先と展開先をリポジトリ内の`build/`配下に限定する。
3. ZIP取得前後でパスを絶対化し、削除対象をビルド専用ディレクトリに限定する。
4. ローカルビルドでは、明示されたFFmpegルートを使う方式も維持してよい。
5. GitHub Actionsで使用する取得処理は固定URLと固定SHA-256だけを許可する。
6. `dist/Tokkun99Logger`を生成する前に既存のデバッグ用`data/`を配布物へ混入させない。
7. 配布物に`data/`が存在したらビルドまたは検証を失敗させる。
8. Python、Conda、システムFFmpegをPATHから除外した状態で起動できることを検証する。

既存のローカル`dist/Tokkun99Logger/data`には実プレイデータが存在し得る。そのフォルダをそのままZIP化してはならない。Release成果物は必ずクリーンビルドから作る。

## 9. ライセンス収集の変更

対象ファイル:

- `scripts/collect_portable_licenses.py`
- `tests/test_portable_licenses.py`
- `packaging/ffmpeg-manifest.json`
- `packaging/README_PORTABLE.txt`
- `README.md`

現行の`FFmpeg-GPL-3.0.txt`前提を削除し、LGPL版に対応させる。

配布物の`LICENSES/`には最低限、次を含める。

```text
LICENSES/
  THIRD_PARTY_NOTICES.txt
  FFmpeg-LGPL-2.1-or-later.txt
  FFmpeg-BUILD.txt
  FFmpeg-MANIFEST.json
  Python依存パッケージのライセンス群
```

`THIRD_PARTY_NOTICES.txt`には次を記載する。

- FFmpegを使用していること。
- FFmpegの正確なバージョンとvariant。
- LGPL 2.1 or laterであること。
- FFmpegの対応ソース参照先。
- BtbNビルド定義の固定参照先。
- 配布した`ffmpeg.exe`のSHA-256。
- FFmpegは本アプリとは別プロセスとして実行されること。

Releaseページにも、FFmpegのライセンスと対応ソースへの案内を掲載できるようREADMEまたはRelease notes用文面を用意する。

対応ソースの提供方法については、単なる浮動URLだけで済ませず、Release時点で取得可能か確認する。必要なら、FFmpegおよびビルド定義の対応ソースを別のRelease assetとして添付する案をユーザーへ提示する。法的判断が必要な場合は断定せず、実装上確認できた事実と残る判断を分けて報告する。

## 10. テスト戦略

### 10.1 単体テスト

録画コマンド生成を直接検証できるよう、必要ならコマンド構築を小さな関数へ分離する。

検証内容:

- `-c:v mpeg4`がある。
- `-q:v 1`がある。
- `-pix_fmt yuv420p`がある。
- `-movflags +faststart`がある。
- `libx264`がない。
- `-preset`がない。
- `-crf`がない。
- 出力は明示的にMP4である。

既存のpre-roll、pause/resume、hold、finalize、異常終了テストを維持する。

### 10.2 FFmpeg統合テスト

固定したLGPL版FFmpegと`ffprobe`を使って短い動画を生成し、次を確認する。

```text
codec_name=mpeg4
pix_fmt=yuv420p
期待したフレーム数
幅320、高さ240
期待したフレームレート
```

既存テスト名`test_ffmpeg_recorder_writes_h264_with_preroll`は、MPEG-4を表す名前へ変更する。

テストがローカルの`C:\tools\ffmpeg`だけへ暗黙依存しないようにする。GitHub Actionsでは取得・検証済みのFFmpegパスを明示的にテストへ渡す。

### 10.3 実機プレイ検証

次を実際のゲームで確認する。

- TITLEからPLAYING開始時に録画される。
- RESULTと必要なMESSAGEまで含まれる。
- 生存時間記録と弾数記録の正式保存が従来どおり動く。
- 非記録動画の削除方針が従来どおり動く。
- 認識失敗と途中終了動画が隔離される。
- GUIの開始、停止、自動監視、終了が正常に動く。
- 動画をWindows上で再生できる。
- 弾、白文字、RESULT数字、MESSAGE文字が十分鮮明である。
- 長時間プレイでも録画停止とMP4 trailer書き込みが完了する。

画質は`-q:v 1`で固定するため、画質比較による設定選択は行わない。ただし、5分、30分程度の録画で容量、CPU負荷、停止所要時間を測定し、Release notesに書く必要がある異常な増加がないか確認する。

### 10.4 ポータブル検証

- Pythonなし。
- Condaなし。
- FFmpegのシステムインストールなし。
- PATHをWindows標準だけに限定。
- 書き込み可能な通常フォルダへ展開。
- 初回起動時にEXE横へ`data/`が生成される。
- 同梱FFmpegで実録画できる。
- 安全停止後にSQLiteとMP4が破損していない。
- パスに空白を含むフォルダでも動く。
- 可能なら日本語を含むフォルダでも動く。

## 11. 後方互換性

- 既存のH.264 MP4は変換しない。
- 過去動画の再生、一覧表示、ファイル名、DB参照を壊さない。
- 新規MPEG-4 Part 2動画も従来どおり`.mp4`として保存する。
- DBスキーマ変更は行わない。
- コーデック名をDBへ追加する変更は、この移行に必須でなければ行わない。
- 既存の`data/`を削除・移動・初期化しない。

## 12. 実装順序

1. 最新ブランチ、未コミット変更、既存テストを確認する。
2. LGPL版FFmpeg候補を一時領域へ取得する。
3. ZIP SHA-256、variant、configure、`mpeg4`エンコーダを検証する。
4. `ffmpeg.exe`のSHA-256と対応ソース・ビルド定義を確定する。
5. `ffmpeg-manifest.json`を更新する。
6. `RunRecorder`を`mpeg4 -q:v 1`へ変更する。
7. 録画単体テストと統合テストを更新する。
8. ライセンス収集処理とテストを更新する。
9. PyInstaller spec、ビルド、ポータブル検証を更新する。
10. 全自動テストを実行する。
11. クリーンな`onedir`成果物を作る。
12. Python/Conda/FFmpegなし相当の環境で起動と録画を検証する。
13. ユーザーへ実プレイ確認を依頼し、容量と画質を確認する。
14. 変更内容、テスト結果、実機確認結果、残るライセンス判断を報告する。
15. ユーザーの明示承認後にだけコミットする。タグ、Release公開は別工程とする。

## 13. 完了条件

以下をすべて満たしたとき、この移行を完了とする。

- 固定したLGPL版FFmpegをSHA-256付きで再取得できる。
- `ffmpeg -version`に`--enable-gpl`と`--enable-nonfree`がない。
- FFmpeg標準`mpeg4`で`-q:v 1`録画できる。
- `ffprobe`が新規動画を`codec_name=mpeg4`として認識する。
- pre-roll、pause、hold、atomic finalize、隔離保存が退行していない。
- 全バージョン管理対象テストが成功する。
- ポータブル版にPython、OpenCV、テンプレート、LGPL FFmpegが必要な形で同梱される。
- 配布物にユーザーの`data/`やデバッグ動画が含まれない。
- Python、Conda、外部FFmpegなしでGUI起動・監視・録画・安全停止できる。
- `LICENSES/`とREADMEのFFmpeg表記がLGPL版と一致する。
- FFmpegの対応ソースとビルド情報を利用者が確認できる。
- 既存H.264動画と既存DBがそのまま利用できる。
- ゲーム入力の自動化が追加されていない。

## 14. Codexへの作業上の注意

- 最初に`git status`、現在ブランチ、最新コミット、リポジトリ内指示を確認する。
- ユーザーの未コミット変更を上書きしない。
- 既存のConda環境を変更しない。プロジェクト専用`.venv`を使う。
- 勝手に既存環境へ大量インストールしない。
- `data/collection`、`data/log`、`artifacts`、`dist`の実データをGitへ追加しない。
- ゲーム本体、ゲーム配布物、ユーザーのプレイ動画を追加しない。
- 既存のローカル`dist`をRelease用成果物として再利用しない。
- 固定URL・固定ハッシュの検証を省略しない。
- 失敗時に別のFFmpegやコーデックへ暗黙にフォールバックしない。
- LGPL対応を理由に、ライセンス・ソース案内を削除しない。
- 法的結論を断定せず、実装上確認できた事項とユーザー判断事項を分ける。
- ユーザーの明示指示なしにpush、PR、タグ、Release公開を行わない。

## 15. Codexへ渡す短い開始指示

以下を新しいCodexタスクへそのまま渡せる。

> `LGPL_FFMPEG_MPEG4_MIGRATION_PLAN.md`を最初から最後まで読み、最新リポジトリ、現在ブランチ、未コミット変更、既存テストを確認してください。ポータブルWindows版で使用しているGPL版FFmpegと`libx264`を、文書で固定したBtbN Windows x64 LGPL版FFmpegとFFmpeg標準`mpeg4`へ移行してください。録画はMP4を維持し、画質は最高設定`-q:v 1`に固定してください。既存H.264動画、DB、保持モード、pre-roll、pause/resume、MESSAGE hold、atomic finalize、異常動画の隔離、WGC既定/MSS代替、入力注入を行わない要件を維持してください。FFmpegのZIPと実行ファイルのSHA-256、`--enable-gpl`/`--enable-nonfree`不在、標準`mpeg4`の存在を機械検証し、ライセンス収集、PyInstaller `onedir`、ポータブル検証、README、テストを更新してください。既存の`dist/data`や実プレイデータを配布物・Gitへ含めないでください。この工程ではタグやGitHub Releaseを公開せず、変更点、自動テスト、実機確認事項、残るライセンス判断を報告してください。
