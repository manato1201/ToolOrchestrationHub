# 第 2 回 死活監視(liveness): 生きているかを 3 通りで見る

> 所要時間の目安: 3 時間 / 前提: 第 0〜1 回

## この回のゴール

- 3 種類の死活監視(`http_bridge_check`・`rpc_check`・`ci_pipeline_check`)の**判定のしかた**を説明できる。
- なぜ時刻に `time.monotonic()` を使うのかを説明できる。
- **「まだ信号が無い」を「正常」にしない**工夫を、コードで指摘できる。
- `LivenessMonitor` の、カテゴリごとの振る舞い(能動・受動・スキップ)を説明できる。

## 1. 結果の型: `HealthResult`

3 つの死活監視は、同じ型を返します。

```python
# 引用: hub/health/base.py::HealthResult
@dataclass(frozen=True)
class HealthResult:
    is_up: bool
    latency_ms: Optional[float] = None
```

- `is_up`: 生きているか。
- `latency_ms`: 応答にかかった時間。**測れる(能動の)ときだけ**入り、受動の判定では `None`。
- `frozen=True`: 作ったあとは書き換えられない(結果を後から書き換える事故を防ぐ)。

## 2. 3 種類

| 種類 | 何を見るか | 生きている条件 | 向いているツール |
|---|---|---|---|
| `http_bridge_check` | `/health` に **GET** して、応答を見る | ステータスが **200** | HTTP の窓口を持つもの |
| `rpc_check` | **ハートビートを最後に受けた時刻** | 経過 < **間隔 × 2** | 独自 RPC・ソケットのツール |
| `ci_pipeline_check` | **CI が最後に成功した時刻** | 経過 < **期待の間隔 × 猶予(1.5 倍)** | cron・CI で定期的に回るもの |

後ろの 2 つは、**Hub が相手に何もしない**(受け取った時刻から**計算するだけ**)。

### 2.1 時刻の計算(`rpc_check`・`ci_pipeline_check`)

```python
# 引用: hub/health/rpc_check.py::rpc_check
def rpc_check(
    tool_id: str, last_heartbeat_at: float, heartbeat_interval_s: float
) -> HealthResult:
    """Sound Middleware Phase3のハートビート/再接続契約を踏襲する。

    Hub側から能動的にRPC接続を開くのではなく、各ツールが定期送出するハートビートの
    受信タイムスタンプが interval の2倍を超えて途絶していないかで生死判定する。
    """
    elapsed = time.monotonic() - last_heartbeat_at
    return HealthResult(is_up=elapsed < heartbeat_interval_s * 2, latency_ms=None)
```

**なぜ「間隔の 2 倍」か**: 1 回の信号が、遅れて・取りこぼされて届かなくても、**すぐに「停止」と言わない**ための余裕。2 回続けて途絶したら、止まっていると見る。

**なぜ `time.monotonic()` か**: 普通の時刻(`time.time()`)は、PC の時計合わせ(夏時間・ネット時刻の修正)で**逆戻りしたり飛んだり**する。`monotonic` は、起動からの経過だけを刻み、**必ず進む**ので、「経過時間」を測るのに向く。
代わりに、`monotonic` の値は**そのプロセスの中だけ**で意味を持つ。だから、ハートビートの受信時刻は**Hub のメモリ**(`LivenessMonitor`)にだけ持ちます(再起動で消える。→ 第 4 回の「未確認」)。

```python
# 実行できる
import time

from hub.health.ci_pipeline_check import ci_pipeline_check
from hub.health.rpc_check import rpc_check

now = time.monotonic()
print("5 秒前に受信(間隔 10 秒)   :", rpc_check("demo", now - 5, 10.0).is_up)
print("19 秒前に受信(間隔 10 秒)  :", rpc_check("demo", now - 19, 10.0).is_up)
print("25 秒前に受信(間隔 10 秒)  :", rpc_check("demo", now - 25, 10.0).is_up)

DAY = 86400.0
print("CI が 1 日 + 6 時間前(猶予 1.5 倍):", ci_pipeline_check(now - 1.25 * DAY, DAY).is_up)
print("CI が 2 日前                     :", ci_pipeline_check(now - 2 * DAY, DAY).is_up)
print("結果の latency_ms                :", rpc_check("demo", now, 10.0).latency_ms)
```

