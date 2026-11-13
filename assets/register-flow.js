(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.InterviewForgeRegister = api;
}(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function codeOf(payload) {
    if (!payload || typeof payload !== "object") return "";
    return String(payload.error_category || payload.code || payload.error_code || "").trim().toLowerCase();
  }

  function controlledMessage(status, payload, fallback) {
    var numericStatus = Number(status);
    if (!(numericStatus >= 400 && numericStatus < 500) || !payload || typeof payload.error !== "string") return fallback || "";
    var category = codeOf(payload);
    var allowedCategories = {
      registration: true,
      already_registered: true,
      rate_limited: true,
      email_not_configured: true,
      email_delivery_failed: true,
      verification_code_expired: true,
      verification_code_attempts_exceeded: true
    };
    var message = payload.error.trim();
    if (!allowedCategories[category] || !message || message.length > 180 || /[\r\n<>]/.test(message)) return fallback || "";
    return message;
  }

  function parseRetryAfter(value, fallback, now) {
    var current = Number(now || Date.now());
    if (value == null || value === "") return Math.max(0, Math.ceil(Number(fallback) || 0));
    var seconds = Number(value);
    if (Number.isFinite(seconds)) return Math.max(0, Math.ceil(seconds));
    var at = Date.parse(String(value));
    if (Number.isFinite(at)) return Math.max(0, Math.ceil((at - current) / 1000));
    return Math.max(0, Math.ceil(Number(fallback) || 0));
  }

  function cooldownFrom(response, payload, now) {
    var bodySeconds = payload && Number(payload.resend_after != null ? payload.resend_after : payload.retry_after);
    if (Number.isFinite(bodySeconds) && bodySeconds >= 0) return Math.ceil(bodySeconds);
    var retryAfter = response && response.headers && typeof response.headers.get === "function"
      ? response.headers.get("Retry-After")
      : "";
    return parseRetryAfter(retryAfter, 0, now);
  }

  function sendCodeError(status, payload, cooldown) {
    var code = codeOf(payload);
    if (Number(status) === 429 || code === "rate_limited" || /rate|too_many|cooldown|resend/.test(code)) {
      return cooldown > 0 ? "发送过于频繁，请在 " + cooldown + " 秒后重试。" : "发送过于频繁，请稍后再试。";
    }
    if (code === "email_not_configured" || /smtp.*(config|unavailable)|mail.*(config|unavailable)|no_smtp/.test(code)) {
      return "邮件服务暂未配置，当前无法发送验证码，请联系管理员。";
    }
    if (code === "email_delivery_failed") return "注册邮件发送失败，请稍后重试；如持续失败，请联系管理员。";
    if (/email.*invalid|invalid.*email/.test(code)) return "请输入有效的邮箱地址。";
    var controlled = controlledMessage(status, payload, "");
    if (controlled) return controlled;
    if (Number(status) >= 500 || /send|mail|smtp/.test(code)) return "验证码发送失败，请稍后重试。";
    return "验证码发送失败，请检查邮箱后重试。";
  }

  function registerError(status, payload) {
    var code = codeOf(payload);
    if (code === "email_not_configured") return "注册邮件服务尚未配置，请联系站内管理员完成 SMTP 设置。";
    if (code === "email_delivery_failed") return "注册邮件发送失败，请稍后重试；如持续失败，请联系管理员。";
    if (code === "already_registered") return controlledMessage(status, payload, "该邮箱或用户名已被占用，请更换后重试或直接登录。");
    if (Number(status) === 429 || code === "rate_limited" || /rate|too_many/.test(code)) return "操作过于频繁，请稍后再试。";
    if (/expired/.test(code)) return "验证码已过期，请重新获取。";
    if (/code.*(invalid|wrong)|invalid.*code|verification.*fail/.test(code)) return "验证码无效，请检查后重试。";
    if (/email.*(taken|exists|used|duplicate)/.test(code)) return "该邮箱暂不可用于注册，请更换邮箱或直接登录。";
    if (/username.*(taken|exists|used|duplicate)/.test(code)) return "该用户名暂不可用，请更换后重试。";
    if (/password|username.*invalid|email.*invalid/.test(code)) return "请检查邮箱、用户名和密码格式后重试。";
    if (/smtp|mail.*config/.test(code)) return "邮件服务暂不可用，暂时无法完成注册，请联系管理员。";
    var controlled = controlledMessage(status, payload, "");
    if (controlled) return controlled;
    return "注册失败，请检查输入后重试。";
  }

  function isValidEmail(value) {
    var email = String(value || "").trim();
    return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  return Object.freeze({
    isEmail: isValidEmail,
    parseRetryAfter: parseRetryAfter,
    cooldownFrom: cooldownFrom,
    sendCodeError: sendCodeError,
    registerError: registerError
  });
}));
