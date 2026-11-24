/* Feedback guest-gate regression; run with: node tests/test_feedback_widget.js */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "assets", "feedback-widget.js"), "utf8");
assert.match(source, /sessionStorage\.setItem\(draftKey/, "auth-gated drafts should survive the same-tab login round trip");
assert.match(source, /clearDraft\(\);/, "a successful submission should remove the local draft");
assert.match(source, /id="fb-images"/, "feedback form should offer an image file input");
assert.match(source, /\/api\/feedback\/images/, "feedback images should upload to the dedicated endpoint");
assert.match(source, /image_ids/, "feedback submission must carry uploaded image ids");

function loadWidget() {
  let resolveReady;
  let prompted = "";
  let markedGuest = "";
  let fetchCalls = 0;
  let fetchImpl = () => Promise.reject(new Error("unexpected fetch"));
  const auth = {
    ready: new Promise((resolve) => { resolveReady = resolve; }),
    state: { status: "checking", user: null, reason: "starting" },
    getState() { return this.state; },
    promptLogin(feature) { prompted = String(feature || ""); },
    markGuest(reason) { markedGuest = String(reason || ""); this.state = { status: "guest", user: null, reason }; }
  };
  const windowObject = {
    InterviewForgeAuth: auth,
    location: {
      origin: "https://example.test",
      pathname: "/cockpit.html",
      search: "?tab=plan",
      hash: "",
      href: "https://example.test/cockpit.html?tab=plan"
    },
    URL,
    Promise,
    setTimeout,
    clearTimeout,
    fetch() {
      fetchCalls += 1;
      return fetchImpl.apply(null, arguments);
    }
  };
  const sandbox = {
    module: { exports: {} },
    window: windowObject,
    Promise,
    Error,
    String,
    Number,
    Object,
    Boolean,
    Array,
    URL,
    encodeURIComponent,
    setTimeout,
    clearTimeout
  };
  vm.runInNewContext(source, sandbox, { filename: "assets/feedback-widget.js" });
  return {
    widget: sandbox.module.exports,
    auth,
    settle() { resolveReady(auth.getState()); },
    getPrompted() { return prompted; },
    getMarkedGuest() { return markedGuest; },
    getFetchCalls() { return fetchCalls; },
    setFetch(fn) { fetchImpl = fn; }
  };
}

(async () => {
  const pending = loadWidget();
  let settled = false;
  const waiting = pending.widget.requireAuthenticated("提交反馈").then(
    () => { settled = true; },
    () => { settled = true; }
  );
  await Promise.resolve();
  assert.strictEqual(settled, false, "checking auth state must block before the form can open");
  pending.auth.state = { status: "guest", user: null, reason: "anonymous" };
  pending.settle();
  await waiting;
  await assert.rejects(
    pending.widget.requireAuthenticated("提交反馈"),
    (error) => error.code === "AUTH_REQUIRED"
  );
  assert.match(pending.getPrompted(), /提交反馈/);
  assert.strictEqual(pending.getFetchCalls(), 0, "guest feedback must never reach fetch");

  const expired = loadWidget();
  expired.auth.state = { status: "authenticated", user: { username: "alice" }, reason: "authenticated" };
  expired.settle();
  expired.setFetch(() => Promise.resolve({ status: 401, ok: false, json: () => Promise.resolve({ error: "未登录" }) }));
  await assert.rejects(
    expired.widget.submitFeedback({ content: "still here" }, "提交反馈"),
    (error) => error.code === "AUTH_REQUIRED"
  );
  assert.strictEqual(expired.getFetchCalls(), 1);
  assert.strictEqual(expired.getMarkedGuest(), "unauthorized");
  assert.match(expired.getPrompted(), /提交反馈/);

  const network = loadWidget();
  network.auth.state = { status: "authenticated", user: { username: "alice" }, reason: "authenticated" };
  network.settle();
  network.setFetch(() => Promise.reject(new TypeError("offline")));
  await assert.rejects(
    network.widget.submitFeedback({ content: "offline" }, "提交反馈"),
    (error) => error.code === "FEEDBACK_NETWORK" && error.category === "network"
  );
  assert.strictEqual(network.getPrompted(), "", "a network failure must not be shown as an auth failure");

  console.log("feedback-widget: auth wait, guest gate, 401 demotion and network separation PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
