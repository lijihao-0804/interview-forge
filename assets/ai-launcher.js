(function (global) {
  "use strict";
  var path = global.location.pathname || "";
  if (/\/pages\/ai-assistant\.html$/.test(path) || !global.InterviewForgeAI) return;

  function pageContext() {
    try { return global.InterviewForgeAI.getPageContext(); } catch (_) { return null; }
  }

  function boot(me) {
    if (!me || document.getElementById("if-ai-launcher")) return;
    var button = document.createElement("button");
    button.id = "if-ai-launcher";
    button.type = "button";
    button.className = "if-ai-launcher";
    button.setAttribute("aria-label", "打开 AI 助手");
    button.innerHTML = '<span class="if-ai-launcher-icon" aria-hidden="true">✦</span><span>AI</span>';
    document.body.appendChild(button);

    var drawer = null;
    var frame = null;
    var contextFrame = null;
    function clearDrawerOpenState() {
      document.documentElement.classList.remove("if-ai-drawer-open");
    }
    function sendContext(requestId) {
      if (!frame || !frame.contentWindow) return;
      var payload = {
        type: "interviewforge:page-context",
        context: pageContext()
      };
      if (requestId) payload.request_id = String(requestId);
      frame.contentWindow.postMessage(payload, global.location.origin);
    }
    function scheduleContext() {
      if (contextFrame !== null) return;
      var requestFrame = global.requestAnimationFrame || function (callback) {
        return global.setTimeout(callback, 16);
      };
      contextFrame = requestFrame(function () {
        contextFrame = null;
        sendContext();
      });
    }
    function close() {
      if (drawer) drawer.remove();
      drawer = null;
      frame = null;
      clearDrawerOpenState();
      button.hidden = false;
      document.body.style.overflow = "";
    }
    function open() {
      if (drawer) { sendContext(); return; }
      try {
        drawer = document.createElement("div");
        drawer.className = "if-ai-drawer-wrap";
        drawer.innerHTML = '<button class="if-ai-drawer-backdrop" type="button" aria-label="关闭 AI 助手"></button>' +
          '<aside class="if-ai-drawer" aria-label="AI 助手" role="dialog"><header class="if-ai-drawer-head"><span>AI 助手</span><span class="if-ai-drawer-actions"><a href="/pages/ai-assistant.html" target="_blank" rel="noopener noreferrer">打开完整页面</a><button type="button" aria-label="关闭">×</button></span></header><iframe title="AI 助手对话" src="/pages/ai-assistant.html?embedded=1"></iframe></aside>';
        document.body.appendChild(drawer);
        document.documentElement.classList.add("if-ai-drawer-open");
        button.hidden = true;
        frame = drawer.querySelector("iframe");
        drawer.querySelector(".if-ai-drawer-backdrop").addEventListener("click", close);
        drawer.querySelector(".if-ai-drawer-actions button").addEventListener("click", close);
        frame.addEventListener("load", sendContext);
        document.body.style.overflow = "hidden";
        sendContext();
      } catch (error) {
        close();
        throw error;
      }
    }
    button.addEventListener("click", open);
    global.addEventListener("message", function (event) {
      if (event.origin !== global.location.origin || !event.data) return;
      if (event.data.type === "interviewforge:request-page-context") sendContext(event.data.request_id);
    });
    var update = function () { if (drawer) scheduleContext(); };
    global.addEventListener("scroll", update, { passive: true });
    document.addEventListener("selectionchange", update);
    global.addEventListener("pagehide", clearDrawerOpenState, { once: true });
  }

  fetch("/api/me", { credentials: "same-origin", cache: "no-store" })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(boot)
    .catch(function () { /* 未登录或服务暂不可用时不显示入口 */ });
}(window));
