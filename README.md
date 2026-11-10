# ToolOrchestrationHub
今まで作ってきたシステム・機能に対しての中継兼モニタリングし、使用者にとって使いやすくするシステムの開発を目的としたリポジトリです

設計は [ToolOrchestrationHub_DESIGN.md](ToolOrchestrationHub_DESIGN.md) を参照してください。
ダッシュボードのビジュアルトークンは [ToolOrchestrationHub_UI_DESIGN.md](ToolOrchestrationHub_UI_DESIGN.md)(MongoDB風デザイントークン)を参照として使用しています。

## 構成

- `hub/registry.py` / `hub/registry.yaml` — Phase1: 12ツールの台帳(`ToolEntry`/`ToolRegistry`)。ホットリロード対応(後述)
- `hub/health/` — Phase2: `http_bridge_check` / `rpc_check` / `ci_pipeline_check` とそれらを束ねる `LivenessMonitor`
- `hub/alert_aggregator.py` — Phase3: `AlertRecord`の正規化・dedup(`upsert_alert`)・解消(`resolve_alert`)
- `hub/alert_store.py` — アラート履歴のSQLite永続化(`.hub_state/alerts.sqlite3`、`AlertAggregator`のオプション。1行 = 1つの発生→解消)
- `hub/notify.py` — 新規/解消アラートの通知チャネル(Windowsトースト、`HUB_SLACK_WEBHOOK_URL`を設定するとSlackも)
- `hub/tool_state.py` / `hub/overview.py` / `hub/alert_history.py` — ツールの状態判定・概況の組み立て・履歴スライダーの下ごしらえ(純関数。後述v2.5)
- `hub/alert_priority.py` / `hub/runbooks.py` / `hub/runbooks.yaml` / `hub/alert_view.py` — アラートの見る順番の補助と運用手順書(表示専用。後述v2.5)
- `hub/repo_sync.py` / `hub/repos.yaml` — 外部13リポジトリのgit差分検知・同期(後述)
- `hub/dashboard/` — Phase4: FastAPI製の読み取り専用ダッシュボード(ツール一覧と死活監視・アラート・リポジトリ・プロファイリング・各種アーティファクトをミラー表示)。画面は `templates/`(`partials/`に概況と共通部品)、`static/style.css`、`static/app.js`
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

## v2.5: 2026-10 UI/運用の改善(IMPROVEMENT_DESIGN / IMPROVEMENT_PLAN)

[IMPROVEMENT_DESIGN_2026-10.md](IMPROVEMENT_DESIGN_2026-10.md)(UI設計)と[IMPROVEMENT_PLAN_2026-10.md](IMPROVEMENT_PLAN_2026-10.md)(H1〜H8 / U1〜U5)に沿った改修。
骨格(配色・書体)は変えず、「決めていないこと」を無くす方向で直した。決めごとの一覧と、オフィスビューの配色・状態表現は
[ToolOrchestrationHub_UI_DESIGN.md](ToolOrchestrationHub_UI_DESIGN.md) の末尾に追記してある。

### 画面(U1〜U5 / H1 / H7 / 設計書 Phase 0〜4)

- **左=ツール一覧、中央=詳細、右=サマリ**の3カラムに再構成。一覧は「記号 + 名前 + 副題 + 状態 + 応答時間」、検索と並べ替え(名前順 / 状態順 / 応答が遅い順)、
  「警告のみ」の絞り込み、「一覧 / オフィス」の切り替え。選択・並べ替え・検索語・テーマは自動更新をまたいで保持される。
- **状態は色だけにしない**: 正常 ✓ / 警告 ▲ / 停止 ■ に加え、「未確認 ○」(信号がまだ無い)と「対象外 –」を足した(偽の「正常」を出さないため)。絵文字は廃止。
- **ツールの丸い記号と固定色**を12ツール全てに割り当て(`registry.yaml` の `symbol` / `color`)、一覧・オフィス・詳細・アラートで同じ表現を使う。
- **アラート履歴スライダー**: 過去の時刻を選ぶと、その時刻に未解消だったアラートからツールの状態を再現する(再生・「いま」で戻る)。
  再現できるのは**アラートの発生・解消だけ**(死活監視の結果そのものは履歴に残らない)。Hubが止まっていた期間は反映されず、画面にもその旨を常に出す。
