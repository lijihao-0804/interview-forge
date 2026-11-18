/* DemoKit timer/lifecycle smoke test; run with: node tests/test_hot100_demo_kit.js */
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

class FakeClassList {
  constructor() { this.items = new Set(); }
  add(...names) { names.forEach((name) => this.items.add(name)); }
  remove(...names) { names.forEach((name) => this.items.delete(name)); }
  toggle(name, force) {
    const enabled = force === undefined ? !this.items.has(name) : !!force;
    if (enabled) this.items.add(name);
    else this.items.delete(name);
    return enabled;
  }
  contains(name) { return this.items.has(name); }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.nodeType = 1;
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
    if (child.parentNode) child.parentNode.removeChild(child);
    this.children.push(child);
    child.parentNode = this;
    if (this.tagName === "SELECT" && child.tagName === "OPTION" && child.selected) this.value = child.value;
    return child;
  }
  insertBefore(child, reference) {
    if (child.parentNode) child.parentNode.removeChild(child);
    const index = reference ? this.children.indexOf(reference) : -1;
    if (index < 0) this.children.push(child);
    else this.children.splice(index, 0, child);
    child.parentNode = this;
    return child;
  }
  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) this.children.splice(index, 1);
    child.parentNode = null;
    return child;
  }
  get firstChild() { return this.children[0] || null; }
  get nextSibling() {
    if (!this.parentNode) return null;
    const index = this.parentNode.children.indexOf(this);
    return index >= 0 ? (this.parentNode.children[index + 1] || null) : null;
  }
  get nextElementSibling() {
    let node = this.nextSibling;
    while (node && node.nodeType !== 1) node = node.nextSibling;
    return node;
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
  descendants() {
    const result = [];
    const walk = (node) => (node.children || []).forEach((child) => {
      result.push(child);
      walk(child);
    });
    walk(this);
    return result;
  }
  matches(selector) {
    const alternatives = String(selector).split(",").map((value) => value.trim()).filter(Boolean);
    return alternatives.some((part) => {
      if (part.includes(" > ")) {
        const [parentSelector, childSelector] = part.split(" > ");
        return this.parentNode && this.parentNode.matches(parentSelector) && this.matches(childSelector);
      }
      const tokens = part.split(/\s+/).filter(Boolean);
      if (tokens.length > 1) {
        if (!this.matches(tokens[tokens.length - 1])) return false;
        let ancestor = this.parentNode;
        while (ancestor) {
          if (tokens.slice(0, -1).every((token) => ancestor.matches(token))) return true;
          ancestor = ancestor.parentNode;
        }
        return false;
      }
      const tag = (part.match(/^[A-Za-z][\w-]*/) || [null])[0];
      const classes = [...part.matchAll(/\.([\w-]+)/g)].map((match) => match[1]);
      const id = (part.match(/#([\w-]+)/) || [null, null])[1];
      return (!tag || this.tagName === tag.toUpperCase()) &&
        classes.every((name) => this.classList.contains(name)) &&
        (!id || (this.attrs || {}).id === id);
    });
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  querySelectorAll(selector) { return this.descendants().filter((item) => item.matches(selector)); }
  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches && node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }
  setAttribute(name, value) { (this.attrs ||= {})[name] = String(value); }
  getAttribute(name) { return (this.attrs || {})[name] ?? null; }
  removeAttribute(name) { if (this.attrs) delete this.attrs[name]; }
}

const created = [];
const app = new FakeElement("main");
const head = new FakeElement("head");
const body = new FakeElement("body");
const docListeners = {};
const document = {
  head,
  body,
  createElement(tag) { const item = new FakeElement(tag); created.push(item); return item; },
  getElementById(id) { return id === "app" ? app : null; },
  addEventListener(name, callback) { (docListeners[name] ||= []).push(callback); },
  removeEventListener(name, callback) {
    docListeners[name] = docListeners[name].filter(listener => listener !== callback);
  },
};

const windowListeners = {};
const storage = new Map();
const window = {
  addEventListener(name, callback) { (windowListeners[name] ||= []).push(callback); },
  removeEventListener(name, callback) {
    windowListeners[name] = windowListeners[name].filter(listener => listener !== callback);
  },
  dispatchEvent(event) { (windowListeners[event.type] || []).forEach((callback) => callback(event)); },
};
window.localStorage = {
  getItem(key) { return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
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
  showCode: true,
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

// 5) 全局语言跟随：非 Java 模式不得保留 Java 行节点，但演示本体与控制仍可用。
created.length = 0;
window.localStorage.setItem("forge-lang", "python");
window.dispatchEvent({ type: "storage", key: "forge-lang" });
const mountedNodes = [];
(function walk(node) {
  mountedNodes.push(node);
  (node.children || []).forEach(walk);
})(app);
const mountedByClass = (name) => mountedNodes.filter((item) => item.classList.items.has(name));
assert.strictEqual(mountedByClass("dk-code-line").length, 0, "Python mode must not display Java-only lines");
const languageNotes = mountedByClass("dk-code-empty");
assert.strictEqual(languageNotes.length, 1, "Python mode needs one language note");
assert(!languageNotes[0].hidden, "language note must be visible when Java code is suppressed");
assert(languageNotes[0].textContent.includes("Python") && languageNotes[0].textContent.includes("Java"));
assert(mountedByClass("dk-stage").length >= 1, "language isolation must preserve the animation stage");
assert(mountedNodes.some((item) => item.tagName === "BUTTON" && item.textContent === "下一步 ▶"),
  "language isolation must preserve step controls");

window.localStorage.setItem("forge-lang", "java");
window.dispatchEvent({ type: "storage", key: "forge-lang" });
const restoredNodes = [];
(function walk(node) {
  restoredNodes.push(node);
  (node.children || []).forEach(walk);
})(app);
const restoredByClass = (name) => restoredNodes.filter((item) => item.classList.items.has(name));
const javaLines = restoredByClass("dk-code-line");
assert.strictEqual(javaLines.length, 4, "returning to Java must restore one node per source line");
assert.deepStrictEqual(javaLines.map((item) => has(item, "on")), [false, true, true, false],
  "returning to Java must restore current line highlighting");
assert(restoredByClass("dk-code-empty")[0].hidden, "language note must hide when code is available");

assert.strictEqual(docListeners.keydown.length, 1, "switching problems keeps one keyboard handler");
assert.strictEqual(windowListeners.pagehide.length, 1, "switching problems releases old playback listeners");
const beforeSelectKey = window.__dk.idx;
docListeners.keydown[0]({key: "ArrowRight", target: {tagName: "SELECT"}});
assert.strictEqual(window.__dk.idx, beforeSelectKey, "the input selector owns its arrow keys");

console.log(JSON.stringify({
  ok: true,
  build_count: buildCount,
  timers_remaining: timers.size,
  autoplay_delays: delays,
  code_lines: lines.length,
  invariants: chips.length,
  compare_builds: compareBuilds,
}));

/* ── 自测模式：语言面板内 H2 也必须按解法分区遮罩 ─────────────────────── */
{
  const selftestSource = fs.readFileSync("scripts/build/build_html_site.py", "utf8");
  const match = selftestSource.match(/SELFTEST_JS = """([\s\S]*?)"""/);
  assert(match, "SELFTEST_JS must be extractable from the HTML builder");

  const pageBody = new FakeElement("body");
  const article = new FakeElement("article");
  article.className = "markdown-body hot100-solution";
  const toggleButton = new FakeElement("button");
  toggleButton.setAttribute("id", "selftestToggle");
  toggleButton.textContent = "自测模式";

  const pageTitle = new FakeElement("h1");
  pageTitle.textContent = "测试题";
  const commonHeading = new FakeElement("h2");
  commonHeading.textContent = "题目与约束";
  const statement = new FakeElement("p");
  statement.className = "statement";
  statement.textContent = "公共题面";

  const pythonPanel = new FakeElement("section");
  pythonPanel.className = "language-panel";
  pythonPanel.dataset.lang = "python";
  const pythonDeriveHead = new FakeElement("h2");
  pythonDeriveHead.textContent = "Python 完整推导";
  const pythonDerive = new FakeElement("p");
  pythonDerive.className = "python-derivation";
  pythonDerive.textContent = "Python 推导内容";
  const pythonCodeHead = new FakeElement("h2");
  pythonCodeHead.textContent = "Python 实现";
  const pythonCode = new FakeElement("pre");
  pythonCode.className = "python-code";
  pythonCode.textContent = "class Solution: ...";
  pythonPanel.appendChild(pythonDeriveHead);
  pythonPanel.appendChild(pythonDerive);
  pythonPanel.appendChild(pythonCodeHead);
  pythonPanel.appendChild(pythonCode);

  const legacyPanel = new FakeElement("section");
  legacyPanel.className = "legacy-solution-panel";
  const legacyHead = new FakeElement("h2");
  legacyHead.textContent = "通用思路";
  const legacyBody = new FakeElement("p");
  legacyBody.className = "legacy-derivation";
  legacyBody.textContent = "旧语言思路内容";
  legacyPanel.appendChild(legacyHead);
  legacyPanel.appendChild(legacyBody);

  const nav = new FakeElement("nav");
  nav.className = "problem-nav";
  const visual = new FakeElement("section");
  visual.className = "reader-visual";
  const visualBody = new FakeElement("div");
  visual.appendChild(visualBody);

  article.appendChild(pageTitle);
  article.appendChild(commonHeading);
  article.appendChild(statement);
  article.appendChild(pythonPanel);
  article.appendChild(legacyPanel);
  article.appendChild(nav);
  article.appendChild(visual);
  pageBody.appendChild(toggleButton);
  pageBody.appendChild(article);

  const selftestDocument = {
    body: pageBody,
    createElement: (tag) => new FakeElement(tag),
    createTextNode: (value) => ({ nodeType: 3, textContent: String(value), parentNode: null }),
    getElementById: (id) => id === "selftestToggle" ? toggleButton : null,
    querySelector: (selector) => pageBody.querySelector(selector),
    querySelectorAll: (selector) => pageBody.querySelectorAll(selector),
    addEventListener() {},
  };
  const selftestWindowListeners = {};
  const replacedUrls = [];
  const selftestWindow = {
    location: { search: "?selftest=1", pathname: "/problem.html", hash: "" },
    history: { replaceState(_state, _title, url) { replacedUrls.push(url); } },
    addEventListener(name, callback) { (selftestWindowListeners[name] ||= []).push(callback); },
  };
  const selftestStorage = new Map();
  const selftestContext = {
    window: selftestWindow,
    document: selftestDocument,
    localStorage: {
      getItem(key) { return selftestStorage.get(key) || null; },
      setItem(key, value) { selftestStorage.set(key, String(value)); },
      removeItem(key) { selftestStorage.delete(key); },
    },
    URLSearchParams,
    CustomEvent: CustomEventFake,
    Array,
    console,
  };
  vm.runInNewContext(match[1], selftestContext, { filename: "SELFTEST_JS" });

  assert.strictEqual(pageBody.classList.contains("selftest-active"), true);
  assert.deepStrictEqual(replacedUrls, ["/problem.html"]);
  assert.strictEqual(statement.closest(".selftest-block"), null, "public statement must stay visible");
  assert.strictEqual(nav.closest(".selftest-block"), null, "problem navigation must stay visible");
  assert(pythonDerive.closest(".selftest-block"), "Python derivation must be masked");
  assert(pythonCode.closest(".selftest-block"), "Python implementation must be masked");
  assert(legacyBody.closest(".selftest-block"), "legacy language-panel derivation must be masked");
  assert(visual.closest(".selftest-block"), "visualization must remain separately masked");

  const blocks = pageBody.querySelectorAll(".selftest-block");
  assert.strictEqual(blocks.length, 4, "three solution segments plus one visualization must be wrapped");
  const revealButtons = blocks.map((block) => block.querySelector(".selftest-reveal"));
  assert(revealButtons.filter(Boolean).length === blocks.length, "every hidden block needs a reveal button");
  assert(revealButtons.some((button) => button.closest(".language-panel") === pythonPanel),
    "Python reveal controls must remain inside the Python language scope");
  assert(revealButtons.some((button) => button.closest(".legacy-solution-panel") === legacyPanel),
    "legacy reveal controls must remain inside their language scope");

  // 模拟语言容器显隐：wrapper 与按钮仍在 panel 内，因此服务端渲染的
  // data-lang / data-hide-in-language 规则会随当前语言共同隐藏它们。
  pythonPanel.style.display = "none";
  legacyPanel.style.display = "none";
  assert(pythonDerive.closest(".language-panel").style.display === "none");
  assert(legacyBody.closest(".legacy-solution-panel").style.display === "none");

  const firstButton = revealButtons.find(Boolean);
  const firstBlock = firstButton.parentNode;
  const firstContent = firstBlock.querySelector(".selftest-content");
  assert.strictEqual(firstContent.hidden, true);
  firstButton.click();
  assert.strictEqual(firstContent.hidden, false);
  assert.strictEqual(firstBlock.querySelector(".selftest-reveal"), null);

  toggleButton.click();
  assert.strictEqual(pageBody.classList.contains("selftest-active"), false);
  assert.strictEqual(pageBody.querySelectorAll(".selftest-block").length, 0,
    "leaving selftest mode must fully unwrap language-panel content");
  assert.strictEqual(pythonDerive.parentNode, pythonPanel);
  assert.strictEqual(pythonCode.parentNode, pythonPanel);
  assert.strictEqual(legacyBody.parentNode, legacyPanel);
}
