const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function testLiveUpdates() {
  let now = 0;
  let timerId = 0;
  const timers = new Map();
  const elements = new Map();
  const document = new EventTarget();
  document.hidden = false;
  document.getElementById = id => {
    if (!elements.has(id)) {
      const el = new EventTarget();
      el.replaceChildren = () => {};
      elements.set(id, el);
    }
    return elements.get(id);
  };
  const window = new EventTarget();
  const rendered = [];
  window.CodeFocusDisplay = {
    mountReader: () => (code, language) => rendered.push([code, language]),
    renderAnswers: value => value ? 1 : 0,
  };
  const requests = [];
  let version = 1;
  let unavailable = false;
  const fetch = async (url, options) => {
    assert.equal(url, "/api/code-focus/publication");
    const condition = options.headers["If-None-Match"];
    requests.push({ time: now, condition });
    if (unavailable) throw new Error("offline");
    const tag = '"' + version + '"';
    if (condition === tag) return { status: 304 };
    return {
      ok: true, status: 200, headers: { get: () => tag },
      json: async () => ({ version, code: "print(" + version + ")", language: "python", answers: "BC" }),
    };
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../assets/code-focus-live.js"), "utf8"), {
    document, window, navigator: { onLine: true }, AbortController, fetch, Date: { now: () => now },
    setTimeout(fn, delay) { timers.set(++timerId, { fn, at: now + delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });

  async function advance(ms) {
    const end = now + ms;
    for (;;) {
      const next = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > end) break;
      now = next[1].at;
      timers.delete(next[0]);
      await next[1].fn();
    }
    now = end;
  }
  function visible(value) {
    document.hidden = !value;
    document.dispatchEvent(new Event("visibilitychange"));
  }
  await advance(0);
  assert.deepEqual(rendered, [["print(1)", "python"]]);
  visible(false);
  visible(true);
  await advance(29999);
  assert.equal(requests.length, 1);
  await advance(1);
  assert.equal(requests[1].condition, '"1"');
  assert.equal(rendered.length, 1);
  visible(false);
  version++;
  await advance(180000);
  assert.equal(requests.length, 2);
  visible(true);
  await advance(0);
  assert.deepEqual(rendered[1], ["print(2)", "python"]);
  unavailable = true;
  await advance(30000);
  await advance(59999);
  assert.equal(requests.length, 4);
  unavailable = false;
  await advance(1);
  assert.equal(requests.length, 5);
  assert.equal(rendered.length, 2);
}

testLiveUpdates().catch(error => { console.error(error); process.exitCode = 1; });