```text
# 出力
5 秒前に受信(間隔 10 秒)   : True
19 秒前に受信(間隔 10 秒)  : True
25 秒前に受信(間隔 10 秒)  : False
CI が 1 日 + 6 時間前(猶予 1.5 倍): True
CI が 2 日前                     : False
結果の latency_ms                : None
```

### 2.2 能動の確認(`http_bridge_check`)

```python
# 引用: hub/health/http_bridge_check.py::http_bridge_check
async def http_bridge_check(endpoint: str, timeout_s: float = 3.0) -> HealthResult:
    """rag_local_bridge.pyの/health等、未認証で公開済みの/healthをそのまま叩く。

    X-API-Keyヘッダは/health自体には不要
    (rag_local_bridge.py `_require_auth()` の除外対象と同じ前提)。

    レイテンシは`httpx.Response.elapsed`ではなく自前でmonotonic計測する。
    `elapsed`はレスポンスがtiming拡張を持つ場合のみ有効で、MockTransport等では
    未設定のままRuntimeErrorになるため。
    """
    started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(endpoint)
            latency_ms = (time.monotonic() - started_at) * 1000
            return HealthResult(is_up=resp.status_code == 200, latency_ms=latency_ms)
    except httpx.RequestError:
        return HealthResult(is_up=False, latency_ms=None)
```

- **`async def`**: 通信の待ち時間に、他のことを進められる(Hub は 13 個を順番に待たない)。
- **`httpx.RequestError` だけを捕まえる**: つながらない・時間切れは「停止」。それ以外(コードのバグ)は、握りつぶさず**表に出す**。
- 応答が **200 以外**(404・500)でも `is_up=False`(「何か返ってきた」だけでは、正常とは言わない)。

```python
# 実行できる
import asyncio

from hub.health.http_bridge_check import http_bridge_check

# 何も待ち受けていないポート(9)へ。つながらないので「停止」になる
result = asyncio.run(http_bridge_check("http://127.0.0.1:9/health", timeout_s=1.0))
print(result)
```

```text
# 出力
HealthResult(is_up=False, latency_ms=None)
```

## 3. 「まだ信号が無い」を、正常にしない

`LivenessMonitor` は、受信時刻を辞書に溜めます。**一度も届いていないツール**の扱いが肝心です。

```python
# 引用: hub/health/runner.py::LivenessMonitor._eval_rpc_check
def _eval_rpc_check(self, entry: ToolEntry, now: float) -> Optional[HealthResult]:
    if entry.tool_id not in self._heartbeats:
        # まだ一度もハートビートを受信していない。ci_pipeline_check同様、
        # nowにフォールバックして「起動直後は常にup」と誤判定しないようNoneを返す。
        return None
    heartbeat_interval_s = entry.check_params.get("heartbeat_interval_s", 10.0)
    last_heartbeat_at = self._heartbeats[entry.tool_id]
    return rpc_check(entry.tool_id, last_heartbeat_at, heartbeat_interval_s)
```

`None` は「**判定できない**」。`False`(停止)でも `True`(正常)でもない。これが、画面の**「未確認」**(○)になります。
もし「無いなら今の時刻を最後の受信にする」と書くと、Hub を起動した直後は**全員が「正常」**に見える。**偽の安心**を作るので、してはいけない(コメントが、その理由を書いている)。

