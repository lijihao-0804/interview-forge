/*
 * 无头校验所有 DemoKit 演示页：把每个页面的内联脚本跑在 vm 沙箱里，
 * 用假的 DemoKit 截获 mount(cfg)，然后对每个 demo × 每个尺寸做结构体检。
 *
 * 校验项：
 *   1. build() 不抛异常，且至少产出若干步；
 *   2. 每一步都有 view，描述非空；
 *   3. step 里的 {line: n} 必须落在代码面板的行数范围内（多语言时取最小行数）；
 *   4. invariants 的 test() 对每一步都不抛异常；
 *   5. code.langs 的各语言行数必须完全一致（行号对齐协议）。
 *
 * 用法：node tests/test_hot100_demo_pages.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const VISUAL_DIR = path.join(__dirname, "..", "books", "hot100", "05-可视化");
const MIN_STEPS = 3;

function fakeElement(tag) {
  const node = {
    tagName: String(tag || "div").toUpperCase(),
    children: [],
    style: { setProperty() {}, removeProperty() {}, getPropertyValue: () => "" },
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    textContent: "",
    innerHTML: "",
    value: "",
    appendChild(child) { node.children.push(child); return child; },
    append(...kids) { kids.forEach((k) => node.children.push(k)); },
    removeChild(child) {
      const i = node.children.indexOf(child);
      if (i >= 0) node.children.splice(i, 1);
      return child;
    },
    insertBefore(child) { node.children.unshift(child); return child; },
    setAttribute() {}, getAttribute: () => null, removeAttribute() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    querySelector: () => fakeElement("div"),
    querySelectorAll: () => [],
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }),
    focus() {}, click() {}, remove() {}
  };
  // 页面脚本常写 node.parentNode.insertBefore(...)，给个惰性的假父节点，避免递归造节点。
  let parent = null;
  const lazyParent = () => (parent || (parent = fakeElement("div")));
  Object.defineProperty(node, "parentNode", { get: lazyParent });
  Object.defineProperty(node, "parentElement", { get: lazyParent });
  return node;
}

function makeSandbox(mounts, selects) {
  const store = Object.create(null);
  const doc = {
    createElement: (t) => {
      const n = fakeElement(t);
      if (String(t).toLowerCase() === "select" && selects) selects.push(n);
      return n;
    },
    createTextNode: () => fakeElement("#text"),
    querySelector: () => fakeElement("div"),
    querySelectorAll: () => [],
    getElementById: () => fakeElement("div"),
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
    body: fakeElement("body"),
    head: fakeElement("head"),
    documentElement: fakeElement("html")
  };
  const win = {
    document: doc,
    localStorage: {
      getItem: (k) => (k in store ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: (k) => { delete store[k]; }
    },
    addEventListener() {}, removeEventListener() {}, postMessage() {},
    matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
    requestAnimationFrame: (fn) => { void fn; return 0; },
    cancelAnimationFrame() {},
    setTimeout: () => 0,
    clearTimeout() {},
    CustomEvent: function CustomEvent(type, init) { this.type = type; this.detail = init && init.detail; },
    console,
    URLSearchParams,
    URL,
    location: { href: "http://localhost/", search: "", hash: "", origin: "http://localhost" },
    navigator: { userAgent: "node" },
    DemoKit: {
      el(tag, cls, text) {
        const n = fakeElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
      },
      mount(cfg) { mounts.push(cfg); }
    }
  };
  win.window = win;
  win.self = win;
  win.globalThis = win;
  win.parent = win;
  return win;
}

function inlineScripts(html) {
  const out = [];
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    if (/\bsrc\s*=/i.test(m[1])) continue;
    if (/type\s*=\s*"(?!text\/javascript)/i.test(m[1])) continue;
    out.push(m[2]);
  }
  return out;
}

function codeLineCount(code, problems, where) {
  if (!code) return null;
  if (Array.isArray(code)) return code.length;
  if (code.langs) {
    const names = Object.keys(code.langs);
    const counts = names.map((l) => code.langs[l].length);
    const min = Math.min(...counts);
    if (min !== Math.max(...counts)) {
      problems.push(
        `${where}: code.langs 行数不对齐 —— ` +
        names.map((l, i) => `${l}=${counts[i]}`).join(", ")
      );
    }
    return min;
  }
  return code.lines ? code.lines.length : null;
}

function collectSteps(cfg, size) {
  const steps = [];
  const ctx = {
    stage: fakeElement("div"),
    vars: fakeElement("div"),
    descBox: fakeElement("div"),
    step(desc, view, meta) {
      const m = meta || {};
      const line = m.line != null ? m.line : (view ? view.line : null);
      steps.push({ desc: desc, view: view, opts: { line: line } });
    },
    phase(type, desc, view, meta) {
      view = view || {};
      view.phase = type;
      ctx.step(desc, view, meta);
    },
    setVar() {}, clearVars() {}, log() {}, note() {}, reset() {}
  };
  cfg.build(ctx, size);
  return steps;
}

function treeDepth(node, guard) {
  if (!node || typeof node !== "object") return 0;
  if ((guard || 0) > 64) return 0;
  return 1 + Math.max(
    treeDepth(node.left, (guard || 0) + 1),
    treeDepth(node.right, (guard || 0) + 1)
  );
}

function lineNumbers(opts) {
  const l = opts && opts.line;
  if (l == null) return [];
  return Array.isArray(l) ? l : [l];
}

function checkDemo(file, cfg, problems) {
  const where = `${file} #${cfg.no || cfg.title || "?"}`;
  const maxLine = codeLineCount(cfg.code, problems, where);
  // 引擎把整个 size 对象（{label, value}）交给 build，这里保持一致。
  const sizes = (cfg.sizes && cfg.sizes.length ? cfg.sizes : [null]);

  sizes.forEach((size) => {
    const tag = size ? (size.label || size.value) : "默认";
    let steps;
    try {
      steps = collectSteps(cfg, size);
    } catch (e) {
      problems.push(`${where} [size=${tag}]: build 抛异常 —— ${e && e.message}`);
      return;
    }
    if (steps.length < MIN_STEPS) {
      problems.push(`${where} [size=${tag}]: 只有 ${steps.length} 步，少于 ${MIN_STEPS} 步`);
    }
    steps.forEach((s, i) => {
      if (!s.view || typeof s.view !== "object") {
        problems.push(`${where} [size=${tag}] 第 ${i + 1} 步缺少 view`);
      }
      if (!s.desc || !String(s.desc).trim()) {
        problems.push(`${where} [size=${tag}] 第 ${i + 1} 步描述为空`);
      }
      if (maxLine) {
        lineNumbers(s.opts).forEach((n) => {
          if (!(n >= 1 && n <= maxLine)) {
            problems.push(`${where} [size=${tag}] 第 ${i + 1} 步 line=${n} 超出代码面板 1..${maxLine}`);
          }
        });
      }
    });
    // 用户的验收标准：树类演示至少要能看出三层，两层的树讲不清结构。
    const deep = steps.some((s) => s.view && s.view.tree && treeDepth(s.view.tree) >= 3);
    if (steps.some((s) => s.view && s.view.tree) && !deep) {
      problems.push(`${where} [size=${tag}]: 树最深只有 ${
        Math.max(0, ...steps.map((s) => (s.view && s.view.tree ? treeDepth(s.view.tree) : 0)))
      } 层，至少要有 3 层`);
    }
    (cfg.invariants || []).forEach((inv, k) => {
      steps.forEach((s, i) => {
        try {
          inv.test(s.view);
        } catch (e) {
          problems.push(`${where} [size=${tag}] 不变量 #${k + 1} 在第 ${i + 1} 步抛异常 —— ${e && e.message}`);
        }
      });
    });
  });
}

function run() {
  const files = fs.readdirSync(VISUAL_DIR).filter((f) => f.endsWith(".html"));
  const problems = [];
  const report = [];

  files.forEach((f) => {
    const html = fs.readFileSync(path.join(VISUAL_DIR, f), "utf8");
    if (!/assets\/demo-kit\.js/.test(html)) return;

    const mounts = [];
    const selects = [];
    const sandbox = makeSandbox(mounts, selects);
    vm.createContext(sandbox);
    inlineScripts(html).forEach((src) => {
      try {
        vm.runInContext(src, sandbox, { timeout: 10000 });
      } catch (e) {
        problems.push(`${f}: 内联脚本执行失败 —— ${e && e.message}`);
      }
    });
    // 页面只挂载下拉框当前选中的那道题；把每个选项都切一遍，才能覆盖全部 demo。
    selects.forEach((sel) => {
      if (typeof sel.onchange !== "function") return;
      sel.children.forEach((opt) => {
        const v = opt.value;
        if (!v || v === sel.value) return;
        sel.value = v;
        try {
          sel.onchange();
        } catch (e) {
          problems.push(`${f}: 切到题目 "${v}" 时抛异常 —— ${e && e.message}`);
        }
      });
    });
    if (!mounts.length) {
      problems.push(`${f}: 引用了 demo-kit 却没有任何 DemoKit.mount 调用`);
      return;
    }
    // 切下拉框时初始那道题会被重新挂载一次，按题号去重。
    const seen = new Set();
    const unique = mounts.filter((cfg) => {
      const id = String(cfg.no || cfg.title);
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    unique.forEach((cfg) => checkDemo(f, cfg, problems));
    report.push(`${f}: ${unique.length} demo`);
  });

  report.forEach((line) => console.log("  " + line));
  if (problems.length) {
    console.error("\nFAIL (" + problems.length + "):");
    problems.forEach((p) => console.error("  - " + p));
    process.exit(1);
  }
  console.log("\nALL OK");
}

run();
