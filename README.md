# ToolOrchestrationHub
今まで作ってきたシステム・機能に対しての中継兼モニタリングし、使用者にとって使いやすくするシステムの開発を目的としたリポジトリです

設計は [ToolOrchestrationHub_DESIGN.md](ToolOrchestrationHub_DESIGN.md) を参照してください。
ダッシュボードのビジュアルトークンは [ToolOrchestrationHub_UI_DESIGN.md](ToolOrchestrationHub_UI_DESIGN.md)(MongoDB風デザイントークン)を参照として使用しています。

## 構成

- `hub/registry.py` / `hub/registry.yaml` — Phase1: 12ツールの台帳(`ToolEntry`/`ToolRegistry`)。ホットリロード対応(後述)
- `hub/health/` — Phase2: `http_bridge_check` / `rpc_check` / `ci_pipeline_check` とそれらを束ねる `LivenessMonitor`
- `hub/alert_aggregator.py` — Phase3: `AlertRecord`の正規化・dedup(`upsert_alert`)・解消(`resolve_alert`)
- `hub/alert_store.py` — アラート履歴のSQLite永続化(`.hub_state/alerts.sqlite3`、`AlertAggregator`のオプション)
- `hub/notify.py` — 新規/解消アラートのローカル通知チャネル(v1: Windowsトースト通知のみ)
- `hub/repo_sync.py` / `hub/repos.yaml` — 外部13リポジトリのgit差分検知・同期(後述)
- `hub/dashboard/` — Phase4: FastAPI製の読み取り専用ダッシュボード(Registry状態・Alert一覧・各種アーティファクト・Profiling・Repositoriesをミラー表示)
- `profiling_tool/` — ToolOrchestrationHubの**サブ機能**として統合された計測基盤(後述)

## セットアップ・実行

```bash
uv sync --extra dev
uv run pytest -q
uv run hub  # http://127.0.0.1:8790 でダッシュボードを起動
```

`hub/registry.yaml`内の`poll_interval_s`・`check_params`(ハートビート/CI間隔など)は暫定値です。各ツール側の実装が固まり次第、このファイルのみを更新すれば追従できます(Hub自身の内部アーキテクチャは変更不要)。

## v1.1で追加した機能

DESIGN.mdのPhase0-4確定後、実際に使う上でのギャップを埋めるために追加した拡張。Hub自身の内部アーキテクチャ(Registry/Relay/AlertAggregatorの3層構成)は変更していない。

- **通知**: 新規open/resolve確定のタイミングでWindowsトースト通知を送出する(既定でseverity `warn`以上)。非Windows環境やwinotify未インストール時は自動でno-opになる。
- **registry.yamlのホットリロード**: 5秒間隔でmtimeを監視し、変更があれば自動反映する。ダッシュボードの「Reload registry.yaml」ボタン、または`POST /api/registry/reload`で即時トリガも可能
- **アラート履歴の永続化**: `.hub_state/alerts.sqlite3`にAlertRecordを保存し、Hub再起動後も履歴を保持する。resolved後30日経過したレコードは1時間毎に自動prune
- **ダッシュボードの自動更新**: 既定で20秒毎にmeta refreshする(`/?refresh=0`で停止、`/?refresh=N`で間隔変更)
- **liveness信号の受信エンドポイント**: observed_only/cli_batch系ツール(`category`に関わらずrpc_check/ci_pipeline_check対象)からの受動的な信号受信口。Hub側から能動的に接続しにいく設計ではないため、各ツール側からこのエンドポイントを叩いてもらう必要がある

  ```bash
  # rpc_check対象(例: sound_middleware)からのハートビート
  curl -X POST http://127.0.0.1:8790/api/heartbeat/sound_middleware

  # ci_pipeline_check対象(例: research_collector)からのCI成功通知
  curl -X POST http://127.0.0.1:8790/api/ci-success/research_collector
  ```

  対象tool_idの`health_check`と一致しない場合は400、未登録のtool_idは404を返す。

## v1.2で追加した機能

