"""profiling_tool/dashboard/main.py

`profiling-dashboard`コマンドのエントリポイント(スタンドアロン起動用、オプション)。
日常利用はToolOrchestrationHub本体のダッシュボード(`uv run hub`)経由が主。
"""

from __future__ import annotations

import argparse


def run() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="profiling-dashboard", description="ProfilingTool standalone dashboard"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run("profiling_tool.dashboard.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    run()