- **オフィス表示**: 12ツールを机に置いたSVG。画面の色・記号と人物のポーズ(静か / 手を挙げる / うなだれる)で状態を表し、文字でも必ず併記する(v2.6で、動きは要対応の記号の脈動だけにした)。
- **アラート一覧**: 名前 + 灰色の副題(発生元・発生回数・見る順番の目安)の2段。未解消が上、解消済みは灰色で下。
- **遊びごころは場所を決めて入れる**: 空状態(アラートなし。v2.6で蜂の巣のASCIIに)、解消・新規の知らせ(v2.6でトーストに)、ブラウザでの404ページ。全て `prefers-reduced-motion` で止まる。
- ダーク(既定)/ライトのテーマ切替、狭い画面での1列化。見出し・列名は日本語に統一。同期(Sync)は確認ダイアログを挟み、操作は危険度の低い順に並べて離した。

### 台帳・運用(H4 / H6 / H8 / H2)

- **`isolation` / `owner_rules`(H4)**: `registry.yaml` に隔離方式(none / sandbox-bash / container / vm)とツール固有の制約を追加。
  **隔離方式は全て暫定の初期値**: 根拠(repos.yamlの docker compose 起動、CIランナーでの実行)がある項目だけ none 以外で、残りは「いまホストで直接動かしている」前提の none。
  方針として隔離したいツール(例: GUI操作を自動実行する VLMAutoReplayTool)は、`registry.yaml` を書き換えるだけで反映される。
- **運用手順書(H6)**: `hub/runbooks.yaml` に、アラート種別(死活監視 / プロファイリング / 視覚回帰 / アセット診断 / その他)ごとの「やること / やらないこと / 成果物」を固定。
  アラート行と詳細カードの「対応手順」から開く。初版の文面なので、運用に合わせて書き換える。ファイルが壊れていてもHubは手順なしで起動する。
- **導入前チェック(H8)**: [docs/PLUGIN_PRECHECK.md](docs/PLUGIN_PRECHECK.md)(出典 / SKILL.md / 権限の3点、1ページ)。
- **見る順番の補助(H2)**: 緊急 / 通常 / 情報不足のバッジと並び順。ルールベース(重大度・再発回数・停止かどうか・間接指標かどうか)で、
  数値は較正された確率ではなく「目安」と表示する。**通知・dedup・resolveには一切つなげていない**(補助が壊れても通知は従来どおり出る)。
  LLM等へ差し替える場合は `AlertPriorityClassifier` を満たす実装を `create_app(classifier=...)` に渡す。

### 見つけて直した不具合

- **再発したアラートの履歴が再起動で潰れていた**: 保存を `alert_id` だけの主キーにしていたため、解消後に同じアラートが再発すると過去の解消済み行が上書きされ、
  開始時刻も古いまま残った。1行 = 1ライフサイクル(`alert_id` + `first_seen_at`)にし、旧DBは初回起動時に自動で移行する(データは保持)。
- **30日経過した解消済みアラートのpruneで、同じ `alert_id` の「いま未解消の再発」まで消えていた**: レコード単位で削除するようにした。
- リポジトリ節の注意書き(`.data-warning`)のCSSが存在せず、スタイル無しで表示されていた。

### 実装していないもの(理由)

| ID | 内容 | 見送った理由 |
|---|---|---|
| H3 | 13リポジトリの構造図(CodeBoarding)を差分検知時に再生成 | CodeBoardingは未導入で、動かして `analysis.json` の形を確かめられない。さらにLLMを使うため、コスト上限とプロバイダの判断が先に要る(計画書も「上限を決める」としている)。自動実行はせず、決めてから着手する |
| H5 | 台帳に TransferKit を追加 | TransferKit は「(仮)構想」でまだ存在せず、healthの契約も無い。いま載せると死活監視が常時 down になり、誤アラートとSlack/トースト通知の元になる(台帳12件のテストも崩れる)。`registry.yaml` の末尾に、実装後に足すための雛形をコメントで残した |
| H2 の確率 | 「ラベル + 確率」 | ルールベースのため較正された確率を出せない。目安のscoreと理由を出す |
| H7 の紙吹雪・波紋 | 解消時の紙吹雪 / 新規時のタップ波紋 | v2.5では解消時の紙吹雪だけにしたが、v2.6で「1画面の動きは2種類まで」(設計書追補)に合わせ、どちらも入れずトーストで知らせる形にした |

### 設計書の検証チェックリストとの対応

