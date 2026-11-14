# 6. トラブルと保守

## 症状 → 原因 → 直し方

| 症状 | 原因 | 直し方 |
|---|---|---|
| ブラウザで開くと **403**「このHostでは受け付けません」 | `127.0.0.1`・`localhost`・`::1` 以外の名前(LAN の IP・別のホスト名)で開いている | 環境変数 `HUB_ALLOWED_HOSTS` に、その名前を足して再起動(`uv run hub --host <IP>` は自動で足す。`0.0.0.0` は足さない) |
| ボタンを押すと **403**「他のサイトからの変更操作は…」 | Origin が Hub の Host と一致しない(別のポートのページ・プロキシ越し・`file://` から) | 同じ URL(Host とポート)で開く。リバースプロキシを使うなら、Host を保つ |
| **401**「API キーが正しくありません」 | キーの打ち間違い・削除済み・別の `HUB_AUTH_FILE` | `python -m hub.auth list` で名前を確認し、`add` で作り直す(キーは作成時の 1 度だけ表示) |
| **403**「この操作には operator 以上が…」 | 役割が足りない(`viewer` で POST) | 送る側のキーを `operator` にする。同期・registry 再読込は `admin` |
| `HUB_AUTH=required` で**起動しない** | ユーザーが 1 人もいない(fail-closed) | `python -m hub.auth add --name <名前> --role admin` |
| ツールが**ずっと「未確認」** | 信号が一度も届いていない(`rpc` はハートビート、CI 系は成功通知) | `curl -X POST .../api/heartbeat/<id>`(または `ci-success`)を送る。**Hub を再起動すると、また未確認に戻る**(受信時刻はメモリ) |
| **CI 系が、成功通知を送ったのに「未確認」のまま** | 下の既知の問題 1 | 次の周期(`poll_interval_s`)まで待つ。台帳の `poll_interval_s` を短くする |
| 送ったのに**400** | `health_check` の種類が違う(CI 系へ heartbeat など)/ 不正な値 | 台帳の `health_check` を見て、正しい口へ送る |
| **404** | その `tool_id` が台帳に無い | `registry.yaml` に足す(5 秒で反映) |
| 台帳を直したのに**反映されない** | YAML の構文・検証エラー(古い台帳のまま動く) | `POST /api/registry/reload`(admin)のエラー文を見る。循環・存在しない依存・重複 ID を確認 |
| 通知が来ない | `warn` 未満(既定)/ スヌーズ中 / `winotify` が無い / Slack の URL が未設定 | 重大度・スヌーズ・`HUB_SLACK_WEBHOOK_URL` を確認。通知は `notify.py` が `logger` に失敗を残す |
| 通知が**連発する** | 署名に時刻・乱数が入っていて、dedup が効かない / フラッピング | 署名を固定する(送り手側)。短期的には「Snooze 1h」 |
| Start が「running」なのに**動いていない** | 同じ既定ポート(Vite の 5173 など)を、別のリポジトリが使っている | `repos.yaml` の `url` のポートを分ける |
| Sync が**拒否**される | 未コミットの変更がある / fast-forward できない | 対象リポジトリで、コミットか退避をしてから。Hub は無理に取り込まない |
| 画面が**古い** | 自動更新が止まっている(`?refresh=0`) | `/?refresh=20`(既定 20 秒) |

## 既知の問題(コードは変えていない。直すときの手がかり)

文書を作るときに、コードを読んで・動かして見つけたものです。**本物の挙動**で、直すかは判断が要ります。

### 1. CI 系ツールは、初回の成功通知のあと、最長 `poll_interval_s` のあいだ「未確認」のまま

`LivenessMonitor.check_once` は、`monitored` のツールを `poll_interval_s` で**間引き**ます。判定不能(`None`)のときも「試した時刻」(`_last_polled_at`)を記録するため、Hub を起動した直後(成功通知がまだ無い)に 1 回試すと、**そのあと `poll_interval_s` が過ぎるまで、成功通知が届いても再評価されません**。

```python
# 実行できる
import asyncio
import time

from hub.health.runner import LivenessMonitor
from hub.registry import ToolRegistry

registry = ToolRegistry.load()
entry = registry.get("the_algorithm_illustrated")   # ci_pipeline_check・poll_interval_s: 86400
monitor = LivenessMonitor(registry)
t0 = time.monotonic()

print("poll_interval_s:", entry.poll_interval_s)
print("起動直後(成功通知なし)       :", asyncio.run(monitor.check_once(entry, now=t0)))
monitor.record_ci_success(entry.tool_id, at=t0 + 10)
print("10 秒後に成功通知 → 15 秒後   :", asyncio.run(monitor.check_once(entry, now=t0 + 15)))
print("1 日(86400 秒)たったあと     :", asyncio.run(monitor.check_once(entry, now=t0 + 86401)))
```