DESIGN.md Phase3は「Profiling Tool(主経路)/Visual Regression QA Tool/Asset Data Insight Suite/
Hub自身のヘルスチェックの4ソースをAlertRecordへ正規化する」としていましたが、実際に配線されて
いたのはHub自身のヘルスチェック由来のみで、他3ソース用の`normalize_from_*`関数は定義済みのまま
呼び出し口がありませんでした。受信エンドポイントを追加し、4ソース全てが実際にAlertAggregatorへ
到達するようにしました。

```bash
# Profiling Tool(主経路)からの生アラート
curl -X POST http://127.0.0.1:8790/api/alerts/profiling-tool \
  -H "Content-Type: application/json" \
  -d '{"signature": "gpu_frame_budget_exceeded", "severity": "critical", "message": "frame budget exceeded"}'

# Visual Regression QA Toolからの1件分の評価結果
curl -X POST http://127.0.0.1:8790/api/alerts/visual-regression-qa \
  -H "Content-Type: application/json" \
  -d '{"case_id": "battle_hud_overlay", "passed": false, "message": "pixel diff 3.4%"}'

# Asset Data Insight Suiteのreport_manifest.json 1エントリ分
curl -X POST http://127.0.0.1:8790/api/alerts/asset-data-insight \
  -H "Content-Type: application/json" \
  -d '{"asset_id": "characters/hero_base_mesh", "severity": "warn", "message": "polycount budget exceeded"}'
```

`severity: "info"`(またはVRQAの`passed: true`)を送ると、同一シグネチャのopenアラートを
resolveする信号として扱います(Research-Collectorの自動closeと同型のライフサイクル)。

## v2.0: ProfilingToolをサブ機能として統合

「ToolOrchestrationHubが主軸、ProfilingToolはサブ機能」という方針のもと、別リポジトリだった
ProfilingTool(ProfilingTool_DESIGN.mdに基づく計測基盤: span/counter/event/GpuTimestampQueryの
コアSDK + VLM/Sound/GI/VideoFactory向け4アダプタ + 集計 + アラート)を`profiling_tool/`
サブパッケージとして本リポジトリに統合しました。

- 日常利用はHub本体のダッシュボード(`uv run hub`、ポート8790)の**Profiling**セクションが主。
  同一プロセス内で`profiling_tool.dashboard.data_sources`を直接呼び出し、最新runのlatency/usage
  サマリを表示します(profiling_tool側の不具合でHub本体が落ちないよう例外は握りつぶします)
- トレースを詳細に掘り下げたい場合は`uv run profiling-dashboard`(ポート8791)のスタンドアロン
  版も引き続き使えます(バックエンド表示・サービス連携状況・実データサンプル等)
- デモ用トレースの生成: `uv run python profiling_tool/scripts/generate_demo_traces.py`
- 実装時に設計書側の欠陥(sound_adapterのダウンサンプル判定がunderrun検知を巻き込んでいた)と、
  Jinja2の`tojson`が非ASCII文字を`\uXXXX`エスケープする不具合(バックエンド・データ表示パネルの
  文字化けにつながる)を発見し修正しています。

## v2.1: 13リポジトリのgit差分反映・同期

ユーザー追加要件「gitの最新の状態を反映・差分ダウンロードという形で管理」に対応しました。
`hub/repos.yaml`に登録した13個の外部リポジトリ(AssetDataInsightSuite, VLMAutoReplayTool,
WeatherGeoBridge, The-Algorithm-Illustrated, ColorEncyclopedia, RAGReel,
VisualRegressionQATool, MagicCircleGenerator, FlowchartVisualizerExtension,
LoreDesktopAndWebSystem, LearningQuickDraw, LearningFluidEngine, CADGPUInferenceModeling)
に対して、Hubのダッシュボードの**Repositories**セクションが状態を表示します。

安全性の方針を2段階に分けています:

- **自動実行するのは`git fetch`(差分検知)のみ**。ワーキングツリーは一切変更しません。
  既定30分間隔でバックグラウンド実行し、「Check all」ボタンで即時トリガもできます
