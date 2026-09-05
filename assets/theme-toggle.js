/* InterviewForge 主题切换（由 study_server 注入）。
 * 三态循环：跟随系统 → 浅色 → 深色 → 跟随系统，localStorage 持久化。
 * 通过 html[data-theme="light|dark"] 覆写 prefers-color-scheme（CSS 已支持）。 */
(function () {
  "use strict";
  if (document.getElementById("forge-theme-btn")) return;
  var KEY = "forge-theme";
  var MODES = [
    { v: "system", icon: "💻", label: "主题：跟随系统（点击切换浅色）" },
    { v: "light", icon: "☀️", label: "主题：浅色（点击切换深色）" },
    { v: "dark", icon: "🌙", label: "主题：深色（点击切换回跟随系统）" }
  ];

  function stored() {
    var v = null;
    try { v = localStorage.getItem(KEY); } catch (e) { }
    return MODES.some(function (m) { return m.v === v; }) ? v : "system";
  }

  function apply(mode) {
    var root = document.documentElement;
    if (mode === "light" || mode === "dark") root.setAttribute("data-theme", mode);
    else root.removeAttribute("data-theme");
    try { localStorage.setItem(KEY, mode); } catch (e) { }
    paint(mode);
  }

  function paint(mode) {
    var m = MODES.filter(function (x) { return x.v === mode; })[0] || MODES[0];
    btn.textContent = m.icon;
    btn.title = m.label;
  }

  var btn = document.createElement("div");
  btn.id = "forge-theme-btn";
  btn.style.cssText = "position:fixed;left:16px;bottom:16px;z-index:9998;width:34px;height:34px;" +
    "border-radius:50%;border:1px solid #dfe4ee;background:rgba(255,255,255,.92);cursor:pointer;" +
    "display:flex;align-items:center;justify-content:center;font-size:15px;user-select:none;" +
    "box-shadow:0 6px 18px rgba(33,45,73,.14);transition:transform .15s";
  btn.onclick = function () { apply(MODES[(MODES.findIndex(function (m) { return m.v === stored(); }) + 1) % MODES.length].v); };

  // 首帧：先按系统/存储值上色，避免闪烁
  apply(stored());
  document.body.appendChild(btn);
})();
