# 第 4 回 ツールの状態と、アラートの見る順番

> 所要時間の目安: 2.5 時間 / 前提: 第 1〜3 回

## この回のゴール

- ツール 1 件の状態(**正常・警告・停止・未確認・対象外**)が、**何から決まる**のかを説明できる。
- 「停止」と「警告」を分ける理由と、「未確認」がある理由を説明できる。
- **同じ規則を、ライブ表示と履歴の再現の両方で使う**設計の利点を説明できる。
- アラートの**見る順番**(緊急・通常・情報不足)が、どう計算されるか(ルールベース)を説明できる。
- 見る順番を**差し替える**ための拡張点(`Protocol`)を説明できる。

## 1. 5 つの状態

| 状態 | 記号 | 意味 |
|---|---|---|
| 停止 | ■ | 死活監視が down を返した、または死活監視由来のアラートが未解消 |
| 警告 | ▲ | 生きているが、**別のアラート**(しきい値超過・視覚回帰の失敗など)が未解消 |
| 正常 | ✓ | 死活監視が up で、未解消のアラートが無い |
| 未確認 | ○ | 死活監視の信号がまだ**一度も無く**、アラートも無い |
| 対象外 | – | 台帳で `category: excluded` |

**色だけに頼らず、記号と文字を必ず添える**(色が見えにくい人にも、モノクロの印刷でも読める)。絵文字は使わず、文字の記号だけ。

**「警告」を「重大度が warn」ではなく「停止ではない未解消アラートがある」で決める**のがコツです。
視覚回帰(VRQA)の失敗は重大度が `critical` ですが、**ツールは動いています**。これを「停止(■)」と見せると、「落ちている」と誤解する。重大度は、各アラートの行に別に出します。

## 2. 決めるのは、1 つの純関数

```python
# 引用: hub/tool_state.py::derive_tool_state
def derive_tool_state(
    entry: ToolEntry,
    *,
    is_up: Optional[bool],
    open_alerts: Iterable[AlertRecord],
    assume_ok_without_alerts: bool = False,
) -> ToolState:
    """死活監視の最新結果(is_up)と、そのツールの未解消アラートから状態を決める。

    is_upがNoneなのは「まだ死活監視の信号が無い」か、過去の時刻の再現で死活監視の結果そのものが
    残っていない場合。後者ではassume_ok_without_alerts=Trueにして、未解消のアラートが無いことを
    「正常」とみなす(履歴にはアラートの発生・解消しか残らないため、これが再現できる限界)。
    """
    if entry.category is ToolCategory.EXCLUDED:
        return ToolState.EXCLUDED

    liveness_id = health_check_alert_id(entry.tool_id)
    alerts = list(open_alerts)
    liveness_alert_open = any(a.alert_id == liveness_id for a in alerts)
    other_alert_open = any(a.alert_id != liveness_id for a in alerts)

    # 最新の死活監視がupなら、解消待ちの古いliveness alertより新しい結果を信じる
    if is_up is False or (is_up is None and liveness_alert_open):
        return ToolState.DOWN
    if other_alert_open:
        return ToolState.WARN
    if is_up is True or assume_ok_without_alerts:
        return ToolState.OK
    return ToolState.UNKNOWN
```

**純関数**(同じ入力には、いつも同じ出力。ファイル・時刻・グローバルを読まない)にしてあるので、テストが書きやすく、**どこからでも同じ規則で呼べます**。

読み方の要点:

1. `excluded` なら、他のことを見ずに `EXCLUDED`。
2. `is_up is False` → **停止**。`is_up is None` かつ死活監視のアラートが open → これも**停止**(信号は無いが、前に down で open した)。
3. 停止でなく、他のアラートが open → **警告**。
4. `is_up is True`(または、履歴の再現で `assume_ok_without_alerts=True`)→ **正常**。
5. どれでもない = 信号が無くアラートも無い → **未確認**。

「最新の死活監視が up なら、解消待ちの古い liveness アラートより、**新しい結果を信じる**」(コメント)。`is_up` が分かっているときはそれを優先し、`is_up is None`(信号なし)のときだけ、残っている死活監視のアラートを根拠にしているのは、そのためです。

