# 7. 基礎の補強(言語・設計思想・アルゴリズム・用語)

講義と学習資料の**前提になっている知識**を、ここで補います。「Python の基本」と書いてあったものを、**この Hub のコードで実際に使われている形**で、動かして確かめます。

## 1. 言語の基礎: Hub で使う Python

### 1.1 型ヒントと `Optional`(`X | None`)

型ヒントは、**実行には影響しない注釈**です(読む人と、型検査ツールのため)。`Optional[str]` と `str | None` は同じで、「文字列か、無いこと(`None`)」。**`None` かもしれない値は、使う前に確かめる**。

```python
# 実行できる
from typing import Optional


def describe(last_seen: Optional[float], now: float) -> str:
    if last_seen is None:                      # None を先に処理する(信号がまだ一度も無い)
        return "未確認"
    return f"{now - last_seen:.0f} 秒前"


print(describe(None, 100.0))
print(describe(70.0, 100.0))
```

```text
# 出力
未確認
30 秒前
```

### 1.2 `Enum`(`str` を継ぎ足す)と、並べ替えのキー

`class ToolState(str, Enum)` は、**決まった値の集まり**を作る。`str` も継ぐので、JSON にそのまま `"ok"` と書ける。表(`STATE_META`)に**日本語・記号・順位**を持たせ、`sorted(..., key=...)` で**問題のあるものが先**に並ぶ。

```python
# 実行できる
from hub.tool_state import STATE_META, ToolState

print([s.value for s in ToolState])
states = [ToolState.OK, ToolState.DOWN, ToolState.WARN, ToolState.UNKNOWN]
ordered = sorted(states, key=lambda s: STATE_META[s][2])      # 3 つ目が「並べ替えの順位」
print([STATE_META[s][0] for s in ordered])
print("str としても比べられる:", ToolState.OK == "ok")
```

```text
# 出力
['ok', 'warn', 'down', 'unknown', 'excluded']
['停止', '警告', '未確認', '正常']
str としても比べられる: True
```

### 1.3 `@dataclass`(`frozen=True`)

**データを持つだけのクラス**を、短く書く。`frozen=True` は**作ったあと書き換えられない**(不変)。設定・登録の 1 件(`ToolEntry`・`Principal`)に向く。**誰かが途中で書き換えて、別の場所の挙動が変わる**事故を防ぐ。

```python
# 実行できる
from dataclasses import FrozenInstanceError, dataclass, replace


@dataclass(frozen=True)
class Entry:
    tool_id: str
    interval_s: float = 60.0


e = Entry("rag")
print(e)
try:
    e.interval_s = 5.0
except FrozenInstanceError:
    print("書き換えは拒否される")
print("変えたいときは、新しいものを作る:", replace(e, interval_s=5.0))
```

```text
# 出力
Entry(tool_id='rag', interval_s=60.0)
書き換えは拒否される
変えたいときは、新しいものを作る: Entry(tool_id='rag', interval_s=5.0)
```

### 1.4 `Protocol`(構造的な型)

`NotificationSink` は **「`send` を持つもの」という約束**だけを決める。**継承しなくても**、同じ形のメソッドを持てば、その型として扱える(ダックタイピングに型を付けたもの)。`Slack`・`Windows の通知`・`何もしない(Null)` を、**呼ぶ側を変えずに差し替えられる**。

```python
# 実行できる
from typing import Protocol


class Sink(Protocol):
    def send(self, message: str) -> None: ...


class PrintSink:                      # Sink を継承していない
    def send(self, message: str) -> None:
        print("通知:", message)


class NullSink:
    def send(self, message: str) -> None:
        pass


def notify_all(sinks: list[Sink], message: str) -> None:
    for sink in sinks:
        sink.send(message)             # どの Sink か、ここでは知らない


notify_all([PrintSink(), NullSink()], "ツール A が停止")
```

```text
# 出力
通知: ツール A が停止
```

### 1.5 デコレーターと `with`(ロック)

