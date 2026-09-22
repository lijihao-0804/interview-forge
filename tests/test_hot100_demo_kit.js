/* DemoKit timer/lifecycle smoke test; run with: node tests/test_hot100_demo_kit.js */
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class FakeClassList {
  constructor() { this.items = new Set(); }
  add(...names) { names.forEach((name) => this.items.add(name)); }
  remove(...names) { names.forEach((name) => this.items.delete(name)); }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.classList = new FakeClassList();
    this._className = "";
    this.style = { setProperty: (key, value) => { this.style[key] = value; } };
    this.dataset = {};
    this.listeners = {};
    this._text = "";
    this._innerHTML = "";
    this.value = "";
    this.disabled = false;
  }
  set className(value) {
    this._className = String(value || "");
    this.classList.items = new Set(this._className.split(/\s+/).filter(Boolean));
  }
  get className() { return this._className; }
  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    if (this.tagName === "SELECT" && child.tagName === "OPTION" && child.selected) this.value = child.value;
    return child;
  }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get textContent() { return this._text || this.children.map((child) => child.textContent).join(""); }
  set innerHTML(value) { this._innerHTML = String(value ?? ""); this.children = []; }
  get innerHTML() { return this._innerHTML; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  click() {
    if (typeof this.onclick === "function") this.onclick({ target: this });
    (this.listeners.click || []).forEach((callback) => callback({ target: this }));
  }
  querySelector() { return null; }
  setAttribute(name, value) { (this.attrs ||= {})[name] = String(value); }
  getAttribute(name) { return (this.attrs || {})[name] ?? null; }
}

const created = [];
const app = new FakeElement("main");
const head = new FakeElement("head");
const body = new FakeElement("body");
const document = {
  head,
  body,
  createElement(tag) { const item = new FakeElement(tag); created.push(item); return item; },
  getElementById(id) { return id === "app" ? app : null; },
  addEventListener() {},
};

const windowListeners = {};
const window = {
  addEventListener(name, callback) { (windowListeners[name] ||= []).push(callback); },
  dispatchEvent(event) { (windowListeners[event.type] || []).forEach((callback) => callback(event)); },
};

let nextTimerId = 1;
const timers = new Map();
function setTimeoutFake(callback, delay) {
  const id = nextTimerId++;
  timers.set(id, { callback, delay });
  return id;
}
function clearTimeoutFake(id) { timers.delete(id); }
function runNextTimer() {
  const first = timers.entries().next().value;
  assert(first, "expected a pending timer");
  timers.delete(first[0]);
  first[1].callback();
  return first[1].delay;
}

class CustomEventFake { constructor(type) { this.type = type; } }
const context = {
  window,
  document,
  CustomEvent: CustomEventFake,
  setTimeout: setTimeoutFake,
  clearTimeout: clearTimeoutFake,
  Number,
  Math,
  String,
  console,
};
vm.runInNewContext(fs.readFileSync("books/hot100/05-可视化/assets/demo-kit.js", "utf8"), context, {
  filename: "books/hot100/05-可视化/assets/demo-kit.js",
});

let buildCount = 0;
context.window.DemoKit.mount({
  no: "146",
  title: "LRU",
  stageHeight: 360,
  sizes: [{ label: "小", value: "small" }, { label: "大", value: "large" }],
  build(ctx) {
    buildCount += 1;
    ctx.step("开始", { n: 1 });
    ctx.phase("compare", "比较", { n: 2 }, { duration: 420 });
    ctx.step("更新", { n: 3 });
    ctx.step("完成", { n: 4 });
  },
  render(view, stage) { stage.appendChild(new FakeElement("span")); },
});

const buttons = created.filter((item) => item.tagName === "BUTTON");
const button = (label) => buttons.find((item) => item.textContent === label);
const play = button("▶ 自动播放");
const reset = button("↻ 重置");
const speed4 = button("4×");
assert(play && reset && speed4, "DemoKit controls missing");
assert.strictEqual(app.children.find((item) => item.classList.items.has("dk-stage")).style["--dk-stage-height"], "360px");
assert.strictEqual(context.window.__dk.steps[1].phase, "compare");
assert.strictEqual(context.window.__dk.steps[1].duration, 420);