- **実際の取り込み(`git pull --ff-only`)は人間がダッシュボードの「Sync」ボタンを押した
  ときのみ**実行します。Hubが無人で他プロジェクトのファイルを書き換えることはありません。
  ローカルに未コミットの変更がある場合(dirty)や、履歴が分岐していてfast-forwardできない
  場合は同期を拒否します(他プロジェクトの作業を破壊しない)

```bash
# 全リポジトリの差分検知を即時実行(git fetchのみ)
curl -X POST http://127.0.0.1:8790/api/repos/check

# 特定リポジトリの差分を取り込む(git pull --ff-only、dirty/非ff-onlyなら409)
curl -X POST http://127.0.0.1:8790/api/repos/asset_data_insight_suite/sync
```

## v2.2: 13リポジトリを個別に起動

ユーザー追加要件「個別に起動できるようにしたい」に対応しました。13リポジトリは
Next.js/Vite/Python/Docker Compose/C++ビルド等スタックが大きく異なるため、各リポジトリの
README/package.json/pyproject.tomlを調査し、`hub/repos.yaml`の`launch:`に実際の起動コマンドを
暫定設定しています。

- **単一コマンドで起動できるもの**(AssetDataInsightSuite, VLMAutoReplayTool,
  The-Algorithm-Illustrated, ColorEncyclopedia, MagicCircleGenerator, CADGPUInferenceModeling):
  Startボタン1つ
- **複数プロセスの起動が要るもの**(WeatherGeoBridge: Worker/Web/MCP、
  VisualRegressionQATool: Backend/Frontend、LoreDesktopAndWebSystem: Docker Compose):
  対象ごとにStartボタンを分けている
- **明確な起動コマンドが無いもの**(RAGReel: C++ビルド必須、FlowchartVisualizerExtension:
  IDE拡張、LearningQuickDraw/LearningFluidEngine: スクリプト集): Startボタンは出さず、
  「Open folder」のみ提示する

Hub(`hub/process_launcher.py`)は「起動ボタンを押したら新しいコンソールウィンドウで
そのコマンドを実行する」という、人間が手動でターミナルを開く操作を代行するだけに留めます。
起動後のプロセス管理(停止・ログ監視・再起動)は行わず、開いたコンソール自体をユーザーが
直接操作する前提です。実行するコマンドはHTTPリクエストからではなく`hub/repos.yaml`の
固定値のみを使うため、任意のシェルコマンドを注入できる経路はありません。

```bash
# MagicCircleGeneratorのdevサーバーを起動(hub/repos.yamlのlaunch[0]に対応)
curl -X POST http://127.0.0.1:8790/api/repos/magic_circle_generator/launch/0

# 起動コマンドの無いリポジトリでもフォルダは開ける
curl -X POST http://127.0.0.1:8790/api/repos/rag_reel/open-folder
```

**既知の制約**: 「running/stopped」バッジは`launch.url`への疎通確認のみで判定しており、
プロセスの識別はしていません。実機確認で、MagicCircleGeneratorのdevサーバー(Vite既定ポート
5173)を起動した状態でVisualRegressionQATool(Frontendも同じ5173がデフォルト)を見ると、
実際には起動していないのに「running」と誤表示されることを確認しています。複数リポジトリが
同じ既定ポートを使う組み合わせでは、この誤検知が起こり得ることをダッシュボード上にも注記して
います。

## v2.3で追加した機能

リファクタリング・不備再確認の一環で見つけた設計原則との不整合を修正した上で、
使いやすさ向上のため以下5点を追加した。

- **起動疎通確認/13リポジトリの差分検知チェックのバックグラウンドキャッシュ化**:
  v2.2時点では`launch.url`への疎通確認をダッシュボード描画のたび(既定20秒毎の自動更新含む)に
  実行しており、他機能で徹底している「バックグラウンドでキャッシュし、リクエスト経路は読むだけ」
  という非hot-path原則から外れていた。専用バックグラウンドループ(10秒間隔)へ切り出し、
  併せて`RepoSyncManager.check_all()`(13リポジトリのgit fetch)も、repo_idごとに独立した
  ロックを持つため安全な範囲で直列実行から並行実行に変更した。
