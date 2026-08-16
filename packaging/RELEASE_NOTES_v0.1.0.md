# Tokkun '99 Logger v0.1.0

『特訓'99 -君よ、男避けに避けろ-』のプレイ結果、生存時間記録とRESULT画面に表示される弾数記録の2系統のハイスコア動画、終了時メッセージを自動記録するWindows用ポータブルロガーの初回公開版です。

## ダウンロード

`Tokkun99Logger-v0.1.0-windows-x64.zip`をダウンロードしてください。GitHubが自動表示する`Source code (zip)`は実行用ポータブル版ではありません。ダウンロード後は`SHA256SUMS.txt`でZIPのSHA-256を確認できます。

## 対象ゲーム

オリジナル版『特訓'99 -君よ、男避けに避けろ-』は、作者びい氏の[配布ページ](https://bee.in.coocan.jp/tk)から入手できます。公式サイトは[「やればできる。」](https://bee.in.coocan.jp/)です。

ゲーム本体はこのロガーのReleaseに含まれません。『特訓'99』を制作・公開され、現在も遊べる形で残してくださっている作者のびい氏に感謝いたします。

## 使い方

1. ZIPを通常の書き込み可能なフォルダへ展開します。
2. 『特訓'99』を起動します。
3. `Tokkun99Logger.exe`を起動します。

## 主な機能

- 生存時間の歴代記録を更新したrunの動画
- RESULT画面に表示される弾数の歴代記録を更新したrunの動画
- 終了時メッセージ収集
- ゲーム起動・終了に追従する自動監視
- WGC既定、MSS代替の画面キャプチャ
- `.incomplete`を用いた安全なMP4確定

## 動作条件

- Windows 10/11 x64
- オリジナル版『特訓'99』
- 320×240のゲームクライアント領域
- ゲームを最小化せず、他のウィンドウで覆わないこと

## 重要事項

- ゲームへEnterやキー入力を送る機能はありません。
- アプリと同梱FFmpegは未署名です。Windows SmartScreenやMicrosoft Defenderの警告が表示される可能性があります。
- 新規動画はLGPL版FFmpegのMPEG-4 Part 2、最高品質`-q:v 1`です。この設定は数学的な可逆圧縮ではなく、H.264よりファイルサイズが大きくなる場合があります。
- 対象は固定320×240画面です。未知の画面配置や数字字形はレビュー対象になります。
- 同梱FFmpegのrav1eについて、公開元のActionsログ失効により実ビルドのCargo lockを完全には証明できず、`cargo-c`も未固定です。固定日時とバイナリから依存関係を再構成して通知を収録し、この不確実性を既知の制約として受容しています。

## ライセンスと第三者資産

- アプリ本体: MIT License
- 同梱FFmpeg: LGPL-3.0-or-later
- ゲーム由来の小さな認識テンプレートはMIT Licenseの対象外です。

詳細はZIP内の`LICENSE`、`THIRD_PARTY_ASSETS.md`、`LICENSES/`を参照してください。FFmpegの対応ソースとBtbNビルド定義は`LICENSES/FFmpeg-MANIFEST.json`に固定URLで記載します。

## ビルド情報

- Git tag: `v0.1.0`
- Commit: `<full-commit-sha>`
- 自動テスト: Release workflow内で実行
- ZIP SHA-256: `SHA256SUMS.txt`参照