`@something` は、**関数を包んで機能を足す**書き方(FastAPI の `@app.get("/path")` は、「この関数をこの URL に結びつける」)。`with lock:` は、**入るときに鍵を取り、出るときに(例外でも)必ず返す**。複数のスレッドが同じ値を同時に書き換えないために使う(`audit.py` の `_lock`)。

```python
# 実行できる
import threading

calls = []


def traced(func):
    def wrapper(*args):
        calls.append(func.__name__)
        return func(*args)
    return wrapper


@traced
def add(a, b):
    return a + b


lock = threading.Lock()
counter = 0


def bump():
    global counter
    for _ in range(1000):
        with lock:                      # 同時に 1 つのスレッドだけが入れる
            counter += 1


threads = [threading.Thread(target=bump) for _ in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(add(1, 2), calls, "カウンター:", counter)
```

```text
# 出力
3 ['add'] カウンター: 4000
```

### 1.6 `async` / `await`

`async def` は、**待つ間に他の仕事をさせられる関数**。`await` は「ここで結果を待つ(その間、他が動く)」。HTTP の呼び出しや `git` の実行など、**待ち時間が長い処理**を、スレッドを増やさずに並べる。

```python
# 実行できる
import asyncio


async def check(name: str, wait: float) -> str:
    await asyncio.sleep(wait)           # ネットワークを待つ、の代わり
    return f"{name}: 応答あり"


async def main():
    results = await asyncio.gather(check("a", 0.02), check("b", 0.01), check("c", 0.03))
    print(results)                      # gather は、呼んだ順で結果を返す


asyncio.run(main())
```

```text
# 出力
['a: 応答あり', 'b: 応答あり', 'c: 応答あり']
```

## 2. 設計思想

| 原則 | 意味 | Hub のどこに出るか | 破るとどうなるか |
|---|---|---|---|
| **見るだけ(単一障害点にならない)** | 監視役が、監視される側を壊さない・止めない | 死活監視は読むだけ。例外は人が押す起動と `git pull` | Hub の不具合で、全ツールが止まる |
| **偽の「正常」を出さない** | 分からないことは、**分からない**と表示する | 信号が無い間は「**未確認**」(`ToolState.UNKNOWN`) | 動いていないツールを「正常」と信じる |
| **判定は純関数に切り出す** | 画面・保存先と分け、同じ規則を何度でも使う | `tool_state.py`(ライブと過去の再現で同じ規則) | 画面ごとに規則が食い違う |
| **差し替えられる口(Protocol)** | 具体的な実装に依存しない | `NotificationSink`・`AlertStore` | 通知先を足すたびに、呼ぶ側を直す |
| **依存の向きを一方向に** | 循環 import を避ける | `alert_store.py → alert_aggregator.py`(逆はしない) | 循環 import で起動できない |
| **fail-closed** | 設定が足りないとき、通さずに閉じる | 認証・Host / Origin の検査 | 設定漏れが、そのまま穴になる |
| **色だけに頼らない** | 記号と文字を併記する | `STATE_META` の日本語・記号 | 色が見分けられない人に伝わらない |
| **1 件にまとめて、解消まで追う** | 同じ異常の通知を何十回も出さない | `AlertAggregator`(id で重複排除) | 通知が洪水になり、本当の異常が埋もれる |

## 3. 関数・アルゴリズム

