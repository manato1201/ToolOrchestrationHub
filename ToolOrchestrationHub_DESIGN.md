# ToolOrchestrationHub 設計書

**設計指標: 全ツールを繋ぐ中継基盤+異常検知アラート(監視のみ、各ツールの権限は奪わない)**
作成日: 2026-08-11 / 想定規模: 中〜大規模(レジストリ+ヘルスチェック+アラート集約+ダッシュボード、他12件の統合が前提)

本文書はワークスペース内13文書(改善計画4件+新規設計8件)のうち最後に書かれるcapstone文書である。他12文書は個別ツールの内部改善・新規設計を扱うが、本文書はそれらを横断して「ツール間の連携を中継し、異常を検知して通知する」薄いハブ層のみを設計対象とする。各ツールのコア機能・データプレーンには一切踏み込まない。

---

## Phase 0: コンセプト・要件定義

### 目的

`Desktop\GameDevelopment`配下には独立したツール・パイプラインが多数存在し、それぞれが個別にHTTPブリッジ・RPC・CI/CDを持つ。しかし「どのツールが今生きているか」「どこかで異常が起きたら誰が気づくか」を横断的に把握する手段がない。ToolOrchestrationHub(以下Hub)は、既存の連携パターンを**再実装せず**、(1) ツールの存在とtransportを登録する**Registry**、(2) 各ツールの生存を監視する**Liveness監視**、(3) 複数ソースからのアラートを正規化・重複排除する**AlertAggregator**、(4) それらを読み取り専用で可視化する**ダッシュボード**、の4層のみを提供する。

### 統合対象棚卸し表

このバッチの他12文書それぞれが持つ連携面(実装済み/計画済み)を棚卸しし、Hub側がどう連携するかを対応させる。この表がHub設計全体の一次入力であり、以降の全フェーズはこの表の記述に従う。

| # | 対象 | 既存/計画済み連携パターン | Hub側の連携方法 |
|---|---|---|---|
| 1 | LoreDesktopAndWebSystem | RPC+プロセス分離(改善計画書Phase4: UIシェル/`loreforge-worker`間`QLocalSocket`)、`:8766`ブリッジ経由のRAGアシスタント(Phase7、`X-API-Key`ヘッダ認証を再利用) | Registryのtransport型2種(`rpc`/`http_bridge`)のプロトタイプとして採用する。Hub自体はこのRPCチャネルに介入しない |
| 2 | The-Algorithm-Illustrated | 静的サイト、CI/CDあり(ビルド成功/失敗のみ) | ヘルスチェックはCI最終成功run経過時間のみ。`ci_pipeline_check`の対象 |
| 3 | Research-Collector | GitHub Actions cron、Issue自動作成(`auth-expired`/`refresh-soon`ラベル)/`refresh_auth.ps1`による自動クローズの実装済みパターン | Hub新設のdedup/resolveアラートライフサイクルの直接の前例。新規モデルを発明せずこのIssueライフサイクルを踏襲する |
| 4 | DevelopmentRAGEnvironment | `rag_local_bridge.py`の`:8766`ブリッジ、`/health`エンドポイント(未認証、`/admin`/`/ui`と並び認証除外) | `http_bridge_check`の直接のヘルスチェック対象。既存`/health`をそのまま再利用し新規エンドポイントは要求しない |
| 5 | LearningQt(VideoFactory) | Orchestrator/JobPipeline/ResourceBudgetManager(GPU厳密直列、排他制御あり) | Hubは観察のみで介入しない対象として明記。GPU排他のクリティカルパスにHubの監視トラフィックを一切入れない |
| 6 | AssetDataInsightSuite | CI定期実行、`report_manifest.json`、Issue通知 | Hubの主要な購読元の一つ。`report_manifest.json`を読み取り専用でダッシュボードに表示する |
| 7 | SoundMiddleware | 独自RPC(realtime)、ハートビート/再接続契約(Phase3で確定) | 監視/管理チャネルのみHubに相乗りさせる。realtimeのhot pathにはHubを絶対に入れない |
| 8 | VisualRegressionQATool | 差し替え可能アラートsink(Phase5で確定) | Hubを数あるsink実装の1つとして登録する。既存sinkインターフェースを変更しない |
| 9 | ColorEncyclopedia | 静的サイト、実行時連携なし | 対象外と明示する。Registryにも登録しない |
| 10 | VLMAutoReplayTool | StepLog、`:8766`ブリッジ利用(DevelopmentRAGEnvironment経由) | Profiling Tool経由で間接的にメトリクス取得する。Hubから直接フックしない |
| 11 | DynamicGIMiddleware | フレーム毎GPUコスト計測対象 | Profiling Tool経由で間接的にメトリクス取得する。フレームクリティカルパスには入らない |
| 12 | ProfilingTool | メトリクス/アラート発行契約(Phase4で確定済み) | Hubの主要な購読元。AlertAggregatorの主経路として位置づける |

