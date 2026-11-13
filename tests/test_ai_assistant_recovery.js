/* Exercise the production form handlers and ReadableStream reader without a provider or a browser dependency. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(path.join(__dirname, "../assets/ai-assistant.js"), "utf8");
const url = "https://forge.test/pages/ai-assistant.html";
const encode = new TextEncoder();
const originalContext = { title: "LRU 题解", path: "/books/lru.html" };
const json = (payload, status = 200) => Response.json(payload, { status });
const stream = (body) => new Response(body, { headers: { "Content-Type": "text/event-stream" } });
const event = (name, payload) => "event: " + name + "\r\ndata: " + JSON.stringify(payload) + "\r\n\r\n";
const noRecord = () => json({ error_category: "chat_request_not_found" }, 404);

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.classes = new Set();
    this.classList = {
      add: (name) => this.classes.add(name),
      remove: (name) => this.classes.delete(name),
      toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name),
    };
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.scrollHeight = this.scrollTop = this.clientHeight = 0;
  }
  set className(value) { this.classes = new Set(value.split(/\s+/)); }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text || ""; }
  get childElementCount() { return this.children.length; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { this.children.push(...children); }
  insertBefore(child, sibling) { this.children.splice(this.children.indexOf(sibling), 0, child); }
  replaceChildren(...children) {
    this.children = children.flatMap((child) => child.tag === "fragment" ? child.children : [child]);
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => {
      const match = selector.startsWith(".") ? child.classes.has(selector.slice(1)) : child.tag === selector;
      return (match ? [child] : []).concat(child.querySelectorAll(selector));
    });
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  setAttribute(name, value) { this[name] = value; }
  focus() {}
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type, detail = {}) {
    return Promise.all((this.listeners[type] || []).map((fn) => fn({ preventDefault() {}, ...detail })));
  }
}

function storage() {
  const entries = new Map();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key),
  };
}

function backend() {
  return {
    username: "alice", sessions: ["s1"], posts: [], lookups: [], rows: [], actions: [],
    lookup() { return noRecord(); },
    post() { throw new Error("transport disconnected"); },
    async fetch(resource, options = {}) {
      if (resource === "/api/me") return json({ username: this.username });
      if (resource === "/api/chat/sessions") {
        if (options.method === "POST") { this.sessions.unshift("s2"); return json({ id: "s2", title: "s2" }); }
        return json({ items: this.sessions.map((id) => ({ id, title: id })) });
      }
      const [, session, route] = resource.match(/^\/api\/chat\/sessions\/(\w+)\/(.+)$/) || [];
      if (route === "messages") return json({ session: { title: session }, items: this.rows });
      if (route === "actions?status=pending") return json({ items: this.actions });
      if (route && route.startsWith("requests/")) {
        this.lookups.push({ session, key: route.slice(9), user: this.username });
        return this.lookup();
      }
      assert.equal(route, "stream", "unexpected request " + resource);
      this.posts.push({ session, body: options.body, signal: options.signal });
      return this.post(JSON.parse(options.body), options.signal);
    },
  };
}

async function until(condition, label) {
  for (let i = 0; i < 100; i++) {
    if (condition()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.fail(label);
}

async function boot(server, tab = storage(), local = storage(), embedded = false) {
  const nodes = new Map();
  function get(id) {
    if (!nodes.has(id)) nodes.set(id, new Element(id));
    return nodes.get(id);
  }
  const document = {
    body: new Element("body"), getElementById: get,
    createElement: (tag) => new Element(tag), createDocumentFragment: () => new Element("fragment"),
  };
  const polls = new Set();
  const window = Object.assign(new Element("window"), {
    location: new URL(url + (embedded ? "?embedded=1" : "")), crypto: webcrypto,
    InterviewForgeAI: { getPageContext: () => originalContext },
    setTimeout(callback, ms) {
      if (ms < 1000) return setTimeout(callback, ms);
      polls.add(callback);
      return callback;
    },
    clearTimeout(timer) { if (!polls.delete(timer)) clearTimeout(timer); },
    requestAnimationFrame: (callback) => setTimeout(callback, 0),
  });
  window.parent = embedded ? { postMessage(msg) {
    window.dispatch("message", { origin: window.location.origin, data: {
      type: "interviewforge:page-context", request_id: msg.request_id, context: window.InterviewForgeAI.getPageContext(),
    } });
  } } : window;
  vm.runInNewContext(source, { window, document, location: window.location, URLSearchParams, AbortController,
    sessionStorage: tab, localStorage: local, fetch: server.fetch.bind(server), performance, TextDecoder });
  await until(() => ["已连接", "等待重试", "等待核对", "原请求仍在处理…"].includes(get("status").textContent), "open chat");
  return {
    get, tab, local, window,
    nextPoll() {
      assert.equal(polls.size, 1, "one status poll is scheduled");
      const [callback] = polls;
      polls.delete(callback);
      callback();
    },
    submit(text) { get("messageInput").value = text; return get("composer").dispatch("submit"); },
    click(id) { return get(id).dispatch("click"); },
    ready() { return until(() => get("status").textContent === "已连接", "chat ready"); },
    bubbles() { return get("messages").querySelectorAll(".bubble").map((node) => node.innerHTML); },
  };
}

async function lostDoneAndNewTurn() {
  const server = backend(), ui = await boot(server);
  const sources = [{ title: "题解", url: "/books/lru.html" }];
  server.post = ({ message }) => {
    server.rows = [{ role: "user", content: message }, { role: "assistant", content: "已保存",
      metadata: { stream_message_id: "original", library_sources: sources } }];
    server.actions = [{ action_id: "same-action", display_name: "待确认" }];
    server.lookup = () => json({ status: "completed", message_id: "original" });
    // A final frame missing its blank line is not a terminal receipt.
    return stream(event("message.start", {}) + event("message.delta", { delta: "局部" }) +
      'event: message.done\ndata: {"message_id":"original"}\n');
  };
  await ui.submit("一道题");
  assert.deepEqual(ui.bubbles(), ["一道题", "<p>已保存</p>"]);
  assert.equal(ui.get("messages").querySelectorAll(".action-card").length, 1);
  assert.equal(ui.get("messages").querySelector("a").href, "/books/lru.html");
  assert.equal(server.posts.length, 1);
  assert.equal(server.lookups[0].key, JSON.parse(server.posts[0].body).client_request_id);
  await ui.submit("一道题");
  assert.notEqual(JSON.parse(server.posts[1].body).client_request_id, server.lookups[0].key);
}

async function frozenRetryAndReader() {
  const server = backend(), ui = await boot(server, storage(), storage(), true);
  await ui.submit("原问题");
  assert.equal(ui.get("retryTurn").hidden, false);
  assert.equal(ui.get("messageInput").value, "原问题");
  ui.window.InterviewForgeAI.getPageContext = () => ({ path: "/books/new.html" });
  server.post = () => {
    const text = ": heartbeat\r\n\r\n" + event("message.start", {}) +
      'event: message.delta\r\ndata: {\r\ndata: "delta":"答案"}\r\n\r\n' + event("message.done", { message_id: "m" });
    return stream(new ReadableStream({ start(controller) {
      for (const byte of encode.encode(text)) controller.enqueue(Uint8Array.of(byte));
      // A proxy can keep the HTTP connection open after the terminal event.
    } }));
  };
  await ui.click("retryTurn");
  await ui.ready();
  assert.equal(server.posts[0].body, server.posts[1].body);
  assert.deepEqual(JSON.parse(server.posts[1].body).page_context, originalContext);
  assert.deepEqual(ui.bubbles(), ["原问题", "<p>答案</p>"]);
  assert.equal(server.lookups.length, 1);
}

async function reloadAndIsolation() {
  const server = backend(), old = await boot(server);
  await old.click("newSession");
  await until(() => old.get("chatTitle").textContent === "s2", "select new session");
  await old.submit("仅限本账户");
  const key = JSON.parse(server.posts[0].body).client_request_id;
  server.sessions = ["s1", "s2"]; // The saved session is no longer first in the list.
  server.lookup = () => { throw new Error("offline"); };
  const embedded = await boot(server, old.tab, old.local, true);
  assert.equal(embedded.get("retryTurn").textContent, "检查状态");
  server.username = "bob";
  const checks = server.lookups.length;
  const other = await boot(server, old.tab, old.local);
  assert.equal(other.get("chatTitle").textContent, "s1");
  assert.equal(other.get("messageInput").value, "");
  assert.equal(server.lookups.length, checks);
  server.username = "alice";
  let poll = 0;
  server.lookup = () => {
    if (poll++ === 0) return json({ status: "in_progress" });
    server.rows = [{ role: "user", content: "仅限本账户" }, { role: "assistant", content: "历史答案" }];
    return json({ status: "completed", message_id: "m" });
  };
  await embedded.window.dispatch("online");
  await until(() => embedded.get("status").textContent === "原请求仍在处理…", "active receipt");
  embedded.nextPoll();
  await embedded.ready();
  assert.equal(server.posts.length, 1);
  assert.ok(server.lookups.every((x) => x.session === "s2" && x.key === key && x.user === "alice"));
  assert.deepEqual(embedded.bubbles(), ["仅限本账户", "<p>历史答案</p>"]);
}

async function stopAndTerminalEffect() {
  const server = backend(), ui = await boot(server);
  server.post = () => stream(new ReadableStream({ start(controller) {
    controller.enqueue(encode.encode(event("message.start", {})));
  } }));
  const pending = ui.submit("停");
  await until(() => server.posts.length === 1, "original stream opened");
  await ui.click("stop");
  await pending;
  assert.ok(server.posts[0].signal.aborted);
  assert.equal(ui.get("retryTurn").hidden, true);
  assert.match(ui.get("error").textContent, /已停止/);
  await boot(server, ui.tab, ui.local);
  assert.equal(server.posts.length, 1);
  assert.equal(server.lookups.length, 1);
  server.post = () => stream(event("message.start", {}) + event("error", { message: "断开" }));
  server.lookup = () => json({ status: "interrupted", message_id: "m" });
  server.rows = [{ role: "user", content: "保存" }];
  server.actions = [{ action_id: "exists" }];
  await ui.submit("保存");
  assert.equal(ui.get("retryTurn").hidden, true);
  assert.ok(ui.get("messages").querySelector(".action-card"));
  assert.match(ui.get("error").textContent, /已保存/);
  assert.equal(server.posts.length, 2);
}

async function staleCallbacksAndEdit() {
  const server = backend(), ui = await boot(server);
  let finish;
  server.post = () => new Promise((resolve) => { finish = resolve; });
  const old = ui.submit("旧会话的消息");
  await until(() => finish, "first send admitted");
  await ui.click("newSession");
  await until(() => ui.get("chatTitle").textContent === "s2", "second session selected");
  finish(stream(event("message.start", {}) + event("message.delta", { delta: "过时的结果" })));
  await old;
  assert.deepEqual(ui.bubbles(), []);
  assert.equal(server.lookups.length, 0);
  server.post = () => { throw new Error("offline"); };
  await ui.submit("新会话提问");
  await ui.click("editTurn");
  assert.equal(ui.get("messageInput").disabled, false);
  assert.equal(ui.get("messageInput").value, "新会话提问");
  await ui.submit("修改后的提问");
  assert.notEqual(JSON.parse(server.posts[1].body).client_request_id, JSON.parse(server.posts[2].body).client_request_id);
  assert.equal(server.posts[0].session, "s1");
  assert.equal(server.posts[1].session, "s2");
}

(async () => {
  await lostDoneAndNewTurn();
  await frozenRetryAndReader();
  await reloadAndIsolation();
  await stopAndTerminalEffect();
  await staleCallbacksAndEdit();
  console.log("chat recovery: receipts, retries, reload, accounts, cancellation and stale callbacks passed");
})().catch((err) => { console.error(err); process.exitCode = 1; });
