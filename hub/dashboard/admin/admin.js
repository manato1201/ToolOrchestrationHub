// 管理画面(admin だけ): registry.yaml の再読み込みと、リポジトリの同期(git pull --ff-only)。
// サーバーが /admin・/admin.js を admin に限る(/static の外)。ダッシュボード(app.js)は、読み取りと operator の操作だけ。
(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  const reloadRegistryBtn = $("#reload-registry-btn");
  if (reloadRegistryBtn) {
    reloadRegistryBtn.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      btn.disabled = true;
      btn.textContent = "Reloading...";
      try {
        const res = await fetch("/api/registry/reload", { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.location.reload();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Reload registry.yaml";
        window.alert(`registry.yamlの再読込に失敗しました: ${err}`);
      }
    });
  }

  // 同期はワーキングツリーを書き換える操作なので、必ず確認を挟む(設計書の検証: 破壊的な操作に確認が入る)。
  // 2026-11-26: 確認は「長押し(約 1.2 秒)」で行う(spring.js の holdButton)。押してすぐ離しても実行しない。
  // 何が起きるかは、ボタンの title と aria-label に書く。spring.js が無いときは、従来の確認ダイアログ。
  const syncRepo = async (target) => {
    const res = await fetch(`/api/repos/${target.dataset.repoId}/sync`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  };
  if (window.HubMotion) {
    $$(".repo-sync-btn").forEach((btn) => {
      const name = btn.dataset.repoName || btn.dataset.repoId;
      const behind = btn.dataset.commitsBehind;
      btn.setAttribute(
        "aria-label",
        `長押しで ${name} を同期(git pull --ff-only。${behind ? `${behind}件の更新を取り込む` : "リモートの更新を取り込む"})`,
      );
      window.HubMotion.holdButton(btn, {
        label: "長押しで Sync",
        doneLabel: "同期しました",
        onComplete: async () => {
          await syncRepo(btn);
          window.setTimeout(() => window.location.reload(), 1200);
        },
        onError: (err) => window.alert(`同期に失敗しました: ${err.message || err}`),
      });
    });
    return;
  }

  $$(".repo-sync-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const name = target.dataset.repoName || target.dataset.repoId;
      const behind = target.dataset.commitsBehind;
      const message =
        `${name} をリモートの最新へ同期します(git pull --ff-only)。\n` +
        `${behind ? `${behind}件の更新が` : "リモートの更新が"}ワーキングツリーに取り込まれます。\n\n続けますか?`;
      if (!window.confirm(message)) return;
      target.disabled = true;
      target.textContent = "Syncing...";
      try {
        const res = await fetch(`/api/repos/${target.dataset.repoId}/sync`, { method: "POST" });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
        window.location.reload();
      } catch (err) {
        target.disabled = false;
        target.textContent = "Sync";
        window.alert(`同期に失敗しました: ${err}`);
      }
    });
  });
})();