```text
# 出力
poll_interval_s: 86400
起動直後(成功通知なし)       : None
10 秒後に成功通知 → 15 秒後   : None
1 日(86400 秒)たったあと     : HealthResult(is_up=True, latency_ms=None)
```

`the_algorithm_illustrated`・`asset_data_insight_suite`・`visual_regression_qa_tool` は 86400 秒(1 日)、`research_collector` は 21600 秒(6 時間)。**直す案**: ①判定不能(`None`)のときは「試した時刻」を記録しない ②`record_ci_success` で、そのツールの間引きの記録を消す。

### 2. 「最終応答」が、実際の受信より新しく見える

`last_signal_age_s` が「up と確認できた時刻」(`_last_up_at`)も候補に入れるため、up の間は、**直近の確認の時刻**(最大 5 秒前)になります(講義[第 2 回](../lecture/02-health-checks.md)の注意)。**直す案**: 候補から `_last_up_at` を外す(受信時刻だけにする)。ただし、`http_bridge_check` のような**能動**のツールには、`_last_up_at` が必要。

### 3. `rpc_check` / `ci_pipeline_check` が、`now` を受け取らない

`check_once(entry, now=...)` の `now` は、間引きと `_last_up_at` にだけ効き、`rpc_check` などの内部は `time.monotonic()` を**自分で読む**。時刻を進めたテストが書きにくい。**直す案**: 両関数に `now` 引数(既定は `time.monotonic()`)を足す。

### 4. ループが例外を握りつぶし、ログに残らない

`_poll_loop`・`_prune_loop`・`_repo_check_loop` は、`except Exception: pass`。Hub が**止まらない**のが狙いだが、**想定外のバグも、静かに無視**される(通知 `notify.py` は `logger.exception` で残している)。**直す案**: `logger.exception(...)` を足す。

### 5. モジュールを import すると、副作用がある

`hub/dashboard/app.py` の末尾 `app = create_app()` が、import 時に実行される(`.hub_state/alerts.sqlite3` の作成・`repos.yaml` の読み込み)。テストは `create_app(...)` に一時フォルダを渡して避けている。**直す案**: `uvicorn --factory` と `create_app` を使い、モジュール末尾の `app` をやめる。

### 6. その他の制約(設計上の割り切り)

- **再起動で、受信時刻・スヌーズ・起動の記録が消える**(メモリだけ)。アラート履歴は残る。
- 履歴スライダーが再現できるのは、**アラートの発生・解消だけ**(死活監視の結果そのものは残らない)。
- `percentile_by_span_name` は**最近傍順位**(線形補間ではない)。件数が少ないと、p50 が上側の値になる。
- `TraceWriter.append` は、追記のたびに**ファイル全体を書き直す**。
- `repos.yaml` の `command` は `shell=True` で実行される(**書き換えられる人を信頼できる人に限る**)。
- ダッシュボードから `profiling_tool` を呼ぶ処理は、例外を握りつぶす(Hub 本体を落とさないため。原因はログに残りにくい)。

## 定期の保守

| いつ | 何を |
|---|---|
| 毎回の変更 | `uv run pytest -q` と `python tools/check_docs.py` を通す |
| 台帳を変えたとき | 件数を決め打ちするテスト(`== 12`・`== 13`)と、文書の数([4 拡張](04-extend.md) レシピ 1)を直す |
| 月 1 回 | `uv lock --upgrade` → `uv run pytest -q`。`pyjwt`・`fastapi`・`httpx` の更新に注意 |
| 月 1 回 | `~/.tool_orchestration_hub/audit.jsonl` の**大きさ**を確認する(ローテーションの仕組みは**ない**。大きくなったら、手で退避) |
| 四半期 | ユーザー(`python -m hub.auth list`)を見直し、使わないキーを `remove` |
| 暫定値の確認 | `registry.yaml` の `poll_interval_s`・`check_params`・`isolation` は**暫定**。相手の実際の間隔に合わせる |
| 関数を直したとき | `python tools/check_docs.py --update` で、文書の引用・出力を作り直し、**説明が合っているか**を読む |

## 変更履歴の置き場所

README は**入口**に絞ってあります。バージョンごとの追加機能・不具合の記録(v1.1〜v2.7)は、[変更履歴と詳細](../reference/changelog.md)に**そのまま**移してあります。新しい版を足すときは、そちらの末尾に追記してください。
