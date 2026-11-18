(function (global) {
  "use strict";
  var path = global.location.pathname || "";
  if (/\/pages\/ai-assistant\.html$/.test(path) || !global.InterviewForgeAI) return;

  function pageContext() {
    try { return global.InterviewForgeAI.getPageContext(); } catch (_) { return null; }
  }

  var openDrawer = null;
  var pendingOpen = false;
  global.addEventListener("interviewforge:open-ai", function () {
    pendingOpen = true;
    requestOpen();
  });

  function waitForAuth() {
    if (global.InterviewForgeAuth && global.InterviewForgeAuth.ready) return Promise.resolve(global.InterviewForgeAuth);
    return new Promise(function (resolve, reject) {
      var timer = global.setTimeout(function () {
        document.removeEventListener("interviewforge:auth-ready", ready);
        reject(new Error("登录状态暂时不可用，请刷新页面后重试"));
      }, 12000);
      function ready() {
        global.clearTimeout(timer);
        document.removeEventListener("interviewforge:auth-ready", ready);
        if (global.InterviewForgeAuth) resolve(global.InterviewForgeAuth);
        else reject(new Error("登录状态暂时不可用，请刷新页面后重试"));
      }
      document.addEventListener("interviewforge:auth-ready", ready, { once: true });
    });
  }

  function requestOpen() {
    waitForAuth().then(function (auth) {
      return auth.requireUser("使用 AI 助手");
    }).then(function () {
      if (openDrawer) openDrawer();
      else pendingOpen = true;
    }).catch(function (error) {
      if (error && error.code !== "AUTH_REQUIRED") global.alert(error.message || "登录状态暂时不可用，请刷新页面后重试。");
    });
  }

  function boot() {
    if (document.getElementById("if-ai-launcher")) return;
    var button = document.createElement("button");
    button.id = "if-ai-launcher";
    button.type = "button";
    button.className = "if-ai-launcher";
    button.setAttribute("aria-label", "打开 AI 助手");
    button.innerHTML = '<span class="if-ai-launcher-icon" aria-hidden="true">✦</span><span>AI</span>';
    document.body.appendChild(button);

    var drawer = null;
    var frame = null;
    var opener = null;
    var previousOverflow = "";
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
      if (!drawer) return;
      if (drawer.open) drawer.close();
      drawer.remove();
      drawer = null;
      frame = null;
      clearDrawerOpenState();
      button.hidden = false;
      document.body.style.overflow = previousOverflow;
      if (opener && opener.isConnected) opener.focus();
      opener = null;
    }
    function open() {
      if (drawer) { sendContext(); return; }
      try {
        opener = document.activeElement;
        previousOverflow = document.body.style.overflow;
        drawer = document.createElement("dialog");
        drawer.className = "if-ai-drawer-wrap";
        drawer.setAttribute("aria-label", "学习助手");
        drawer.style.cssText = "position:fixed;inset:0;margin:0;padding:0;border:0;width:100%;height:100%;max-width:none;max-height:none;background:transparent";
        drawer.innerHTML = '<button class="if-ai-drawer-backdrop" type="button" tabindex="-1" aria-hidden="true"></button>' +
          '<aside class="if-ai-drawer"><header class="if-ai-drawer-head"><div class="if-ai-origin"><small>当前学习页</small><span></span></div>' +
          '<div class="if-ai-drawer-actions"><button type="button" class="if-ai-expand" aria-pressed="false">展开</button>' +
          '<a href="/pages/ai-assistant.html" data-navigation-policy="new-tab" target="_blank" rel="noopener noreferrer" aria-label="在新标签页打开学习助手">独立打开 ↗</a>' +
          '<button type="button" class="if-ai-close" aria-label="关闭学习助手">×</button></div></header>' +
          '<iframe title="AI 助手对话" src="/pages/ai-assistant.html?embedded=1"></iframe></aside>';
        document.body.appendChild(drawer);
        document.documentElement.classList.add("if-ai-drawer-open");
        button.hidden = true;
        frame = drawer.querySelector("iframe");
        drawer.querySelector(".if-ai-drawer-backdrop").addEventListener("click", close);
        drawer.querySelector(".if-ai-origin span").textContent = document.title.split(" · ")[0] || "当前页面";
        var expandButton = drawer.querySelector(".if-ai-expand");
        expandButton.addEventListener("click", function () {
          var wide = drawer.classList.toggle("if-ai-wide");
          expandButton.setAttribute("aria-pressed", String(wide));
          expandButton.textContent = wide ? "收窄" : "展开";
        });
        var closeButton = drawer.querySelector(".if-ai-close");
        closeButton.addEventListener("click", close);
        drawer.addEventListener("cancel", function (event) { event.preventDefault(); close(); });
        frame.addEventListener("load", function () {
          sendContext();
          // Keyboard events in the same-origin conversation do not bubble into the outer document.
          var inner = frame && frame.contentDocument;
          if (inner) inner.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing && !inner.querySelector("dialog[open]")) {
              event.preventDefault();
              close();
            }
          });
        });
        drawer.showModal();
        closeButton.focus();
        document.body.style.overflow = "hidden";
        sendContext();
      } catch (error) {
        close();
        throw error;
      }
    }
    openDrawer = open;
    button.addEventListener("click", requestOpen);
    global.addEventListener("message", function (event) {
      if (!frame || event.source !== frame.contentWindow || event.origin !== global.location.origin || !event.data) return;
      if (event.data.type === "interviewforge:request-page-context") sendContext(event.data.request_id);
    });
    var update = function () { if (drawer) scheduleContext(); };
    global.addEventListener("scroll", update, { passive: true });
    document.addEventListener("selectionchange", update);
    global.addEventListener("pagehide", clearDrawerOpenState, { once: true });
    if (pendingOpen) { pendingOpen = false; requestOpen(); }
  }

  boot();
}(window));
