"""docs/diagrams/ の構成図(SVG)を作る。直すときは、ここを直して `python tools/make_diagrams.py` を実行する。

  architecture.svg   全体の構成(監視される側のツール・Hub の中身・利用者と通知・外部リポジトリの操作)

部品は tools/svgkit.py。座標は手で決める。決まり: ①矢印はカードの横(か上)から出入り(カードの下には文字がある)
②縦に渡るときは、カードの間のすき間を通る ③流れの説明は、図に詰めず、本文の Mermaid(シーケンス図)に書く。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from svgkit import Diagram  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagrams"


def architecture() -> Diagram:
    d = Diagram(1700, 990, "ToolOrchestrationHub の構成",
                "監視される側のツールは、ハートビート・CI 成功・アラートを Hub の FastAPI へ送る。Hub は、台帳(registry)のツールを LivenessMonitor で見て、"
                "AlertAggregator が重複をまとめ、SQLite に保存し、トーストと Slack で知らせる。ダッシュボードは、同じ状態を読むだけ。"
                "リポジトリの同期と起動は、人がボタンを押したときだけ動く。")
    d.text(40, 44, "ToolOrchestrationHub — 構成", cls="hd")
    d.text(40, 66, "青=主な流れ / 灰の破線=補助 / 監視だけ(ツールの権限は奪わない)。能動の確認は http_bridge だけで、あとは相手からの信号を待つ", cls="note")

    # ---- 左: 監視される側 ----
    d.group(40, 100, 250, 640, "TOOLS — 監視される側", color="gray")
    http = d.card(150, 190, "server", "http_bridge 系", "dev_rag_environment\nprofiling_tool")
    rpc = d.card(150, 340, "pulse", "rpc 系", "lore・sound・learning_qt\n(相手が信号を送る)")
    ci = d.card(150, 490, "clock", "CI / cron 系", "the_algorithm・research\nasset・vrqa")
    snd = d.card(150, 640, "chart", "アラートの送り手", "Profiling・VRQA\nAsset Data Insight")

    # ---- 中央: Hub ----
    d.group(480, 100, 860, 640, "HUB — FASTAPI (hub/)", color="teal")
    reg = d.card(640, 190, "list", "registry", "registry.yaml (12 件)\n5 秒でホットリロード")
    store = d.card(1160, 190, "db", "alert_store", "SQLite (.hub_state/)\n解消後 30 日で削除")
    app = d.card(640, 415, "terminal", "app.py", "heartbeat・ci-success・\nアラートの受け口")
    mon = d.card(900, 415, "pulse", "LivenessMonitor", "http / rpc / ci の\n3 種の死活監視")
    agg = d.card(1160, 415, "tag", "AlertAggregator", "alert_id で 1 件にまとめる\nopen → resolved")
    dash = d.card(1160, 640, "browser", "dashboard", "tool_state・overview\n状態の決め方は 1 か所")
    d.text(500, 722, "入口の検査: security.py(Host・Origin)・auth.py(API キー・役割)・audit.py(監査ログ)", cls="note")

    # ---- 右: 利用者と通知 ----
    d.group(1420, 100, 240, 640, "OUTPUT — 利用者", color="blue")
    notify = d.card(1530, 415, "cloud", "通知", "Windows トースト\nSlack Webhook")
    user = d.card(1530, 640, "user", "利用者(ブラウザ)", "/ は viewer 以上\n/admin は admin だけ")

    # ---- 下: 外部リポジトリ ----
    d.group(480, 790, 860, 170, "REPOS — 外部リポジトリ(人が押したときだけ)", color="purple")
    sync = d.card(640, 860, "branch", "repo_sync", "git fetch は自動\npull は人が押す")
    repos = d.card(900, 860, "folder", "13 リポジトリ", "repos.yaml")
    launch = d.card(1160, 860, "terminal", "process_launcher", "固定のコマンドを\n新しい窓で開く")

    # ---- 矢印 ----
    d.arrow([http.right, (420, 190), (420, 322), (882, 322), (882, 383)][::-1], "GET /health(Hub から確認)", at=1, dx=-215, dy=-10)
    d.arrow([rpc.right, (540, 340), (540, 415), app.left], "heartbeat", at=0)
    d.arrow([ci.right, (540, 490), (540, 415), app.left], "ci-success", at=0)
    d.arrow([snd.right, (540, 640), (540, 415), app.left], "POST /api/alerts/*", at=0)
    d.arrow([reg.right, (918, 190), (918, 383)], "台帳の一覧", at=0)
    d.arrow([app.right, mon.left], "record_heartbeat", at=0)
    d.arrow([mon.right, agg.left], "down / up", at=0)
    d.arrow([app.top, (640, 350), (1144, 350), (1144, 383)], "アラート受信 → ingest", kind="secondary", at=1, dy=-10)
    d.arrow([(1176, 383), (1176, 330), (1260, 330), (1260, 190), store.right], "save", at=2, dx=22, dy=0)
    d.arrow([agg.right, notify.left], "on_open / on_resolve", at=0)
    d.arrow([(1192, 415), (1300, 415), (1300, 540), (1160, 540), (1160, 608)], "状態を読む", kind="secondary", at=2, dy=-10)
    d.arrow([dash.right, user.left], "HTML / JSON", at=0)
    d.arrow([sync.right, repos.left], "fetch / pull --ff-only", kind="secondary", at=0)
    d.arrow([launch.left, repos.right], "起動", kind="secondary", at=0)
    return d


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "architecture.svg").write_text(architecture().svg(), encoding="utf-8")
    print("wrote", OUT / "architecture.svg")


if __name__ == "__main__":
    main()
