/* hub/dashboard/static/spring.js
 *
 * 状態変化の動き(ばね)。2026-11-26 に足した 3 つの部品と、それを動かす小さなばねの計算。
 *   1. セグメント(.chip-group): 選択中の下地が、ばねで滑って移る。速さに応じて少し伸び縮みする。
 *   2. 読み込み → 完了(Start ボタン): 文字 → 回る輪 + 状態 → 完了の印(✓)と色。失敗は揺れる。
 *   3. 長押しで実行(管理画面の Sync): 押している間に塗りが進み、満ちたら実行。途中で離すと戻って揺れる。
 *
 * 動きの元: designbookmark.com の Motion 部品(Segmented control・Loading to success・Hold to publish)。
 * 元のコードはライセンスの記載が無いので写さない。**ばねの強さ・減衰の値と、動きの決まりだけ**を合わせて、
 * ここで書き直した(値は style.css の --spring-* に置く)。
 *
 * 計算: 質量 1 のばね。a = -k(x - 目標) - c·v を、半陰的オイラー(速度を先に更新)で、1 フレームを 4 分割して積む。
 * 1 フレームの時間は最大 1/30 秒(タブが裏に回った後に飛ばない)。
 * 動きを減らす設定(prefers-reduced-motion): ばねは使わず、すぐ目標の値にする(止める = 消すのでなく、即時の切替)。
 * 長押しの「塗りが進む」は進み具合の表示(情報)なので、動きを減らす設定でも進む。
 */
