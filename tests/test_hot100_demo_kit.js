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

console.log(JSON.stringify({ ok: true, build_count: buildCount, timers_remaining: timers.size, autoplay_delays: delays }));
