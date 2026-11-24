# 2. コードの読み方(どこに何があるか)

## ファイルの地図(`hub/`)

| ファイル | 行数の目安 | 役割 | 読む順 |
|---|---|---|---|
| `registry.py` + `registry.yaml` | 260 | 台帳(`ToolEntry`・`ToolRegistry`・検証・ホットリロード) | ① |
| `health/base.py`・`rpc_check.py`・`ci_pipeline_check.py`・`http_bridge_check.py` | 10〜30 | 3 種の死活監視と結果の型 | ② |
| `health/runner.py` | 150 | `LivenessMonitor`(受信時刻の保持・カテゴリごとの振り分け・間引き) | ③ |
| `alert_aggregator.py` | 270 | アラートの型・正規化・dedup・解消・スヌーズ | ④ |
| `alert_store.py` | 135 | SQLite への保存・読み戻し・旧スキーマの移行 | ⑤ |
| `tool_state.py` | 90 | 状態(正常・警告・停止・未確認・対象外)を決める純関数 | ⑥ |
| `overview.py` | 280 | 画面用の概況(一覧・サマリ・波及の木)の組み立て。履歴の再現も | ⑦ |
| `dashboard/app.py` | 820 | FastAPI アプリの本体(`create_app`・5 ループ・全ルート) | ⑧ |
| `security.py` | 110 | Host の許可リスト・Origin の検査(ミドルウェア) | ⑨ |
| `auth.py`・`auth_routes.py` | 350・110 | API キー・役割・Cloudflare Access・ログイン画面 | ⑩ |
| `audit.py` | 115 | 監査ログ(JSON Lines)のミドルウェアと読み出し | ⑩ |
| `notify.py` | 190 | 通知先(Windows トースト・Slack)と、まとめ役 | |
| `repo_sync.py`・`repos.yaml` | 299 | 15 リポジトリの `git fetch` / `pull --ff-only`、起動コマンドの定義 | |
| `process_launcher.py` | 140 | 起動(新しいコンソール窓)・フォルダを開く・疎通確認 | |
| `alert_priority.py`・`alert_view.py`・`alert_history.py` | 100・75・75 | 見る順番の補助・画面用の飾り・履歴スライダーの下ごしらえ | |
| `runbooks.py`・`runbooks.yaml` | 115 | アラート種別ごとの運用手順書 | |
| `tool_identity.py` | 80 | ツールの記号と色(台帳に無ければ名前・ID から自動生成) | |
| `main.py` | 40 | `hub` コマンドの入口(`--host`・`--port`) | |

`hub/dashboard/` の中身: `templates/`(`index.html`・`admin.html`・`404.html`・`partials/`)・`static/`(`app.js`・`auth.js`・`style.css`・`parts.css`)・`admin/admin.js`(admin だけに配る)。

## 読み方の順番

**① 台帳 → ② 死活監視 → ③ ランナー → ④ アラート → ⑥ 状態**(ここまでが核。`hub/` の小さい純粋なモジュール)。次に**⑧ app.py** で、それらが**どう配線されているか**を見ると、全体がつながります。⑨⑩は、入口の守り(講義第 5 回)。

## `dashboard/app.py` の構造

800 行を超えますが、構造は単純です。

1. **定数**(間隔・保持期間・上限): `POLL_LOOP_INTERVAL_S = 5`・`ALERT_RETENTION = 30 日`・`MAX_ALERT_MESSAGE_LEN = 1000`・`MAX_SNOOZE_MINUTES`(7 日)。
2. **ヘルパー**(`_ARTIFACT_SPECS` など): プロファイリング・VRQA・Asset Data Insight の**成果物**(`data/`)を、ダッシュボードに映す。
3. **`create_app(...)`** — 1 つの大きな関数で、部品を作り、ループを定義し、ルートを登録する(**クロージャ**: 中の関数が、外の `registry`・`monitor`・`aggregator` を直接使う)。
   - 引数 `registry_path`・`db_path`・`repos_path`・`runbooks_path`・`classifier`・`allowed_hosts` は**テストで差し替えるため**にある。
   - 順序: 台帳 → `LivenessMonitor` → 通知先 → `SqliteAlertStore` → `AlertAggregator`(通知・保存を渡す)→ 手順書・分類器 → ループ → `_lifespan` → `FastAPI(...)` → ミドルウェア(Host・Origin、監査)→ ルート。
4. **モジュール末尾の `app = create_app()`**: `uvicorn hub.dashboard.app:app` が使う。

> **気をつけること(既知の制約)**: `app = create_app()` が**モジュールを import しただけで実行される**ため、`import hub.dashboard.app` は、`.hub_state/alerts.sqlite3` の作成や `repos.yaml` の読み込みという**副作用**を持ちます(テストは、`create_app(...)` に一時フォルダを渡して避けている)。この文書の実行例も、import で `.hub_state/`(`.gitignore` 済み)を作ります。

## `profiling_tool/`(サブ機能)

| 場所 | 役割 |
|---|---|
| `core/span.py` | `SpanRecorder`・`SpanGuard`(`with` で入れ子の区間を計測) |
| `core/counter.py`・`event.py`・`gpu_timestamp_query.py` | 数値・出来事・GPU の区間 |
| `core/chrome_trace.py`・`recorder.py` | Chrome Trace Event 形式への変換、`TraceWriter`(runId ごとの追記) |
| `adapters/` | VLM・Sound・GI・VideoFactory 向けの 4 つの接続口 |
| `aggregate.py` | p50・p95、カウンタの要約、run 間の差(純関数) |
| `alerting/threshold_alert.py` | しきい値で `AlertSink` に出す。`ToolOrchestrationHubSink` が Hub の `POST /api/alerts/profiling-tool` へ送る |
| `dashboard/` | スタンドアロン版(`uv run profiling-dashboard`・ポート 8791)と、Hub が呼ぶ `data_sources` |

Hub 本体は、`profiling_tool` の**内部実装に踏み込まず**、`data_sources` と `aggregate` の**公開の関数だけ**を呼びます(`profiling_tool` の不具合で Hub が落ちないよう、例外は握りつぶす)。

## データのファイル(`data/`・設定)

| 場所 | 中身 |
|---|---|
| `data/asset_data_insight/`・`profiling_tool/`・`visual_regression_qa/` | 画面に映す**サンプルの成果物**(コミット対象) |
| `hub/registry.yaml`・`runbooks.yaml`・`repos.yaml` | 編集して使う設定データ |
| `.hub_state/` | 実行時の状態(アラートの SQLite)。`.gitignore` |
| `.profiling_state/` | 計測のトレース。`.gitignore` |

## 設計書との対応

| 文書 | 何が書いてあるか |
|---|---|
| `ToolOrchestrationHub_DESIGN.md` | Phase 0〜4 の設計(台帳・死活監視・アラート・ダッシュボード) |
| `ToolOrchestrationHub_UI_DESIGN.md` | 画面のデザイントークンと決めごと |
| `IMPROVEMENT_DESIGN_2026-10.md`・`IMPROVEMENT_PLAN_2026-10.md` | 2026-10 の UI・運用の改善(H1〜H8・U1〜U5) |
| `docs/SECURITY_REVIEW_2026-10.md` | セキュリティ点検の記録(確定・要確認・却下) |
| `docs/PLUGIN_PRECHECK.md` | プラグイン導入前の 3 点チェック |
| [変更履歴と詳細](../reference/changelog.md) | v1.1〜v2.7 の経緯 |