| 名前 | 場所 | 何をする | 計算量・注意 |
|---|---|---|---|
| **経過時間のしきい値判定** | `health/rpc_check.py` | 最後の信号からの経過が `間隔 × 2` を超えたら停止 | O(1)。**時計の差**で判定するので、時計が巻き戻ると誤判定しうる |
| **id による重複排除** | `alert_aggregator.py` | 辞書(`dict`)で「同じ id の未解消」を 1 件にする | 平均 O(1)(ハッシュ表) |
| **キー付きの並べ替え** | `tool_state.py` | `sorted(key=順位)`。**安定ソート**(同順位は元の順) | O(n log n) |
| **一定時間の比較** | `auth.py` | `hmac.compare_digest`: 一致の**位置**が、応答時間に出ない | O(n)。`==` は、最初の違いで止まるので、時間から推測されうる |
| **ハッシュ化** | `auth.py` | 鍵・パスワードを、**元に戻せない値**にして保存・比較 | 一方向。同じ入力は同じ値 |
| **加点式の優先度** | `alert_priority.py` | 重大度の基礎点(0.10 / 0.40 / 0.70)に、死活監視 +0.10・再発(2 回 +0.10、3 回以上 +0.15)・間接的な指標 −0.15 を足し引きし、**0.70 以上で「緊急」** | O(1)。**しきい値と加減点は目安**(根拠を `reasons` に残す) |

```python
# 実行できる
import hashlib
import hmac

stored = hashlib.sha256(b"secret-key").hexdigest()          # 保存するのは、ハッシュだけ
print("ハッシュの長さ:", len(stored))
print("正しい鍵:", hmac.compare_digest(stored, hashlib.sha256(b"secret-key").hexdigest()))
print("違う鍵:", hmac.compare_digest(stored, hashlib.sha256(b"other").hexdigest()))

# 辞書による重複排除: 同じ id は 1 件
alerts = {}
for alert_id in ["a:down", "a:down", "b:slow", "a:down"]:
    alerts.setdefault(alert_id, 0)
    alerts[alert_id] += 1
print(alerts)
```

```text
# 出力
ハッシュの長さ: 64
正しい鍵: True
違う鍵: False
{'a:down': 3, 'b:slow': 1}
```

## 4. IT の用語の補強

| 用語 | 意味 | この Hub での出番 |
|---|---|---|
| **ハートビート** | 相手が「生きています」と**定期的に知らせる**信号 | `rpc_check`・`ci_pipeline_check` |
| **ポーリング** | こちらから**定期的に聞きに行く**方式 | `http_bridge_check` |
| **死活監視** | 動いているかを確かめること | `health/` |
| **単一障害点(SPOF)** | そこが壊れると全体が止まる所 | Hub が、なってはいけないもの |
| **ASGI / FastAPI** | Python の非同期 Web の仕組み / その上のフレームワーク | `dashboard/`・`main.py` |
| **CORS / Origin / Host** | ブラウザが別のサイトから呼べるかの取り決め / 呼んだ元 / 宛先の名前 | `security.py`(DNS rebinding 対策) |
| **RBAC** | 役割(ロール)で操作を許す仕組み | `auth.py` |
| **監査ログ** | 誰がいつ何をしたかの**追記専用**の記録 | `audit.py` |
| **Webhook** | 出来事を、相手の URL へ HTTP で知らせる | `SlackWebhookSink` |
| **ランブック(runbook)** | 障害のときの**手順書** | `runbooks.yaml` |
| **flaky** | 同じ条件でも、成功したり失敗したりする不安定なテスト | VRQA との連携 |
| **冪等(べきとう)** | 何回やっても、結果が同じ | アラートの重複排除 |
| **SQLite** | ファイル 1 つの軽いデータベース | `alert_store.py` |

## 確認問題

1. `@dataclass(frozen=True)` にする利点は何ですか。
2. `Protocol` を使うと、通知先を足すときに、呼ぶ側を直さなくてよいのは、なぜですか。
3. 「未確認」という状態があるのは、設計のどんな原則からですか。
4. `hmac.compare_digest` を、`==` の代わりに使うのは、なぜですか。

## 解答

1. 作ったあとに書き換えられず、別の場所の挙動が、知らないうちに変わる事故を防げる。
2. 呼ぶ側は「`send` を持つもの」としか知らないので、同じ形の新しい型を足すだけで済む。
3. 偽の「正常」を出さない(分からないことは、分からないと表示する)。
4. `==` は最初の違いで止まるので、応答時間から、どこまで合っているかを推測されうる。一定時間で比べると、それができない。
