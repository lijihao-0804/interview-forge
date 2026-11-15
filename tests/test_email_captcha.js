"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("assets/email-captcha.js", "utf8");

async function scenario(response) {
  const scripts = [];
  const options = [];
  const container = { hidden: true, textContent: "", setAttribute() {} };
  const window = {
    fetch: async () => { if (response instanceof Error) throw response; return response; },
    turnstile: { render(_target, opts) { options.push(opts); return 1; }, reset() {} },
  };
  const document = { querySelector() { return null; }, createElement() { return { setAttribute() {} }; }, head: { appendChild(x) { scripts.push(x); } } };
  vm.runInNewContext(source, { window, document, Promise, Object, String, Error });
  const api = await window.InterviewForgeCaptcha.load(container);
  await Promise.resolve();
  return { api, container, options, scripts };
}

(async () => {
  for (const response of [new Error("offline"), { ok: false }, { ok: true, json: async () => ({}) },
    { ok: true, json: async () => ({ captcha: { provider: "turnstile" } }) }]) {
    const state = await scenario(response);
    assert.equal(state.api.blocked, true);
    assert.equal(state.container.hidden, false);
    assert.match(state.container.textContent, /验证码发送已暂停/);
    assert.equal(state.options.length, 0);
  }
  const disabled = await scenario({ ok: true, json: async () => ({ captcha: null }) });
  assert.equal(disabled.api.blocked, false);
  assert.equal(disabled.api.enabled, false);
  assert.equal(disabled.container.hidden, true);
  const enabled = await scenario({ ok: true, json: async () => ({ captcha: { provider: "turnstile", site_key: "test-site" } }) });
  assert.equal(enabled.api.enabled, true);
  assert.equal(enabled.api.token(), "");
  enabled.options[0].callback("synthetic-token");
  assert.equal(enabled.api.token(), "synthetic-token");
  enabled.options[0]["expired-callback"]();
  assert.equal(enabled.api.token(), "");
  for (const name of ["register", "forgot-password"]) {
    const page = fs.readFileSync("pages/" + name + ".html", "utf8");
    assert.match(page, /sendButton\.disabled = captcha\.blocked/);
    assert.match(page, /if \(captcha\.blocked \|\| sending/);
    assert.match(page, /InterviewForgeCaptcha\.load\(captchaBox\)/);
  }
  console.log("email-captcha: partial/unavailable config blocks sending; explicit disabled and valid widget pass");
})().catch(error => { console.error(error); process.exitCode = 1; });
