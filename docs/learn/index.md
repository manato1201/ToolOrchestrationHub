# ToolOrchestrationHub 学習資料(保守・拡張の実務編)

このフォルダは、**Hub を直す・足す人**のための資料です。基礎から順に学ぶ講義は [../lecture/index.md](../lecture/index.md)(第 0〜6 回)にあります。

| # | 資料 | いつ読むか |
|---|---|---|
| 1 | [全体像](01-overview.md) | 何がどう動いているか(プロセス・ループ・データの置き場所・環境変数)を知りたい |
| 2 | [コードの読み方](02-code-tour.md) | どのファイルから読むか、どこに何があるか知りたい |
| 3 | [内側のしくみ](03-internals.md) | アラートの保存・通知・git 同期・起動・入口の守りの中身を知りたい |
| 4 | [拡張のレシピ](04-extend.md) | ツール・送り手・通知先・リポジトリ・手順書を**足したい** |
| 5 | [テストの書き方と実行](05-testing.md) | テストを回す・足す・文書の検査を通したい |
| 6 | [トラブルと保守](06-troubleshooting-maintenance.md) | 動かない・403・「未確認」が消えない、定期的な保守をしたい |
| – | [用語集](glossary.md) | 分からない言葉が出た |

## 最初の 15 分

1. [README](../../README.md) の**クイックスタート**で、`uv run hub` を起動し、`http://127.0.0.1:8790` を開く。
2. [構成図](../diagrams/architecture.svg)を見ながら、[全体像](01-overview.md)の「5 つのループ」を読む。
3. `curl -X POST http://127.0.0.1:8790/api/heartbeat/sound_middleware` を送り、画面の `sound_middleware` が「未確認」から「正常」へ変わるのを見る(第 0 回の図の流れ)。

## 目的別の近道

| やりたいこと | 読む場所 |
|---|---|
| ツールを 1 件足す | [4 拡張](04-extend.md) レシピ 1(`registry.yaml` に書くだけ) |
| 送り手(アラートの発生元)を足す | [4 拡張](04-extend.md) レシピ 3・講義[第 6 回](../lecture/06-testing-capstone.md) |
| 通知先を足す(Teams・Discord など) | [4 拡張](04-extend.md) レシピ 4 |
| 他のリポジトリを同期・起動の対象にする | [4 拡張](04-extend.md) レシピ 5 |
| ユーザー・役割・API キーを管理する | [3 内側](03-internals.md)「入口の守り」・講義[第 5 回](../lecture/05-security-and-auth.md) |
| 403 や 401 が出る | [6 トラブル](06-troubleshooting-maintenance.md) |
| 設計の経緯(v1.1〜v2.7)を知る | [変更履歴と詳細](../reference/changelog.md) |