play.click();
assert.strictEqual(timers.size, 1, "play must create exactly one timer");
assert.strictEqual(play.textContent, "⏸ 暂停");
const delays = [];
while (timers.size) delays.push(runNextTimer());
assert.deepStrictEqual(delays, [900, 900], "autoplay sequence should use one timer per delayed step");
assert.strictEqual(play.textContent, "▶ 自动播放");
assert.strictEqual(timers.size, 0, "autoplay must stop at the final step");

play.click();
assert.strictEqual(timers.size, 1);
play.click();
assert.strictEqual(timers.size, 0, "pause must clear the timer");

play.click();
speed4.click();
assert.strictEqual(timers.size, 1, "speed change must keep one timer");
assert.strictEqual(runNextTimer(), 225, "speed change must affect the next tick");
reset.click();
assert.strictEqual(timers.size, 0, "reset must stop old playback");
assert(buildCount >= 2, "reset must rebuild the demo");

play.click();
assert.strictEqual(timers.size, 1);
(windowListeners.pagehide || []).forEach((callback) => callback());
assert.strictEqual(timers.size, 0, "pagehide must stop playback");

/* ── 增强层：代码行同步 / 不变量条 / 反例对照 ───────────────────────────── */
created.length = 0;
let compareBuilds = 0;
context.window.DemoKit.mount({
  no: "3",
  title: "增强层冒烟",
  code: ["int left = 0;", "for (int r = 0; r < n; r++) {", "  left = max(left, last[c] + 1);", "}"],
  invariants: [
    { label: "窗口内无重复", test: (view) => view.ok === true },
    { label: "窗口长度", test: (view) => `${view.len}` },
  ],
  compare: {
    label: "错误写法",
    build(ctx) {
      compareBuilds += 1;
      ctx.step("错误：left 回退", { len: 9, ok: false });
      ctx.step("错误：答案偏大", { len: 9, ok: false });
    },
    render(view, stage) { stage.appendChild(new FakeElement("span")); },
  },
  build(ctx) {
    ctx.step("初始化", { len: 0, ok: true }, { line: 1 });
    ctx.step("右端扩张", { len: 1, ok: true }, { line: 2 });
    ctx.step("左端跳过重复", { len: 2, ok: false }, { line: [2, 3] });
  },
  render(view, stage) { stage.appendChild(new FakeElement("span")); },
});

const byClass = (name) => created.filter((item) => item.classList.items.has(name));
const has = (item, name) => item.classList.items.has(name);

// 1) 代码窗格：每行一个节点，并按 meta.line 高亮（1 基）。
const lines = byClass("dk-code-line");
assert.strictEqual(lines.length, 4, "code pane must render one node per line");
assert.deepStrictEqual(lines.map((item) => has(item, "on")), [true, false, false, false],
  "step 1 must highlight only line 1");

// 2) 不变量条：布尔 -> ok/bad，字符串 -> 作为补充说明。
const chips = byClass("dk-inv");
assert.strictEqual(chips.length, 2, "one chip per invariant");
assert(has(chips[0], "ok") && !has(chips[0], "bad"), "true invariant must render as ok");

// 3) 前进后代码高亮与不变量同步更新；line 支持数组。
const next = created.filter((item) => item.tagName === "BUTTON").find((item) => item.textContent === "下一步 ▶");
next.click();
next.click();
assert.deepStrictEqual(lines.map((item) => has(item, "on")), [false, true, true, false],
  "array line meta must highlight several lines");
assert(has(chips[0], "bad"), "false invariant must flip the chip to bad");

// 4) 反例对照：与主线同时构建，勾选后才接入布局。
assert.strictEqual(compareBuilds, 1, "compare branch must be built alongside the main one");
const main = byClass("dk-main")[0];
assert(main && has(main, "has-code"), "code pane must switch the grid on");
assert(!has(main, "is-compare"), "compare column stays off until toggled");
const toggle = byClass("dk-toggle")[0];
const checkbox = toggle.children.find((item) => item.tagName === "INPUT");
checkbox.checked = true;
checkbox.onchange();
assert(has(main, "is-compare"), "toggling must open the compare column");

console.log(JSON.stringify({
  ok: true,
  build_count: buildCount,
  timers_remaining: timers.size,
  autoplay_delays: delays,
  code_lines: lines.length,
  invariants: chips.length,
  compare_builds: compareBuilds,
}));