- [x] スライダーで過去の時刻に動かしたとき、状態が当時のアラート履歴と一致する(`tests/test_overview.py` / `tests/test_dashboard_overview.py`。再現の限界は上記のとおり)
- [x] 色を消しても状態が分かる(全状態に文字ラベルと記号を定義。テストで検証)
- [x] ツールが増えても一覧が崩れない(20件で検証。一覧は中でスクロールし、オフィスはグリッドで自動配置)
- [x] 破壊的な操作(同期)に確認が入る(確認ダイアログを経てから初めてAPIを叩く)
- [x] 既存の通知(Windowsトースト / Slack)に影響がない(通知経路は変更なし。補助や手順書が壊れても通知されることをテストで確認)
- [x] 台帳に隔離方式が全ツール分入っている(値は暫定)
- [x] オフィスビューの状態が、死活監視の結果と一致する(同じ状態判定を一覧・オフィス・サマリで共有)
- [x] 分類補助を外しても、アラートが従来どおり通知される
- [ ] 構造図の再生成コストが上限を超えない — H3を見送ったため対象外

未検証: 実機のブラウザは Chrome のみ。Firefox / Safari / スマホ実機は未確認(狭い画面のレイアウトはCSSの設計と幅の強制縮小で確認)。

## v2.6: 設計書の追補(UIパーツ・動きの予算・キー操作)と、Hub自身のセキュリティ点検

[IMPROVEMENT_DESIGN_2026-10.md](IMPROVEMENT_DESIGN_2026-10.md) / [IMPROVEMENT_PLAN_2026-10.md](IMPROVEMENT_PLAN_2026-10.md) の更新分に沿った改修。
部品・動きの予算・キー操作の決めごとは [ToolOrchestrationHub_UI_DESIGN.md](ToolOrchestrationHub_UI_DESIGN.md) の末尾に追記した。

### セキュリティ(X2)— 別コミット `fix(security)`

Hubは認証のないローカルAPIで、ブラウザで別のサイトを開くだけで、そのページから**起動・git pull・フォルダ表示**のAPIを叩けた(再現済み)。
- **Hostの許可リスト**(DNS rebinding対策)と、**変更操作のOriginがHub自身と一致すること**(CSRF対策)を検査する(`hub/security.py`)。
  curlや各ツールからのheartbeat/アラート送信(Originなし)は影響しない。
- **`127.0.0.1` / `localhost` / `::1` 以外のホスト名・IPで開いている場合は、環境変数 `HUB_ALLOWED_HOSTS`(カンマ区切り)に足す**必要がある(足さないと403。メッセージに直し方を出す)。
  `uv run hub --host <非ループバック>` では警告を出す(認証が無いため)。
- あわせて、スヌーズの不正入力が500になる問題、アラート本文の長さ無制限、CSVエクスポートの数式インジェクション、プロファイリング画面のパストラバーサルを修正。
- 点検の記録(確定 / 要確認 / 却下)は [docs/SECURITY_REVIEW_2026-10.md](docs/SECURITY_REVIEW_2026-10.md)。**別エージェントによる独立検証はしていない**(再現テストで代えた)。

### 画面(UIパーツ6種 + 動き)

- **バッジ**(アラート件数 / タブ名「(5) …」)、**トグルスイッチ**(スヌーズ)、**ドロワー**(右から詳細。オフィスの机・狭い画面・直近のアラートの押下)、
  **トースト**(新規・解消。Windowsトースト / Slackと対応)、**ステップインジケーター**(「Start all」の進行)、**スケルトン**(起動直後の「確認中」)、
  **スタッガー**(初回表示、そのタブで1回だけ)。
- **動きは2種類まで**(出入り・脈動)。そのため、v2.5の紙吹雪・人物のタイプ/手を振る・空状態のチェックの描画は取り下げた(静止ポーズ + 脈動、トースト、蜂の巣に置き換え)。
  `@keyframes` は `hub-enter` / `hub-pulse`(と404の `wander`)だけで、テストで固定している。
- **キー操作**: `/` 検索、`a` 要対応のみ、`o` オフィス、`Esc` 閉じる。**前回の表示に戻す**(並べ替え・絞り込み・表示・テーマを、直前の変更の前へ。もう一度押すとやり直し)。
- **空状態の蜂の巣(ASCII)**: 各ツール=働き蜂、Hub=巣。画面外・裏のタブ・動きを減らす設定では止まる。既存の色だけを使う。

### 台帳(Z16 / X13)

- `description` / `concerns` / `todo` を詳細カードに出す(既存コメントの「暫定」「要判断」を項目化)。
- `depends_on` から、詳細カードの「台帳上の依存」と、右サマリの**「波及の見込み」**(停止しているツールを使っているツールの木)。
  台帳のコメントから読み取れる関係だけで**実測ではない**(画面にも明記)。存在しないID・自己参照・循環は読み込み時に弾く(ホットリロードでも)。

### 今回も実装していない追補