```python
# 実行できる
import asyncio
import time

from hub.health.runner import LivenessMonitor
from hub.registry import ToolEntry, ToolRegistry

entry = ToolEntry.from_dict({
    "tool_id": "demo_rpc", "display_name": "デモ", "transport": "rpc", "endpoint": None,
    "health_check": "rpc_check", "category": "observed_only",
    "check_params": {"heartbeat_interval_s": 10},
})
monitor = LivenessMonitor(ToolRegistry([entry]))
now = time.monotonic()

print("1. 信号なし        :", asyncio.run(monitor.check_once(entry, now=now)))
print("   最後の信号から  :", monitor.last_signal_age_s("demo_rpc", now=now))

monitor.record_heartbeat("demo_rpc", at=now - 3)
print("2. 3 秒前に受信    :", asyncio.run(monitor.check_once(entry, now=now)).is_up)
print("   確認の直後の経過:", round(monitor.last_signal_age_s("demo_rpc", now=now), 1), "秒 ← 3 秒ではない(下の注意)")

monitor.record_heartbeat("demo_rpc", at=now - 30)  # 最後の受信が 30 秒前だったとする
print("3. 30 秒前に受信   :", asyncio.run(monitor.check_once(entry, now=now)).is_up)
```

```text
# 出力
1. 信号なし        : None
   最後の信号から  : None
2. 3 秒前に受信    : True
   確認の直後の経過: 0.0 秒 ← 3 秒ではない(下の注意)
3. 30 秒前に受信   : False
```

> **注意(既知の癖)**: 上の 2 の「最後の信号から」が、3 秒でなく **0 秒**になっています。`last_signal_age_s` は、ハートビートの受信時刻・CI 成功の時刻に加えて、**「up と確認できた時刻」**(`_last_up_at`)も候補にして、いちばん新しいものを使います。`_poll_loop` は 5 秒おきに確認するので、up の間は、この値がいつも直近の確認の時刻になり、**画面の「最終応答」が、実際の受信よりも新しく見えます**。
> もう 1 つ: `check_once(entry, now=...)` の `now` は、能動の確認の**間引き**と `_last_up_at` には効きますが、`rpc_check` / `ci_pipeline_check` の内部は**自分で `time.monotonic()` を読みます**(`now` を渡していない)。そのため、時刻を進めて「30 秒後」を再現するには、`now` を進めるのでなく、**`record_heartbeat(at=過去の時刻)`** で、受信時刻のほうを過去にします(3 の書き方)。
> どちらも**コードは変えていません**。直すなら、`rpc_check` などに `now` を引数で渡すのが筋です([学習資料](../learn/06-troubleshooting-maintenance.md)の「既知の問題」にも記載)。

## 4. カテゴリで振る舞いを分ける

`check_once` は、台帳の `category` を見て、3 通りに分かれます。

```python
# 引用: hub/health/runner.py::LivenessMonitor.check_once
async def check_once(self, entry: ToolEntry, *, now: Optional[float] = None) -> Optional[HealthResult]:
    """1ツール分のliveness評価を行う。categoryに応じて能動/受動/スキップを切り替える。"""
    now = now if now is not None else time.monotonic()

    if entry.category is ToolCategory.EXCLUDED:
        return None
    if entry.health_check is None:
        return None

    if entry.category is ToolCategory.OBSERVED_ONLY:
        # 受動監視のみ。record_heartbeatで既に受信済みのタイムスタンプに対する
        # ローカル計算であり、対象ツールへの能動的な接続は一切発生しない。
        if entry.health_check != "rpc_check":
            return None
        result = self._eval_rpc_check(entry, now)
        if result is not None:
            self._results[entry.tool_id] = result
            if result.is_up:
                self._last_up_at[entry.tool_id] = now
        return result

    # category is monitored: 能動チェック。poll_interval_sでレート制限する。
    last_polled = self._last_polled_at.get(entry.tool_id)
    if entry.poll_interval_s is not None and last_polled is not None:
        if now - last_polled < entry.poll_interval_s:
            return self._results.get(entry.tool_id)

    result = await self._dispatch_active(entry, now)
    self._last_polled_at[entry.tool_id] = now
    if result is not None:
        self._results[entry.tool_id] = result
        if result.is_up:
            self._last_up_at[entry.tool_id] = now
    return result
```