```python
# 実行できる
from datetime import datetime, timezone

from hub.alert_aggregator import AlertRecord, Severity, health_check_alert_id
from hub.registry import ToolEntry
from hub.tool_state import derive_tool_state, state_glyph, state_label


def entry(category="monitored"):
    return ToolEntry.from_dict({"tool_id": "demo", "display_name": "デモ", "transport": "rpc", "endpoint": None,
                                "health_check": "rpc_check", "category": category})


def alert(alert_id, severity=Severity.CRITICAL):
    return AlertRecord(alert_id, "demo", severity, "テスト", first_seen_at=datetime(2026, 11, 1, tzinfo=timezone.utc))


liveness = alert(health_check_alert_id("demo"))
other = alert("demo:other0000000000", Severity.CRITICAL)

rows = [
    ("信号なし・アラートなし", dict(is_up=None, open_alerts=[])),
    ("up・アラートなし", dict(is_up=True, open_alerts=[])),
    ("down", dict(is_up=False, open_alerts=[])),
    ("up・別のアラート(critical)", dict(is_up=True, open_alerts=[other])),
    ("信号なし・死活監視のアラートが残っている", dict(is_up=None, open_alerts=[liveness])),
    ("up に戻った・古い死活監視のアラートが残っている", dict(is_up=True, open_alerts=[liveness])),
    ("履歴の再現(信号なし・アラートなし)", dict(is_up=None, open_alerts=[], assume_ok_without_alerts=True)),
]
for label, kwargs in rows:
    state = derive_tool_state(entry(), **kwargs)
    print(f"{state_glyph(state)} {state_label(state):4} ← {label}")
print("対象外:", state_label(derive_tool_state(entry("excluded"), is_up=False, open_alerts=[liveness])))
```

```text
# 出力
○ 未確認  ← 信号なし・アラートなし
✓ 正常   ← up・アラートなし
■ 停止   ← down
▲ 警告   ← up・別のアラート(critical)
■ 停止   ← 信号なし・死活監視のアラートが残っている
✓ 正常   ← up に戻った・古い死活監視のアラートが残っている
✓ 正常   ← 履歴の再現(信号なし・アラートなし)
対象外: 対象外
```

注目: **「up・別のアラート(critical)」は「警告」**(停止ではない)。**「up に戻った・古い死活監視のアラートが残っている」は「正常」**(最新の結果を信じる)。

## 3. 同じ規則を、2 か所で使う

状態を決める規則は、**ダッシュボードのコードから切り離して**あります(`hub/tool_state.py`)。理由:

- **ライブ表示**: 死活監視の最新結果 + いま open のアラート。
- **履歴スライダー**: 過去の時刻に open だったアラートだけ(死活監視の結果そのものは残っていないので `is_up=None` + `assume_ok_without_alerts=True`)。

**同じ関数**を使うので、一覧・オフィス表示・右のサマリ・履歴で、**状態が食い違わない**(テストでも確かめています)。規則を 2 か所に書くと、片方だけ直して、食い違う。

```python
# 実行できる
from datetime import datetime, timedelta, timezone

from hub.alert_aggregator import AlertRecord, Severity
from hub.registry import ToolEntry
from hub.tool_state import derive_tool_state, state_label

t0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
tool = ToolEntry.from_dict({"tool_id": "demo", "display_name": "デモ", "transport": "rpc", "endpoint": None,
                            "health_check": "rpc_check", "category": "monitored"})
history = [AlertRecord("demo:aaaa", "demo", Severity.WARN, "遅い", first_seen_at=t0, resolved_at=t0 + timedelta(minutes=30))]

for minutes in (-10, 10, 40):
    at = t0 + timedelta(minutes=minutes)
    open_then = [a for a in history if a.is_open_at(at)]
    state = derive_tool_state(tool, is_up=None, open_alerts=open_then, assume_ok_without_alerts=True)
    print(f"発生から {minutes:+3d} 分: open={len(open_then)} → {state_label(state)}")
```

```text
# 出力
発生から -10 分: open=0 → 正常
発生から +10 分: open=1 → 警告
発生から +40 分: open=0 → 正常
```

## 4. アラートの見る順番(補助)

アラートが何件も open のとき、**どれから見るか**の目安を付けます。ラベルは 3 つ: **緊急 / 通常 / 情報不足**。

