/* LearnWise AI scroll story engine (no dependencies).
   Three modes, chosen from the screen and the user's motion settings:
   - cine  (wide screens): one tall .story with a sticky .stage. Scrolling moves a progress value t.
           Scene k is driven by x = t - k: it emerges from behind (x -0.38..0), holds (0..0.62), then
           shrinks back and fades (0.62..1) while scene k+1 enters. Panels shrink-to-fit, never clip.
   - lite  (phones, tablets, short screens): normal flowing page; each panel gently scales and fades
           in as it rises into view and eases back as it leaves. All content stays full size and readable.
   - plain (reduced motion, "Simple view", or if this file is missing): ordinary stacked sections. */
(function (root) {
  "use strict";
  var ENTER = 0.38, HOLD = 0.62, TAIL = 0.6;

  function smooth(x) { return x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x); }

  // Pure: look of one scene in cine mode. o = opacity, s = scale, y = shift (vh), r = tilt (deg).
  function sceneState(x) {
    if (x <= -ENTER) return { o: 0, s: 0.8, y: 5, r: 0 };
    if (x < 0) {
      var e = smooth((x + ENTER) / ENTER);
      return { o: smooth(Math.min(1, e * 1.4)), s: 0.8 + 0.2 * e, y: 5 * (1 - e), r: 0 };
    }
    if (x <= HOLD) return { o: 1, s: 1, y: 0, r: 0 };
    if (x < 1) {
      var g = smooth((x - HOLD) / (1 - HOLD));
      return { o: 1 - smooth((g - 0.45) / 0.55), s: 1 - 0.42 * g, y: -4 * g, r: 7 * g };
    }
    return { o: 0, s: 0.58, y: -4, r: 7 };
  }

  // Pure: look of one panel in lite mode. vTop = panel top relative to the viewport, h = panel height.
  function liteState(vTop, h, vh) {
    var e = smooth((vh - vTop - 0.08 * vh) / (0.35 * vh));     // 0 below the fold, 1 once well inside
    var g = smooth((0.4 * vh - (vTop + h)) / (0.4 * vh));      // 0 until the panel's bottom nears the top
    return { s: (0.9 + 0.1 * e) * (1 - 0.08 * g), o: (0.35 + 0.65 * e) * (1 - 0.5 * g) };
  }

  function mount(rootEl) {
    var scenes = [].slice.call(rootEl.querySelectorAll(".scene"));
    var panels = scenes.map(function (s) { return s.querySelector(".panel"); });
    var stage = rootEl.querySelector(".stage");
    var dots = [].slice.call(rootEl.querySelectorAll(".dots button"));
    var hdrEl = document.getElementById("hdr");
    var n = scenes.length;
    var mq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)")
      : { matches: false, addEventListener: function () {}, removeEventListener: function () {} };
    var mode = "plain", cur = 0, tgt = 0, raf = 0, rz = 0, io = null, ro = null;
    var fits = [], last = [], slot = 600, hdr = 0, tops = [], hs = [], liteKey = [];

    function simple() { try { return localStorage.getItem("lw_simple") === "1"; } catch (e) { return false; } }
    function pick() {
      if (mq.matches || simple()) return "plain";
      return innerWidth >= 900 && innerHeight >= 520 ? "cine" : "lite";
    }

    function count(el) {
      if (mq.matches) return;
      [].forEach.call(el.querySelectorAll("[data-count]"), function (c) {
        var v = +c.getAttribute("data-count"), suf = c.getAttribute("data-suf") || "", t0 = performance.now();
        (function f(now) {
          var p = Math.min(1, (now - t0) / 900);
          c.textContent = Math.round(v * smooth(p)) + suf;
          if (p < 1) requestAnimationFrame(f);
        })(t0);
      });
    }
    function seen(el) { if (!el.classList.contains("seen")) { el.classList.add("seen"); count(el); } }

    /* ---------- cine ---------- */
    function measure() {
      hdr = hdrEl ? hdrEl.offsetHeight : 0;
      var sh = innerHeight - hdr, sw = stage.clientWidth || innerWidth;
      slot = sh;
      rootEl.style.setProperty("--hdr", hdr + "px");
      rootEl.style.setProperty("--stage", sh + "px");
      rootEl.style.setProperty("--h", Math.round(sh + (n - 1 + TAIL) * slot) + "px");
      fits = panels.map(function (p) {
        return p && p.offsetHeight ? Math.min(1, (sh - 20) / p.offsetHeight, (sw - 20) / p.offsetWidth) : 1;
      });
      last = [];
      frame();
    }
    function apply(t) {
      var best = 0, bo = -1;
      scenes.forEach(function (s, k) {
        var st = sceneState(t - k), f = fits[k] || 1;
        if (st.o > bo) { bo = st.o; best = k; }
        var key = [st.o.toFixed(3), st.s.toFixed(3), st.y.toFixed(2), st.r.toFixed(2), f.toFixed(3)].join();
        if (last[k] === key) return;
        last[k] = key;
        var live = st.o > 0.5;
        s.style.opacity = st.o;
        s.style.visibility = st.o < 0.01 ? "hidden" : "visible";
        s.style.transform = "translate3d(0," + st.y + "vh,0) rotateX(" + st.r + "deg) scale(" + (st.s * f) + ")";
        s.style.pointerEvents = live ? "auto" : "none";
        s.inert = !live; // scenes out of view cannot take focus or clicks
        if (live) seen(s);
      });
      dots.forEach(function (d, k) { if (k === best) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current"); });
    }
    function frame() {
      raf = 0;
      var r = rootEl.getBoundingClientRect();
      tgt = Math.max(0, Math.min(n - 1 + TAIL, (hdr - r.top) / slot));
      cur += (tgt - cur) * 0.22; // light smoothing so mouse-wheel steps feel fluid
      if (Math.abs(tgt - cur) < 0.0008) cur = tgt;
      apply(cur);
      if (cur !== tgt) raf = requestAnimationFrame(frame);
    }

    /* ---------- lite: positions are cached, so a scroll frame needs no layout reads ---------- */
    function measureLite() {
      var y = scrollY;
      tops = scenes.map(function (s) { return s.getBoundingClientRect().top + y; });
      hs = panels.map(function (p, k) { return p ? p.offsetHeight : scenes[k].offsetHeight; });
      liteKey = [];
      liteFrame();
    }
    function liteFrame() {
      raf = 0;
      var y = scrollY, vh = innerHeight;
      panels.forEach(function (p, k) {
        if (!p) return;
        var vTop = tops[k] - y, st = liteState(vTop, hs[k], vh);
        if (st.o > 0.5 && vTop < vh * 0.9) seen(scenes[k]);
        var key = st.s.toFixed(3) + "," + st.o.toFixed(3);
        if (liteKey[k] === key) return;
        liteKey[k] = key;
        p.style.transform = "scale(" + st.s.toFixed(3) + ")";
        p.style.opacity = st.o.toFixed(3);
      });
    }

    /* ---------- plain ---------- */
    function observeStacked() {
      if (io) return;
      if (!("IntersectionObserver" in window)) { scenes.forEach(seen); return; }
      io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) seen(e.target); }); }, { threshold: 0.18 });
      scenes.forEach(function (s) { io.observe(s); });
    }

    function schedule() { if (!raf) raf = requestAnimationFrame(mode === "cine" ? frame : liteFrame); }
    function remeasure() { if (mode === "cine") measure(); else if (mode === "lite") measureLite(); }
    function watch() {
      if (!("ResizeObserver" in window)) return;
      ro = new ResizeObserver(remeasure);
      panels.forEach(function (p) { if (p) ro.observe(p); });
    }

    function teardown(m) {
      if (ro) { ro.disconnect(); ro = null; }
      if (m === "cine") {
        rootEl.classList.remove("cine");
        removeEventListener("scroll", schedule);
        rootEl.style.removeProperty("--h");
        scenes.forEach(function (s) { s.removeAttribute("style"); s.inert = false; });
      } else if (m === "lite") {
        rootEl.classList.remove("lite");
        removeEventListener("scroll", schedule);
        panels.forEach(function (p) { if (p) { p.style.removeProperty("transform"); p.style.removeProperty("opacity"); } });
      }
    }
    function setup(m) {
      if (io) { io.disconnect(); io = null; }
      if (m === "cine") { rootEl.classList.add("cine"); addEventListener("scroll", schedule, { passive: true }); watch(); measure(); }
      else if (m === "lite") { rootEl.classList.add("lite"); addEventListener("scroll", schedule, { passive: true }); watch(); measureLite(); }
      else observeStacked();
    }
    function recheck() {
      var m = pick();
      if (m !== mode) { teardown(mode); mode = m; setup(m); } else remeasure();
    }
    function onResize() { if (!rz) rz = requestAnimationFrame(function () { rz = 0; recheck(); }); }

    function goTo(i) {
      var behavior = mq.matches ? "auto" : "smooth";
      if (mode === "cine") scrollTo({ top: rootEl.getBoundingClientRect().top + scrollY - hdr + (i + 0.15) * slot, behavior: behavior });
      else scenes[i].scrollIntoView({ behavior: behavior, block: "start" });
    }
    dots.forEach(function (d, k) { d.addEventListener("click", function () { goTo(k); }); });

    function unmount() {
      teardown(mode); mode = "plain";
      if (io) { io.disconnect(); io = null; }
      removeEventListener("resize", onResize); removeEventListener("load", remeasure);
      if (mq.removeEventListener) mq.removeEventListener("change", recheck);
      cancelAnimationFrame(raf); cancelAnimationFrame(rz);
      rootEl.classList.remove("js");
    }

    rootEl.classList.add("js");
    addEventListener("resize", onResize);
    addEventListener("load", remeasure); // fonts and layout settle after load
    if (mq.addEventListener) mq.addEventListener("change", recheck);
    recheck();
    return { measure: remeasure, goTo: goTo, unmount: unmount, mode: function () { return mode; }, active: function () { return mode === "cine"; } };
  }

  var api = { mount: mount, sceneState: sceneState, liteState: liteState, ENTER: ENTER, HOLD: HOLD, TAIL: TAIL };
  root.Story = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