### アーキテクチャ全体像

サービスメッシュ(Istio/Linkerd等のサイドカー方式)やAPIゲートウェイは、この規模(12ツール、単一デスクトップ環境)には重量級すぎるため採用しない。あくまで一般的な前例として引用するに留め、本設計は**軽量なサービスレジストリ+リレー**のみを実装する。

```
                    +---------------------+
                    |   Hub Dashboard     |  読み取り専用
                    |  (Phase 4)          |
                    +----------+----------+
                               |
                    +----------v----------+
                    |  AlertAggregator     |  正規化・dedup・resolve
                    |  (Phase 3)           |
                    +----------+----------+
                               |
        +----------------------+----------------------+
        |                      |                       |
+-------v-------+     +--------v--------+     +--------v--------+
| ToolRegistry   |     | Liveness監視     |     | 各ツールの     |
| (Phase 1)      |<----| (Phase 2)        |     | 既存アラート発行 |
| registry.yaml  |     | http_bridge_check|     | (Profiling Tool |
+----------------+     | rpc_check        |     |  / VRQA / ADIS) |
                        | ci_pipeline_check|     +-----------------+
                        +------------------+

   Relay(監視・制御トラフィックのみ) ── データプレーンには入らない
```

`ToolRegistry`(存在/transport/ヘルスチェック契約の台帳)、`Relay`(監視・制御トラフィックのみを中継し、各ツールのデータプレーンには一切入らない)、`AlertAggregator`(複数ソースのアラートを正規化・集約)の3コンポーネントで構成する。

### 要求機能

1. 12ツールを`ToolEntry`として一元登録し、`transport`種別を明示する
2. 各ツールのtransportに応じたヘルスチェックを定期実行し、liveness状態を保持する
3. Profiling Tool / Visual Regression QA Tool / Asset Data Insight Suite / Hub自身のヘルスチェックから届くアラートを`AlertRecord`へ正規化し、同一障害の重複を1件に集約する
4. 各ツールが自律的に生成するアーティファクト(Perfettoトレース、`report_manifest.json`、`EvaluationResult`履歴)を読み取り専用で1画面に集約表示する

### 非機能要件

- **Hub自体がどのツールの単一障害点にもならないこと。** 各ツールはHub停止時も自身のコア機能を単独で維持できる。Hubが落ちても、LoreDesktopAndWebSystemのRPC編集もSound Middlewareのリアルタイム再生もLearningQtのGPUジョブもHubの生死に関わらず動き続ける
- ヘルスチェックのポーリング頻度は各ツール自身のヘルスチェック間隔より高頻度にしない(相手側の負荷を増やさない)
- Registryのエントリ追加・削除はHubの再起動なしで反映できることが望ましいが、v1では静的ファイルの再読込で足りる

### 前提・制約

- Hubはこのワークスペース内のツールを対象とし、外部SaaS的な汎用サービスメッシュを目指さない
- 各ツールとの連携マッピング(統合対象棚卸し表)は、参照元の12文書が未確定・実装途上の箇所を含むため、**すべて「暫定」として扱う**。Hub自身の内部アーキテクチャ(Registry/Relay/AlertAggregatorの3層構成)はここで確定的にコミットするが、個々のtransport・エンドポイント名は各文書の実装が進むにつれて更新される前提とする

