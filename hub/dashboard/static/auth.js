// 認証(HUB_AUTH=required)用: ログインへの誘導・役割に足りない操作の無効化・ログアウト。off(既定)のときは何もしない。
//
// app.js は変えない。/api/* が 401 を返したら、ログインのページ(/login)へ移す。
// 権限の判断はサーバー側(403)で、ここは「押せない理由」を先に見せる表示だけ。
(() => {
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input, init) => {
    const res = await nativeFetch(input, init);
    const url = typeof input === "string" ? input : input.url;
    if (res.status === 401 && url.startsWith("/api/") && !url.startsWith("/api/auth/")) {
      location.href = "/login";
    }
    return res;
  };

  const RANK = { viewer: 0, operator: 1, admin: 2 };
  const GATES = [
    [".alert-snooze-btn, .alert-unsnooze-btn, #repos-check-btn, .repo-launch-btn, .repo-launch-all-btn, .repo-open-folder-btn", "operator"],
    ["#reload-registry-btn, .repo-sync-btn", "admin"],
  ];

  function applyGates(role) {
    for (const [selector, minimum] of GATES) {
      if (RANK[role] >= RANK[minimum]) continue;
      for (const node of document.querySelectorAll(selector)) {
        if (!node.disabled) node.disabled = true; // すでに無効なら触らない(監視の無限ループを避ける)
        const text = `この操作には ${minimum} 以上の権限が必要です`;
        if (node.title !== text) node.title = text;
      }
    }
  }

  // 一覧の差し替え(自動更新・履歴スライダー)で作り直されるボタンにも当て直す。
  // requestAnimationFrame は見えていないタブで止まるので、setTimeout を使う。
  function gateByRole(role) {
    if (!(role in RANK) || role === "admin") return;
    let scheduled = false;
    const run = () => {
      scheduled = false;
      applyGates(role);
    };
    new MutationObserver(() => {
      if (!scheduled) {
        scheduled = true;
        setTimeout(run, 0);
      }
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    run();
  }

  function showAccount(me) {
    const strip = document.createElement("div");
    strip.textContent = `${me.name}(${me.role}) `;
    Object.assign(strip.style, { position: "fixed", right: "12px", bottom: "8px", zIndex: "900", fontSize: "12px", opacity: "0.9" });
    const logout = document.createElement("button");
    logout.type = "button";
    logout.textContent = "ログアウト";
    logout.className = "btn-reload btn-small";
    logout.addEventListener("click", async () => {
      await nativeFetch("/api/auth/logout", { method: "POST" });
      location.href = "/login";
    });
    strip.append(logout);
    document.body.append(strip);
  }

  const start = () =>
    nativeFetch("/api/auth/me")
      .then((r) => r.json())
      .then((me) => {
        if (me.mode !== "required" || !me.authenticated) return;
        gateByRole(me.role);
        showAccount(me);
      })
      .catch(() => {});
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
