/* hub/dashboard/static/app.js
 *
 * ダッシュボードのブラウザ側の動き。サーバーが描いたHTML(概況の断片は /fragments/overview)に対して
 * 「絞り込み・並べ替え・表示切替・選択」「アラート履歴スライダー」「テーマ」「解消時の演出」
 * 「各種ボタンの操作」を足すだけで、状態の判定・集計はここでは一切しない(サーバーのoverview.pyが正)。
 *
 * 状態の保持: 並べ替え・絞り込み・表示・選択中のツール・検索語・テーマは localStorage に覚え、
 * 自動更新(ページの再読み込み)をまたいで維持する。localStorageが使えない環境でも動く。
 */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const storage = {
    get(key, fallback) {
      try {
        const value = window.localStorage.getItem(key);
        return value === null ? fallback : value;
      } catch (err) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, value);
      } catch (err) {
        /* 保存できなくても画面は動く */
      }
    },
  };

  // ------------------------------------------------------------------ テーマ
  const root = document.documentElement;
  const themeToggle = $("#theme-toggle");

  function currentTheme() {
    return root.dataset.theme === "light" ? "light" : "dark";
  }

  function renderThemeToggle() {
    if (!themeToggle) return;
    const icon = $(".theme-toggle-icon", themeToggle);
    if (icon) icon.textContent = currentTheme() === "dark" ? "☾" : "☀";
    themeToggle.setAttribute("aria-pressed", currentTheme() === "light" ? "true" : "false");
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      storage.set("hub.theme", next);
      renderThemeToggle();
    });
  }
  renderThemeToggle();

  // ------------------------------------------------------------------ 自動更新
  // 履歴スライダーで過去を見ている間は止める(再読み込みすると見ていた時刻が消えてしまうため)。
  let historyMode = false;
  const refreshSeconds = Number(document.body.dataset.refreshInterval) || 0;

  function scheduleRefresh() {
    if (refreshSeconds <= 0) return;
    window.setTimeout(() => {
      if (historyMode) {
        scheduleRefresh();
      } else {
        window.location.reload();
      }
    }, refreshSeconds * 1000);
  }
  scheduleRefresh();

  // ------------------------------------------------------------------ 概況(左一覧・中央・右サマリ)
  const defaultUi = { sort: "state", filter: "all", view: "list", selected: null, query: "" };
  let ui = { ...defaultUi };
  try {
    ui = { ...defaultUi, ...JSON.parse(storage.get("hub.ui", "{}")) };
  } catch (err) {
    ui = { ...defaultUi };
  }

  function saveUi() {
    storage.set("hub.ui", JSON.stringify(ui));
  }

  const overviewRoot = $("#overview-root");
  const ATTENTION_STATES = new Set(["warn", "down"]);

  function compareRows(a, b) {
    const byName = a.name.localeCompare(b.name, "ja");
    if (ui.sort === "name") return byName;
    if (ui.sort === "latency") {
      // 遅い順。応答時間が無いもの(-1)は最後
      if (a.latency < 0 && b.latency < 0) return byName;
      if (a.latency < 0) return 1;
      if (b.latency < 0) return -1;
      return b.latency - a.latency || byName;
    }
    return a.rank - b.rank || byName; // 状態順: 問題があるものが先
  }

  function rowInfo(el) {
    return {
      id: el.dataset.toolId,
      name: el.dataset.name || "",
      rank: Number(el.dataset.stateRank),
      latency: Number(el.dataset.latency),
      state: el.dataset.state,
      search: el.dataset.search || "",
    };
  }

  function applyOverviewState() {
    const card = $("#overview-card");
    if (!card) return;

    const query = ui.query.trim().toLowerCase();
    const isVisible = (info) =>
      (!query || info.search.includes(query)) && (ui.filter === "all" || ATTENTION_STATES.has(info.state));

    const setChip = (button, on) => {
      button.classList.toggle("is-active", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    };
    $$("[data-sort]", card).forEach((b) => setChip(b, b.dataset.sort === ui.sort));
    $$("[data-filter]", card).forEach((b) => setChip(b, b.dataset.filter === ui.filter));
    $$("[data-view]", card).forEach((b) => setChip(b, b.dataset.view === ui.view));

    const input = $("#tool-search", card);
    if (input && input.value !== ui.query) input.value = ui.query;

    // 一覧(.tool-list)とオフィス(.office-grid)は同じdata属性を持つので、同じ規則で並べて隠す
    const infos = new Map();
    for (const container of [$("#tool-list", card), $("#office-grid", card)]) {
      if (!container) continue;
      const items = $$(":scope > li", container).map((li) => {
        const info = rowInfo(li.firstElementChild);
        infos.set(info.id, info);
        return { li, info };
      });
      items.sort((x, y) => compareRows(x.info, y.info));
      for (const { li, info } of items) {
        container.appendChild(li);
        li.hidden = !isVisible(info);
      }
    }

    const all = [...infos.values()];
    const visible = all.filter(isVisible);
    const count = $("#tool-count", card);
    if (count) count.textContent = `${visible.length} / ${all.length} 件表示`;
    const empty = $("#tool-list-empty", card);
    if (empty) empty.hidden = visible.length !== 0;

    // 選択中のツール(絞り込みで見えなくなったら、見えている先頭へ)
    let selected = ui.selected;
    const selectable = new Set(visible.map((info) => info.id));
    if (!selected || !selectable.has(selected)) {
      const preferred = card.dataset.defaultTool;
      selected = preferred && selectable.has(preferred) ? preferred : (visible[0] && visible[0].id) || null;
    }
    $$(".tool-row, .office-tile", card).forEach((el) => {
      const on = el.dataset.toolId === selected;
      el.classList.toggle("is-selected", on);
      if (on) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    });
    $$(".tool-detail", card).forEach((el) => {
      el.hidden = el.dataset.toolId !== selected;
    });

    const office = $("#office", card);
    if (office) office.hidden = ui.view !== "office";
    // 注意: data-view は表示切替ボタンの属性名と同じなので使わない(カード自身に付けると、
    // ボタン判定のclosest("[data-view]")がカードに一致して、行のクリックが横取りされてしまう)
    card.dataset.activeView = ui.view;
  }

  if (overviewRoot) {
    overviewRoot.addEventListener("click", (event) => {
      const chip = event.target.closest("button[data-sort], button[data-filter], button[data-view]");
      if (chip) {
        if (chip.dataset.sort) ui.sort = chip.dataset.sort;
        if (chip.dataset.filter) ui.filter = chip.dataset.filter;
        if (chip.dataset.view) ui.view = chip.dataset.view;
        saveUi();
        applyOverviewState();
        return;
      }
      const pick = event.target.closest(".tool-row, .office-tile");
      if (pick) {
        ui.selected = pick.dataset.toolId;
        saveUi();
        applyOverviewState();
      }
    });
    overviewRoot.addEventListener("input", (event) => {
      if (event.target.id === "tool-search") {
        ui.query = event.target.value;
        saveUi();
        applyOverviewState();
      }
    });
  }
  applyOverviewState();

  // ------------------------------------------------------------------ 空状態の動き
  // 「現在アラートはありません」のチェックの描画は、このタブで最初に見たときだけ。
  // 20秒ごとの自動更新のたびに動いて落ち着かなくならないよう、2回目以降は描き終えた状態で出す。
  (function calmOnce() {
    let played = false;
    try {
      played = window.sessionStorage.getItem("hub.calmPlayed") === "1";
      window.sessionStorage.setItem("hub.calmPlayed", "1");
    } catch (err) {
      played = false;
    }
    if (played) $$(".calm").forEach((el) => el.classList.add("is-played"));
  })();

  // ------------------------------------------------------------------ 解消時の演出(小さな紙吹雪)
  // 通常は静か(原則 P8)。前回の読み込み時には未解消だったアラートが、今回は解消されているときだけ、
  // 右サマリの上に小さく出す。動きを減らす設定のときは出さない。
  (function celebrateResolved() {
    const card = $("#overview-card");
    if (!card || card.dataset.mode !== "live") return;
    let current = [];
    try {
      current = JSON.parse(card.dataset.openAlertKeys || "[]");
    } catch (err) {
      return;
    }
    let previous = null;
    try {
      previous = JSON.parse(storage.get("hub.openAlertKeys", "null"));
    } catch (err) {
      previous = null;
    }
    storage.set("hub.openAlertKeys", JSON.stringify(current));
    if (!Array.isArray(previous) || reducedMotion()) return;

    const nowOpen = new Set(current);
    const resolvedCount = previous.filter((key) => !nowOpen.has(key)).length;
    if (resolvedCount > 0) burstConfetti($(".summary-panel", card));
  })();

  function burstConfetti(anchor) {
    if (!anchor) return;
    const layer = document.createElement("div");
    layer.className = "confetti-layer";
    layer.setAttribute("aria-hidden", "true");
    const palette = ["var(--state-ok-text)", "var(--text-parchment)", "var(--text-limestone)"];
    for (let i = 0; i < 14; i += 1) {
      const piece = document.createElement("span");
      piece.className = "confetti-piece";
      piece.style.setProperty("--dx", `${Math.round((Math.random() - 0.5) * 120)}px`);
      piece.style.setProperty("--dy", `${Math.round(30 + Math.random() * 60)}px`);
      piece.style.setProperty("--rot", `${Math.round(Math.random() * 360)}deg`);
      piece.style.setProperty("--delay", `${Math.round(Math.random() * 120)}ms`);
      piece.style.background = palette[i % palette.length];
      layer.appendChild(piece);
    }
    anchor.appendChild(layer);
    window.setTimeout(() => layer.remove(), 1400);
  }

  // ------------------------------------------------------------------ アラート履歴スライダー
  (function setupHistorySlider() {
    const bar = $("#history-bar");
    const range = $("#history-range");
    if (!bar || !range || !overviewRoot) return;

    let timeline = { start: null, end: null, events: [] };
    try {
      timeline = JSON.parse(bar.dataset.timeline);
    } catch (err) {
      return;
    }
    const atLabel = $("#history-at");
    const ticksEl = $("#history-ticks");
    const playBtn = $("#history-play");
    const nowBtn = $("#history-now");
    const RANGE_MAX = Number(range.max) || 1000;

    const startMs = timeline.start ? Date.parse(timeline.start) : null;
    const endMs = Date.parse(timeline.end);
    const spanMs = startMs === null ? 1 : Math.max(endMs - startMs, 1);
    const eventTimes = startMs === null ? [] : [...new Set(timeline.events.map((e) => Date.parse(e.at)))].sort((a, b) => a - b);

    const msFromValue = (value) => startMs + (spanMs * value) / RANGE_MAX;
    const valueFromMs = (ms) => Math.round(((ms - startMs) / spanMs) * RANGE_MAX);
    const formatAt = (ms) =>
      new Date(ms).toLocaleString("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

    // 目盛り: 発生(塗りつぶし)と解消(白抜き)。色だけでなく形でも区別する
    if (ticksEl && startMs !== null) {
      for (const event of timeline.events) {
        const tick = document.createElement("span");
        tick.className = `history-tick history-tick-${event.kind}`;
        tick.style.left = `${Math.min(100, Math.max(0, ((Date.parse(event.at) - startMs) / spanMs) * 100))}%`;
        tick.title = `${event.kind === "opened" ? "発生" : "解消"}: ${event.source_tool_id}(${formatAt(Date.parse(event.at))})`;
        ticksEl.appendChild(tick);
      }
    }

    let controller = null;
    let debounceTimer = null;
    let playTimer = null;
    let cursorMs = null;

    async function swapOverview(atMs) {
      if (controller) controller.abort();
      controller = new AbortController();
      const url = atMs === null ? "/fragments/overview" : `/fragments/overview?at=${encodeURIComponent(new Date(atMs).toISOString())}`;
      try {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        overviewRoot.innerHTML = await res.text();
        applyOverviewState();
      } catch (err) {
        if (err.name !== "AbortError") window.alert(`履歴の取得に失敗しました: ${err}`);
      }
    }

    function showAt(atMs) {
      if (atMs === null) {
        historyMode = false;
        document.body.classList.remove("is-history");
        if (atLabel) atLabel.textContent = "いま";
        range.value = String(RANGE_MAX);
      } else {
        historyMode = true;
        document.body.classList.add("is-history");
        if (atLabel) atLabel.textContent = formatAt(atMs);
      }
      swapOverview(atMs);
    }

    function stopPlaying() {
      if (playTimer) window.clearTimeout(playTimer);
      playTimer = null;
      if (playBtn) playBtn.textContent = "▶ 再生";
    }

    function stepPlayback() {
      const next = eventTimes.find((t) => t > cursorMs);
      if (next === undefined) {
        stopPlaying();
        showAt(null);
        return;
      }
      cursorMs = next;
      range.value = String(valueFromMs(next));
      showAt(next);
      playTimer = window.setTimeout(stepPlayback, 900);
    }

    if (playBtn) {
      playBtn.textContent = "▶ 再生";
      playBtn.disabled = eventTimes.length === 0;
      playBtn.addEventListener("click", () => {
        if (playTimer) {
          stopPlaying();
          return;
        }
        // 「いま」にいる、または最後まで再生した後は、最初の出来事から再生し直す
        cursorMs = historyMode && cursorMs !== null ? cursorMs : startMs - 1;
        playBtn.textContent = "一時停止";
        stepPlayback();
      });
    }

    if (nowBtn) {
      nowBtn.addEventListener("click", () => {
        stopPlaying();
        showAt(null);
      });
    }

    range.addEventListener("input", () => {
      stopPlaying();
      window.clearTimeout(debounceTimer);
      debounceTimer = window.setTimeout(() => {
        const value = Number(range.value);
        if (value >= RANGE_MAX) {
          showAt(null);
        } else {
          cursorMs = msFromValue(value);
          showAt(cursorMs);
        }
      }, 120);
    });
  })();

  // ------------------------------------------------------------------ 表の検索(リポジトリ)
  function setupTableSearch(inputId, tableId, countId, emptyId) {
    const searchInput = document.getElementById(inputId);
    const table = document.getElementById(tableId);
    const countLabel = document.getElementById(countId);
    const emptyNotice = document.getElementById(emptyId);
    if (!searchInput || !table) return;

    const rows = $$(".table-search-row", table);

    function applyFilter() {
      const query = searchInput.value.trim().toLowerCase();
      let shown = 0;
      rows.forEach((row) => {
        const matches = !query || row.dataset.search.includes(query);
        row.hidden = !matches;
        if (matches) shown += 1;
      });
      if (countLabel) countLabel.textContent = `${shown} / ${rows.length} 件表示`;
      table.hidden = shown === 0;
      if (emptyNotice) emptyNotice.hidden = shown !== 0;
    }

    searchInput.addEventListener("input", applyFilter);
    applyFilter();
  }
  setupTableSearch("repos-filter-search", "repos-table", "repos-filter-count", "repos-filter-empty");

  // ------------------------------------------------------------------ アラートの絞り込み・エクスポート・スヌーズ
  (function setupAlertFilter() {
    const searchInput = $("#alert-filter-search");
    const statusSelect = $("#alert-filter-status");
    const severitySelect = $("#alert-filter-severity");
    const sourceSelect = $("#alert-filter-source");
    const countLabel = $("#alert-filter-count");
    const emptyNotice = $("#alert-filter-empty");
    const table = $("#alert-table");
    if (!searchInput || !table) return;

    const rows = $$(".alert-row", table);

    function applyFilter() {
      const query = searchInput.value.trim().toLowerCase();
      const status = statusSelect.value;
      const severity = severitySelect.value;
      const source = sourceSelect.value;
      let shown = 0;
      rows.forEach((row) => {
        const matches =
          (!status || row.dataset.status === status) &&
          (!severity || row.dataset.severity === severity) &&
          (!source || row.dataset.source === source) &&
          (!query || row.dataset.search.includes(query));
        row.hidden = !matches;
        if (matches) shown += 1;
      });
      countLabel.textContent = `${shown} / ${rows.length} 件表示`;
      table.hidden = shown === 0;
      emptyNotice.hidden = shown !== 0;
    }

    [searchInput, statusSelect, severitySelect, sourceSelect].forEach((el) => {
      el.addEventListener("input", applyFilter);
      el.addEventListener("change", applyFilter);
    });
    applyFilter();
  })();

  (function setupAlertExport() {
    const jsonBtn = $("#alert-export-json-btn");
    const csvBtn = $("#alert-export-csv-btn");
    if (!jsonBtn && !csvBtn) return;

    function downloadBlob(content, mime, filename) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }

    function toCsv(rows) {
      const columns = ["alert_id", "status", "severity", "source_tool_id", "message", "occurrence_count", "priority", "first_seen_at", "resolved_at"];
      const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const lines = [columns.join(",")];
      rows.forEach((r) => lines.push(columns.map((c) => escape(r[c])).join(",")));
      return lines.join("\r\n");
    }

    async function fetchAlerts() {
      const res = await fetch("/api/alerts");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    }

    if (jsonBtn) {
      jsonBtn.addEventListener("click", async () => {
        try {
          downloadBlob(JSON.stringify(await fetchAlerts(), null, 2), "application/json", "alerts.json");
        } catch (err) {
          window.alert(`エクスポートに失敗しました: ${err}`);
        }
      });
    }
    if (csvBtn) {
      csvBtn.addEventListener("click", async () => {
        try {
          downloadBlob(toCsv(await fetchAlerts()), "text/csv;charset=utf-8", "alerts.csv");
        } catch (err) {
          window.alert(`エクスポートに失敗しました: ${err}`);
        }
      });
    }
  })();

  $$(".alert-snooze-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      target.disabled = true;
      try {
        const res = await fetch(`/api/alerts/${target.dataset.alertId}/snooze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ minutes: 60 }),
        });
        if (!res.ok) {
          const body = await res.json();
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        window.location.reload();
      } catch (err) {
        target.disabled = false;
        window.alert(`スヌーズに失敗しました: ${err}`);
      }
    });
  });

  $$(".alert-unsnooze-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      target.disabled = true;
      try {
        const res = await fetch(`/api/alerts/${target.dataset.alertId}/unsnooze`, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.location.reload();
      } catch (err) {
        target.disabled = false;
        window.alert(`スヌーズ解除に失敗しました: ${err}`);
      }
    });
  });

  // ------------------------------------------------------------------ 台帳の再読み込み・リポジトリ操作
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

  const reposCheckBtn = $("#repos-check-btn");
  if (reposCheckBtn) {
    reposCheckBtn.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      btn.disabled = true;
      btn.textContent = "Checking...";
      try {
        const res = await fetch("/api/repos/check", { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        window.location.reload();
      } catch (err) {
        btn.disabled = false;
        btn.textContent = "Check all";
        window.alert(`リポジトリのチェックに失敗しました: ${err}`);
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

  $$(".repo-launch-btn").forEach((btn) => {
    const originalText = btn.textContent;
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      target.disabled = true;
      target.textContent = "Starting...";
      try {
        const res = await fetch(`/api/repos/${target.dataset.repoId}/launch/${target.dataset.targetIndex}`, { method: "POST" });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
        target.textContent = "Started";
        window.setTimeout(() => window.location.reload(), 1500);
      } catch (err) {
        target.disabled = false;
        target.textContent = originalText;
        window.alert(`起動に失敗しました: ${err}`);
      }
    });
  });

  // 複数プロセス構成のリポジトリ向け一括起動。既存の単体起動エンドポイントを順番に叩くだけ。
  $$(".repo-launch-all-btn").forEach((btn) => {
    const originalText = btn.textContent;
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const repoId = target.dataset.repoId;
      const launchButtons = $$(`.repo-launch-btn[data-repo-id="${repoId}"]`);
      target.disabled = true;
      target.textContent = "Starting all...";
      let failedCount = 0;
      for (const launchBtn of launchButtons) {
        try {
          const res = await fetch(`/api/repos/${repoId}/launch/${launchBtn.dataset.targetIndex}`, { method: "POST" });
          if (!res.ok) failedCount += 1;
        } catch (err) {
          failedCount += 1;
        }
      }
      if (failedCount > 0) {
        window.alert(`${failedCount}件の起動に失敗しました。個別のStartボタンで状況を確認してください。`);
        target.disabled = false;
        target.textContent = originalText;
      } else {
        target.textContent = "Started all";
        window.setTimeout(() => window.location.reload(), 1500);
      }
    });
  });

  $$(".repo-open-folder-btn").forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      target.disabled = true;
      try {
        const res = await fetch(`/api/repos/${target.dataset.repoId}/open-folder`, { method: "POST" });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      } catch (err) {
        window.alert(`フォルダを開けませんでした: ${err}`);
      } finally {
        target.disabled = false;
      }
    });
  });
})();