### アンチパターン(全フェーズ共通)

- Sound MiddlewareのRPCがリアルタイム制約(ハートビート/再接続契約、Phase3)を持つことから得られる教訓として、**Hubを遅延クリティカルパスに絶対に入れない**。監視トラフィックとデータトラフィックを物理的に分離する
- 各ツールが既に持つtransport(RPC、HTTPブリッジ、CI cron)を再実装しない。差異は**アダプタ**(`health/*_check.py`)で吸収し、対象ツール側のコードは変更しない
- Hubのダッシュボードを二次的な正となる状態源(source of truth)にしない。各ツールの実データが常に正であり、ダッシュボードはそのスナップショットの読み取り専用ミラーに過ぎない
- LearningQtのResourceBudgetManagerが握るGPU排他制御にHubが介入しない。Hubは観測するだけで、ジョブのスケジューリングやリソース割当には一切関与しない

**検証チェックリスト:**
- [ ] 統合対象棚卸し表の12行全てに`transport`種別と暫定/確定の別が明記されている
- [ ] アーキテクチャ図のRelayが「監視・制御トラフィックのみ」であることが要求機能・非機能要件の記述と矛盾しない
- [ ] 非機能要件の「単一障害点にならない」が各対象ツールについて個別に検証可能な形で書かれている
- [ ] アンチパターン4件が全てPhase1以降の実装記述と整合している

---

## Phase 1: ツールレジストリ(最優先・基盤)

**目的:** 12ツールの存在・transport・ヘルスチェック契約を単一の台帳として持つ。後続の全フェーズ(ヘルスチェック、アラート集約、ダッシュボード)はこのレジストリを起点にする。

**実装内容:**

1. `hub/ToolRegistry`のエントリ型を定義する。`transport`の列挙値は、この統合対象棚卸し表で実際に登場した4パターンをそのまま反映したものであり、新規に発明した抽象ではない:

```python
# hub/registry.py
from dataclasses import dataclass
from enum import Enum

class TransportKind(str, Enum):
    HTTP_BRIDGE = "http_bridge"   # 例: DevelopmentRAGEnvironmentの:8766ブリッジ
    RPC = "rpc"                   # 例: LoreDesktopAndWebSystemのQLocalSocket、SoundMiddlewareの独自RPC
    CI_BATCH = "cli_batch"        # 例: Research-Collectorのcron実行、AssetDataInsightSuiteのCI定期実行
    STATIC_SITE = "static_site"   # 例: The-Algorithm-Illustrated、ColorEncyclopedia(監視対象外)

@dataclass
class ToolEntry:
    tool_id: str
    display_name: str
    transport: TransportKind
    endpoint: str | None        # http_bridge/rpcのみ必須。cli_batch/static_siteはNone
    health_check: str           # 対応するhealth/*_check.pyの関数名
    category: str               # "monitored" | "observed_only" | "excluded"
```

2. v1は静的`registry.yaml`のみとする。動的自己登録(各ツールが起動時にHubへ自らpingして登録する方式)は将来課題として**明示的にスコープ外**とし、v1では手動メンテナンスの台帳で足りるとする。全12エントリはPhase0の統合対象棚卸し表と1:1対応するため、代表4件のみ示す(残り8件も同型):

```yaml
# hub/registry.yaml (v1・静的台帳、12エントリのうち代表4件を抜粋)
tools:
  - tool_id: dev_rag_environment
    display_name: "DevelopmentRAGEnvironment"
    transport: http_bridge
    endpoint: "http://127.0.0.1:8766/health"
    health_check: http_bridge_check
    category: monitored             # 既存/healthをそのまま監視対象にする
  - tool_id: research_collector
    display_name: "Research-Collector"
    transport: cli_batch
    endpoint: null
    health_check: ci_pipeline_check
    category: monitored             # cron最終成功runの経過時間のみ見る
  - tool_id: sound_middleware
    display_name: "SoundMiddleware"
    transport: rpc
    endpoint: null
    health_check: rpc_check
    category: observed_only         # realtime hot pathには入らない、受動監視のみ
  - tool_id: color_encyclopedia
    display_name: "ColorEncyclopedia"
    transport: static_site
    endpoint: null
    health_check: null
    category: excluded              # 実行時連携なし、Hub対象外
```

