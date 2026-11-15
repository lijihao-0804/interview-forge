/* Optional Cloudflare Turnstile mount for the anonymous email forms.
 * The backend only enables it when IF_TURNSTILE_SITE_KEY/SECRET are set; the
 * form asks /api/register/config first and renders nothing otherwise. */
(function (root) {
  "use strict";

  var SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  var widgetId = null;

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
    widgetId = null;
    var api = {
      enabled: true,
      token: function () { return ""; },
      reset: function () { if (widgetId !== null && root.turnstile) root.turnstile.reset(widgetId); }
    };
    if (!config || config.provider !== "turnstile" || !config.site_key) {
      container.hidden = true;
      return { enabled: false, token: function () { return ""; }, reset: function () {} };
    }
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

  root.InterviewForgeCaptcha = Object.freeze({ mount: mount });
}(typeof window !== "undefined" ? window : globalThis));