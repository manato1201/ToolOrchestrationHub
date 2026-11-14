# 第 1 回 台帳(registry): 監視する相手をデータで持つ

> 所要時間の目安: 2 時間 / 前提: 第 0 回

## この回のゴール

- 台帳の 1 件(`ToolEntry`)の**必須の項目**と、それぞれの意味を説明できる。
- 壊れた台帳(未知の種別・欠けた項目・循環した依存)が、**読み込み時に弾かれる**ことを確かめられる。
- 台帳が**再起動なしで反映される**仕組み(ホットリロード)を説明できる。
- 「Hub が壊れた台帳で止まらない」ための工夫を説明できる。

## 1. 台帳の 1 件

`registry.yaml` の 1 件は、`ToolEntry`(データクラス)になります。

| 項目 | 意味 | 値の例 |
|---|---|---|
| `tool_id` | 他の場所から指す名前(重複禁止) | `sound_middleware` |
| `display_name` | 画面に出す名前 | `Sound Middleware` |
| `transport` | ツールとの**つなぎ方**(4 種) | `http_bridge` / `rpc` / `cli_batch` / `static_site` |
| `endpoint` | 能動で叩く URL(無ければ `null`) | `http://127.0.0.1:8766/health` |
| `health_check` | どの死活監視を使うか(関数名。無ければ `null`) | `rpc_check` |
| `category` | Hub がどう関わるか(3 種) | `monitored` / `observed_only` / `excluded` |
| `poll_interval_s` | 能動の確認の**最小間隔**(秒) | `30` |
| `check_params` | 判定のパラメータ | `heartbeat_interval_s: 10` |

**任意**の項目(未指定でも動く): `isolation`(隔離方式の方針)・`owner_rules`・`symbol` / `color`(画面の記号と色)・`description` / `concerns` / `todo`(メモ)・`depends_on`(使っているツール)。

```python
# 引用: hub/registry.py::TransportKind
class TransportKind(str, Enum):
    """統合対象棚卸し表で実際に登場した4パターン。新規に発明した抽象ではない。"""

    HTTP_BRIDGE = "http_bridge"  # 例: DevelopmentRAGEnvironmentの:8766ブリッジ
    RPC = "rpc"  # 例: LoreDesktopAndWebSystemのQLocalSocket、SoundMiddlewareの独自RPC
    CI_BATCH = "cli_batch"  # 例: Research-Collectorのcron実行、AssetDataInsightSuiteのCI定期実行
    STATIC_SITE = "static_site"  # 例: The-Algorithm-Illustrated、ColorEncyclopedia(監視対象外)
```

> **`str, Enum` と書く理由**: 値が文字列そのもの(`"rpc"`)として比べられ、YAML や JSON と相互に変換しやすい。未知の値は `TransportKind("ftp")` が `ValueError` を出すので、**打ち間違いをその場で見つけられる**。

## 2. 読み込み時に弾く

`ToolEntry.from_dict` は、YAML の 1 件(辞書)を、検査しながら `ToolEntry` にします。壊れていれば `RegistryError`(自作の例外)を出します。

```python
# 実行できる
from hub.registry import RegistryError, ToolEntry

good = {
    "tool_id": "demo",
    "display_name": "デモ",
    "transport": "http_bridge",
    "endpoint": "http://127.0.0.1:9/health",
    "health_check": "http_bridge_check",
    "category": "monitored",
    "poll_interval_s": 30,
}
entry = ToolEntry.from_dict(good)
print(entry.tool_id, entry.transport.value, entry.category.value, entry.poll_interval_s)

bads = {
    "必須項目が足りない": {"tool_id": "x"},
    "未知の transport": {**good, "transport": "ftp"},
    "色の形が違う": {**good, "color": "red"},
    "symbol が長すぎる": {**good, "symbol": "abc"},
    "depends_on が文字列": {**good, "depends_on": "other"},
}
for label, raw in bads.items():
    try:
        ToolEntry.from_dict(raw)
    except RegistryError as exc:
        message = str(exc).removeprefix("demo: ")   # 先頭の「どのツールか」を除く
        print(label, "→", message.split(":")[0].split("(")[0])
```