3. `category`は3値(`monitored`: Hubが能動的にヘルスチェックする / `observed_only`: 他ツール経由の間接メトリクスのみ受動的に受け取る / `excluded`: Registryには載せるが監視対象外)とし、LoreDesktopAndWebSystem・LearningQt・SoundMiddleware・VLMAutoReplayTool・DynamicGIMiddlewareのように「観察のみで介入しない/間接取得のみ」の対象と、ColorEncyclopediaのように対象外の対象を型レベルで明示する。残り8エントリ(LoreDesktopAndWebSystem=`rpc`/`observed_only`、The-Algorithm-Illustrated=`static_site`/`monitored`、LearningQt=`rpc`/`observed_only`、AssetDataInsightSuite=`cli_batch`/`monitored`、VisualRegressionQATool=`cli_batch`/`monitored`、VLMAutoReplayTool=`http_bridge`/`observed_only`、DynamicGIMiddleware=`rpc`/`observed_only`、ProfilingTool=`http_bridge`/`monitored`)はPhase0棚卸し表のtransport列をそのまま転記する

**検証チェックリスト:**
- [ ] `registry.yaml`の12エントリ全てが`ToolEntry`スキーマでパースエラーなくロードされる
- [ ] `transport`の値が統合対象棚卸し表の記述と1:1で一致する
- [ ] `category: excluded`のColorEncyclopediaがPhase2以降のヘルスチェックループから除外されることをコードで確認
- [ ] `category: observed_only`のLoreDesktopAndWebSystem/LearningQt/SoundMiddlewareに対してHubが能動的な接続を開始しないことをコードレビューで確認

---

## Phase 2: ヘルスチェック+Liveness監視

**目的:** Registryの`health_check`フィールドが指す3種類のチェック関数を実装し、各ツールが「生きているか」を定期的に判定する。新規のヘルスチェックプロトコルは作らず、各ツールが既に持つ契約をそのまま再利用する。

**実装内容:**

1. `health/http_bridge_check.py`: DevelopmentRAGEnvironmentの`rag_local_bridge.py`が既に持つ**未認証**`/health`エンドポイントを直接再利用する。新規エンドポイントの追加要求は行わない:

```python
# hub/health/http_bridge_check.py
import httpx

async def http_bridge_check(endpoint: str, timeout_s: float = 3.0) -> "HealthResult":
    """rag_local_bridge.pyの/health等、未認証で公開済みの/healthをそのまま叩く。
    X-API-Keyヘッダは/health自体には不要(rag_local_bridge.py `_require_auth()`の除外対象)。
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(endpoint)
            return HealthResult(is_up=resp.status_code == 200, latency_ms=resp.elapsed.total_seconds() * 1000)
    except httpx.RequestError:
        return HealthResult(is_up=False, latency_ms=None)
```

2. `health/rpc_check.py`: Sound Middleware Phase3で確定するハートビート/再接続契約を**直接再利用**する。LoreDesktopAndWebSystem(`QLocalSocket`)・LearningQt・DynamicGIMiddlewareのRPC系についても同じハートビート待受パターンを踏襲する(ただしcategoryが`observed_only`の対象へは能動的に接続を開始せず、相手からのハートビート信号を受動的に監視するのみ):

```python
# hub/health/rpc_check.py
def rpc_check(tool_id: str, last_heartbeat_at: float, heartbeat_interval_s: float) -> "HealthResult":
    """Sound Middleware Phase3のハートビート/再接続契約を踏襲。
    Hub側から能動的にRPC接続を開くのではなく、各ツールが定期送出するハートビートの
    受信タイムスタンプが interval の2倍を超えて途絶していないかで生死判定する。
    """
    import time
    elapsed = time.monotonic() - last_heartbeat_at
    return HealthResult(is_up=elapsed < heartbeat_interval_s * 2, latency_ms=None)
```