```python
# 引用: hub/alert_priority.py::RuleBasedPriorityClassifier
class RuleBasedPriorityClassifier:
    """重大度・発生回数・停止かどうか・指標の直接/間接から目安のscoreを作り、ラベルへ落とす。"""

    def assess(self, alert: AlertRecord, *, tool_category: Optional[ToolCategory] = None) -> PriorityAssessment:
        message = (alert.message or "").strip()
        base = _SEVERITY_BASE[alert.severity]
        reasons = [f"重大度: {alert.severity.value}"]

        is_liveness = alert.alert_id == health_check_alert_id(alert.source_tool_id)
        score = base

        if is_liveness:
            score += 0.10
            reasons.append("死活監視で停止を検知")
        if alert.occurrence_count >= 3:
            score += 0.15
            reasons.append(f"再発 {alert.occurrence_count}回目")
        elif alert.occurrence_count == 2:
            score += 0.10
            reasons.append("再発 2回目")
        if not is_liveness and tool_category in (ToolCategory.OBSERVED_ONLY, ToolCategory.EXCLUDED):
            score -= 0.15
            reasons.append("他ツール経由の間接的な指標")

        score = round(min(1.0, max(0.0, score)), 2)

        if self._lacks_information(message):
            return PriorityAssessment(
                AlertPriority.INSUFFICIENT, score, (*reasons, "メッセージに原因の手掛かりが無い")
            )
        priority = AlertPriority.URGENT if score >= _URGENT_THRESHOLD else AlertPriority.NORMAL
        return PriorityAssessment(priority, score, tuple(reasons))

    @staticmethod
    def _lacks_information(message: str) -> bool:
        if len(message) < 6:
            return True
        return "unknown" in message.lower() and len(message) < _PLACEHOLDER_MAX_LEN
```

基準点(重大度)に、加点・減点をして、**0〜1 の目安 `score`** にします。

| 要素 | 点 |
|---|---|
| 重大度 | info 0.10 / warn 0.40 / critical 0.70 |
| 死活監視で停止 | +0.10 |
| 再発 2 回目 / 3 回以上 | +0.10 / +0.15 |
| 他ツール経由の**間接**の指標(`observed_only` など) | −0.15 |

`score ≥ 0.70` → **緊急**。それ未満 → **通常**。ただし、**メッセージが短すぎる・`unknown` だけ**など、原因の手掛かりが無いときは、点に関わらず **情報不足**。

**これは較正された確率ではなく、「目安」**です(画面にもそう書く)。重みの数値は、実運用のデータで調整したものではなく、**初期値**です。

```python
# 実行できる
from datetime import datetime, timezone

from hub.alert_aggregator import AlertRecord, Severity, health_check_alert_id
from hub.alert_priority import RuleBasedPriorityClassifier
from hub.registry import ToolCategory

classifier = RuleBasedPriorityClassifier()
t = datetime(2026, 11, 1, tzinfo=timezone.utc)

cases = {
    "VRQA の失敗(critical・動作中)": (AlertRecord("a:1", "a", Severity.CRITICAL, "pixel diff 3.4% over threshold", t), ToolCategory.MONITORED),
    "警告(warn)": (AlertRecord("a:2", "a", Severity.WARN, "polycount budget exceeded", t), ToolCategory.MONITORED),
    "警告・3 回目の再発": (AlertRecord("a:3", "a", Severity.WARN, "polycount budget exceeded", t, occurrence_count=3), ToolCategory.MONITORED),
    "間接の指標(critical)": (AlertRecord("a:4", "a", Severity.CRITICAL, "queue length is high", t), ToolCategory.OBSERVED_ONLY),
    "死活監視の停止": (AlertRecord(health_check_alert_id("a"), "a", Severity.CRITICAL, "a liveness check: down", t), ToolCategory.OBSERVED_ONLY),
    "メッセージが空に近い": (AlertRecord("a:5", "a", Severity.CRITICAL, "unknown", t), ToolCategory.MONITORED),
}
for label, (alert, category) in cases.items():
    r = classifier.assess(alert, tool_category=category)
    print(f"{r.label:4} score={r.score:.2f}  {label}")
```

```text
# 出力
緊急   score=0.70  VRQA の失敗(critical・動作中)
通常   score=0.40  警告(warn)
通常   score=0.55  警告・3 回目の再発
通常   score=0.55  間接の指標(critical)
緊急   score=0.80  死活監視の停止
情報不足 score=0.70  メッセージが空に近い
```

