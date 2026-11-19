/* InterviewForge 主题切换（由 study_server 注入）。
 * 三态循环：跟随系统 → 浅色 → 深色 → 跟随系统，localStorage 持久化。
 * 通过 html[data-theme="light|dark"] 覆写 prefers-color-scheme（CSS 已支持）。 */
(function () {
  "use strict";
  if (document.getElementById("forge-theme-btn")) return;
  var KEY = "forge-theme";
  var controlId = document.currentScript && document.currentScript.getAttribute("data-theme-control");
  var systemScheme = controlId && window.matchMedia("(prefers-color-scheme: dark)");
  var btn, select, currentMode = "system";
  var MODES = [
    { v: "system", icon: "💻", label: "主题：跟随系统（点击切换浅色）" },
    { v: "light", icon: "☀️", label: "主题：浅色（点击切换深色）" },
    { v: "dark", icon: "🌙", label: "主题：深色（点击切换回跟随系统）" }
  ];

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return currentMode; }
  }

  function apply(mode, persist) {
    mode = mode === "light" || mode === "dark" ? mode : "system";
    currentMode = mode;
    var root = document.documentElement;
    if (mode === "light" || mode === "dark") root.setAttribute("data-theme", mode);
    else root.removeAttribute("data-theme");
    if (systemScheme) root.toggleAttribute("data-system-dark", systemScheme.matches);
    if (persist !== false) try { localStorage.setItem(KEY, mode); } catch (e) { }
    if (select) select.value = mode;
    if (btn) {
      var m = MODES.find(function (x) { return x.v === mode; });
      btn.textContent = m.icon;
      btn.title = m.label;
    }
  }

  if (controlId) {
    // This page loads the script before its stylesheet to apply the saved palette on first paint.
    function bindSelect() {
      select = document.getElementById(controlId);
      if (!select) return;
      select.value = currentMode;
      select.addEventListener("change", function () { apply(select.value); });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindSelect, { once: true });
    else bindSelect();
    var systemChanged = function () { apply(currentMode, false); };
    if (systemScheme.addEventListener) systemScheme.addEventListener("change", systemChanged);
    else systemScheme.addListener(systemChanged);
  } else {
    var embedded = new URLSearchParams(window.location.search).get("embedded") === "1";
    btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", "切换主题");
    btn.id = "forge-theme-btn";
    btn.style.cssText = "position:fixed;left:16px;bottom:calc(16px + env(safe-area-inset-bottom));z-index:9998;width:34px;height:34px;" +
      "border-radius:50%;border:1px solid #dfe4ee;background:rgba(255,255,255,.92);cursor:pointer;" +
      "display:flex;align-items:center;justify-content:center;padding:0;font-size:15px;user-select:none;" +
      "box-shadow:0 6px 18px rgba(33,45,73,.14);transition:transform .15s";
    btn.onclick = function () { apply(MODES[(MODES.findIndex(function (m) { return m.v === currentMode; }) + 1) % MODES.length].v); };
    if (!embedded) document.body.appendChild(btn);
  }

  apply(stored(), false);
  window.addEventListener("storage", function (event) {
    if (event.key === KEY || event.key === null) apply(stored(), false);
  });
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) apply(stored(), false);
  });
})();