```text
# 出力
demo http_bridge monitored 30
必須項目が足りない → ToolEntryに必須フィールドが不足しています
未知の transport → 未知のtransport種別です
色の形が違う → colorは#rrggbb形式で指定してください
symbol が長すぎる → symbolは1〜2文字の文字列で指定してください
depends_on が文字列 → depends_onは文字列のリストで指定してください
```

「何が悪いか」を、**どのツールの何の項目か**まで書いたメッセージにして、台帳を直す人が迷わないようにしています(出力は、見やすいように先頭だけ表示しました)。

## 3. 依存の循環を弾く

`depends_on` は「このツールが使っているツール」。障害が**どこまで波及するか**の木(「波及の見込み」)を作るために使います。
循環(A→B→A)があると、木が**終わらなくなる**ので、読み込み時に弾きます(ホットリロードでも同じ検査を通る)。

```python
# 引用: hub/registry.py::_validate_dependencies
def _validate_dependencies(entries: dict[str, ToolEntry]) -> None:
    """depends_onが、存在するツールだけを指し、自分自身や循環を含まないことを確かめる。

    循環があると「原因の木」(障害の波及の表示)が終わらなくなるため、読み込み時に弾く。
    ホットリロードでも同じ検証を通るので、壊れた台帳に置き換わることはない。
    """
    for entry in entries.values():
        for dep in entry.depends_on:
            if dep == entry.tool_id:
                raise RegistryError(f"{entry.tool_id}: depends_onに自分自身は指定できません")
            if dep not in entries:
                raise RegistryError(f"{entry.tool_id}: depends_onの{dep!r}は台帳にありません")

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(tool_id: str, path: list[str]) -> None:
        if tool_id in done:
            return
        if tool_id in visiting:
            cycle = " -> ".join([*path[path.index(tool_id):], tool_id])
            raise RegistryError(f"depends_onが循環しています: {cycle}")
        visiting.add(tool_id)
        for dep in entries[tool_id].depends_on:
            visit(dep, [*path, tool_id])
        visiting.discard(tool_id)
        done.add(tool_id)

    for tool_id in entries:
        visit(tool_id, [])
```

これは**深さ優先探索**(DFS)です。「いま辿っている途中の印」(`visiting`)と「調べ終えた印」(`done`)の 2 つの集合で、**途中の印のあるものに戻ってきたら循環**と分かります。

```python
# 実行できる
from hub.registry import RegistryError, ToolEntry, ToolRegistry


def make(tool_id, depends_on=()):
    return ToolEntry.from_dict({
        "tool_id": tool_id, "display_name": tool_id, "transport": "rpc", "endpoint": None,
        "health_check": "rpc_check", "category": "observed_only", "depends_on": list(depends_on),
    })


cases = {
    "正しい(c → b → a)": [make("a"), make("b", ["a"]), make("c", ["b"])],
    "自分自身": [make("a", ["a"])],
    "存在しない相手": [make("a", ["zzz"])],
    "循環(a → b → a)": [make("a", ["b"]), make("b", ["a"])],
    "tool_id の重複": [make("a"), make("a")],
}
for label, entries in cases.items():
    try:
        ToolRegistry(entries)
        print(label, "→ OK")
    except RegistryError as exc:
        print(label, "→", exc)
```

```text
# 出力
正しい(c → b → a) → OK
自分自身 → a: depends_onに自分自身は指定できません
存在しない相手 → a: depends_onの'zzz'は台帳にありません
循環(a → b → a) → depends_onが循環しています: a -> b -> a
tool_id の重複 → tool_idが重複しています: a
```

## 4. ホットリロード(再起動なしで反映する)

`registry.yaml` を編集したら、Hub を**再起動せずに**反映したい。方法は単純で、**ファイルの更新時刻(mtime)を 5 秒おきに見る**だけです。

```python
# 引用: hub/registry.py::ToolRegistry.has_changed_on_disk
def has_changed_on_disk(self) -> bool:
    """load()/reload()以降にsource_pathのmtimeが変化したか(ホットリロードの判定用)。"""
    return self._stat_mtime(self._source_path) != self._loaded_mtime
```