## 5. 差し替えられるように作る(`Protocol`)

見る順番を、将来 LLM などに替えたくなるかもしれません。そのための拡張点が `AlertPriorityClassifier`(**`Protocol`**)です。

```python
# 引用: hub/alert_priority.py::AlertPriorityClassifier
class AlertPriorityClassifier(Protocol):
    def assess(self, alert: AlertRecord, *, tool_category: Optional[ToolCategory] = None) -> PriorityAssessment: ...
```

`Protocol` は「**この形のメソッドを持っていればよい**」という約束(構造的な型付け)。継承は要りません。`create_app(classifier=...)` に渡せば、差し替わります。

**重要な設計判断**: この補助は**表示専用**で、**通知・dedup・resolve には一切つながっていません**。補助が壊れても、通知は従来どおり出る(テストで確かめている)。便利な機能と、必須の機能の**経路を分ける**考え方です。

```python
# 実行できる
from datetime import datetime, timezone

from hub.alert_aggregator import AlertRecord, Severity
from hub.alert_priority import AlertPriority, PriorityAssessment, RuleBasedPriorityClassifier


class AlwaysUrgentForSound:
    """自作の分類器: sound_middleware のアラートは、いつも緊急。ほかは既定のルールに任せる。"""

    def __init__(self):
        self._fallback = RuleBasedPriorityClassifier()

    def assess(self, alert, *, tool_category=None):
        if alert.source_tool_id == "sound_middleware":
            return PriorityAssessment(AlertPriority.URGENT, 1.0, ("sound は常に緊急(自作の規則)",))
        return self._fallback.assess(alert, tool_category=tool_category)


t = datetime(2026, 11, 1, tzinfo=timezone.utc)
classifier = AlwaysUrgentForSound()
for tool in ("sound_middleware", "learning_qt"):
    a = AlertRecord(f"{tool}:x", tool, Severity.INFO, "テスト用のメッセージです", t)
    r = classifier.assess(a)
    print(tool, "→", r.label, r.score, r.reasons)
```

```text
# 出力
sound_middleware → 緊急 1.0 ('sound は常に緊急(自作の規則)',)
learning_qt → 通常 0.1 ('重大度: info',)
```

## 確認問題

1. VRQA の失敗(重大度 `critical`)で、ツールの状態が「停止」でなく「警告」になるのは、なぜですか。
2. 信号が一度も無いツールが「未確認」になる意味を、「正常」「停止」との違いで説明してください。
3. 状態を決める関数を、ダッシュボードの中に書かず、`tool_state.py` に分けたのは、なぜですか。
4. `score` が 0.9 でも「情報不足」になることがあるのは、なぜですか。
5. 見る順番の補助を、通知の経路につなげなかったのは、なぜですか。

## 解答

1. ツールは**動いている**から。重大度は「どれだけ問題か」で、「動いているか」とは別。「停止」と見せると、落ちていると誤解する。
2. 「正常」は、up を**確認できた**。「停止」は、down を**確認できた**。「未確認」は、**まだ確かめられていない**。偽の「正常」「停止」を出さず、分からないことを正直に示す。
3. ライブ表示と履歴の再現で、**同じ規則**を使うため。2 か所に書くと、片方だけ直して食い違う。純関数なので、テストも書きやすい。
4. メッセージに**原因の手掛かりが無い**(短すぎる・`unknown` だけ)と、点が高くても、何を見ればよいか分からないので、「情報不足」を優先する。
5. 補助が壊れたり、誤った順番を付けたりしても、**肝心の通知が止まらない**ようにするため(必須の機能と、便利な機能の経路を分ける)。

## まとめ

- 状態は 5 つ。**死活監視の最新結果 + 未解消のアラート**から、1 つの純関数で決める。「停止」と「警告」を分け、「未確認」で偽の正常を作らない。
- ライブと履歴で同じ関数を使うので、状態が食い違わない。
- 見る順番は、ルールベースの**目安**(確率ではない)。`Protocol` で差し替えられ、通知とは独立。
- 次の回は、Hub 自身を守る**入口**(Host・Origin・API キー・役割・監査ログ)。
