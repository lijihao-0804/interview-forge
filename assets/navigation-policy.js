/* InterviewForge 轻量站内导航策略。
 * 只处理已有 <a> 的打开方式：连续流程/主导航固定当前页，独立学习内容
 * 继承历史新标签行为并允许用户切换；外链始终新标签。 */
(function () {
  "use strict";
  var KEY = "learningContentOpenMode";
  var DEFAULT = "new-tab";
  var VALID = { "same-tab": true, "new-tab": true };
  var SAME_TAB_SELECTOR = [
    ".site-nav a", ".topbar nav a", ".dashboard-nav a", ".hot100-topnav a",
    ".site-brand", ".brand", ".top a", ".breadcrumb a", ".chapter-nav a",
    ".problem-nav-btn", ".sol-nav-item", ".nav-toc", ".fap-admin-link", "#entry-admin"
  ].join(",");

  function readPreference() {
    try {
      var value = localStorage.getItem(KEY);
      return VALID[value] ? value : DEFAULT;
    } catch (error) { return DEFAULT; }
  }
  function writePreference(value) {
    if (!VALID[value]) value = DEFAULT;
    try { localStorage.setItem(KEY, value); } catch (error) { }
    applyAll();
    return value;
  }
  function isExternal(anchor) {
    try {
      var url = new URL(anchor.href, document.baseURI);
      return url.origin !== location.origin;
    } catch (error) { return false; }
  }
  function declaredMode(anchor) {
    var declared = anchor.getAttribute("data-navigation-policy");
    if (declared === "user-preference") return "user-preference";
    if (VALID[declared] || declared === "new-tab") return declared;
    if (anchor.matches && anchor.matches(SAME_TAB_SELECTOR)) return "same-tab";
    // 历史产物中 target=_blank 的内部独立内容属于可切换偏好，保持默认行为。
    return (anchor.getAttribute("target") || "").toLowerCase() === "_blank" ? "user-preference" : "same-tab";
  }
  function resolveNavigationMode(mode, preference) {
    if (mode === "user-preference") return VALID[preference] ? preference : DEFAULT;
    return mode === "new-tab" ? "new-tab" : "same-tab";
  }
  function applyAnchor(anchor) {
    if (!anchor || !anchor.href) return;
    var raw = (anchor.getAttribute("href") || "").trim().toLowerCase();
    if (!raw || raw.charAt(0) === "#" || /^(?:javascript:|mailto:|tel:)/.test(raw) || anchor.hasAttribute("download")) return;
    var mode = isExternal(anchor) ? "new-tab" : resolveNavigationMode(declaredMode(anchor), readPreference());
    if (mode === "new-tab") {
      anchor.setAttribute("target", "_blank");
      anchor.setAttribute("rel", "noopener noreferrer");
    } else {
      anchor.removeAttribute("target");
      // same-tab 不依赖 rel；移除旧生成器遗留值，避免语义混淆。
      anchor.removeAttribute("rel");
    }
  }
  function applyAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.matches && scope.matches("a")) applyAnchor(scope);
    scope.querySelectorAll("a[href]").forEach(applyAnchor);
  }
  window.ForgeNavigationPolicy = {
    key: KEY,
    getPreference: readPreference,
    setPreference: writePreference,
    resolveNavigationMode: resolveNavigationMode,
    apply: applyAll
  };
  applyAll(document);
  window.addEventListener("storage", function (event) {
    if (event.key === KEY) applyAll(document);
  });
  // 书架/中控台已有脚本会动态创建学习入口；只观察新增节点，不拦截点击。
  if (window.MutationObserver) {
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (node.nodeType === 1) applyAll(node);
        });
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