```python
# 引用: hub/registry.py::ToolRegistry.reload
def reload(self, path: Optional[Path | str] = None) -> "ToolRegistry":
    """静的ファイルを再読込する。v1の「再起動なし反映」要件を満たす最小実装。

    pathを省略した場合は直近load()したパス(source_path)を再読込する。
    """
    target = Path(path) if path is not None else self._source_path or DEFAULT_REGISTRY_PATH
    fresh = ToolRegistry.load(target)
    self._entries_by_id = fresh._entries_by_id
    self._source_path = fresh._source_path
    self._loaded_mtime = fresh._loaded_mtime
    return self
```

大事な順序: **新しい台帳を先に読み込んで検証し(`fresh`)、成功したときだけ中身を入れ替える**。書き換え途中の壊れた YAML を読んでも、`load` が例外を出して**古い台帳がそのまま残る**。
監視ループ側は、その例外(`RegistryError`)だけを捕まえて、次の 5 秒後に再試行します(`hub/dashboard/app.py` の `_registry_watch_loop`)。

```python
# 実行できる
import os
import tempfile
from pathlib import Path

from hub.registry import RegistryError, ToolRegistry

YAML = """tools:
  - tool_id: demo
    display_name: デモ
    transport: rpc
    endpoint: null
    health_check: rpc_check
    category: observed_only
"""

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "registry.yaml"
    path.write_text(YAML, encoding="utf-8")
    registry = ToolRegistry.load(path)
    print("最初:", [e.tool_id for e in registry.all()], "変わった?", registry.has_changed_on_disk())

    path.write_text(YAML + YAML.split("tools:\n")[1].replace("demo", "second"), encoding="utf-8")
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 10))  # 更新時刻を進める
    print("編集後: 変わった?", registry.has_changed_on_disk())
    registry.reload()
    print("再読込:", [e.tool_id for e in registry.all()])

    path.write_text("tools: [この行は壊れた: YAML", encoding="utf-8")
    os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 20))
    try:
        registry.reload()
    except RegistryError:
        print("壊れた YAML は拒否。残っているのは:", [e.tool_id for e in registry.all()])
```

```text
# 出力
最初: ['demo'] 変わった? False
編集後: 変わった? True
再読込: ['demo', 'second']
壊れた YAML は拒否。残っているのは: ['demo', 'second']
```

## 5. 台帳を「データ」にした理由

- **ツールを足すのに、コードを触らない**。`registry.yaml` に 1 件書いて保存すれば、5 秒で画面に出る。
- **判断の置き場所が 1 つ**。どの死活監視を使うか・間隔はいくつかが、ツール側のコードでなく台帳に載る。
- 暫定値(`poll_interval_s` など)は、ツール側の実装が固まったら、**台帳だけを直せば追従**できる。

## 確認問題

1. `ToolEntry.from_dict` が例外を出すとき、`RegistryError` という**自作の例外**にそろえているのは、なぜですか。
2. 依存の循環を、読み込み時に弾くのは、なぜですか。
3. `reload()` が「先に読み込み、成功したら入れ替える」順序なのは、なぜですか。
4. `category: excluded` と、台帳に載せないことの違いは。

## 解答

1. 呼び出し側(監視ループ・リロードの API)が、**`RegistryError` だけを捕まえれば足りる**ようにするため。YAML の構文エラーなど別の例外も、ここでラップしている。
2. 「波及の見込み」の木を作る処理が、**終わらなくなる**から。画面を出すときに無限ループにならないよう、入口で止める。
3. 書き換え途中の壊れたファイルを読んでも、**古い台帳が残り**、Hub が止まらないようにするため。
4. `excluded` は、台帳(と画面)には**載るが、監視しない**。載せなければ、存在そのものが画面から消える。

## まとめ

- 台帳は YAML のデータで、1 件が `ToolEntry`。種別は `Enum` で、打ち間違いは読み込み時に弾く。
- 依存の循環・自分自身・存在しない相手・重複も、読み込み時に弾く(DFS)。
- ホットリロードは、更新時刻の監視+「検証してから入れ替える」。壊れた台帳でも Hub は止まらない。
- 次の回は、台帳の `health_check` が指す、**3 種類の死活監視**。
