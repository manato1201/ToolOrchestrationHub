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

  // 同期はワーキングツリーを書き換える操作なので、必ず確認を挟む(設計書の検証: 破壊的な操作に確認が入る)
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
