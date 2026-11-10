"""ログイン状態の確認と、ブラウザ用のログイン(API キー → HttpOnly クッキー)。ログインのページ(/login)も、ここ。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from . import audit, auth

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    api_key: str


def _me(mode: str, principal: auth.Principal | None) -> dict:
    if principal is None:
        return {"mode": mode, "authenticated": False, "name": None, "role": None, "source": None}
    return {"mode": mode, "authenticated": True, "name": principal.name, "role": principal.role,
            "source": principal.source}


@router.get("/api/auth/me")
def me(request: Request) -> dict:
    """GUI が最初に呼ぶ。未ログインでも 401 にせず、authenticated=false を返す。"""
    return _me(auth.auth_mode(), auth.current_principal(request))


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response) -> dict:
    if auth.auth_mode() == "off":
        return _me("off", auth.ANONYMOUS)
    key = body.api_key.strip()
    user = auth.find_by_key(key, auth.load_users())
    ip = request.client.host if request.client else None
    if user is None:
        audit.record("login_failed", method="POST", path="/api/auth/login", status=401, ip=ip)
        raise HTTPException(status_code=401, detail="API キーが正しくありません。")
    audit.record("login", actor=user["name"], role=user["role"], source="key", method="POST",
                 path="/api/auth/login", status=200, ip=ip)
    # JS から読めないクッキー。別サイトからは送られない(SameSite=Strict)。WebSocket(/ws/hud)のハンドシェイクにも付く。
    response.set_cookie(auth.COOKIE_NAME, key, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/")
    return _me("required", auth.Principal(name=user["name"], role=user["role"], source="key"))


@router.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    principal = auth.current_principal(request) if auth.auth_mode() == "required" else None
    if principal is not None:
        audit.record("logout", actor=principal.name, role=principal.role, source=principal.source, method="POST",
                     path="/api/auth/logout", status=204, ip=request.client.host if request.client else None)
    response.delete_cookie(auth.COOKIE_NAME, path="/")


@router.get("/api/auth/audit", dependencies=[auth.admin])
def audit_log(limit: int = 100) -> dict:
    """監査ログ(新しい順)。admin だけ。本文・キー・クッキーは記録されていない。"""
    return {"entries": audit.read_recent(max(1, min(limit, 500)))}


# ---- ログインのページ(認証が required で、まだログインしていないとき、/ から回される)
LOGIN_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ToolOrchestrationHub — ログイン</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0e1117;color:#e6edf3;display:grid;place-items:center;min-height:100vh;margin:0;padding:16px}
  main{width:min(420px,100%);display:grid;gap:12px}
  input,button{font:inherit;padding:10px 12px;border-radius:6px;border:1px solid #30363d;background:#161b22;color:inherit}
  button{background:#238636;border-color:#2ea043;cursor:pointer}
  button:disabled{opacity:.6;cursor:default}
  #err{color:#ff7b72;min-height:1.2em}
</style></head>
<body><main>
  <h1 style="font-size:20px;margin:0">ToolOrchestrationHub</h1>
  <p>この環境は認証が必要です。管理者から受け取った API キーを入れてください。</p>
  <form id="f" style="display:grid;gap:8px">
    <label for="k">API キー</label>
    <input id="k" type="password" autocomplete="off" required autofocus>
    <button id="b" type="submit">ログイン</button>
  </form>
  <p id="err" role="alert"></p>
</main>
<script>
document.getElementById("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const b = document.getElementById("b"), k = document.getElementById("k"), err = document.getElementById("err");
  b.disabled = true; err.textContent = "";
  try {
    const res = await fetch("/api/auth/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({api_key: k.value.trim()})});
    if (res.ok) { location.href = "/"; return; }
    const d = await res.json().catch(() => ({}));
    err.textContent = d.detail || ("ログインに失敗しました(" + res.status + ")");
    k.value = "";
  } finally { b.disabled = false; }
});
</script></body></html>"""


@router.get("/login", include_in_schema=False)
def login_page(request: Request):
    """認証が off ならダッシュボードへ。すでにログイン済みでも、ダッシュボードへ。"""
    if auth.auth_mode() == "off":
        return RedirectResponse("/", status_code=303)
    try:
        if auth.current_principal(request) is not None:
            return RedirectResponse("/", status_code=303)
    except HTTPException:
        pass
    return HTMLResponse(LOGIN_PAGE)
