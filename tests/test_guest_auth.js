/* Guest auth gate regression test; run with: node tests/test_guest_auth.js */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "assets", "guest-auth.js"), "utf8");
const listeners = new Map();
const document = {
  addEventListener(name, callback) { listeners.set(name, callback); },
  removeEventListener(name) { listeners.delete(name); },
  getElementById() { return null; },
  createElement() { throw new Error("guest request should not open the fallback modal"); },
  head: { appendChild() {} },
  body: { appendChild() {} }
};

let authSettle;
let authState = { status: "checking", user: null, reason: "starting" };
let prompted = "";
const auth = {
  ready: new Promise((resolve) => { authSettle = resolve; }),
  getState() { return authState; },
  promptLogin(feature) { prompted = String(feature || ""); },
  markGuest(reason) { authState = { status: "guest", user: null, reason }; }
};
const calls = [];
const responses = [];
const window = {
  InterviewForgeAuth: auth,
  location: {
    origin: "https://example.test",
    pathname: "/books/hot100/example.html",
    search: "?from=guest",
    hash: "#answer"
  },
  setTimeout,
  clearTimeout,
  fetch(input, options) {
    calls.push({ input, options });
    return Promise.resolve(responses.shift());
  }
};
const sandbox = { window, document, URL, Promise, Error, String, Number, Object, setTimeout, clearTimeout };
vm.runInNewContext(source, sandbox, { filename: "assets/guest-auth.js" });
const guestAuth = window.InterviewForgeGuestAuth;

(async () => {
  assert(guestAuth, "guest auth API should be installed");
  assert.strictEqual(guestAuth.getState().status, "checking");

  let readySettled = false;
  const ready = guestAuth.ready(5000).then((session) => {
    readySettled = true;
    return session;
  });
  await Promise.resolve();
  assert.strictEqual(readySettled, false, "checking state must not be treated as ready");

  authState = { status: "guest", user: null, reason: "anonymous" };
  authSettle(authState);
  assert.strictEqual((await ready).status, "guest");

  await assert.rejects(
    guestAuth.request("/api/private", {}, "使用 AI"),
    (error) => error.code === "AUTH_REQUIRED"
  );
  assert.match(prompted, /使用 AI/);
  assert.strictEqual(calls.length, 0, "guest private request must not reach fetch");

  authState = { status: "authenticated", user: { username: "reader" }, reason: "authenticated" };
  responses.push({ status: 200, ok: true });
  const ok = await guestAuth.request("/api/private", { method: "POST" }, "保存进度");
  assert.strictEqual(ok.status, 200);
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].options.credentials, "same-origin");
  assert.strictEqual(calls[0].options.method, "POST");

  responses.push({ status: 401, ok: false });
  await assert.rejects(
    guestAuth.request("/api/private", {}, "提交练习"),
    (error) => error.code === "AUTH_REQUIRED"
  );
  assert.strictEqual(guestAuth.getState().status, "guest");

  console.log("guest-auth: checking wait, guest blocking, authenticated pass and 401 demotion PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
