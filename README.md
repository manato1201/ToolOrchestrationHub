# ToolOrchestrationHub

今まで作ってきたシステム・機能を**中継・モニタリング**し、使用者にとって使いやすくするための**監視の中継所**です。
12 個のツールの**生死・アラート**と、13 個のリポジトリの**git の状態**を、1 つの画面と通知に集めます。**見るだけ**で、ツールの権限は奪いません。

![構成図](docs/diagrams/architecture.svg)

## 状態

| 項目 | 内容 |
|---|---|
| 版 | v2.7(認証・役割・監査ログ。経緯は [変更履歴](docs/reference/changelog.md)) |
| 台帳 | 12 ツール(`hub/registry.yaml`)・13 リポジトリ(`hub/repos.yaml`) |
| テスト | `uv run pytest -q` で全部通る(Hub 本体 + `profiling_tool` + 文書の検査) |
| 画面の確認 | 実ブラウザは **Chrome のみ**。Firefox・Safari・スマホ実機は**未確認** |
| 認証 | 既定は**なし**(`HUB_AUTH=off`。Host・Origin の検査だけ)。複数人なら `HUB_AUTH=required` |
| 既知の問題 | [トラブルと保守](docs/learn/06-troubleshooting-maintenance.md)(CI 系の「未確認」が長引く等) |

## クイックスタート

```bash
uv sync --extra dev
uv run pytest -q
uv run hub          # http://127.0.0.1:8790 でダッシュボードを起動
```

```bash
# 各ツールからの信号(認証を必須にしたときは X-API-Key を付ける)
curl -X POST http://127.0.0.1:8790/api/heartbeat/sound_middleware
curl -X POST http://127.0.0.1:8790/api/ci-success/research_collector
curl -X POST http://127.0.0.1:8790/api/alerts/profiling-tool -H "Content-Type: application/json" \
  -d '{"signature": "gpu_frame_budget_exceeded", "severity": "critical", "message": "frame budget exceeded"}'
```

`hub/registry.yaml` の `poll_interval_s`・`check_params` は**暫定値**です。ツール側が固まったら、このファイルだけを直せば追従します(再起動不要・5 秒で反映)。

## できること

- **台帳**(`hub/registry.py`・`registry.yaml`): ツールをデータで持つ。ホットリロード、壊れた台帳は拒否して古いまま動く。
- **死活監視**(`hub/health/`): HTTP の `/health`(能動)・ハートビート(受動)・CI の最終成功(経過時間)。**信号が無い間は「未確認」**(偽の正常を出さない)。
- **アラート**(`hub/alert_aggregator.py`): 4 つの送り手を同じ形に正規化し、重複を 1 件にまとめ、解消まで追う。SQLite に保存し、再起動後も履歴が残る。
- **通知**(`hub/notify.py`): Windows トースト、`HUB_SLACK_WEBHOOK_URL` を設定すると Slack も。
- **ダッシュボード**(`hub/dashboard/`): ツール一覧・詳細・サマリ・履歴スライダー・オフィス表示・アラートのフィルタ・エクスポート。
- **リポジトリ**(`hub/repo_sync.py`・`process_launcher.py`): `git fetch` で差分を検知(自動)、`git pull --ff-only` は**人が押したときだけ**、起動は固定のコマンドを新しい窓で。
- **入口の守り**(`hub/security.py`・`auth.py`・`audit.py`): Host の許可リスト、Origin の検査、API キー、`viewer` / `operator` / `admin`、監査ログ、`/admin` の分離。
- **`profiling_tool/`**(サブ機能): span・counter・event の計測 → Chrome Trace 形式 → 集計(p50・p95)。

## ドキュメント

| 読みたいもの | 場所 |
|---|---|
| 全体の地図 | [docs/index.md](docs/index.md) |
| **基礎から学ぶ**(講義 7 回) | [docs/lecture/](docs/lecture/index.md) |
| **保守・拡張する**(レシピ・テスト・トラブル・用語集) | [docs/learn/](docs/learn/index.md) |
| バージョンごとの記録(v1.1〜v2.7) | [docs/reference/changelog.md](docs/reference/changelog.md) |
| 設計書 | [ToolOrchestrationHub_DESIGN.md](ToolOrchestrationHub_DESIGN.md)・[UI 設計](ToolOrchestrationHub_UI_DESIGN.md) |
| 改善の設計と計画(2026-10) | [IMPROVEMENT_DESIGN_2026-10.md](IMPROVEMENT_DESIGN_2026-10.md)・[IMPROVEMENT_PLAN_2026-10.md](IMPROVEMENT_PLAN_2026-10.md) |
| セキュリティ点検 | [docs/SECURITY_REVIEW_2026-10.md](docs/SECURITY_REVIEW_2026-10.md) |

## セキュリティの要点

- Hub は**認証のないローカル API**として始まったので、まず **Host の許可リスト**(DNS rebinding)と、変更操作の **Origin の一致**(CSRF)を検査します。`127.0.0.1`・`localhost`・`::1` 以外の名前で開くときは、環境変数 `HUB_ALLOWED_HOSTS` に足してください(足さないと 403)。
- **複数人で使うときは `HUB_AUTH=required`**。ユーザーが 1 人もいなければ**起動しません**(fail-closed)。API キーは**ハッシュだけ**保存されます。
  ```bash
  uv run python -m hub.auth add --name alice --role admin   # キーは 1 度だけ表示される
  HUB_AUTH=required uv run hub
  ```
- `hub/repos.yaml` の `command` は**シェルとして実行**されます。書き換えられる人は、信頼できる人に限ってください。
- 秘密(Slack の Webhook URL・API キー)は**環境変数**で渡し、リポジトリに書かないでください。

## 限界(正直に)

- 受信時刻・スヌーズ・起動の記録は**メモリだけ**。再起動すると、受動のツールは**次の信号まで「未確認」**に戻ります(アラート履歴は残ります)。
- 履歴スライダーが再現できるのは**アラートの発生・解消だけ**です(死活監視の結果そのものは残りません)。
- 優先度(緊急・通常・情報不足)は**ルールベースの目安**で、較正された確率ではありません。通知・dedup には**つながっていません**。
- 実装していない追補(H3 構造図の自動生成・H5 TransferKit・Cloudflare ミラーなど)の理由は、[変更履歴](docs/reference/changelog.md)にあります。
