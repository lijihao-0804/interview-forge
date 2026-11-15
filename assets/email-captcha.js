/* Optional Cloudflare Turnstile mount for the anonymous email forms.
 * The backend only enables it when IF_TURNSTILE_SITE_KEY/SECRET are set; the
 * only an explicitly disabled config permits sending without a widget. */
(function (root) {
  "use strict";

  var SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

  function loadScript() {
    return new Promise(function (resolve, reject) {
      if (root.turnstile && root.turnstile.render) { resolve(root.turnstile); return; }
      var existing = document.querySelector("script[data-forge-captcha]");
      if (existing) {
        existing.addEventListener("load", function () { resolve(root.turnstile); });
        existing.addEventListener("error", reject);
        return;
      }
      var script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.setAttribute("data-forge-captcha", "1");
      script.onload = function () { resolve(root.turnstile); };
      script.onerror = function () { reject(new Error("captcha_script_failed")); };
      document.head.appendChild(script);
    });
  }

  /** Mount Turnstile into `container`; returns a token getter ("" when disabled). */
  function mount(container, config) {
    container.hidden = false;
    var widgetId = null;
    var api = {
      enabled: true,
      blocked: false,
      token: function () { return ""; },
      reset: function () { if (widgetId !== null && root.turnstile) root.turnstile.reset(widgetId); }
    };
    if (config === null) {
      container.hidden = true;
      return { enabled: false, blocked: false, token: function () { return ""; }, reset: function () {} };
    }
    if (!config || config.provider !== "turnstile" || !config.site_key) return unavailable(container);
    loadScript().then(function (turnstile) {
      if (!turnstile || typeof turnstile.render !== "function") throw new Error("captcha_unavailable");
      widgetId = turnstile.render(container, {
        sitekey: String(config.site_key),
        theme: "auto",
        callback: function (token) { api.token = function () { return String(token || ""); }; },
        "expired-callback": function () { api.token = function () { return ""; }; }
      });
    }).catch(function () {
      container.textContent = "人机验证加载失败，请刷新页面后重试。";
      container.hidden = false;
    });
    return api;
  }

  function unavailable(container) {
    container.hidden = false;
    container.textContent = "人机验证暂不可用，验证码发送已暂停。请稍后刷新重试；已有账号仍可登录。";
    container.setAttribute("role", "status");
    return { enabled: true, blocked: true, token: function () { return ""; }, reset: function () {} };
  }

  function load(container) {
    container.hidden = false;
    container.textContent = "正在确认验证码发送服务…";
    return root.fetch("/api/register/config", { cache: "no-store", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("captcha_config_unavailable");
        return response.json();
      }).then(function (payload) {
        if (!payload || !Object.prototype.hasOwnProperty.call(payload, "captcha")) {
          throw new Error("captcha_config_invalid");
        }
        container.textContent = "";
        return mount(container, payload.captcha);
      }).catch(function () { return unavailable(container); });
  }

  root.InterviewForgeCaptcha = Object.freeze({ mount: mount, load: load });
}(typeof window !== "undefined" ? window : globalThis));