(() => {
  const reduceQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  const reduced = () => Boolean(reduceQuery && reduceQuery.matches);
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  // ---- ばねの値(style.css の :root。「強さ 減衰」の 2 つの数) --------------------------------
  function token(name, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return raw || fallback;
  }
  function springToken(name, fallback) {
    const parts = token(name, fallback).split(/\s+/).map(Number);
    return { k: parts[0], c: parts[1] };
  }
  function numberToken(name, fallback) {
    const n = Number(token(name, String(fallback)));
    return Number.isFinite(n) ? n : fallback;
  }

  // ---- ばねの計算(1 つの rAF ループで、動いているばねだけを進める) ----------------------------
  const active = new Set();
  let rafId = 0;
  let last = 0;
  const SUBSTEPS = 4;
  const REST_X = 0.001;
  const REST_V = 0.01;

  function frame(now) {
    const dt = Math.min((now - last) / 1000, 1 / 30);
    last = now;
    const h = dt / SUBSTEPS;
    for (const s of Array.from(active)) {
      for (let i = 0; i < SUBSTEPS; i++) {
        const a = -s.k * (s.x - s.target) - s.c * s.v;
        s.v += a * h;
        s.x += s.v * h;
      }
      if (Math.abs(s.x - s.target) < REST_X && Math.abs(s.v) < REST_V) {
        s.x = s.target;
        s.v = 0;
        active.delete(s);
      }
      s.onUpdate(s.x, s.v);
    }
    rafId = active.size ? window.requestAnimationFrame(frame) : 0;
  }

  function wake(s) {
    active.add(s);
    if (!rafId) {
      last = performance.now();
      rafId = window.requestAnimationFrame(frame);
    }
  }

  // spring({value, k, c, onUpdate}) → { to(target, {velocity}), set(value), kick(velocity), tune(k, c), x, v }
  function spring({ value = 0, k = 300, c = 20, onUpdate = () => {} }) {
    const s = { x: value, v: 0, target: value, k, c, onUpdate };
    return {
      get x() { return s.x; },
      get v() { return s.v; },
      to(target, opts = {}) {
        s.target = target;
        if (typeof opts.velocity === "number") s.v = opts.velocity;
        if (reduced()) {
          s.x = target;
          s.v = 0;
          active.delete(s);
          s.onUpdate(s.x, s.v);
          return;
        }
        wake(s);
      },
      set(v) {
        s.x = v;
        s.target = v;
        s.v = 0;
        active.delete(s);
        s.onUpdate(s.x, s.v);
      },
      kick(velocity) {
        if (reduced()) return;
        s.v += velocity;
        wake(s);
      },
      tune(nk, nc) {
        s.k = nk;
        s.c = nc;
      },
    };
  }

  // ---- 1. セグメント(.chip-group の選択中の下地) -------------------------------------------
  // 下地は 1 つの要素(.seg-ind)。選択中のチップ(.is-active)の位置と幅へ、横はばねで、縦と幅はすぐに合わせる。
  function syncSegments(root) {
    const scope = root || document;
    scope.querySelectorAll(".chip-group").forEach((group) => {
      const chips = Array.from(group.querySelectorAll(":scope > .chip"));
      if (!chips.length) return;
      let st = group._seg;
      if (!st || !group.contains(st.ind)) {
        const ind = document.createElement("span");
        ind.className = "seg-ind";
        ind.setAttribute("aria-hidden", "true");
        group.prepend(ind);
        group.classList.add("is-seg");
        const { k, c } = springToken("--spring-seg", "300 20");
        st = group._seg = { ind, current: null, y: 0, w: 0 };
        st.sx = spring({
          value: 0, k, c,
          onUpdate: (x, v) => {
            const sp = clamp(Math.abs(v) / 1400, 0, 0.22);
            ind.style.transform = `translate(${x}px, ${st.y}px) scale(${1 + sp}, ${1 - sp / 2})`;
          },
        });
      }
      const on = chips.find((chip) => chip.classList.contains("is-active"));
      if (!on) {
        st.ind.hidden = true;
        st.current = null;
        return;
      }
      st.ind.hidden = false;
      st.y = on.offsetTop;
      st.w = on.offsetWidth;
      st.ind.style.width = `${st.w}px`;
      st.ind.style.height = `${on.offsetHeight}px`;
      if (st.current === null || st.current === on || on.offsetTop !== group._segLastTop) {
        st.sx.set(on.offsetLeft);   // 初めて・同じチップ・行が変わった(折り返し)ときは、動かさずに合わせる
      } else {
        st.sx.to(on.offsetLeft);
      }
      group._segLastTop = on.offsetTop;
      st.current = on;
    });
  }
  window.addEventListener("resize", () => {
    document.querySelectorAll(".chip-group.is-seg").forEach((group) => {
      if (group._seg) group._seg.current = null;   // 幅が変わったら、次の同期は動かさずに合わせる
    });
    syncSegments(document);
  });

  // ---- 2. 読み込み → 完了(ボタン) ----------------------------------------------------------
  const SVG_NS = "http://www.w3.org/2000/svg";
  function checkIcon(size) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("busy-check");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", "M5 12.5l4.5 4.5L19 7.5");
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "2.6");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-dasharray", "22");
    path.setAttribute("stroke-dashoffset", "22");
    svg.appendChild(path);
    return { svg, path };
  }

  // busy(button) → { loading(text), text(text), success(text), fail(), settle(ms) }
  // 元のボタンの中身は、fail() で戻す。成功したら、呼び出し側が再読み込みする前提(戻さない)。
  function busy(button) {
    const original = Array.from(button.childNodes).map((n) => n.cloneNode(true));
    const tWidth = springToken("--spring-busy-width", "300 22");
    const tLabel = springToken("--spring-busy-label", "400 30");
    const tSpin = springToken("--spring-busy-spin", "300 28");
    const tDone = springToken("--spring-busy-done", "220 20");
    const tFill = springToken("--spring-busy-fill", "200 30");
    const tCheck = springToken("--spring-busy-check", "120 20");
    const tShake = springToken("--spring-hold-shake", "700 9");

    const spin = document.createElement("span");
    spin.className = "busy-spin";
    spin.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.className = "busy-label";
    const { svg, path } = checkIcon(16);
    let angle = 0;
    let spinning = false;
    let spinLast = 0;

    const wSpring = spring({ value: button.offsetWidth, ...tWidth, onUpdate: (x) => { button.style.width = `${x}px`; } });
    const labelSpring = spring({ value: 0, ...tLabel, onUpdate: (x) => {
      label.style.opacity = String(clamp(x, 0, 1));
      label.style.transform = `translateY(${(1 - clamp(x, 0, 1)) * 6}px)`;
    } });
    const spinSpring = spring({ value: 0, ...tSpin, onUpdate: (x) => {
      const p = clamp(x, 0, 1);
      spin.style.opacity = String(p);
      spin.style.setProperty("--busy-scale", String(0.6 + 0.4 * p));
    } });
    const doneSpring = spring({ value: 0, ...tDone, onUpdate: (x) => {
      svg.style.opacity = String(clamp(x, 0, 1));
    } });
    const fillSpring = spring({ value: 0, ...tFill, onUpdate: (x) => {
      button.style.setProperty("--busy-fill", `${clamp(x, 0, 1) * 100}%`);
    } });
    const checkSpring = spring({ value: 22, ...tCheck, onUpdate: (x) => {
      path.setAttribute("stroke-dashoffset", String(Math.max(0, x)));
    } });
    const shakeSpring = spring({ value: 0, ...tShake, onUpdate: (x) => {
      button.style.translate = `${x}px 0`;
    } });

    function spinLoop(now) {
      if (!spinning) return;
      const dt = Math.min((now - spinLast) / 1000, 1 / 30);
      spinLast = now;
      angle = (angle + 504 * dt) % 360;   // 1 秒に 1.4 回転
      spin.style.setProperty("--busy-angle", `${angle}deg`);
      window.requestAnimationFrame(spinLoop);
    }

    // 中身を入れ替えて、幅を「いまの幅 → 新しい中身の幅」へばねで移す
    function morph(nodes) {
      const from = button.offsetWidth;
      button.style.width = "";
      button.replaceChildren(...nodes);
      const to = button.offsetWidth;
      wSpring.set(from);
      wSpring.to(to);
    }

    return {
      loading(text) {
        button.classList.add("is-busy");
        label.textContent = text;
        morph([spin, label]);
        labelSpring.set(0);
        labelSpring.to(1);
        spinSpring.to(1);
        if (!reduced() && !spinning) {
          spinning = true;
          spinLast = performance.now();
          window.requestAnimationFrame(spinLoop);
        }
      },
      text(text) {
        if (label.textContent === text) return;
        label.textContent = text;
        const to = (() => { const w = button.style.width; button.style.width = ""; const n = button.offsetWidth; button.style.width = w; return n; })();
        wSpring.to(to);
      },
      success(text) {
        spinning = false;
        spinSpring.to(0);
        button.classList.add("is-done");
        label.textContent = text;
        morph([svg, label]);
        doneSpring.set(0);
        doneSpring.to(1);
        fillSpring.to(1);
        checkSpring.set(22);
        window.setTimeout(() => checkSpring.to(0), reduced() ? 0 : 150);
        button.setAttribute("aria-label", text);
      },
      fail() {
        spinning = false;
        button.classList.remove("is-busy", "is-done");
        button.style.width = "";
        button.style.removeProperty("--busy-fill");
        button.removeAttribute("aria-label");
        button.replaceChildren(...original);
        shakeSpring.set(0);
        shakeSpring.kick(-260);   // 失敗は揺らす(左へ弾いて、ばねで戻る)
      },
      settle(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, reduced() ? Math.min(ms, 300) : ms));
      },
    };
  }

  // ---- 3. 長押しで実行 ----------------------------------------------------------------------
  // holdButton(button, {label, doneLabel, onComplete, onError}) — onComplete は Promise を返す(失敗なら reject → onError)。
  // 塗りは押している間だけ、一定の速さで進む(進み具合の表示)。満ちたら丸くなり ✓、onComplete を呼ぶ。
  function holdButton(button, { label, doneLabel, onComplete, onError }) {
    const holdMs = numberToken("--hold-ms", 1200);
    const doneMs = numberToken("--hold-done-ms", 1700);
    const tRelease = springToken("--spring-hold-release", "260 14");
    const tMorph = springToken("--spring-hold-morph", "320 20");
    const tSquash = springToken("--spring-hold-squash", "520 20");
    const tShake = springToken("--spring-hold-shake", "700 9");

    button.classList.add("hold");
    button.replaceChildren();
    const fill = document.createElement("span");
    fill.className = "hold-fill";
    fill.setAttribute("aria-hidden", "true");
    const under = document.createElement("span");
    under.className = "hold-label";
    under.textContent = label;
    const over = document.createElement("span");
    over.className = "hold-label hold-label-top";
    over.setAttribute("aria-hidden", "true");
    over.textContent = label;
    const { svg, path } = checkIcon(18);
    button.append(fill, under, over, svg);

    let width = 0;
    let mode = "idle";   // idle / holding / done
    let progress = 0;
    let holdStart = 0;
    let squashX = 1;
    let shakeX = 0;

    const paint = () => {
      const p = clamp(progress, 0, 1);
      fill.style.width = `${p * 100}%`;
      over.style.clipPath = `inset(0 ${(1 - p) * 100}% 0 0)`;
      button.style.transform = `translateX(${shakeX}px) scale(${squashX})`;
    };
    const fillSpring = spring({ value: 0, ...tRelease, onUpdate: (x) => { progress = x; paint(); } });
    const squash = spring({ value: 1, ...tSquash, onUpdate: (x) => { squashX = x; paint(); } });
    const shake = spring({ value: 0, ...tShake, onUpdate: (x) => { shakeX = x; paint(); } });
    const morph = spring({ value: 0, ...tMorph, onUpdate: (x) => { if (width) button.style.width = `${x}px`; } });

    function tick(now) {
      if (mode !== "holding") return;
      progress = clamp((now - holdStart) / holdMs, 0, 1);
      paint();
      if (progress >= 1) {
        complete();
        return;
      }
      window.requestAnimationFrame(tick);
    }

    function start() {
      if (mode !== "idle" || button.disabled) return;
      mode = "holding";
      width = button.offsetWidth;
      holdStart = performance.now() - progress * holdMs;   // 戻りきる前に押し直したら、その位置から
      fillSpring.set(progress);
      squash.to(0.96);
      window.requestAnimationFrame(tick);
    }

    function stop() {
      if (mode !== "holding") return;
      mode = "idle";
      const reached = progress;
      squash.to(1);
      fillSpring.set(progress);
      fillSpring.to(0);
      shake.kick(-260 * reached);   // 途中で離した: 進んだ分だけ「いいえ」と揺れる
    }

    function reset() {
      mode = "idle";
      button.classList.remove("is-done");
      morph.tune(tMorph.k * 0.8, tMorph.c);
      morph.to(width);
      progress = 0;
      fillSpring.set(0);
      path.setAttribute("stroke-dashoffset", "22");
      window.setTimeout(() => { button.style.width = ""; }, reduced() ? 0 : 600);
    }

    async function complete() {
      mode = "done";
      squash.to(1, { velocity: 2.5 });
      button.classList.add("is-done");
      button.setAttribute("aria-busy", "true");
      morph.tune(tMorph.k, tMorph.c);
      morph.set(width);
      morph.to(button.offsetHeight);   // 丸くなる
      path.setAttribute("stroke-dashoffset", "0");
      try {
        await onComplete();
        under.textContent = doneLabel;
      } catch (err) {
        button.removeAttribute("aria-busy");
        reset();
        shake.kick(-260);
        if (onError) onError(err);
        return;
      }
      window.setTimeout(() => button.removeAttribute("aria-busy"), doneMs);
    }

    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      try {
        button.setPointerCapture(event.pointerId);
      } catch (err) {
        // 捕捉できないポインタ(支援技術の合成イベントなど)でも、長押しはできる
      }
      start();
    });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) button.addEventListener(type, stop);
    button.addEventListener("keydown", (event) => {
      if ((event.key === " " || event.key === "Enter") && !event.repeat) {
        event.preventDefault();
        start();
      }
    });
    button.addEventListener("keyup", (event) => {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        stop();
      }
    });
    button.addEventListener("contextmenu", (event) => event.preventDefault());
    // クリック(押してすぐ離す)では実行しない。長押しが確認の代わり
    button.addEventListener("click", (event) => event.preventDefault());
    paint();
    return { reset };
  }

  window.HubMotion = { spring, syncSegments, busy, holdButton, reduced };
})();
