# 4. 拡張のレシピ

どれも、**「データを足す」→「関数を足す」→「テストを足す」**の順で、小さく進めます。Hub の中心(`AlertAggregator`・`LivenessMonitor`)は、**変えなくて済む**ように作ってあります。

## レシピ 1: ツールを台帳に 1 件足す(コード変更なし)

1. `hub/registry.yaml` の `tools:` の末尾に、1 件足す。

   ```yaml
     - tool_id: build_server
       display_name: "Build Server"
       transport: rpc                  # http_bridge / rpc / cli_batch / static_site
       endpoint: null
       health_check: rpc_check         # http_bridge_check / rpc_check / ci_pipeline_check / null
       category: observed_only         # monitored / observed_only / excluded
       check_params:
         heartbeat_interval_s: 30      # 相手が送る間隔。この 2 倍で途絶したら停止
       symbol: "Bs"                    # 任意(1〜2 文字)
       color: "#4b6d5a"                # 任意(#rrggbb)
       depends_on: []                  # 任意(使っているツールの tool_id)
   ```

2. 保存する。**5 秒以内**に反映される(再起動不要)。壊れた YAML は拒否され、**古い台帳のまま**動き続ける。
3. 相手のツールから、ハートビートを送る(認証が必須なら `X-API-Key: <operator のキー>`)。

   ```bash
   curl -X POST http://127.0.0.1:8790/api/heartbeat/build_server
   ```

4. **種類の選び方**:

   | ツールの性質 | `health_check` | `category` | 必要な設定 |
   |---|---|---|---|
   | `/health` を持つ HTTP の窓口 | `http_bridge_check` | `monitored` | `endpoint`・`poll_interval_s`・`check_params.timeout_s` |
   | 定期的に自分で合図を送る | `rpc_check` | `observed_only` | `check_params.heartbeat_interval_s` |
   | cron・CI で回り、成功を通知できる | `ci_pipeline_check` | `monitored` | `check_params.expected_interval_s`・`grace_multiplier`・成功時に `POST /api/ci-success/<id>` |
   | 監視しない(載せるだけ) | `null` | `excluded` | なし |

5. **テストと文書の更新**: 件数を決め打ちしているテスト(`tests/test_registry.py`・`test_overview.py`・`test_dashboard_data_sources.py` の `12`)と、文書の実行例(講義第 0 回の「台帳の件数」)の数を、**新しい件数に直す**。

> `poll_interval_s` と `check_params` は、**ツール側の実際の間隔に合わせた暫定値**。固まったら、台帳だけを直す。

## レシピ 2: 新しい種類の死活監視を足す

例: TCP ポートに接続できるかだけを見る `tcp_check`。

1. `hub/health/tcp_check.py` を作る。**`HealthResult` を返す**関数にする(能動なら `async def`)。

   ```python
   async def tcp_check(host: str, port: int, timeout_s: float = 2.0) -> HealthResult:
       started = time.monotonic()
       try:
           _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout_s)
       except (OSError, asyncio.TimeoutError):
           return HealthResult(is_up=False, latency_ms=None)
       writer.close()
       return HealthResult(is_up=True, latency_ms=(time.monotonic() - started) * 1000)
   ```

2. `hub/health/__init__.py` の `__all__` に足す。
3. `hub/health/runner.py` の **`_dispatch_active`** に、`if entry.health_check == "tcp_check": ...` の分岐を足す(**未知の名前は `ValueError`** になるので、足し忘れは、すぐ分かる)。
4. `registry.yaml` で `health_check: tcp_check` を使う。
5. **テスト**(`tests/test_health_checks.py`・`test_runner.py` の形): 閉じたポートで `is_up=False`、待ち受けるサーバーで `True`。

**判断の目安**: 受動(相手が送る)にできるなら**受動**のほうが、相手に何も開かず安全。能動は、相手に負荷・権限の問題が出ないものだけにする。

## レシピ 3: アラートの送り手を足す

講義[第 6 回の総合演習](../lecture/06-testing-capstone.md)が、完成形です。手順:

1. **`normalize_from_xxx`**(`hub/alert_aggregator.py`): 受け取った辞書 → `AlertRecord`。署名(何を同じ異常とみなすか)・重大度・`info` = 解消の決めを書く。
2. **受け口**(`hub/dashboard/app.py`): `@app.post("/api/alerts/xxx", dependencies=[auth.operator])` で、`_normalize_and_ingest(normalize_from_xxx, payload)` を呼ぶ。**本文の長さの上限・不正な値の 400**は、`_normalize_and_ingest` が既に面倒を見る。
3. **台帳に載せる**(レシピ 1)。載せなくても動くが、画面でツールに紐づかない。
4. **運用手順書**: `hub/runbooks.py` に種別の定数(`KIND_*`・`ALL_KINDS`)と、送り手 → 種別の表 `_KIND_BY_SOURCE` を足し、`hub/runbooks.yaml` に本文を書く。足さなければ `generic` の手順になる。
5. **テスト**: 正規化・dedup・`info` での解消・不正な値で 400・`viewer` が 403。

