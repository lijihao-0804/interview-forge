/* InterviewForge 反馈小部件（由服务端在 HTML 响应中注入）。
 * 游客可继续浏览内容；提交反馈属于写操作，必须先确认已登录。
 * 认证状态确认完成前不会打开表单或发送请求；会话失效时只降级为游客并给出登录入口。 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root && root.document) api.install();
}(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  var installed = false;
  var draftKey = "interviewforge:feedback-draft";
  var draft = { content: "", contact: "" };

  function loadDraft() {
    try {
      var stored = root.sessionStorage && JSON.parse(root.sessionStorage.getItem(draftKey) || "{}");
      if (stored && typeof stored === "object") {
        draft = {
          content: String(stored.content || "").slice(0, 2000),
          contact: String(stored.contact || "").slice(0, 120)
        };
      }
    } catch (_) { }
  }

  function rememberDraft() {
    try {
      if (!root.sessionStorage) return;
      if (!draft.content && !draft.contact) root.sessionStorage.removeItem(draftKey);
      else root.sessionStorage.setItem(draftKey, JSON.stringify(draft));
    } catch (_) { }
  }

  function clearDraft() {
    draft = { content: "", contact: "" };
    try { if (root.sessionStorage) root.sessionStorage.removeItem(draftKey); } catch (_) { }
  }

  function authError(feature) {
    var error = new Error("登录后才能" + String(feature || "提交反馈"));
    error.code = "AUTH_REQUIRED";
    error.category = "unauthorized";
    return error;
  }

  function isAuthRequired(error) {
    return Boolean(error && (error.code === "AUTH_REQUIRED" || error.category === "unauthorized"));
  }

  function authProviders() {
    return [root.InterviewForgeAuth, root.InterviewForgeGuestAuth].filter(function (provider) {
      return provider && typeof provider === "object";
    });
  }

  function readAuthState() {
    var providers = authProviders();
    for (var index = 0; index < providers.length; index += 1) {
      var provider = providers[index];
      if (typeof provider.getState !== "function") continue;
      var current = provider.getState();
      if (!current || !current.status) continue;
      if (current.status === "authenticated" && current.user) {
        return { status: "authenticated", user: current.user, reason: current.reason || "authenticated" };
      }
      if (current.status === "guest" || current.status === "error") {
        return { status: current.status, user: null, reason: current.reason || "" };
      }
      if (current.status === "checking") return { status: "checking", user: null, reason: current.reason || "" };
    }
    return { status: "error", user: null, reason: "session_check_unavailable" };
  }

  function waitForAuth() {
    var providers = authProviders();
    for (var index = 0; index < providers.length; index += 1) {
      var provider = providers[index];
      if (!provider.ready || typeof provider.ready.then !== "function") continue;
      return Promise.resolve(provider.ready).then(readAuthState, function () {
        return { status: "error", user: null, reason: "session_check_failed" };
      });
    }
    return Promise.resolve(readAuthState());
  }

  function currentPage() {
    return (root.location && root.location.pathname || "/index.html") +
      (root.location && root.location.search || "") +
      (root.location && root.location.hash || "");
  }

  function authHref(path) {
    var next = currentPage();
    try {
      var candidate = new root.URL(next, root.location && root.location.origin || undefined);
      if (candidate.origin !== (root.location && root.location.origin)) next = "/index.html";
      if (candidate.pathname === "/pages/login.html" || candidate.pathname === "/pages/register.html") {
        next = "/index.html";
      }
    } catch (_) {
      next = "/index.html";
    }
    return path + "?next=" + encodeURIComponent(next);
  }

  function showFallbackPrompt(feature) {
    if (!root.document) return;
    var previous = root.document.getElementById("forge-feedback-auth-modal");
    if (previous) previous.remove();
    var modal = root.document.createElement("div");
    modal.id = "forge-feedback-auth-modal";
    modal.className = "forge-feedback-auth-mask";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "forge-feedback-auth-title");
    modal.innerHTML = '<section class="forge-feedback-auth-dialog" tabindex="-1">' +
      '<h2 id="forge-feedback-auth-title">登录后即可提交反馈</h2>' +
      '<p class="forge-feedback-auth-copy"></p>' +
      '<div class="forge-feedback-auth-actions">' +
      '<button type="button" data-close>暂不登录</button>' +
      '<a data-register>注册</a><a class="primary" data-login>登录</a></div></section>';
    modal.querySelector(".forge-feedback-auth-copy").textContent =
      "游客可阅读和搜索。登录后才能" + String(feature || "提交反馈") + "。";
    modal.querySelector("[data-login]").href = authHref("/pages/login.html");
    modal.querySelector("[data-register]").href = authHref("/pages/register.html");
    function close() {
      modal.remove();
      root.document.removeEventListener("keydown", onKeydown);
    }
    function onKeydown(event) { if (event.key === "Escape") close(); }
    modal.querySelector("[data-close]").onclick = close;
    modal.addEventListener("click", function (event) { if (event.target === modal) close(); });
    root.document.addEventListener("keydown", onKeydown);
    root.document.body.appendChild(modal);
    modal.querySelector(".forge-feedback-auth-dialog").focus();
  }

  function promptLogin(feature) {
    var providers = authProviders();
    for (var index = 0; index < providers.length; index += 1) {
      if (typeof providers[index].promptLogin === "function") {
        providers[index].promptLogin(String(feature || "提交反馈"));
        return;
      }
    }
    showFallbackPrompt(feature);
  }

  function markGuest(reason) {
    var providers = authProviders();
    for (var index = 0; index < providers.length; index += 1) {
      if (typeof providers[index].markGuest === "function") {
        providers[index].markGuest(reason || "unauthorized");
        return;
      }
    }
  }

  function requireAuthenticated(feature) {
    var action = String(feature || "提交反馈");
    return waitForAuth().then(function () {
      var current = readAuthState();
      if (current.status === "authenticated" && current.user) return current.user;
      promptLogin(action);
      throw authError(action);
    });
  }

  function readResponse(response) {
    var parsing = Promise.resolve().then(function () {
      return response && typeof response.json === "function" ? response.json() : {};
    }).catch(function () { return {}; });
    return parsing.then(function (data) {
      return { ok: Boolean(response && response.ok), status: Number(response && response.status || 0), data: data || {} };
    });
  }

  function submitFeedback(payload, feature) {
    var action = String(feature || "提交反馈");
    return requireAuthenticated(action).then(function () {
      if (typeof root.fetch !== "function") {
        var unavailable = new Error("网络请求不可用");
        unavailable.code = "FEEDBACK_NETWORK";
        unavailable.category = "network";
        throw unavailable;
      }
      return root.fetch("/api/feedback", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      });
    }).then(function (response) {
      if (response && response.status === 401) {
        markGuest("unauthorized");
        promptLogin(action);
        throw authError(action);
      }
      return readResponse(response);
    }, function (error) {
      if (isAuthRequired(error)) throw error;
      var network = new Error("网络错误，请稍后再试");
      network.code = "FEEDBACK_NETWORK";
      network.category = "network";
      network.cause = error;
      throw network;
    });
  }

  function install() {
    if (installed || !root.document) return false;
    installed = true;
    var document = root.document;
    if (document.getElementById("forge-fb-btn")) return true;

    var style = document.createElement("style");
    style.textContent =
      ":root{--forge-auth-reserve:76px}" +
      "#forge-fb-btn{position:fixed;right:16px;bottom:calc(var(--forge-auth-reserve,76px) + env(safe-area-inset-bottom));z-index:9996;width:38px;height:38px;border-radius:50%;" +
      "border:1px solid #dfe4ee;background:rgba(255,255,255,.94);box-shadow:0 6px 18px rgba(33,45,73,.18);" +
      "font-size:17px;line-height:36px;text-align:center;cursor:pointer;user-select:none;transition:transform .15s,bottom .15s,opacity .15s}" +
      "#forge-fb-btn:hover{transform:scale(1.1);background:#eeedff}#forge-fb-btn:disabled{opacity:.58;cursor:wait;transform:none}" +
      "#forge-fb-panel{position:fixed;right:16px;bottom:calc(var(--forge-auth-reserve,76px) + 52px + env(safe-area-inset-bottom));z-index:10000;width:min(320px,calc(100vw - 32px));" +
      "background:#fff;border:1px solid #dfe4ee;border-radius:14px;padding:16px;box-shadow:0 16px 44px rgba(33,45,73,.22);" +
      "font:14px/1.6 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#182235}" +
      "#forge-fb-panel h3{margin:0 0 4px;font-size:15px}" +
      "#forge-fb-panel .fap-page{font-size:11px;color:#66748a;margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      "#forge-fb-panel textarea{width:100%;height:96px;resize:vertical;padding:8px 10px;border:1px solid #dfe4ee;" +
      "border-radius:8px;font:inherit;background:#fbfcff;box-sizing:border-box}" +
      "#forge-fb-panel input{width:100%;margin-top:8px;padding:7px 10px;border:1px solid #dfe4ee;border-radius:8px;" +
      "font:inherit;background:#fbfcff;box-sizing:border-box}" +
      "#forge-fb-panel .fap-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}" +
      "#forge-fb-panel button{border:0;border-radius:8px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}" +
      "#forge-fb-panel .fap-send{background:#5654d4;color:#fff}#forge-fb-panel .fap-send:hover{background:#4543bd}" +
      "#forge-fb-panel .fap-close{background:transparent;color:#66748a}" +
      "#forge-fb-panel .fap-hint{font-size:12px;color:#66748a;margin-top:6px;min-height:16px}" +
      "#forge-fb-panel .fap-hint.err{color:#b3372f}#forge-fb-panel .fap-hint.ok{color:#157a52}" +
      ".forge-feedback-auth-mask{position:fixed;inset:0;z-index:10020;display:grid;place-items:center;padding:20px;background:rgba(12,18,30,.52);backdrop-filter:blur(3px)}" +
      ".forge-feedback-auth-dialog{width:min(100%,430px);padding:23px;border:1px solid var(--line,#dfe4ee);border-radius:16px;color:var(--text,#182235);background:var(--panel,#fff);box-shadow:0 24px 70px rgba(10,14,22,.28);font:14px/1.65 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif}" +
      ".forge-feedback-auth-dialog h2{margin:0;font-size:20px}.forge-feedback-auth-dialog p{margin:10px 0 0;color:var(--muted,#66748a)}" +
      ".forge-feedback-auth-actions{display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap;margin-top:20px}" +
      ".forge-feedback-auth-actions a,.forge-feedback-auth-actions button{padding:8px 13px;border:1px solid var(--line,#dfe4ee);border-radius:9px;color:var(--text,#182235);background:var(--soft,#f7f8fc);font:inherit;font-weight:650;text-decoration:none;cursor:pointer}" +
      ".forge-feedback-auth-actions .primary{border-color:var(--brand,#5654d4);color:#fff;background:var(--brand,#5654d4)}" +
      "@media (max-width:640px){#forge-fb-btn{right:10px}#forge-fb-panel{right:10px}}";
    document.head.appendChild(style);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", "提交反馈（需要登录）");
    btn.id = "forge-fb-btn";
    btn.title = "反馈问题（需要登录）";
    btn.textContent = "🐞";

    var panel = null;
    function closePanel() {
      if (!panel) return;
      draft.content = panel.querySelector("#fb-content").value;
      draft.contact = panel.querySelector("#fb-contact").value;
      rememberDraft();
      panel.remove();
      panel = null;
    }

    function setHint(message, kind) {
      if (!panel) return;
      var hint = panel.querySelector("#fb-hint");
      hint.textContent = message;
      hint.className = "fap-hint" + (kind ? " " + kind : "");
    }

    function setSending(sending) {
      if (!panel) return;
      var send = panel.querySelector(".fap-send");
      send.disabled = Boolean(sending);
      send.textContent = sending ? "提交中…" : "提交反馈";
    }

    function openPanel() {
      loadDraft();
      panel = document.createElement("div");
      panel.id = "forge-fb-panel";
      panel.innerHTML =
        '<h3>反馈问题 🐞</h3>' +
        '<div class="fap-page"></div>' +
        '<textarea id="fb-content" placeholder="遇到什么问题？（必填，1~2000 字）&#10;例如：某某页面打不开 / 复习日期不对 / 显示错乱…"></textarea>' +
        '<input id="fb-contact" placeholder="联系方式（选填：QQ / 微信 / 邮箱）" autocomplete="off">' +
        '<div class="fap-actions"><button class="fap-close" type="button">取消</button>' +
        '<button class="fap-send" type="button">提交反馈</button></div>' +
        '<div class="fap-hint" id="fb-hint"></div>';
      document.body.appendChild(panel);
      var page = panel.querySelector(".fap-page");
      page.title = root.location.href;
      page.textContent = "页面：" + root.location.pathname;
      panel.querySelector("#fb-content").value = draft.content;
      panel.querySelector("#fb-contact").value = draft.contact;
      panel.querySelector(".fap-close").onclick = closePanel;
      panel.querySelector("#fb-content").focus();

      panel.querySelector(".fap-send").onclick = function () {
        var content = panel.querySelector("#fb-content").value.trim();
        if (!content) {
          setHint("请先填写问题描述", "err");
          return;
        }
        draft.content = content;
        draft.contact = panel.querySelector("#fb-contact").value.trim();
        rememberDraft();
        setSending(true);
        setHint("提交中…");
        submitFeedback({
          content: content,
          contact: draft.contact,
          page: root.location.pathname + root.location.search
        }, "提交反馈").then(function (result) {
          if (result.ok) {
            clearDraft();
            setHint("已提交，感谢反馈！我们会尽快处理。", "ok");
            setSending(false);
            setTimeout(closePanel, 1500);
            return;
          }
          if (result.status === 401) {
            setHint("登录后提交反馈；已保留填写内容，登录返回后可重新提交。", "err");
            return;
          }
          var message = String(result.data && result.data.error || "提交失败，请稍后再试")
            .replace(/[\u0000-\u001f\u007f]+/g, " ").trim().slice(0, 240);
          setHint(message || "提交失败，请稍后再试", "err");
          setSending(false);
        }).catch(function (error) {
          if (isAuthRequired(error)) {
            setHint("登录后提交反馈；已保留填写内容，登录返回后可重新提交。", "err");
            return;
          }
          setHint("网络错误，请稍后再试", "err");
          setSending(false);
        });
      };
    }

    btn.onclick = function () {
      if (panel) { closePanel(); return; }
      if (btn.disabled) return;
      btn.disabled = true;
      requireAuthenticated("提交反馈").then(function () {
        btn.disabled = false;
        openPanel();
      }, function () {
        btn.disabled = false;
      });
    };

    document.body.appendChild(btn);
    return true;
  }

  return Object.freeze({
    install: install,
    requireAuthenticated: requireAuthenticated,
    submitFeedback: submitFeedback,
    isAuthRequired: isAuthRequired
  });
}));