3. `health/ci_pipeline_check.py`: The-Algorithm-Illustrated、Research-Collector、AssetDataInsightSuite、Visual Regression QA Toolなど、CI/CD cronベースのツール向け。「最終成功runからの経過時間」のみを見る(それ以上の詳細判定はCI側の責務としてHubは持ち込まない):

```python
# hub/health/ci_pipeline_check.py
def ci_pipeline_check(last_success_at: float, expected_interval_s: float, grace_multiplier: float = 1.5) -> "HealthResult":
    """CI最終成功runからの経過時間のみで判定する。Runログの内容解析はしない。"""
    import time
    elapsed = time.monotonic() - last_success_at
    return HealthResult(is_up=elapsed < expected_interval_s * grace_multiplier, latency_ms=None)
```

4. ポーリング間隔は`category: monitored`の各ツールについて、対象ツール自身のヘルスチェック/cron間隔以下にしない(非機能要件の非hot-path原則をここで具体化する)。例えばResearch-Collectorのcronが6時間おきなら、Hub側の`ci_pipeline_check`呼び出しも6時間おき以下に留める

**検証チェックリスト:**
- [ ] `http_bridge_check`がDevelopmentRAGEnvironmentの実際の`/health`エンドポイントに対して`X-API-Key`ヘッダなしで200を得る(既存の認証除外仕様と一致)
- [ ] `rpc_check`が意図的にハートビートを止めたモックに対し`heartbeat_interval_s * 2`以内にdownと判定する
- [ ] `ci_pipeline_check`がResearch-Collectorの実際のcron間隔(6時間おき)を`expected_interval_s`として正しく設定されている
- [ ] `category: observed_only`のツールに対してHubが能動的なRPC接続を1件も開始していないことをネットワークキャプチャで確認
- [ ] 各チェックのポーリング間隔が対象ツール自身の間隔を上回っていないこと(非hot-path原則の実装確認)

---

## Phase 3: アラート集約+通知ルーティング

**目的:** 複数ソースから届くアラートを単一のライフサイクルモデルへ正規化し、重複を1件に集約、解消時に自動でresolve状態へ遷移させる。

**実装内容:**

1. `hub/AlertAggregator`はProfiling Tool(主経路)/Visual Regression QA Tool/Asset Data Insight Suite/Hub自身のヘルスチェック(Phase2)の4ソースを`AlertRecord`へ正規化する:

```python
# hub/alert_aggregator.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"

@dataclass
class AlertRecord:
    alert_id: str            # sourceToolId + 正規化した障害シグネチャのハッシュ。dedupキー
    source_tool_id: str
    severity: Severity
    message: str
    first_seen_at: datetime
    resolved_at: datetime | None   # Noneの間はopen。resolve検知でタイムスタンプを刻む

def normalize_from_profiling_tool(raw_alert: dict) -> AlertRecord: ...
def normalize_from_visual_regression_qa(raw_evaluation: dict) -> AlertRecord: ...
def normalize_from_asset_data_insight(raw_manifest_entry: dict) -> AlertRecord: ...
def normalize_from_health_check(tool_id: str, result: "HealthResult") -> AlertRecord: ...
```

2. **dedup/resolveのライフサイクルは新規発明しない。** Research-Collectorが既に実装・実機検証済みの「同一ラベル(`auth-expired`/`refresh-soon`)でのIssue自動作成→open中Issueの重複防止チェック→解消時の`gh issue close`」パターンを名指しで直接の前例として引用し、`AlertRecord.alert_id`をIssueのラベル+検索キーに相当するdedupキーとして同型に扱う:

