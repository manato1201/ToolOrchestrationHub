"""hub/main.py

`hub`コマンドのエントリポイント。Phase4ダッシュボード(FastAPI)をuvicornで起動する。
"""

from __future__ import annotations

import argparse
import sys

from .security import ALLOWED_HOSTS_ENV, extend_allowed_hosts_env, is_loopback_host


def run() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(
        prog="hub", description="ToolOrchestrationHub dashboard"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if not is_loopback_host(args.host):
        # HubのAPIには認証が無い(起動・git pull・アラートの変更ができる)。LAN等へ公開すると、
        # そのネットワークの誰でも操作できる。意図した場合だけ使うこと。
        extend_allowed_hosts_env(args.host)
        print(
            f"警告: --host {args.host} は認証がありません。このネットワークの誰でもHubの起動・同期・アラート操作を"
            f"実行できます。公開する意図がなければ --host 127.0.0.1 のままにしてください。"
            f"別のホスト名で開く場合は環境変数 {ALLOWED_HOSTS_ENV} に追加が必要です。",
            file=sys.stderr,
        )

    uvicorn.run(
        "hub.dashboard.app:app", host=args.host, port=args.port, reload=args.reload
    )


if __name__ == "__main__":
    run()