| カテゴリ | 振る舞い |
|---|---|
| `excluded` | **何もしない**(`None`) |
| `observed_only` | **受動だけ**(`rpc_check` のみ)。接続を開かない |
| `monitored` | `poll_interval_s` で**間引いた**能動の確認 |

**間引き**が大事です。`_poll_loop` は 5 秒おきに全員を見回しますが、`poll_interval_s: 30` のツールは、**30 秒たつまで前回の結果を返す**だけ。ツール側の自分の確認の間隔より、**Hub が頻繁に叩かない**(相手に負担をかけない)ための仕組みです。

```python
# 実行できる
import asyncio

from hub.health.runner import LivenessMonitor
from hub.registry import ToolEntry, ToolRegistry

entry = ToolEntry.from_dict({
    "tool_id": "demo_http", "display_name": "デモ", "transport": "http_bridge",
    "endpoint": "http://127.0.0.1:9/health", "health_check": "http_bridge_check",
    "category": "monitored", "poll_interval_s": 30, "check_params": {"timeout_s": 1.0},
})
monitor = LivenessMonitor(ToolRegistry([entry]))


async def main():
    first = await monitor.check_once(entry, now=100.0)       # 実際に叩く
    again = await monitor.check_once(entry, now=110.0)       # 10 秒後: 30 秒未満なので、叩かない
    print("1 回目 is_up:", first.is_up, "/ 10 秒後は同じ結果:", again is first)
    later = await monitor.check_once(entry, now=131.0)       # 31 秒後: 叩き直す
    print("31 秒後は新しい結果:", later is not first)
    print("確認済み?", monitor.has_checked("demo_http"))


asyncio.run(main())
```

```text
# 出力
1 回目 is_up: False / 10 秒後は同じ結果: True
31 秒後は新しい結果: True
確認済み? True
```

## 確認問題

1. `rpc_check` が「間隔の 2 倍」途絶するまで、停止と言わないのは、なぜですか。
2. 経過時間を測るのに `time.time()` でなく `time.monotonic()` を使うのは、なぜですか。
3. ハートビートが一度も無いツールの判定が `None` なのは、なぜですか。`False` や `True` ではだめですか。
4. `http_bridge_check` が、ステータス 404 を `is_up=True` にしないのは、なぜですか。
5. `poll_interval_s` で間引くのは、誰のためですか。

## 解答

1. 1 回の遅れ・取りこぼしを、すぐに「停止」と誤報しないため(2 回続けて途絶したら停止)。
2. 普通の時刻は、時計合わせで逆戻り・ジャンプするから。`monotonic` は必ず進むので、経過の計算が壊れない。
3. `True` だと、Hub の起動直後に**全員が偽の「正常」**になる。`False` だと、まだ何も起きていないのに**偽の「停止」**で通知が飛ぶ。「分からない」を、`None`(画面では未確認)で正直に表す。
4. 「何かが応答した」だけでは、期待の窓口が動いているとは言えない(エラー画面かもしれない)。200 だけを正常とする。
5. **監視される側**のため。相手の自分の確認の間隔より、Hub が頻繁に叩かない。

## まとめ

- 死活監視は 3 種類。**能動**(`http_bridge_check`)と、受信時刻から**計算するだけ**の受動(`rpc_check`・`ci_pipeline_check`)。
- 経過は `time.monotonic()`。「間隔の 2 倍」「期待の 1.5 倍」の余裕で、誤報を減らす。
- **信号が無い間は `None` = 未確認**。偽の「正常」を作らない。
- `LivenessMonitor` が、カテゴリで能動・受動・スキップを切り替え、`poll_interval_s` で間引く。
- 次の回は、判定の結果から生まれる**アラート**のライフサイクル。
