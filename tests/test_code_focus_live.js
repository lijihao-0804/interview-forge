const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function testLiveUpdates() {
  const elements = new Map();
  const document = new EventTarget();
  document.hidden = false;
  document.getElementById = id => {
    if (!elements.has(id)) elements.set(id, new EventTarget());
    return elements.get(id);
  };
  const window = new EventTarget();
  const rendered = [];
  window.CodeFocusDisplay = {
    mountReader: () => (code, lang) => rendered.push([code, lang]),
    renderAnswers: raw => raw ? 1 : 0,
  };
  const streams = [];
  class EventSource extends EventTarget {
    static OPEN = 1;
    static CLOSED = 2;
    constructor(url) {
      super();
      assert.equal(url, "/api/code-focus/publication/events");
      this.readyState = 1;
      streams.push(this);
    }
    notify(version) {
      const event = new Event("publication");
      event.data = String(version);
      this.dispatchEvent(event);
    }
    close() { this.readyState = 2; }
  }
  let version = 0;
  let holdResponse;
  let failNextRead = false;
  const reads = [];
  const fetch = async (url, options) => {
    assert.equal(url, "/api/code-focus/publication");
    assert.equal(options.credentials, "omit");
    const snapshot = version;
    reads.push(snapshot);
    if (failNextRead) {
      failNextRead = false;
      throw new Error("Network unavailable");
    }
    if (holdResponse) await holdResponse;
    return { ok: true, json: async () => ({ version: snapshot, code: "v" + snapshot, language: "python", answers: "" }) };
  };
  const timers = new Map();
  let timerId = 0;
  const settle = () => new Promise(resolve => setImmediate(resolve));
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../assets/code-focus-live.js"), "utf8"), {
    document, window, navigator: { onLine: true }, AbortController, EventSource, fetch,
    setTimeout(fn, delay) { timers.set(++timerId, {fn, delay}); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  await settle();
  assert.deepEqual(reads, [0]);
  streams[0].notify(0);
  streams[0].notify("bad");
  await settle();
  assert.equal(reads.length, 1);
  assert.equal(timers.size, 0, "idle reader must not schedule content checks");

  let release;
  holdResponse = new Promise(resolve => { release = resolve; });
  streams[0].notify(++version);
  streams[0].notify(++version);
  streams[0].notify(version);
  assert.deepEqual(reads, [0, 1]);
  holdResponse = null;
  release();
  await settle();
  assert.deepEqual(reads, [0, 1, 2]);
  assert.deepEqual(rendered.at(-1), ["v2", "python"]);
  assert.equal(timers.size, 0);

  document.hidden = true;
  document.dispatchEvent(new Event("visibilitychange"));
  assert.equal(streams[0].readyState, EventSource.CLOSED);
  streams[0].notify(++version);
  assert.deepEqual(reads, [0, 1, 2]);
  document.hidden = false;
  document.dispatchEvent(new Event("visibilitychange"));
  assert.equal(streams.length, 2);
  streams[1].notify(version);
  await settle();
  assert.deepEqual(rendered.at(-1), ["v3", "python"]);
  streams[1].notify(version);
  await settle();
  assert.deepEqual(reads, [0, 1, 2, 3]);
  assert.equal(timers.size, 0);

  failNextRead = true;
  streams[1].notify(++version);
  await settle();
  assert.equal(rendered.at(-1)[0], "v3");
  const [[retryId, retry]] = timers;
  assert.equal(retry.delay, 2000);
  timers.delete(retryId);
  await retry.fn();
  assert.equal(rendered.at(-1)[0], "v4");
  assert.equal(timers.size, 0);

  streams[1].close();
  streams[1].dispatchEvent(new Event("error"));
  assert.equal(timers.size, 1);
  document.hidden = true;
  document.dispatchEvent(new Event("visibilitychange"));
  assert.equal(timers.size, 0, "a hidden tab must not reopen the event stream");
  document.hidden = false;
  document.dispatchEvent(new Event("visibilitychange"));
  streams[2].notify(version);
  await settle();
  assert.equal(reads.length, 6);
}

testLiveUpdates().catch(error => { console.error(error); process.exitCode = 1; });
