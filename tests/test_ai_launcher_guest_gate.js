/* AI launcher auth-delay regression; run with: node tests/test_ai_launcher_guest_gate.js */
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "assets", "ai-launcher.js"), "utf8");

function eventTarget(extra) {
  const listeners = Object.create(null);
  return Object.assign({
    addEventListener(name, callback) {
      (listeners[name] || (listeners[name] = [])).push(callback);
    },
    dispatch(name, event) {
      (listeners[name] || []).forEach((callback) => callback(event || {}));
    }
  }, extra || {});
}

function bootHarness(requireUser) {
  const bodyChildren = [];
  const classNames = [];
  const body = eventTarget({
    style: {},
    appendChild(node) {
      bodyChildren.push(node);
      node.parent = body;
      return node;
    }
  });

  function element(tagName) {
    return eventTarget({
      tagName: tagName.toUpperCase(),
      children: [],
      style: {},
      hidden: false,
      setAttribute(name, value) { this[name] = value; },
      appendChild(node) { this.children.push(node); return node; },
      remove() { this.removed = true; }
    });
  }

  const document = eventTarget({
    body,
    documentElement: {
      classList: {
        add(name) { classNames.push(["add", name]); },
        remove(name) { classNames.push(["remove", name]); }
      }
    },
    getElementById() { return null; },
    createElement(tagName) {
      if (tagName === "div") {
        const drawer = element("div");
        const backdrop = element("button");
        const close = element("button");
        const frame = element("iframe");
        frame.contentWindow = { postMessage(message) { frame.message = message; } };
        Object.defineProperty(drawer, "innerHTML", {
          set(value) {
            drawer.markup = String(value);
            const sourceMatch = drawer.markup.match(/src="([^"]+)"/);
            if (sourceMatch) frame.src = sourceMatch[1];
          }
        });
        drawer.querySelector = function (selector) {
          if (selector === "iframe") return frame;
          if (selector === ".if-ai-drawer-backdrop") return backdrop;
          if (selector === ".if-ai-drawer-actions button") return close;
          return null;
        };
        drawer.frame = frame;
        return drawer;
      }
      return element(tagName);
    }
  });

  let authCalls = 0;
  let prompted = 0;
  let alerts = 0;
  const auth = {
    ready: Promise.resolve(),
    requireUser(feature) {
      authCalls += 1;
      prompted += 1;
      assert.match(String(feature || ""), /使用 AI 助手/);
      return requireUser;
    }
  };
  const windowObject = eventTarget({
    document,
    location: { pathname: "/cockpit.html", origin: "https://example.test" },
    InterviewForgeAuth: auth,
    InterviewForgeAI: { getPageContext() { return { title: "guest gate" }; } },
    alert() { alerts += 1; },
    setTimeout,
    clearTimeout
  });
  const sandbox = {
    window: windowObject,
    document,
    Promise,
    Error,
    String,
    setTimeout,
    clearTimeout
  };
  vm.runInNewContext(source, sandbox, { filename: "assets/ai-launcher.js" });
  return {
    window: windowObject,
    bodyChildren,
    getAuthCalls() { return authCalls; },
    getPrompted() { return prompted; },
    getAlerts() { return alerts; },
    drawer() { return bodyChildren.find((item) => item.className === "if-ai-drawer-wrap"); }
  };
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  let allowOpen;
  const authenticated = bootHarness(new Promise((resolve) => { allowOpen = resolve; }));
  authenticated.window.dispatch("interviewforge:open-ai");
  await flush();
  assert.strictEqual(authenticated.getAuthCalls(), 1);
  assert.strictEqual(authenticated.drawer(), undefined, "drawer must stay closed while auth is pending");

  allowOpen();
  await flush();
  assert(authenticated.drawer(), "drawer should open after the session becomes authenticated");
  assert.match(authenticated.drawer().frame.src, /ai-assistant\.html\?embedded=1/);

  let rejectGuest;
  const guest = bootHarness(new Promise((_resolve, reject) => { rejectGuest = reject; }));
  guest.window.dispatch("interviewforge:open-ai");
  await flush();
  assert.strictEqual(guest.drawer(), undefined, "guest must never receive the writable AI drawer");
  const denied = new Error("登录后才能使用 AI 助手");
  denied.code = "AUTH_REQUIRED";
  rejectGuest(denied);
  await flush();
  assert.strictEqual(guest.getPrompted(), 1);
  assert.strictEqual(guest.getAlerts(), 0, "AUTH_REQUIRED should stay an auth prompt, not a generic alert");

  console.log("ai-launcher: delayed auth, guest denial and authenticated open PASS");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
