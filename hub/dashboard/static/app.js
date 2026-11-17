/* hub/dashboard/static/app.js
 *
 * ダッシュボードのブラウザ側の動き。サーバーが描いたHTML(概況の断片は /fragments/overview)に対して
 * 「絞り込み・並べ替え・表示切替・選択」「アラート履歴スライダー」「ドロワー・トースト」「キー操作」
 * 「各種ボタンの操作」を足すだけで、状態の判定・集計はここでは一切しない(サーバーのoverview.pyが正)。
 *
 * 状態の保持: 並べ替え・絞り込み・表示・選択中のツール・検索語・テーマは localStorage に覚え、
 * 自動更新(ページの再読み込み)をまたいで維持する。localStorageが使えない環境でも動く。
 * 動きは2種類まで(出入り・脈動。parts.css冒頭の「動きの予算」)。ここで足す動きは、スタッガー・トースト・
 * 一覧↔オフィスの押し出し・状態が切り替わったときの弾み(pop)のクラス付けと、空状態の蜂の巣だけ。
 * 全て動きを減らす設定で止まる。無限に続く動きは持たない(蜂の巣も、開いた直後と、触れている間だけ)。
 */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isNarrow = () => window.matchMedia("(max-width: 960px)").matches;

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

  const session = {
    get(key) {
      try {
        return window.sessionStorage.getItem(key);
      } catch (err) {
        return null;
      }
    },
    set(key, value) {
      try {
        window.sessionStorage.setItem(key, value);
      } catch (err) {
        /* 保存できなくても画面は動く */
      }
    },
  };

  const parseJson = (text, fallback) => {
    try {
      const value = JSON.parse(text);
      return value === null ? fallback : value;
    } catch (err) {
      return fallback;
    }
  };

  const BASE_TITLE = "ToolOrchestrationHub";

  // ------------------------------------------------------------------ 表示設定(並び順・絞り込み・表示・テーマ)
  const root = document.documentElement;
  const themeToggle = $("#theme-toggle");
  const restoreBtn = $("#restore-view");

  const defaultUi = { sort: "state", filter: "all", view: "list", selected: null, query: "" };
  let ui = { ...defaultUi, ...parseJson(storage.get("hub.ui", "{}"), {}) };

  function saveUi() {
    storage.set("hub.ui", JSON.stringify(ui));
  }

  function currentTheme() {
    return root.dataset.theme === "light" ? "light" : "dark";
  }

  function setTheme(theme) {
    root.dataset.theme = theme;
    storage.set("hub.theme", theme);
    renderThemeToggle();
  }

  function renderThemeToggle() {
    if (!themeToggle) return;
    const icon = $(".theme-toggle-icon", themeToggle);
    if (icon) icon.textContent = currentTheme() === "dark" ? "☾" : "☀";
    themeToggle.setAttribute("aria-pressed", currentTheme() === "light" ? "true" : "false");
  }

  // 「表示設定」= 並び順・絞り込み・表示(一覧/オフィス)・テーマ。選択中のツールと検索語は含めない(その場の操作のため)。
  const displaySnapshot = () => ({ sort: ui.sort, filter: ui.filter, view: ui.view, theme: currentTheme() });
  const sameSnapshot = (a, b) => !!a && !!b && ["sort", "filter", "view", "theme"].every((k) => a[k] === b[k]);

  function renderRestoreButton() {
    if (!restoreBtn) return;
    const previous = parseJson(storage.get("hub.uiPrev", "null"), null);
    restoreBtn.disabled = !previous || sameSnapshot(previous, displaySnapshot());
  }

  // 変更の前の表示設定を1つだけ覚えておき、「前回の表示に戻す」で入れ替える(もう一度押すとやり直し)
  function changeDisplay(mutator) {
    const before = displaySnapshot();
    mutator();
    if (!sameSnapshot(before, displaySnapshot())) storage.set("hub.uiPrev", JSON.stringify(before));
    saveUi();
    applyOverviewState();
    renderRestoreButton();
  }

  function restoreView() {
    const previous = parseJson(storage.get("hub.uiPrev", "null"), null);
    if (!previous) return;
    const current = displaySnapshot();
    ui.sort = previous.sort;
    ui.filter = previous.filter;
    ui.view = previous.view;
    if (previous.theme) setTheme(previous.theme);
    storage.set("hub.uiPrev", JSON.stringify(current));
    saveUi();
    applyOverviewState();
    renderRestoreButton();
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      changeDisplay(() => setTheme(currentTheme() === "dark" ? "light" : "dark"));
    });
  }
  if (restoreBtn) restoreBtn.addEventListener("click", restoreView);
  renderThemeToggle();

  // ------------------------------------------------------------------ 自動更新
  // 履歴スライダーで過去を見ている間・ドロワーを開いている間は止める
  // (再読み込みすると、見ていた時刻や開いていた詳細が消えてしまうため)。
  let historyMode = false;
  let drawerToolId = null;
  const refreshSeconds = Number(document.body.dataset.refreshInterval) || 0;

  function scheduleRefresh() {
    if (refreshSeconds <= 0) return;
    window.setTimeout(() => {
      if (historyMode || drawerToolId !== null) {
        scheduleRefresh();
      } else {
        window.location.reload();
      }
    }, refreshSeconds * 1000);
  }
  scheduleRefresh();

  // ------------------------------------------------------------------ 概況(左一覧・中央・右サマリ)
  const overviewRoot = $("#overview-root");
  const ATTENTION_STATES = new Set(["warn", "down"]);
  let lastView = null;

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

  // 新しく見える側を右から押し出す(出入りの動き)。動きを減らす設定ではCSSが止める
  function pushIn(element) {
    if (!element || reducedMotion()) return;
    element.classList.remove("is-entering");
    void element.offsetWidth;
    element.classList.add("is-entering");
    const done = () => element.classList.remove("is-entering");
    element.addEventListener("animationend", done, { once: true });
    window.setTimeout(done, 500);
  }

  // 1回きりの小さな弾み(状態の切り替わり・操作の完了)。終わったらクラスを外す。動きを減らす設定では何もしない
  function pop(element) {
    if (!element || reducedMotion()) return;
    element.classList.remove("pop");
    void element.offsetWidth;
    element.classList.add("pop");
    const done = () => element.classList.remove("pop");
    element.addEventListener("animationend", done, { once: true });
    window.setTimeout(done, 500);
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
    if (lastView !== null && lastView !== ui.view) pushIn(ui.view === "office" ? office : $("#tool-details", card));
    lastView = ui.view;

    refreshDrawer();
  }

  function selectTool(toolId) {
    ui.selected = toolId;
    saveUi();
    applyOverviewState();
  }

  // 一覧を見たまま詳細を見る(ドロワー)。オフィス表示と狭い画面では、中央の詳細が遠いので、ドロワーで開く
  const shouldUseDrawer = () => ui.view === "office" || isNarrow();

  function handleOverviewClick(event) {
    const chip = event.target.closest("button[data-sort], button[data-filter], button[data-view]");
    if (chip) {
      changeDisplay(() => {
        if (chip.dataset.sort) ui.sort = chip.dataset.sort;
        if (chip.dataset.filter) ui.filter = chip.dataset.filter;
        if (chip.dataset.view) ui.view = chip.dataset.view;
      });
      return;
    }
    const opener = event.target.closest("[data-open-drawer]");
    if (opener) {
      selectTool(opener.dataset.openDrawer);
      openDrawer(opener.dataset.openDrawer);
      return;
    }
    const link = event.target.closest("[data-select-tool]");
    if (link) {
      selectTool(link.dataset.selectTool);
      if (drawerToolId !== null || shouldUseDrawer()) openDrawer(link.dataset.selectTool);
      return;
    }
    const pick = event.target.closest(".tool-row, .office-tile");
    if (pick) {
      selectTool(pick.dataset.toolId);
      if (shouldUseDrawer()) openDrawer(pick.dataset.toolId);
    }
  }

  if (overviewRoot) {
    overviewRoot.addEventListener("click", handleOverviewClick);
    overviewRoot.addEventListener("input", (event) => {
      if (event.target.id === "tool-search") {
        ui.query = event.target.value;
        saveUi();
        applyOverviewState();
      }
    });
  }

  // ------------------------------------------------------------------ ドロワー
  const drawer = $("#drawer");
  const drawerBody = $("#drawer-body");
  const drawerTitle = $("#drawer-title");
  const drawerBackdrop = $("#drawer-backdrop");
  let drawerReturnFocus = null;

  function openDrawer(toolId) {
    if (!drawer || !overviewRoot) return;
    const source = $(`.tool-detail[data-tool-id="${CSS.escape(toolId)}"]`, overviewRoot);
    if (!source) return;
    const copy = source.cloneNode(true);
    copy.hidden = false;
    drawerBody.replaceChildren(copy);
    const heading = $("h3", source);
    drawerTitle.textContent = heading ? heading.textContent : "ツールの詳細";
    const wasClosed = drawerToolId === null;
    drawerToolId = toolId;
    if (wasClosed) {
      drawerReturnFocus = document.activeElement;
      drawer.hidden = false;
      if (drawerBackdrop) drawerBackdrop.hidden = false;
      window.requestAnimationFrame(() => drawer.classList.add("is-open"));
      const closeBtn = $("#drawer-close");
      if (closeBtn) closeBtn.focus();
    }
  }

  function closeDrawer() {
    if (!drawer || drawerToolId === null) return;
    drawerToolId = null;
    drawer.classList.remove("is-open");
    if (drawerBackdrop) drawerBackdrop.hidden = true;
    window.setTimeout(() => {
      if (drawerToolId === null) drawer.hidden = true;
    }, 260);
    if (drawerReturnFocus && typeof drawerReturnFocus.focus === "function") drawerReturnFocus.focus();
    drawerReturnFocus = null;
  }

  // 概況が差し替わったとき(履歴の再現・「いま」)、開いている詳細も最新の内容にする
  function refreshDrawer() {
    if (drawerToolId === null) return;
    if (!overviewRoot || !$(`.tool-detail[data-tool-id="${CSS.escape(drawerToolId)}"]`, overviewRoot)) {
      closeDrawer();
      return;
    }
    openDrawer(drawerToolId);
  }

  if (drawer) {
    drawer.addEventListener("click", handleOverviewClick);
    const closeBtn = $("#drawer-close");
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeDrawer);
  }

  // ------------------------------------------------------------------ キー操作(/ 検索, a 要対応のみ, o オフィス, Esc 閉じる)
  // 入力中・修飾キー・IME変換中は何もしない。ブラウザの既存のショートカットとは衝突させない。
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target;
    const typing =
      target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

    if (event.key === "Escape") {
      if (drawerToolId !== null) {
        event.preventDefault();
        closeDrawer();
      } else if (typing && target.id === "tool-search") {
        ui.query = "";
        target.value = "";
        target.blur();
        saveUi();
        applyOverviewState();
      }
      return;
    }
    if (typing) return;

    if (event.key === "/") {
      const input = $("#tool-search");
      if (input) {
        event.preventDefault();
        input.focus();
        input.select();
      }
    } else if (event.key === "a") {
      changeDisplay(() => {
        ui.filter = ui.filter === "attention" ? "all" : "attention";
      });
    } else if (event.key === "o") {
      changeDisplay(() => {
        ui.view = ui.view === "office" ? "list" : "office";
      });
    }
  });

  // ------------------------------------------------------------------ トースト(新しく出た / 解消されたアラート)
  // Windowsトースト・Slack通知と対応するアプリ内の知らせ。前回の読み込みで未解消だったアラートとの差で出す。
  // 初回(前回が無い)は出さない。動きは「出入り」のみで、動きを減らす設定ではCSSが止める。
  const toastsEl = $("#toasts");
  const MAX_TOASTS = 4;

  function showToast({ kind, glyph, label, message, source }) {
    if (!toastsEl) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${kind}`;

    const kindEl = document.createElement("span");
    kindEl.className = "toast-kind";
    kindEl.textContent = `${glyph} ${label}`;

    const body = document.createElement("span");
    body.className = "toast-message";
    body.textContent = message;
    if (source) {
      const sourceEl = document.createElement("span");
      sourceEl.className = "toast-source";
      sourceEl.textContent = source;
      body.appendChild(sourceEl);
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.textContent = "閉じる";
    const dismiss = () => toast.remove();
    close.addEventListener("click", dismiss);
    window.setTimeout(dismiss, 7000);

    toast.append(kindEl, body, close);
    toastsEl.appendChild(toast);
  }

  function updateTitleBadge(openCount) {
    document.title = openCount > 0 ? `(${openCount}) ${BASE_TITLE}` : BASE_TITLE;
  }

  (function announceAlertChanges() {
    const card = $("#overview-card");
    if (!card || card.dataset.mode !== "live") return;
    const current = parseJson(card.dataset.openAlerts, []);
    updateTitleBadge(current.length);

    const previous = parseJson(storage.get("hub.openAlerts", "null"), null);
    storage.set("hub.openAlerts", JSON.stringify(current));
    if (!Array.isArray(previous)) return;

    const previousKeys = new Set(previous.map((a) => a.key));
    const currentKeys = new Set(current.map((a) => a.key));
    const opened = current.filter((a) => !previousKeys.has(a.key));
    const resolved = previous.filter((a) => !currentKeys.has(a.key));

    const toasts = [
      ...opened.map((a) => ({ kind: "new", glyph: a.severity_glyph, label: "新規", message: a.message, source: a.source })),
      ...resolved.map((a) => ({ kind: "resolved", glyph: "✓", label: "解消", message: a.message, source: a.source })),
    ];
    toasts.slice(0, MAX_TOASTS - 1).forEach(showToast);
    if (toasts.length > MAX_TOASTS - 1) {
      showToast({ kind: "new", glyph: "○", label: "ほか", message: `${toasts.length - (MAX_TOASTS - 1)}件の変化があります`, source: "" });
    }
  })();

  // ------------------------------------------------------------------ 初回表示のスタッガー(そのタブで最初の1回だけ)
  // 20秒ごとの自動更新のたびに動いて落ち着かなくならないよう、2回目以降は出さない。
  function staggerOnce() {
    const done = session.get("hub.staggered") === "1";
    session.set("hub.staggered", "1");
    if (done || reducedMotion()) return;
    const containers = [$("#tool-list"), $("#office-grid")].filter(Boolean);
    for (const container of containers) {
      $$(":scope > li", container)
        .filter((li) => !li.hidden)
        .forEach((li, index) => li.style.setProperty("--i", String(Math.min(index, 12))));
      container.classList.add("is-staggering");
      window.setTimeout(() => {
        container.classList.remove("is-staggering");
        $$(":scope > li", container).forEach((li) => li.style.removeProperty("--i"));
      }, 1100);
    }
  }

  // ------------------------------------------------------------------ 状態が切り替わったとき(そのタブで前回と違うものだけ、1回弾む)
  // ツール行の状態ピルと、起動ボタンの 稼働中/起動中/停止中。自動更新(再読み込み)の前後を、sessionStorage の控えと比べる。
  function popChangedStates() {
    const card = $("#overview-card");
    const states = {};
    const targets = {};
    if (card && card.dataset.mode === "live") {
      $$(".tool-row[data-tool-id]").forEach((row) => {
        const key = `tool:${row.dataset.toolId}`;
        states[key] = row.dataset.state;
        targets[key] = $(".tool-row-state > *", row);
      });
    }
    $$(".repo-launch-btn[data-launch-state]").forEach((btn) => {
      const key = `repo:${btn.dataset.repoId}:${btn.dataset.targetIndex}`;
      states[key] = btn.dataset.launchState;
      targets[key] = $(".pill", btn);
    });
    const previous = parseJson(session.get("hub.states"), null);
    session.set("hub.states", JSON.stringify({ ...(previous || {}), ...states }));
    if (!previous) return;
    for (const [key, value] of Object.entries(states)) {
      if (key in previous && previous[key] !== value) pop(targets[key]);
    }
  }

  applyOverviewState();
  renderRestoreButton();
  staggerOnce();
  popChangedStates();

  // ------------------------------------------------------------------ 空状態の蜂の巣(ASCII)
  // 各ツール=働き蜂、Hub=巣。正常なツールは巣のまわりを飛び、それ以外(未確認・対象外)は巣で休む。
  // 動くのは空状態(未解消のアラートが無い)のときだけ。画面外・タブが裏・動きを減らす設定では描画を止める。
  (function setupHive() {
    const pre = $("#hive");
    if (!pre) return;

    const WIDTH = 40;
    const HEIGHT = 9;
    const COMB = [
      "  __    __  ",
      " /  \\__/  \\ ",
      " \\__/  \\__/ ",
      " /  \\__/  \\ ",
      " \\__/  \\__/ ",
      "    \\__/    ",
    ];
    const COMB_X = 14;
    const COMB_Y = 2;
    const CENTER_X = COMB_X + COMB[0].length / 2;
    const CENTER_Y = COMB_Y + COMB.length / 2;
    const RESTING_SPOTS = [
      [COMB_X + 3, COMB_Y + 1],
      [COMB_X + 8, COMB_Y + 1],
      [COMB_X + 5, COMB_Y + 3],
      [COMB_X + 10, COMB_Y + 3],
      [COMB_X + 2, COMB_Y + 4],
      [COMB_X + 7, COMB_Y + 5],
    ];

    const flying = Math.min(Number(pre.dataset.flying) || 0, 10);
    const resting = Math.min(Number(pre.dataset.resting) || 0, RESTING_SPOTS.length);

    // 同じ数なら同じ初期配置になる擬似乱数(静止画1枚のときも毎回同じ絵になる)
    let seed = 20261027 + flying * 31 + resting;
    const random = () => {
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };

    const bees = Array.from({ length: flying }, (_, i) => {
      const angle = (i / Math.max(flying, 1)) * Math.PI * 2;
      return { x: CENTER_X + Math.cos(angle) * 10, y: CENTER_Y + Math.sin(angle) * 3.5, vx: 0, vy: 0 };
    });

    function step() {
      for (const bee of bees) {
        const dx = CENTER_X - bee.x;
        const dy = CENTER_Y - bee.y;
        const dist = Math.hypot(dx, dy) || 1;
        const pull = (dist - 9) * 0.02;
        bee.vx += (-dy / dist) * 0.06 + (dx / dist) * pull + (random() - 0.5) * 0.15;
        bee.vy += (dx / dist) * 0.04 + (dy / dist) * pull * 0.5 + (random() - 0.5) * 0.1;
        const speed = Math.hypot(bee.vx, bee.vy);
        if (speed > 0.9) {
          bee.vx = (bee.vx / speed) * 0.9;
          bee.vy = (bee.vy / speed) * 0.9;
        }
        bee.x = Math.min(WIDTH - 1, Math.max(0, bee.x + bee.vx));
        bee.y = Math.min(HEIGHT - 1, Math.max(0, bee.y + bee.vy * 0.6));
      }
    }

    function render() {
      const grid = Array.from({ length: HEIGHT }, () => Array(WIDTH).fill(" "));
      COMB.forEach((line, row) => {
        [...line].forEach((ch, col) => {
          if (ch !== " ") grid[COMB_Y + row][COMB_X + col] = ch;
        });
      });
      RESTING_SPOTS.slice(0, resting).forEach(([x, y]) => {
        grid[y][x] = ".";
      });
      const bodies = new Set(bees.map((b) => `${Math.round(b.y)},${Math.round(b.x)}`));
      pre.innerHTML = grid
        .map((row, y) => row.map((ch, x) => (bodies.has(`${y},${x}`) ? '<span class="bee">*</span>' : ch)).join(""))
        .join("\n");
    }

    for (let i = 0; i < 6; i += 1) step();
    render();
    if (reducedMotion() || flying === 0) return;

    // 無限には動かさない: 開いた直後の数秒と、マウスやフォーカスが触れている間だけ飛ぶ(装飾なので、止まっていて困らない)
    const ACTIVE_MS = 6000;
    // 20秒ごとの自動更新(再読み込み)のたびに飛び直さないよう、開いた直後に飛ぶのはそのタブで最初の1回だけ
    const firstOpen = session.get("hub.hiveFlown") !== "1";
    session.set("hub.hiveFlown", "1");
    let activeUntil = firstOpen ? performance.now() + ACTIVE_MS : 0;
    let timer = null;
    let visible = true;
    const sleep = () => {
      if (timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
    };
    const wake = () => {
      activeUntil = performance.now() + ACTIVE_MS;
      sync();
    };
    pre.addEventListener("mouseenter", wake);
    const sync = () => {
      const shouldRun = visible && !document.hidden && performance.now() <= activeUntil;
      if (shouldRun && timer === null) {
        timer = window.setInterval(() => {
          step();
          render();
          if (performance.now() > activeUntil) sleep();
        }, 150);
      } else if (!shouldRun && timer !== null) {
        window.clearInterval(timer);
        timer = null;
      }
    };
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((entries) => {
        visible = entries[entries.length - 1].isIntersecting;
        sync();
      }).observe(pre);
    }
    document.addEventListener("visibilitychange", sync);
    sync();
  })();

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
        if (atMs === null) {
          const card = $("#overview-card");
          if (card) updateTitleBadge(parseJson(card.dataset.openAlerts, []).length);
        }
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
      // 先頭が = + - @ タブ 改行 のセルは、Excel等が数式として実行しうる(CSVインジェクション)。
      // アラート本文は外部から届く値なので、' を付けて文字列として扱わせる。
      const escape = (v) => {
        let text = String(v ?? "");
        if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
        return `"${text.replace(/"/g, '""')}"`;
      };
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

  // スヌーズのトグルスイッチ: 押すと通知の一時停止(1時間)がオン/オフになる
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
        target.setAttribute("aria-checked", "true");
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
        target.setAttribute("aria-checked", "false");
        window.location.reload();
      } catch (err) {
        target.disabled = false;
        window.alert(`スヌーズ解除に失敗しました: ${err}`);
      }
    });
  });

  // ------------------------------------------------------------------ 台帳の再読み込み・リポジトリ操作
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
        pop(target);
        window.setTimeout(() => window.location.reload(), 1500);
      } catch (err) {
        target.disabled = false;
        target.textContent = originalText;
        window.alert(`起動に失敗しました: ${err}`);
      }
    });
  });

  // 停止(2026-11-17)。このHubが起動したものだけ止められる(サーバーが記録したPIDで判断する)。
  $$(".repo-stop-btn").forEach((btn) => {
    const originalText = btn.textContent;
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      target.disabled = true;
      target.textContent = "Stopping...";
      try {
        const res = await fetch(`/api/repos/${target.dataset.repoId}/stop/${target.dataset.targetIndex}`, { method: "POST" });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
        target.textContent = "Stopped";
        pop(target);
        window.setTimeout(() => window.location.reload(), 800);
      } catch (err) {
        target.disabled = false;
        target.textContent = originalText;
        window.alert(`停止できませんでした: ${err.message || err}`);
      }
    });
  });

  // 複数プロセス構成のリポジトリ向け一括起動。既存の単体起動エンドポイントを順番に叩くだけ。
  // 進行はステップインジケーターで見せる(待機 → 実行中 → 完了 / 失敗。記号と文字を併記)。
  const STEP_STATES = {
    waiting: { glyph: "○", label: "待機" },
    running: { glyph: "▸", label: "実行中" },
    done: { glyph: "✓", label: "完了" },
    failed: { glyph: "■", label: "失敗" },
  };

  function setStep(item, state) {
    item.dataset.step = state;
    item.querySelector(".steps-glyph").textContent = STEP_STATES[state].glyph;
    item.querySelector(".steps-status").textContent = STEP_STATES[state].label;
  }

  $$(".repo-launch-all-btn").forEach((btn) => {
    const originalText = btn.textContent;
    btn.addEventListener("click", async (event) => {
      const target = event.currentTarget;
      const repoId = target.dataset.repoId;
      const launchButtons = $$(`.repo-launch-btn[data-repo-id="${repoId}"]`);
      target.disabled = true;
      target.textContent = "Starting all...";

      const previous = target.parentElement.querySelector(".steps");
      if (previous) previous.remove();
      const steps = document.createElement("ol");
      steps.className = "steps";
      steps.setAttribute("role", "status");
      const items = launchButtons.map((launchBtn) => {
        const item = document.createElement("li");
        const glyph = document.createElement("span");
        glyph.className = "steps-glyph";
        glyph.setAttribute("aria-hidden", "true");
        const name = document.createElement("span");
        name.className = "steps-name";
        name.textContent = launchBtn.dataset.targetName || launchBtn.textContent.trim();
        const status = document.createElement("span");
        status.className = "steps-status";
        item.append(glyph, name, status);
        setStep(item, "waiting");
        steps.appendChild(item);
        return item;
      });
      target.parentElement.appendChild(steps);

      let failedCount = 0;
      for (const [index, launchBtn] of launchButtons.entries()) {
        setStep(items[index], "running");
        try {
          const res = await fetch(`/api/repos/${repoId}/launch/${launchBtn.dataset.targetIndex}`, { method: "POST" });
          if (res.ok) {
            setStep(items[index], "done");
          } else {
            failedCount += 1;
            setStep(items[index], "failed");
          }
        } catch (err) {
          failedCount += 1;
          setStep(items[index], "failed");
        }
      }
      if (failedCount > 0) {
        // 失敗は、ステップに残したまま、ダイアログで遮らない(どれが失敗したか見える)
        target.disabled = false;
        target.textContent = originalText;
      } else {
        target.textContent = "Started all";
        pop(target);
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