- **アラートのフィルタ/検索**: Open & Resolved Alertsセクションに、ステータス・severity・
  発生元・メッセージ検索の絞り込みバーを追加した(クライアント側フィルタのみで、Hub側の
  集計・再計算は一切行わない)。
- **アラート履歴のエクスポート(JSON/CSV)**: `/api/alerts`が返す正データをブラウザ内で
  JSON/CSVに変換してダウンロードするボタンを追加した。
- **Slack Webhook通知**: `hub/notify.py`にSlackWebhookSink/CompositeSinkを追加した。
  Windowsトースト通知はPCの前にいないと気づけないため、環境変数`HUB_SLACK_WEBHOOK_URL`に
  Slack Incoming Webhook URLを設定すると、既存のトースト通知と併用してSlackへも通知される
  (どちらか一方の配信失敗が他方に波及しない設計)。
- **起動済み・起動失敗の軽量な記録**: 起動ボタンを押した「時刻・OSユーザー名・成否」を
  Hubプロセスのメモリ上に記録し、ダッシュボードの各Startボタン下に表示する。起動後の
  プロセスライフサイクル管理(停止・再起動等)には踏み込まない設計原則は維持しており、
  あくまで「誰が・いつ押したか」の事故防止用の手掛かりに留める(Hub再起動で消える)。
- **起動コマンドの健全性チェック**: `npm`/`uv`/`docker`等、`launch.command`の実行に必要な
  実行ファイルがPATH上に存在するかを`shutil.which`で事前確認する。無い場合はStartボタンの
  下に警告を表示し、実際に起動ボタンを押した場合もPopen由来の分かりにくいエラーではなく
  「コマンド '...' がPATH上に見つかりません」という具体的なメッセージを返す。

```bash
# Slack通知を有効化する場合(Hub起動前に設定)
export HUB_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxx/yyy/zzz"
uv run hub
```

## v2.4で追加した機能

再監査で見つけた不備の修正1点と、使いやすさ向上のため以下4点を追加した。

- **(不備修正)`launch.url`が不正な値の場合に他リポジトリの疎通確認まで巻き込んで
  止まる不整合**: `urlopen()`はスキーム無し等の不正なurlに対し`URLError`/`OSError`ではなく
  `ValueError`を送出するため、`check_target_reachable`がそれを捕捉できていなかった。
  v2.3で追加したバックグラウンド更新ループと組み合わさると、1リポジトリの設定ミスが
  同一サイクル内の他リポジトリの更新まで止めてしまう構造になっていたため、例外捕捉の
  拡張とリポジトリ単位の例外隔離(`asyncio.gather`)で修正した。
- **複数プロセス構成リポジトリの一括起動**: WeatherGeoBridge(Worker/Web/MCP)や
  VisualRegressionQATool(Backend/Frontend)のように複数のStartボタンが必要な対象に、
  「Start all (N)」ボタンを追加した。既存の単体起動エンドポイントを順番に呼ぶだけで、
  Hub側に新しい一括起動APIは追加していない。
- **アラートのスヌーズ/ミュート**: 同一アラートが短時間でopen/resolveを繰り返す
  (フラッピング)場合に、通知(Windowsトースト/Slack)だけを一時的に抑制できる
  「Snooze 1h」ボタンを追加した。アラート自体のopen/resolved状態やdedupには一切
  影響せず、スヌーズ状態もメモリ上にのみ持つ(Hub再起動で解除される)。
- **Registry & Liveness / Repositoriesテーブルの横断検索**: v2.3でAlertセクションに
  追加したフィルタと同じ方針(クライアント側のみ、Hubは再計算しない)で、ツール名・ID・
  リポジトリ名・URLによる検索を追加した。
- **プロファイリングのrun間比較**: Profilingセクションの最新runを、同一target内で
  その直前のrunと比較し、span latency(p50)とcounter(avg)の変化量・変化率を表示する。
  比較ロジックは`profiling_tool/aggregate.py`の純関数(`diff_span_summary`/
  `diff_counter_summary`)として実装し、Hub側では再計算しない。過去runが無いtargetは
  「比較なし」とそのまま表示する。