```python
def upsert_alert(new_alert: AlertRecord, existing: list[AlertRecord]) -> AlertRecord:
    """Research-Collector `refresh_auth.ps1` L45-53 の
    「openなラベル一致Issueがあれば新規作成せず、解消時にcloseする」パターンを踏襲。
    alert_idが一致するopenレコードがあれば新規作成せず、firstSeenAtは据え置く。
    一致するopenレコードが無ければ新規AlertRecordを生成する。
    """
    for existing_alert in existing:
        if existing_alert.alert_id == new_alert.alert_id and existing_alert.resolved_at is None:
            return existing_alert  # 重複作成しない(Research-Collectorの重複防止チェックと同型)
    return new_alert

def resolve_alert(alert: AlertRecord) -> AlertRecord:
    """該当ソースからのアラート解消を検知した時点でresolvedAtを刻む。
    Research-Collectorの自動クローズ(refresh_auth.ps1)と同型のライフサイクル遷移。
    """
    alert.resolved_at = datetime.utcnow()
    return alert
```

3. 通知ルーティング先(Issue作成、Slack、ローカル通知等)はHubのスコープ外とし、v1は`AlertRecord`の状態をダッシュボード(Phase4)に表示するのみに留める。外部通知チャネルへの配信は将来課題として明記する

**検証チェックリスト:**
- [ ] Profiling Toolからのアラートとヘルスチェック由来のアラートが同一障害を指す場合、`alert_id`が一致し1件の`AlertRecord`に集約される
- [ ] `upsert_alert`が既存openレコードに対して`firstSeenAt`を上書きしないこと
- [ ] 障害解消後、対応するソースから正常応答が届いた時点で`resolved_at`が設定されること
- [ ] Research-Collectorの`auth-expired`/`refresh-soon`ラベル運用と、本Hubの`AlertRecord`ライフサイクルが概念上1:1対応することをレビューで確認

---

## Phase 4: 統合ダッシュボード(可視化)

**目的:** 各ツールが自律的に生成する成果物を読み取り専用で1画面に集約する。ダッシュボード側での新規計算・新規判定は一切行わない。

**実装内容:**

1. 表示対象は4種類。いずれも既存ツールが既に生成しているアーティファクトをそのまま読み込むだけで、Hub側での加工・再計算は行わない:
   - Profiling Toolの Perfetto トレース(サマリ表示のみ、トレース本体のビューアはProfiling Tool側の責務)
   - Asset Data Insight Suiteの`report_manifest.json`
   - Visual Regression QA Toolの`EvaluationResult`履歴
   - 自身の`ToolRegistry`/`AlertAggregator`の現在状態

