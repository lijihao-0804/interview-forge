/* Shared guest-mode gate. It waits for the deferred auth widget to settle before
 * any page is allowed to call protected APIs. It never grants access itself. */
(function (root, factory) {
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.InterviewForgeGuestAuth = api;
}(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  var state = { status: "checking", user: null, reason: "" };
  var readyPromise = null;

  function snapshot() {
    var auth = root.InterviewForgeAuth;
    if (auth && typeof auth.getState === "function") {
      var current = auth.getState();
      if (current && current.status) state = { status: current.status, user: current.user || null, reason: current.reason || "" };
    }
    return { status: state.status, user: state.user, reason: state.reason };
  }

  function currentPage() {
    return (root.location && root.location.pathname || "/index.html") +
      (root.location && root.location.search || "") +
      (root.location && root.location.hash || "");
  }

  function safeNext(value) {
    var raw = String(value || "").trim();
    if (!raw) return "/index.html";
    try {
      var origin = root.location && root.location.origin || "http://localhost";
      var target = new URL(raw, origin);
      if (target.origin !== origin || target.pathname.charAt(0) !== "/") return "/index.html";
      return target.pathname + target.search + target.hash;
    } catch (_) {
      return "/index.html";
    }
  }

  function authHref(path, next) {
    return path + (path.indexOf("?") >= 0 ? "&" : "?") + "next=" + encodeURIComponent(safeNext(next || currentPage()));
  }

  function applySession(session) {
    if (session && session.status === "authenticated" && session.user) {
      state = { status: "authenticated", user: session.user, reason: session.reason || "authenticated" };
    } else if (session && session.status === "guest") {
      state = { status: "guest", user: null, reason: session.reason || "anonymous" };
    } else {
      state = { status: "error", user: null, reason: session && session.reason || "session_check_failed" };
    }
    return snapshot();
  }

  function fallbackCheck(resolve) {
    if (root.InterviewForgeAuth && root.InterviewForgeAuth.ready) return;
    if (typeof root.fetch !== "function") {
      resolve(applySession({ status: "error", reason: "session_check_unavailable" }));
      return;
    }
    var controller = typeof root.AbortController === "function" ? new root.AbortController() : null;
    var timer = controller ? root.setTimeout(function () { controller.abort(); }, 10000) : null;
    root.fetch("/api/me", {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller ? controller.signal : undefined
    }).then(function (response) {
      if (response.status === 401) return { status: "guest", reason: "anonymous" };
      if (!response.ok) throw new Error("session_http_" + response.status);
      return response.json().then(function (user) {
        return { status: "authenticated", user: user, reason: "authenticated" };
      });
    }).then(function (session) {
      resolve(applySession(session));
    }).catch(function (error) {
      resolve(applySession({
        status: "error",
        reason: error && error.name === "AbortError" ? "timeout" : "session_check_failed"
      }));
    }).finally(function () {
      if (timer) root.clearTimeout(timer);
    });
  }

  function ready(timeoutMs) {
    if (readyPromise) return readyPromise;
    readyPromise = new Promise(function (resolve) {
      var auth = root.InterviewForgeAuth;
      var settled = false;
      var fallbackTimer = null;
      var hardTimer = null;

      function finish(session) {
        if (settled) return;
        settled = true;
        if (fallbackTimer) root.clearTimeout(fallbackTimer);
        if (hardTimer) root.clearTimeout(hardTimer);
        document.removeEventListener("interviewforge:auth-ready", onReady);
        resolve(applySession(session));
      }

      function onReady(event) {
        finish(event && event.detail || auth && auth.getState && auth.getState());
      }

      if (auth && auth.ready && typeof auth.ready.then === "function") {
        auth.ready.then(finish);
        return;
      }

      document.addEventListener("interviewforge:auth-ready", onReady, { once: true });
      // Production pages receive the auth widget from the server as a deferred
      // script. This fallback keeps static previews and older deployments usable.
      fallbackTimer = root.setTimeout(function () { fallbackCheck(finish); }, 1800);
      hardTimer = root.setTimeout(function () {
        finish({ status: "error", reason: "session_check_timeout" });
      }, Math.max(3000, Number(timeoutMs) || 10000));
    });
    return readyPromise;
  }

  function markGuest(reason) {
    var auth = root.InterviewForgeAuth;
    if (auth && typeof auth.markGuest === "function") auth.markGuest(reason || "unauthorized");
    return applySession({ status: "guest", reason: reason || "unauthorized" });
  }

  function ensureFallbackModal(feature) {
    var previous = document.getElementById("forge-guest-auth-modal");
    if (previous) previous.remove();
    var style = document.getElementById("forge-guest-auth-style");
    if (!style) {
      style = document.createElement("style");
      style.id = "forge-guest-auth-style";
      style.textContent = ".forge-guest-auth-mask{position:fixed;inset:0;z-index:10020;display:grid;place-items:center;padding:20px;background:rgba(12,18,30,.52);backdrop-filter:blur(3px)}.forge-guest-auth-dialog{width:min(100%,430px);padding:23px;border:1px solid var(--line,#dfe4ee);border-radius:16px;color:var(--text,#182235);background:var(--panel,#fff);box-shadow:0 24px 70px rgba(10,14,22,.28)}.forge-guest-auth-dialog h2{margin:0;font-size:20px}.forge-guest-auth-dialog p{margin:10px 0 0;color:var(--muted,#66748a)}.forge-guest-auth-actions{display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap;margin-top:20px}.forge-guest-auth-actions a,.forge-guest-auth-actions button{padding:8px 13px;border:1px solid var(--line,#dfe4ee);border-radius:9px;color:var(--text,#182235);background:var(--soft,#f7f8fc);font:inherit;font-weight:650;text-decoration:none;cursor:pointer}.forge-guest-auth-actions .primary{border-color:var(--brand,#5654d4);color:#fff;background:var(--brand,#5654d4)}";
      document.head.appendChild(style);
    }
    var modal = document.createElement("div");
    modal.id = "forge-guest-auth-modal";
    modal.className = "forge-guest-auth-mask";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "forge-guest-auth-title");
    modal.innerHTML = '<section class="forge-guest-auth-dialog" tabindex="-1"><h2 id="forge-guest-auth-title">登录后即可继续</h2><p id="forge-guest-auth-copy"></p><div class="forge-guest-auth-actions"><button type="button" data-close>暂不登录</button><a href="' + authHref("/pages/register.html") + '">注册</a><a class="primary" href="' + authHref("/pages/login.html") + '">登录</a></div></section>';
    modal.querySelector("#forge-guest-auth-copy").textContent = "游客可阅读和搜索。登录后才能" + String(feature || "使用此功能") + "，完成后会回到当前页面。";
    function close() { modal.remove(); }
    modal.querySelector("[data-close]").addEventListener("click", close);
    modal.addEventListener("click", function (event) { if (event.target === modal) close(); });
    modal.addEventListener("keydown", function (event) { if (event.key === "Escape") close(); });
    document.body.appendChild(modal);
    modal.querySelector(".forge-guest-auth-dialog").focus();
  }

  function promptLogin(feature) {
    var auth = root.InterviewForgeAuth;
    if (auth && typeof auth.promptLogin === "function") return auth.promptLogin(feature);
    ensureFallbackModal(feature);
  }

  function requireUser(feature) {
    return ready().then(function () {
      var current = snapshot();
      if (current.status === "authenticated" && current.user) return current.user;
      promptLogin(feature);
      var error = new Error("登录后才能" + String(feature || "使用此功能"));
      error.code = "AUTH_REQUIRED";
      error.category = "unauthorized";
      throw error;
    });
  }

  function request(input, options, feature) {
    return requireUser(feature).then(function () {
      var requestOptions = Object.assign({ credentials: "same-origin" }, options || {});
      return root.fetch(input, requestOptions).then(function (response) {
        if (response.status === 401) {
          markGuest("unauthorized");
          var error = new Error("登录状态已失效，请重新登录后继续");
          error.code = "AUTH_REQUIRED";
          error.category = "unauthorized";
          throw error;
        }
        return response;
      });
    });
  }

  return Object.freeze({
    ready: ready,
    getState: snapshot,
    isAuthenticated: function () { return snapshot().status === "authenticated"; },
    requireUser: requireUser,
    request: request,
    promptLogin: promptLogin,
    markGuest: markGuest,
    authHref: authHref,
    safeNext: safeNext
  });
}));
