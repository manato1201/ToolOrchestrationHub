"""hub/main.py

`hub`コマンドのエントリポイント。Phase4ダッシュボード(FastAPI)をuvicornで起動する。
"""

from __future__ import annotations

import argparse


def run() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="hub", description="ToolOrchestrationHub dashboard"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "hub.dashboard.app:app", host=args.host, port=args.port, reload=args.reload
    )


if __name__ == "__main__":
    run()