```python
# hub/dashboard/data_sources.py
def load_registry_status(registry: "ToolRegistry") -> list[dict]:
    """Phase1のregistry.yaml + Phase2のliveness結果をそのまま表示用に整形するのみ"""
    ...

def load_alert_summary(aggregator: "AlertAggregator") -> list[dict]:
    """Phase3のAlertRecord一覧をopen/resolved別に整形するのみ。新規判定はしない"""
    ...

def load_asset_insight_manifest(path: str) -> dict:
    """report_manifest.jsonをそのまま読み込むのみ。Hub側でスコア再計算等は行わない"""
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

2. ダッシュボードはPhase0の「二次的な正となる状態源にしない」というアンチパターンを実装レベルで守るため、各データソースの取得元パスとタイムスタンプを画面に必ず併記し、「これはミラーであり最新の正はここではない」ことを利用者に常時示す

**検証チェックリスト:**
- [ ] ダッシュボード表示コード内に集計・再計算ロジックが存在しないこと(コードレビューで確認、読み込み+整形のみであること)
- [ ] `report_manifest.json`更新後、ダッシュボードが再読込で最新内容を反映すること
- [ ] 各パネルに取得元のファイルパス/エンドポイントとタイムスタンプが表示されていること
- [ ] Profiling Toolのトレースビューア機能そのものをHub側で再実装していないこと

---

## Final Phase: 統合検証

- [ ] 12ツール全エントリ(Phase1 `registry.yaml`)がエラーなくロードされ、各`transport`がその文書(統合対象棚卸し表)の実際の連携方式と一致する
- [ ] 意図的にkillしたモックサービス(例: `http_bridge_check`対象のモック`/health`サーバ)が、設定したタイムアウト内にdown検知される
- [ ] 2つの異なるソース(Profiling Toolとヘルスチェック)が同一障害を報告しても重複なく1件の`AlertRecord`になる(Phase3の`upsert_alert`検証の統合版)
- [ ] 各ツール自身のヘルスチェック/cron間隔より高頻度でHubがポーリングしていないことを全`monitored`エントリについて確認する(Phase0の非hot-path原則の実証)
- [ ] `category: observed_only`/`excluded`のツール(LoreDesktopAndWebSystem・LearningQt・SoundMiddleware・ColorEncyclopedia等)に対してHubが能動的な接続・介入を一切行っていないこと
- [ ] Hubプロセスを停止した状態で、監視対象12ツールそれぞれのコア機能(RPC編集、リアルタイム再生、GPUジョブ実行等)が単独で継続動作すること(非機能要件「単一障害点にならない」の実地検証)

---

## 相互参照ドキュメント

- LoreDesktopAndWebSystem Phase4(プロセス分離・`QLocalSocket` RPC)/Phase7(`:8766`ブリッジ経由RAGアシスタント) — Registryのtransport2種の直接の前例
- DevelopmentRAGEnvironment `rag_local_bridge.py`の`:8766`ブリッジ、未認証`/health` — `http_bridge_check`が直接再利用する対象
- Sound Middleware Phase3(ハートビート/再接続契約) — `rpc_check`が直接再利用する対象。realtimeのhot pathには入らない
- Profiling Tool Phase4(メトリクス/アラート発行契約) — `AlertAggregator`の主経路
- Visual Regression QA Tool Phase5(差し替え可能アラートsink) — Hubをsink実装の1つとして登録する対象
- Asset Data Insight Suite Phase4/5(`report_manifest.json`、Issue通知) — Hubの主要な購読元、ダッシュボードでそのまま表示
- Research-Collector(実在・実装済み) — dedup/resolveアラートライフサイクルの直接の前例(`auth-expired`/`refresh-soon`ラベル運用)
- LearningQt Orchestrator/JobPipeline/ResourceBudgetManager(GPU厳密直列) — Hubは観察のみで介入しない対象として明記

---

**優先度注記:** 実装複雑度自体は中程度(レジストリ/ヘルスチェック/アラート集約はサービスメッシュ的な前例が豊富で技術的な目新しさは低い)。しかし本文書の正しさは他12文書のインターフェースに全面依存するため、統合・順序リスクは他のどの文書よりも高い。したがってHub自身の内部アーキテクチャ(Registry/Relay/AlertAggregatorの3層構成、`AlertRecord`スキーマ)はここで確定的にコミットする一方、各ツールとの連携マッピング(統合対象棚卸し表のtransport・エンドポイント名)は他11文書の実装が固まるまで**すべて「暫定」**として扱う。他文書側でtransportやエンドポイントの前提が変わった場合は、Hub側の内部設計を変えずにRegistryのエントリだけを更新すれば追従できる、という分離を本設計の最終的な狙いとする。

---

## Phase 5: UI/アニメーション強化(2026-09-08追記)

**背景**: X上の@ozwxy氏の実演(GPT-6 Astraによる金属反射・ガラス質感・ホログラム・カードめくれ等30種のUIコンポーネント生成デモ、2026年9月7日投稿)を受け、ユーザーがUI/アニメーション面の強化を明示的に要望。統合ダッシュボードとの相性が高い3種のコンポーネントを選定した。既存Phase1〜4の判定ロジック・データソースは一切変更せず、表示レイヤーへの追加のみとする。

### 1. エッジライト(Edge Light) — ツールカードの稼働状態表示

Phase4の`ToolEntry`カードに適用する。`load_registry_status`が返すliveness結果(Phase2`HealthResult`)から3値ステータス(健全/劣化/ダウン)を導出し、カード縁の発光色とパルスアニメーションで表現する。判定ロジック自体はPhase2側に追加せず、表示側で`is_up`/`latency_ms`から導出するのみに留める:

```css
/* hub/dashboard/static/edge-light.css */
.tool-card[data-status="healthy"]  { --glow: #22c55e; }
.tool-card[data-status="degraded"] { --glow: #eab308; }
.tool-card[data-status="down"]     { --glow: #ef4444; }
.tool-card {
  box-shadow: 0 0 0 1px var(--glow), 0 0 10px 2px var(--glow);
  animation: edge-pulse 2.4s ease-in-out infinite;
}
@keyframes edge-pulse {
  0%, 100% { box-shadow: 0 0 0 1px var(--glow), 0 0 6px 1px var(--glow); }
  50%      { box-shadow: 0 0 0 1px var(--glow), 0 0 16px 4px var(--glow); }
}
```

```js
// data-status = healthy | degraded | down (latency_ms >= 500msを劣化閾値とする)
card.dataset.status = !result.is_up ? "down" : (result.latency_ms >= 500 ? "degraded" : "healthy");
```

### 2. セグメントレール(Segment Rail) — transportフィルタ

Phase4ダッシュボードのフィルタUIに採用する。`registry.yaml`の`transport`4値(`http_bridge`/`rpc`/`cli_batch`/`static_site`)+「全て」をレール状のセグメントコントロールで切り替える。フィルタはクライアント側の表示絞り込みのみで、Registryへの再問い合わせは発生させない:

```html
<div class="segment-rail" role="tablist" aria-label="transport filter">
  <button role="tab" aria-selected="true" data-transport="all">全て</button>
  <button role="tab" data-transport="http_bridge">http_bridge</button>
  <button role="tab" data-transport="rpc">rpc</button>
  <button role="tab" data-transport="cli_batch">cli_batch</button>
  <button role="tab" data-transport="static_site">static_site</button>
  <span class="segment-rail__thumb"></span>
</div>
```

```js
rail.addEventListener("click", (e) => {
  const tab = e.target.closest("[role=tab]");
  if (!tab) return;
  moveThumb(tab); // transform: translateX(tab.offsetLeft)でスライド
  renderCards(tab.dataset.transport === "all"
    ? registryStatus
    : registryStatus.filter(t => t.transport === tab.dataset.transport));
});
```

### 3. スタックトースト(Stack Toast) — アラート通知の積み重ね表示

Phase3の`AlertRecord`が複数同時発生した際、ダッシュボード上で積み重なるトースト通知として表示する。`resolved_at`が設定された時点(Phase3`resolve_alert`)で該当トーストのみをスタックから除去する。トースト自体は`AlertRecord`のミラー表示であり、resolve判定ロジックはPhase3据え置きとする:

```js
function renderToastStack(openAlerts /* resolved_at === null のみ */) {
  const sorted = [...openAlerts].sort((a, b) => b.first_seen_at - a.first_seen_at);
  sorted.forEach((alert, i) => {
    const el = getOrCreateToast(alert.alert_id);
    el.className = `toast toast--${alert.severity}`;
    el.style.transform = `translateY(${i * -10}px) scale(${1 - i * 0.03})`;
    el.style.zIndex = 100 - i;
  });
  // resolved_atが立ったアラートに対応するトーストはフェードアウトしDOMから除去
  document.querySelectorAll(".toast").forEach(el => {
    if (!sorted.find(a => a.alert_id === el.dataset.alertId)) el.remove();
  });
}
```

**検証チェックリスト:**
- [ ] エッジライトの3状態(健全/劣化/ダウン)がPhase2の`HealthResult.is_up`/`latency_ms`のみから導出され、新規の判定ロジックをPhase2側に追加していない
- [ ] セグメントレールの選択肢がRegistryの`TransportKind`4値と「全て」のみで、未定義のtransport値を持たない
- [ ] スタックトーストが`resolved_at`セット後、次回ポーリングで該当トーストのみ自動的に除去され、他のopenアラートのスタック順序に影響しない
- [ ] 3コンポーネントいずれもPhase4のアンチパターン「ダッシュボードを二次的な正となる状態源にしない」を破らず、表示レイヤーの追加に留まっている
- [ ] 複数トースト同時発生時のスタック順序が`first_seen_at`降順で安定している