**署名の選び方**(いちばん大事): **同じ異常には、いつも同じ署名**、**別の異常には別の署名**にする。署名に**時刻・乱数・行番号**を入れると、毎回別の異常になり、**dedup が効かない**(通知が連発する)。

## レシピ 4: 通知先を足す(Teams・Discord・メールなど)

1. `hub/notify.py` に、`NotificationSink`(`notify_opened`・`notify_resolved`)を満たすクラスを足す。

   ```python
   class DiscordWebhookSink:
       def __init__(self, url: str, min_severity: Severity = Severity.WARN) -> None: ...
       def notify_opened(self, alert: AlertRecord) -> None: ...      # 失敗しても例外を外へ出さない
       def notify_resolved(self, alert: AlertRecord) -> None: ...
   ```

2. `default_sink()` に、**環境変数があれば追加**する条件を足す(`HUB_SLACK_WEBHOOK_URL` と同じ形)。
3. **規律**: 通知の失敗で、**監視を止めない**(例外を握りつぶし、`logger` に残す)。`CompositeSink` が二重の安全網。**Webhook の URL は環境変数**で渡し、リポジトリに書かない。
4. **テスト**: `tests/test_notify.py` の形(送信を差し替えて、重大度の閾値・失敗の隔離を確かめる)。

## レシピ 5: リポジトリを同期・起動の対象にする

`hub/repos.yaml` に、1 件足します。

```yaml
  - repo_id: my_tool
    display_name: "MyTool"
    local_path: "../MyTool"              # Hub のルートからの相対パス
    remote_url: "https://github.com/<owner>/MyTool.git"
    branch: main
    launch:                              # 無ければ省略し、launch_note に理由を書く
      - name: "Web GUI"
        command: "uv run python -m app --port 5000"
        cwd: "."
        url: "http://127.0.0.1:5000"     # 疎通確認用(任意)
```

- **`command` はシェルとして実行される**(`shell=True`)。**信頼できる、固定のコマンドだけ**を書く。`repos.yaml` を書き換えられる人 = Hub のホストでコードを実行できる人、と考える。
- 複数のプロセスが要るなら、`launch:` に複数件(「Start all」が出る)。
- **ポートの衝突**: 他のリポジトリと既定のポートが同じだと、「running」を誤表示する(既知の制約)。`url` のポートを変えて避ける。
- **テスト**: `tests/test_repo_sync.py` の件数(`== 13`)を直す。

## レシピ 6: 運用手順書を足す・直す

`hub/runbooks.yaml` に、種別ごとに `title`・`do`(やること)・`dont`(やらないこと)・`deliverable`(成果物)を書く。**Hub の再起動後に反映**。壊れたファイルでも Hub は、手順なしで起動する。
手順は「Hub から何かをする」でなく、「**人が確認・判断すること**」だけを書く(Hub は見るだけ)。

## レシピ 7: ルートに役割を付ける

新しい API を足すときは、**最低の役割を必ず宣言**する(宣言しないと、`HUB_AUTH=required` でも**誰でも通る**)。

| 操作の種類 | 役割 |
|---|---|
| 見るだけ(GET) | `auth.viewer` |
| 状態を変えるが、他のプロジェクトには触れない(スヌーズ・信号の送信・起動) | `auth.operator` |
| 他のプロジェクトのファイルを書き換える・設定を読み直す(同期・registry の再読込) | `auth.admin` |

`dependencies=[auth.operator]` を、デコレータに付けるだけ。**テスト**: 役割ごとの 200 / 401 / 403(`tests/test_auth.py` の形)。

## 変更の前に

- 手順書の「**やらないこと**」: Hub から**ツールへ接続・再起動を試みる**機能を足さない(Hub は監視のみ・ツールの権限を持たない)。
- 「便利な補助」は**表示専用**にとどめ、**通知・dedup・resolve の経路につなげない**(補助が壊れても、肝心の通知が止まらない)。
- 変更したら、`uv run pytest -q` と `python tools/check_docs.py`(文書の検査)を通す([5 テスト](05-testing.md))。
