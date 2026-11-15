/* Registration error protocol regression test; run with: node tests/test_register_flow.js */
const assert = require("assert");
const flow = require("../assets/register-flow.js");

function response(status, headers) {
  const values = headers || {};
  return {
    status,
    headers: {
      get(name) {
        const key = Object.keys(values).find((item) => item.toLowerCase() === String(name).toLowerCase());
        return key ? String(values[key]) : null;
      }
    }
  };
}

assert.match(
  flow.sendCodeError(503, {
    error: "注册邮件服务尚未配置，请联系站内管理员完成 SMTP 设置",
    error_category: "email_not_configured"
  }, 0),
  /邮件服务.*未配置.*管理员/
);
assert.match(
  flow.registerError(409, {
    error: "该邮箱或用户名已被占用",
    error_category: "already_registered"
  }),
  /已被占用/
);
assert.match(flow.sendCodeError(502, { error_category: "email_delivery_failed" }, 0), /发送失败/);

const retryPayload = { error: "操作过于频繁", error_category: "rate_limited", retry_after: 120 };
assert.strictEqual(flow.cooldownFrom(response(429, {}), retryPayload), 120);
assert.match(flow.sendCodeError(429, retryPayload, 120), /120 秒/);
assert.strictEqual(flow.cooldownFrom(response(429, { "Retry-After": "75" }), {}), 75);
assert.strictEqual(flow.cooldownFrom(response(200, { "Retry-After": "75" }), { resend_after: 60 }), 60);

const expired = "验证码已过期，请重新获取";
assert.strictEqual(flow.registerError(400, { error: expired, error_category: "registration" }), expired);
const attempts = "验证码错误，今日还可尝试 2 次";
assert.strictEqual(flow.registerError(400, { error: attempts, error_category: "registration" }), attempts);
assert.match(
  flow.registerError(400, { error: "验证码无效", error_category: "verification_code_attempts_exceeded" }),
  /验证码无效|尝试/
);

const markup = "<img src=x onerror=alert(1)>";
assert.strictEqual(flow.registerError(400, { error: markup, error_category: "registration" }), "注册失败，请检查输入后重试。");
assert.strictEqual(flow.registerError(400, { error: "第一行\n第二行", error_category: "registration" }), "注册失败，请检查输入后重试。");
assert.strictEqual(flow.registerError(400, { error: "x".repeat(181), error_category: "registration" }), "注册失败，请检查输入后重试。");

console.log("register-flow: category, controlled 4xx, retry fallback and safe fallback PASS");
