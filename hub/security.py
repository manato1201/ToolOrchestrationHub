"""hub/security.py

Hub自身のHTTP面(認証なしのローカルAPI)を、ブラウザ経由の攻撃から守る最小限の検査。

HubはlocalhostでAPIを公開し、認証を持たない。そのためブラウザで別のサイトを開いているだけで、
そのページのスクリプトが次の2通りでHubを操作できてしまう:

1. **別サイトからの変更操作(CSRF)**: `POST /api/repos/{id}/launch/0`(起動)・`/sync`(git pull)・
   `/open-folder`・スヌーズなどは、本文の無い単純なPOSTなのでプリフライトなしで送られ、実行される。
2. **DNS rebinding**: 攻撃者のドメインが127.0.0.1に解決されるようにして、同一オリジンとして
   Hubの応答(アラート・パス等)を読む。

対策は次の2つ(どちらもブラウザが必ず付けるヘッダを見るだけ):
- **Hostヘッダの許可リスト**: 既定はループバック(127.0.0.1 / localhost / ::1)のみ。DNS rebindingでは
  Hostが攻撃者のドメインになるため弾ける。LANやTailscale越しに開く場合は環境変数 HUB_ALLOWED_HOSTS
  (カンマ区切り)に足す。
- **変更操作(POST/PUT/PATCH/DELETE)のOriginが、そのリクエスト自身のHostと一致すること**。
  Originを付けないクライアント(curl・各ツールからのheartbeat/alert送信・ProfilingToolのSink)は
  ブラウザではないので通す。`Origin: null` と、別のポートのページ(同じlocalhostでも別オリジン)は弾く。

認証そのものは入れていない(ローカル専用の前提を変えない)。非ループバックのhostで起動したときは
hub/main.pyが警告を出す。詳細と点検の結果は docs/SECURITY_REVIEW_2026-10.md。
"""
from __future__ import annotations

import os
from typing import Iterable, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ALLOWED_HOSTS_ENV = "HUB_ALLOWED_HOSTS"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::"})


def host_only(host_header: str) -> str:
    """Hostヘッダからポートを除いたホスト名を小文字で返す(`[::1]:8790` → `::1`)。"""
    host = host_header.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end != -1 else host
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host


def resolve_allowed_hosts(extra: Optional[Iterable[str]] = None) -> frozenset[str]:
    """ループバック + 環境変数 HUB_ALLOWED_HOSTS + 引数の許可ホスト(ポートは無視)。"""
    allowed = set(LOOPBACK_HOSTS)
    raw = os.environ.get(ALLOWED_HOSTS_ENV, "")
    for item in [*raw.split(","), *(extra or [])]:
        item = item.strip()
        if item:
            allowed.add(host_only(item))
    return frozenset(allowed)


def is_same_origin(origin: str, host_header: str) -> bool:
    """OriginのホストとポートがHostヘッダと一致するか(スキームは見ない)。`null`は常に不一致。"""
    if origin.strip().lower() == "null":
        return False
    return urlsplit(origin).netloc.lower() == host_header.strip().lower()


def is_loopback_host(host: str) -> bool:
    return host_only(host) in LOOPBACK_HOSTS


def extend_allowed_hosts_env(host: str) -> bool:
    """`--host 192.168.0.5` のように特定のアドレスで起動したとき、そのアドレスを許可リストへ足す。

    0.0.0.0 / :: のようなワイルドカードは「どのHostでもよい」ことを意味しないので足さない
    (その場合は利用者が HUB_ALLOWED_HOSTS に、実際に開くホスト名を指定する)。足したらTrue。
    """
    if host.strip() in _WILDCARD_HOSTS or is_loopback_host(host):
        return False
    current = os.environ.get(ALLOWED_HOSTS_ENV, "")
    os.environ[ALLOWED_HOSTS_ENV] = f"{current},{host}" if current else host
    return True


def install_request_guard(app: FastAPI, *, allowed_hosts: frozenset[str]) -> None:
    """全リクエストのHostと、変更操作のOriginを検査するミドルウェアを入れる。"""

    @app.middleware("http")
    async def request_guard(request: Request, call_next):
        host_header = request.headers.get("host", "")
        if host_only(host_header) not in allowed_hosts:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"このHostでは受け付けません: {host_header!r}。"
                        f"127.0.0.1 / localhost 以外のホスト名で開く場合は、環境変数 {ALLOWED_HOSTS_ENV} に追加してください"
                    )
                },
            )
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and not is_same_origin(origin, host_header):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "他のサイトからの変更操作は受け付けません(Originが一致しません)"},
                )
        return await call_next(request)