| 項目 | 見送った理由 |
|---|---|
| X3 graphify(H3の代替) | 未導入の外部ツール。13リポジトリでの試走(解析時間・出力の大きさ・言語対応の測定)が要り、外部コードの実行を承認なしに行わないため。台帳の13リポジトリのリンクは、試走して出力先が決まってから |
| C7 Cloudflare外部ミラー(Worker + D1) | Cloudflareアカウント・Access・D1の判断が先に要り、状態の要約を外部へ送る設計のため。ローカルの認証(Q1)の判断とセット |
| Z7 HTML-in-Canvas | 設計書が「製品画面には使わない」としている |
| Y2 #124 Wiggle | 動きの予算(2種類)のため。新規アラートはトーストで知らせる |

設計書・改善書の各追補の「提案(未実装)」の表記は、利用者の文書なので書き換えていない。

### 検証

- 全テスト通過(新規は、セキュリティ・台帳・UIパーツ・動きの予算)。実ブラウザ(Chrome)で、ドロワー・トースト・キー操作・表示の復元・起動手順・蜂の巣(画面外で停止)・スケルトン・バッジ・トグルスイッチ・ライト/ダークを確認。
- 起動手順の表示は、実際には何も起動しないよう `fetch` を差し替えて確認した。
- **未確認**: Firefox / Safari / スマホ実機。蜂の巣の描画コストの実測。`prefers-reduced-motion` は、CSSとJSの分岐をテストで確認したのみ(OS設定での実機確認はしていない)。

## v2.7: 認証・役割・監査ログ(2026-11-10。設計 QL6 / Z43)

Hub は**ツールの起動・`git pull`・registry の読み直し**までできる。既定は従来どおり**認証なし**(`HUB_AUTH=off`。Host / Origin のガードだけが効く)。複数人で使うときは `HUB_AUTH=required` にする。`required` で**ユーザーが 1 人もいなければ起動しない**(設定ミスで素通しにしない)。

| 役割 | できること |
|---|---|
| `viewer` | 見る(ツール一覧・アラート・概況・リポジトリの状態) |
| `operator` | viewer + アラートのスヌーズ・リポジトリの**起動**・Check all・フォルダを開く、各ツール(Profiling・VRQA・Asset Data Insight・CI)からの heartbeat とアラートの送信 |
| `admin` | operator + **registry.yaml の再読み込み**・**リポジトリの同期(git pull。他プロジェクトのファイルを書き換える)** |

```bash
uv run python -m hub.auth add --name alice --role admin       # API キーは 1 度だけ表示される
uv run python -m hub.auth add --name profiler --role operator  # 各ツールが送るためのキー(機械用)
uv run python -m hub.auth add --name bob --role viewer --email bob@example.com --no-key   # Cloudflare Access だけで使う人
uv run python -m hub.auth list
uv run python -m hub.auth remove --name alice                 # そのキーはすぐ使えなくなる
HUB_AUTH=required uv run hub
```

- **ブラウザ**: 未ログインで `/` を開くと `/login` に回る。API キーは HttpOnly・SameSite=Strict のクッキーになる。役割に足りない操作(スヌーズ・起動・Check all=operator、registry の再読み込み・同期=admin)は、ボタンが無効になり必要な権限が表示される。**表示だけで、権限の判断は常にサーバー側(403)**。
- **各ツールからの送信**: `X-API-Key: <operator のキー>` を付ける。`profiling_tool` の `ToolOrchestrationHubSink` は、引数 `api_key` か環境変数 `HUB_API_KEY` を送る。VRQA・Asset Data Insight・CI からの POST も同じ。
- **Cloudflare Access**: `HUB_CF_ACCESS_TEAM_DOMAIN`・`HUB_CF_ACCESS_AUD` を設定すると `Cf-Access-Jwt-Assertion` の JWT も使える(RS256 だけ・署名/発行者/宛先/期限を必須。**ユーザーは自動作成しない**: `--email` で登録していない人は 403)。
- **ユーザーの保存先**: `~/.tool_orchestration_hub/auth_users.json`(`HUB_AUTH_FILE` で変更。キーは**ハッシュだけ**)。
- **監査ログ**(`HUB_AUDIT_LOG`。既定 `~/.tool_orchestration_hub/audit.jsonl`・JSON Lines): **変更系(POST など)**・**拒否(401・403)**・ログイン・ログアウトを、時刻・名前・役割・方式・パス・結果・IP で残す。**本文・キー・クッキー・クエリは記録しない**。読み取りは記録しない。admin だけ `GET /api/auth/audit?limit=100`。
- 依存: `pyjwt[crypto]`。
