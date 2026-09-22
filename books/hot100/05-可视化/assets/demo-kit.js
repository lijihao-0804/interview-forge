/* InterviewForge 演示统一框架（demo-kit）
 * 所有 Hot 100 动画演示共用：统一外壳/控制条/步骤播放器/视图原语。
 * 设计令牌与站点一致（品牌 #5654d4，亮暗自动），无任何外部依赖。
 * 用法：
 *   DemoKit.mount({
 *     no: "94", title: "二叉树的中序遍历", tag: "二叉树 · 递归",
 *     example: "输入：root = [1,null,2,3]　输出：[1,3,2]",
 *     sizes: [{label:"示例 1", value:"..."}, ...],   // 可选：阶数/规模选择
 *     build: (ctx) => {                              // ctx.step(desc, view)
 *       ...算法模拟，ctx.step("访问节点 1", { tree:{...}, stack:[...] })
 *     },
 *     render(view, stage, ctx)                       // 把一帧画到舞台
 *   });
 * ctx 提供：step(desc, view, meta)、phase(type, desc, view, meta)、setVar(k, v)、log(text)。
 *
 * ── 可选增强（全部向后兼容，不配置就是原来的行为）───────────────────────
 * 1) 真动画（FLIP）：render 产出的元素带 data-key="稳定标识" 即可。
 *    框架在每帧重绘前后测量同 key 元素的位置差，用 First-Last-Invert-Play
 *    让它真正滑动；新增的 key 淡入，消失的 key 留下淡出残影，内容/状态变化
 *    的 key 会脉冲一下。没有 data-key 的页面完全不受影响。
 *      stage.innerHTML = arr.map((v,i) => `<div class="dk-cell" data-key="n${v}">${v}</div>`).join("");
 *
 * 2) 代码行同步：cfg.code = ["int l = 0;", "while (l < r) {", ...]
 *    配合 ctx.step(desc, view, { line: 2 })（1 基，可传数组）高亮对应行。
 *    也可以写在 view.line 上。
 *
 * 3) 不变量条：cfg.invariants = [{ label: "栈内高度严格递减", test: (view) => ... }]
 *    test 返回 true/false 显示 ✓/✗；返回字符串则作为补充说明展示。
 *    这是把"看流程"升级成"懂为什么"的关键层。
 *
 * 4) 反例对照：cfg.compare = { label: "错误写法：不判 last[ch] >= left",
 *                              build(ctx), render(view, stage, ctx) }
 *    勾选后并排跑正确版与错误版，同步步进，让错误当场崩出来。
 */
(function (global) {
  "use strict";
  var CSS = `
:root{--dk-bg:#f4f6fb;--dk-panel:#ffffff;--dk-soft:#f6f7fb;--dk-text:#1b2434;--dk-muted:#68758c;
--dk-line:#dfe4ee;--dk-brand:#5654d4;--dk-brand-strong:#4543bd;--dk-brand-soft:#eeedff;
--dk-ok:#157a52;--dk-warn:#a85b00;--dk-err:#b3372f;--dk-code-bg:#151a24;--dk-radius:14px}
@media(prefers-color-scheme:dark){:root{--dk-bg:#0f131b;--dk-panel:#181e29;--dk-soft:#141a24;--dk-text:#eaf0fa;
--dk-muted:#9aa6ba;--dk-line:#313b4c;--dk-brand:#b1afff;--dk-brand-strong:#c4c2ff;--dk-brand-soft:#292955;
--dk-ok:#79d8a8;--dk-warn:#ffc174;--dk-err:#ff969d;--dk-code-bg:#10151f}}
*{box-sizing:border-box;margin:0;padding:0}
.dk-wrap{font:15px/1.7 "Inter","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,sans-serif;
color:var(--dk-text);background:var(--dk-bg);padding:18px 18px 26px;min-height:100%}
.dk-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.dk-no{font:800 22px/1 var(--dk-sans,"Inter",sans-serif);color:var(--dk-brand)}
.dk-head h1{font-size:19px;font-weight:750}
.dk-tag{font-size:12px;color:var(--dk-muted);background:var(--dk-soft);border:1px solid var(--dk-line);
border-radius:999px;padding:2px 10px}
.dk-example{margin:10px 0 14px;padding:9px 13px;border-left:3px solid var(--dk-brand);
background:var(--dk-soft);border-radius:0 9px 9px 0;font-size:13px;color:var(--dk-muted);white-space:pre-wrap}
.dk-stage{position:relative;height:var(--dk-stage-height,320px);min-height:220px;padding:18px;
border:1px solid var(--dk-line);border-radius:var(--dk-radius);background:var(--dk-panel);overflow:auto}
.dk-desc{margin:12px 2px 6px;padding:10px 14px;border-radius:10px;background:var(--dk-brand-soft);
color:var(--dk-brand-strong);font-weight:600;height:68px;min-height:68px;display:flex;align-items:flex-start;overflow:auto}
.dk-vars{display:flex;gap:8px;flex-wrap:nowrap;margin:0 2px 12px;height:40px;min-height:40px;overflow-x:auto;overflow-y:hidden}
.dk-var{font-size:12.5px;padding:3px 10px;border-radius:8px;background:var(--dk-soft);
border:1px solid var(--dk-line);color:var(--dk-muted)}
.dk-var b{color:var(--dk-text);font-weight:700}
.dk-bar{display:flex;align-items:center;gap:9px;flex-wrap:nowrap;min-height:42px;margin:14px 0 6px;overflow-x:auto;white-space:nowrap}
.dk-btn{border:1px solid var(--dk-line);background:var(--dk-panel);color:var(--dk-text);border-radius:9px;
padding:7px 14px;min-height:38px;flex:0 0 auto;font:inherit;font-weight:600;cursor:pointer;white-space:nowrap}
.dk-btn.primary{min-width:104px}
.dk-btn:hover{border-color:var(--dk-brand);color:var(--dk-brand)}
.dk-btn.primary{background:var(--dk-brand);border-color:var(--dk-brand);color:#fff}
.dk-btn.primary:hover{background:var(--dk-brand-strong)}
.dk-btn:disabled{opacity:.45;cursor:not-allowed}
.dk-progress{font-size:13px;color:var(--dk-muted);font-variant-numeric:tabular-nums;flex:0 0 auto}
.dk-speed{display:flex;gap:4px;flex:0 0 auto}
.dk-speed button{border:1px solid var(--dk-line);background:var(--dk-panel);color:var(--dk-muted);
border-radius:7px;padding:4px 9px;font-size:12px;cursor:pointer}
.dk-speed button.on{background:var(--dk-brand-soft);color:var(--dk-brand);border-color:var(--dk-brand);font-weight:700}
.dk-select{padding:6px 10px;border:1px solid var(--dk-line);border-radius:9px;font:inherit;
background:var(--dk-panel);color:var(--dk-text)}
.dk-log{margin-top:10px;padding:10px 13px;border:1px dashed var(--dk-line);border-radius:10px;
color:var(--dk-muted);font-size:13px;min-height:38px;white-space:pre-wrap}
/* ---- 视图原语通用元素 ---- */
.dk-cells{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.dk-cell{min-width:44px;padding:9px 7px;text-align:center;border:1.5px solid var(--dk-line);
border-radius:9px;background:var(--dk-panel);font:650 15px var(--dk-sans,"Inter",sans-serif);
font-variant-numeric:tabular-nums;position:relative;transition:background-color .25s,border-color .25s,color .25s}
.dk-cell .idx{position:absolute;top:-20px;left:50%;transform:translateX(-50%);
font-size:11px;color:var(--dk-muted);font-weight:400}
.dk-cell.hot{border-color:var(--dk-brand);background:var(--dk-brand-soft);color:var(--dk-brand-strong);
box-shadow:0 6px 14px rgba(86,84,212,.25)}
.dk-cell.done{background:var(--dk-soft);color:var(--dk-muted)}
.dk-cell.target{border-color:var(--dk-ok);background:color-mix(in srgb,var(--dk-ok) 14%,var(--dk-panel));color:var(--dk-ok)}
.dk-cell.cmp{border-color:var(--dk-warn);background:color-mix(in srgb,var(--dk-warn) 16%,var(--dk-panel));color:var(--dk-warn)}
.dk-cell.swap{border-color:var(--dk-err);background:color-mix(in srgb,var(--dk-err) 12%,var(--dk-panel));color:var(--dk-err)}
.dk-cell.write{border-color:var(--dk-ok);background:color-mix(in srgb,var(--dk-ok) 10%,var(--dk-panel));color:var(--dk-ok)}
.dk-cell.dim{opacity:.35}
.dk-ptr{position:absolute;top:-38px;left:50%;transform:translateX(-50%);font-size:12px;font-weight:700;
white-space:nowrap;color:var(--dk-brand)}
.dk-ptr::after{content:"▼";display:block;text-align:center;font-size:10px}
.dk-ptr.c1{color:#2563eb}.dk-ptr.c2{color:#d97706}.dk-ptr.c3{color:#0f766e}.dk-ptr.c4{color:#b3372f}
.dk-ptr.c2::after,.dk-ptr.c4::after{color:inherit}
.dk-arrow{align-self:center;color:var(--dk-muted);font-size:14px;padding:0 1px}
.dk-ptr.up::after{content:"▲";transform:rotate(180deg)}
.dk-note{font-size:12px;color:var(--dk-muted);margin-top:6px}
.dk-phase{display:inline-flex;align-items:center;gap:6px;margin:0 0 8px;padding:4px 9px;border:1px solid var(--dk-line);
border-radius:999px;color:var(--dk-brand-strong);background:var(--dk-brand-soft);font-size:12px;font-weight:700}
.dk-phase::before{content:"教学阶段";opacity:.68;font-weight:500}
.dk-stage.phase-compare{border-color:var(--dk-warn)}
.dk-stage.phase-swap_prepare{border-color:var(--dk-warn)}
.dk-stage.phase-swap_move{border-color:var(--dk-brand)}
.dk-stage.phase-swap_done,.dk-stage.phase-done{border-color:var(--dk-ok)}
.dk-stage.is-animating{box-shadow:0 0 0 3px color-mix(in srgb,var(--dk-brand) 18%,transparent)}
/* ---- FLIP 真动画 ---- */
.dk-flip{will-change:transform}
.dk-exit-layer{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:5}
.dk-exit{position:absolute;opacity:1;animation:dk-exit-fade .34s ease forwards}
@keyframes dk-exit-fade{to{opacity:0;transform:translateY(8px) scale(.9)}}
.dk-enter{animation:dk-enter-pop .32s cubic-bezier(.2,.9,.3,1.2) both}
@keyframes dk-enter-pop{from{opacity:0;transform:scale(.72)}to{opacity:1;transform:none}}
.dk-pulse{animation:dk-pulse-flash .42s ease}
@keyframes dk-pulse-flash{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--dk-brand) 55%,transparent)}
100%{box-shadow:0 0 0 9px transparent}}
/* ---- 主区：舞台 + 代码窗格 ---- */
.dk-main{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;align-items:stretch}
.dk-main.has-code{grid-template-columns:minmax(0,1fr) minmax(210px,var(--dk-code-width,32%))}
.dk-main.is-compare{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.dk-main.is-compare.has-code{grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(210px,28%)}
@media(max-width:820px){.dk-main,.dk-main.has-code,.dk-main.is-compare,
.dk-main.is-compare.has-code{grid-template-columns:minmax(0,1fr)}}
.dk-pane{display:flex;flex-direction:column;min-width:0}
.dk-pane-title{display:flex;align-items:center;gap:6px;margin-bottom:5px;font-size:12.5px;font-weight:700;color:var(--dk-muted)}
.dk-pane-title .dot{width:8px;height:8px;border-radius:50%;background:var(--dk-ok)}
.dk-pane.is-wrong .dk-pane-title{color:var(--dk-err)}
.dk-pane.is-wrong .dk-pane-title .dot{background:var(--dk-err)}
.dk-pane.is-wrong .dk-stage{border-color:color-mix(in srgb,var(--dk-err) 48%,var(--dk-line))}
.dk-subdesc{margin-top:7px;padding:7px 11px;border-radius:9px;background:var(--dk-soft);
border:1px solid var(--dk-line);color:var(--dk-muted);font-size:12.5px;min-height:34px}
.dk-pane.is-wrong .dk-subdesc{color:var(--dk-err);background:color-mix(in srgb,var(--dk-err) 8%,var(--dk-panel));
border-color:color-mix(in srgb,var(--dk-err) 34%,var(--dk-line))}
/* ---- 代码窗格 ---- */
.dk-code{height:var(--dk-stage-height,320px);min-height:220px;padding:12px 0;overflow:auto;
border:1px solid var(--dk-line);border-radius:var(--dk-radius);background:var(--dk-code-bg);
font:13px/1.65 "JetBrains Mono","Cascadia Code",Consolas,monospace;color:#c9d4e8}
.dk-code-line{display:flex;gap:10px;padding:1px 12px 1px 8px;white-space:pre;border-left:3px solid transparent;
transition:background-color .2s,border-color .2s}
.dk-code-line .n{flex:0 0 auto;width:20px;text-align:right;color:#5b6880;user-select:none}
.dk-code-line.on{background:rgba(177,175,255,.16);border-left-color:var(--dk-brand);color:#fff}
.dk-code-line.on .n{color:var(--dk-brand)}
/* ---- 代码窗格的语言切换 ---- */
.dk-langs{display:flex;gap:3px;margin-left:auto;flex-wrap:wrap}
.dk-lang{border:1px solid var(--dk-line);background:var(--dk-panel);color:var(--dk-muted);border-radius:6px;
padding:1px 7px;font:600 11px/1.6 inherit;cursor:pointer}
.dk-lang:hover{border-color:var(--dk-brand);color:var(--dk-brand)}
.dk-lang.on{background:var(--dk-brand-soft);border-color:var(--dk-brand);color:var(--dk-brand-strong)}
/* ---- 不变量条 ---- */
.dk-invs{display:flex;gap:7px;flex-wrap:wrap;margin:0 2px 10px}
.dk-inv{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;
font-size:12.5px;font-weight:600;border:1px solid var(--dk-line);background:var(--dk-soft);color:var(--dk-muted)}
.dk-inv .mark{font-weight:800}
.dk-inv.ok{color:var(--dk-ok);border-color:color-mix(in srgb,var(--dk-ok) 42%,var(--dk-line));
background:color-mix(in srgb,var(--dk-ok) 11%,var(--dk-panel))}
.dk-inv.bad{color:var(--dk-err);border-color:color-mix(in srgb,var(--dk-err) 48%,var(--dk-line));
background:color-mix(in srgb,var(--dk-err) 11%,var(--dk-panel))}
.dk-inv .why{font-weight:400;opacity:.85}
/* ---- 对照开关 ---- */
.dk-toggle{display:inline-flex;align-items:center;gap:7px;padding:5px 11px;border:1px solid var(--dk-line);
border-radius:9px;background:var(--dk-panel);color:var(--dk-text);font-size:13px;font-weight:600;cursor:pointer}
.dk-toggle input{accent-color:var(--dk-brand);cursor:pointer}
@media(prefers-reduced-motion:reduce){.dk-flip,.dk-enter,.dk-pulse,.dk-exit{animation:none!important;
transition:none!important;transform:none!important}}
`;

  // 注入统一样式（一次）
  if (!document.getElementById("demo-kit-css")) {
    var style = document.createElement("style");
    style.id = "demo-kit-css";
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // 环境探测：测试替身与老浏览器缺少这些 API 时，增强层整体降级为原行为。
  function canMeasure(node) {
    return !!node && typeof node.querySelectorAll === "function" &&
      typeof node.getBoundingClientRect === "function";
  }
  var reducedMotion = (function () {
    try { return !!(global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches); }
    catch (e) { return false; }
  })();
  function raf(fn) {
    if (typeof global.requestAnimationFrame === "function") global.requestAnimationFrame(fn);
    else fn();
  }

  var MAX_CLONE = 200;   // 超过这个数量就不留淡出残影，避免大网格每帧克隆过多节点
  var FLIP_MS = 360;
  var FX_CLASSES = ["dk-enter", "dk-flip", "dk-pulse"];

  /* 比较状态时必须剔除框架自己加的动画类，否则上一帧的 dk-enter
     会被当成"元素状态变了"，导致下一帧整排元素无谓地闪一下。 */
  function baseClass(node) {
    var name = " " + String(node.className || "") + " ";
    FX_CLASSES.forEach(function (c) { name = name.split(" " + c + " ").join(" "); });
    return name.replace(/\s+/g, " ").trim();
  }

  /* 重绘前：记录每个 data-key 元素相对舞台内容原点的位置、状态与内容签名。 */
  function snapshot(stage) {
    if (!canMeasure(stage)) return null;
    var base;
    try { base = stage.getBoundingClientRect(); } catch (e) { return null; }
    var nodes = stage.querySelectorAll("[data-key]");
    var map = Object.create(null);
    var clone = nodes.length <= MAX_CLONE;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i], r = n.getBoundingClientRect();
      map[n.getAttribute("data-key")] = {
        x: r.left - base.left - (stage.clientLeft || 0) + (stage.scrollLeft || 0),
        y: r.top - base.top - (stage.clientTop || 0) + (stage.scrollTop || 0),
        w: r.width, h: r.height,
        cls: baseClass(n),
        sig: n.innerHTML,
        ghost: clone ? n.cloneNode(true) : null
      };
    }
    return map;
  }

  /* 重绘后：同 key 反向位移再放行（FLIP），新 key 淡入，旧 key 留残影淡出。 */
  function animate(stage, before) {
    if (reducedMotion || !before || !canMeasure(stage)) return;
    var base;
    try { base = stage.getBoundingClientRect(); } catch (e) { return; }
    var nodes = stage.querySelectorAll("[data-key]");
    var moves = [], flashed = [], seen = Object.create(null), i, n, key, old, r, dx, dy;
    for (i = 0; i < nodes.length; i++) {
      n = nodes[i];
      key = n.getAttribute("data-key");
      seen[key] = true;
      old = before[key];
      if (!old) { n.classList.add("dk-enter"); flashed.push(n); continue; }
      r = n.getBoundingClientRect();
      dx = old.x - (r.left - base.left - (stage.clientLeft || 0) + (stage.scrollLeft || 0));
      dy = old.y - (r.top - base.top - (stage.clientTop || 0) + (stage.scrollTop || 0));
      if (Math.abs(dx) > 0.5 || Math.abs(dy) > 0.5) moves.push([n, dx, dy]);
      else if (old.cls !== baseClass(n) || old.sig !== n.innerHTML) { n.classList.add("dk-pulse"); flashed.push(n); }
    }
    if (flashed.length) {
      setTimeout(function () {
        flashed.forEach(function (node) {
          if (node.classList) node.classList.remove("dk-enter", "dk-pulse");
        });
      }, 460);
    }

    // 离场残影：原地淡出，让"被弹栈/被删除"这件事可见。
    var exits = [];
    for (key in before) { if (!seen[key] && before[key].ghost) exits.push(before[key]); }
    if (exits.length) {
      var layer = el("div", "dk-exit-layer");
      exits.forEach(function (o) {
        if (o.ghost.classList) o.ghost.classList.remove.apply(o.ghost.classList, FX_CLASSES);
        var box = el("div", "dk-exit");
        box.style.left = o.x + "px";
        box.style.top = o.y + "px";
        box.style.width = o.w + "px";
        box.style.height = o.h + "px";
        box.appendChild(o.ghost);
        layer.appendChild(box);
      });
      stage.appendChild(layer);
      setTimeout(function () { if (layer.parentNode) layer.parentNode.removeChild(layer); }, FLIP_MS + 60);
    }

    if (!moves.length) return;
    moves.forEach(function (m) {
      m[0].style.transition = "none";
      m[0].style.transform = "translate(" + m[1] + "px," + m[2] + "px)";
    });
    void stage.offsetWidth;                                  // 强制回流，锁定 Invert 状态
    stage.classList.add("is-animating");
    raf(function () {
      moves.forEach(function (m) {
        m[0].classList.add("dk-flip");
        m[0].style.transition = "transform " + FLIP_MS + "ms cubic-bezier(.34,.9,.3,1)";
        m[0].style.transform = "";
      });
      setTimeout(function () {
        stage.classList.remove("is-animating");
        moves.forEach(function (m) {
          m[0].classList.remove("dk-flip");
          m[0].style.transition = "";
          m[0].style.willChange = "";
        });
      }, FLIP_MS + 40);
    });
  }

  /* 把一帧画进舞台：测量 → 清空 → 交给页面的 render → 补动画。 */
  function paint(stage, view, renderFn, ctx) {
    var before = snapshot(stage);
    stage.textContent = "";
    if (view && renderFn) {
      try { renderFn(view, stage, ctx); }
      catch (err) {
        console.error("render error:", err);
        stage.textContent = "渲染出错：" + (err && err.message ? err.message : err);
        return;
      }
    }
    animate(stage, before);
  }

  /* ---- 多语言代码窗格 ----
     cfg.code 可以是 { title, langs: { java: [...], python: [...] } }。
     各语言的行数组必须逐行对齐：ctx.step 的 { line: n } 是同一个编号，
     换语言只换文字，不换行号，高亮协议因此完全不用动。 */
  var LANG_NAMES = { java: "Java", cpp: "C++", python: "Python", go: "Go", c: "C" };
  var LANG_ORDER = ["java", "cpp", "python", "go", "c"];
  function readLang() {
    try {
      var v = global.localStorage && global.localStorage.getItem("forge-lang");
      return v || "java";
    } catch (e) { return "java"; }
  }
  function writeLang(lang) {
    try { global.localStorage && global.localStorage.setItem("forge-lang", lang); } catch (e) {}
  }

  function normalizeCode(code) {
    if (!code) return null;
    if (!Array.isArray(code) && code.langs) {
      var langs = {}, order = [], seen = {};
      LANG_ORDER.concat(Object.keys(code.langs)).forEach(function (l) {
        if (seen[l]) return;
        seen[l] = 1;
        var v = code.langs[l];
        if (v && v.length) { langs[l] = v; order.push(l); }
      });
      if (!order.length) return null;
      return { title: code.title || "对应代码", langs: langs, order: order };
    }
    var lines = Array.isArray(code) ? code : code.lines;
    if (!lines || !lines.length) return null;
    return { title: (Array.isArray(code) ? "" : code.title) || "对应代码", lines: lines };
  }

  /* 语言切换是全局的：监听器只注册一次，永远打给当前挂载的那个实例。 */
  var activeLangSink = null;
  function broadcastLang(lang) {
    writeLang(lang);
    try { document.dispatchEvent(new CustomEvent("forge-lang-change", { detail: { lang: lang } })); } catch (e) {}
    try {
      if (global.parent && global.parent !== global) global.parent.postMessage({ type: "forge-lang", lang: lang }, "*");
    } catch (e) {}
  }
  (function bindLangListeners() {
    function accept(lang) { if (lang && activeLangSink) activeLangSink(lang); }
    try {
      // 同源 iframe 与父页共享 localStorage，storage 事件是主通道（父页改语言时触发）；
      // message 与 forge-lang-change 作为跨文档 / 同页兜底。
      global.addEventListener("storage", function (e) {
        if (!e || e.key === null || e.key === "forge-lang") accept(readLang());
      });
      global.addEventListener("message", function (e) {
        if (e && e.data && e.data.type === "forge-lang") accept(e.data.lang);
      });
      document.addEventListener("forge-lang-change", function (e) {
        if (e && e.detail) accept(e.detail.lang);
      });
    } catch (e) {}
  })();

  function mount(cfg) {
    var wrap = document.getElementById("app") || document.body;
    wrap.textContent = "";
    wrap.classList.add("dk-wrap");

    var code = normalizeCode(cfg.code);
    var compare = cfg.compare && typeof cfg.compare.build === "function" ? cfg.compare : null;
    var invariants = (cfg.invariants || []).filter(function (x) { return x && typeof x.test === "function"; });

    var head = el("div", "dk-head");
    if (cfg.no) head.appendChild(el("span", "dk-no", cfg.no));
    head.appendChild(el("h1", null, cfg.title));
    if (cfg.tag) head.appendChild(el("span", "dk-tag", cfg.tag));
    wrap.appendChild(head);

    if (cfg.example) {
      var ex = el("div", "dk-example");
      ex.textContent = cfg.example;
      wrap.appendChild(ex);
    }

    var sizeSel = null;
    if (cfg.sizes && cfg.sizes.length > 1) {
      var srow = el("div", "dk-bar");
      srow.appendChild(el("span", "dk-var", "规模选择"));
      sizeSel = el("select", "dk-select");
      cfg.sizes.forEach(function (s, i) {
        var o = el("option", null, s.label);
        o.value = i;
        if (i === (cfg.defaultSize || 0)) o.selected = true;
        sizeSel.appendChild(o);
      });
      srow.appendChild(sizeSel);
      wrap.appendChild(srow);
    }

    var stage = el("div", "dk-stage");
    var stageHeight = Number(cfg.stageHeight);
    if (Number.isFinite(stageHeight) && stageHeight >= 220) {
      stage.style.setProperty("--dk-stage-height", Math.round(stageHeight) + "px");
    }

    // 只有用到代码窗格或反例对照时才引入 .dk-main 栅格；
    // 否则舞台仍是 #app 的直接子节点，老页面的布局与测试保持不变。
    var main = null, stageB = null, descB = null, codeLines = [], compareOn = false, cmpToggle = null;
    var codeBox = null, langBar = null, curLang = null;

    function paintCode() {
      if (!codeBox) return;
      var lines = (code.langs ? code.langs[curLang] : code.lines) || [];
      codeBox.textContent = "";
      codeLines.length = 0;
      lines.forEach(function (text, i) {
        var line = el("div", "dk-code-line");
        line.appendChild(el("span", "n", String(i + 1)));
        line.appendChild(el("span", "t", text));
        codeBox.appendChild(line);
        codeLines.push(line);
      });
      if (langBar && langBar.children) {
        [].forEach.call(langBar.children, function (b) {
          if (b.classList) b.classList.toggle("on", b.getAttribute("data-lang") === curLang);
        });
      }
    }
    // persist=true 表示这次切换由本页发起，要写回偏好并通知父页面；
    // 来自外部广播的切换只改自己，避免两端互相回弹。
    function applyLang(lang, persist) {
      if (!code || !code.langs || !code.langs[lang] || lang === curLang) return;
      curLang = lang;
      paintCode();
      if (typeof measureStage === "function") measureStage();
      if (steps && steps.length) highlightCode(steps[idx] ? steps[idx].line : null);
      if (persist) broadcastLang(lang);
    }
    activeLangSink = function (lang) { applyLang(lang, false); };

    if (code || compare) {
      main = el("div", "dk-main");
      if (code) main.classList.add("has-code");

      var paneA = el("div", "dk-pane"), titleA = null;
      if (compare) {
        // 只有并排看反例时「正确写法」这个标题才有对照意义；单独看主线时它是多余的。
        titleA = el("div", "dk-pane-title");
        titleA.appendChild(el("span", "dot"));
        titleA.appendChild(el("span", null, cfg.compareRightLabel || "正确写法"));
        titleA.style.display = "none";
        paneA.appendChild(titleA);
      }
      paneA.appendChild(stage);
      main.appendChild(paneA);

      if (compare) {
        var paneB = el("div", "dk-pane is-wrong");
        var titleB = el("div", "dk-pane-title");
        titleB.appendChild(el("span", "dot"));
        titleB.appendChild(el("span", null, compare.label || "常见错误写法"));
        paneB.appendChild(titleB);
        stageB = el("div", "dk-stage");
        if (Number.isFinite(stageHeight) && stageHeight >= 220) {
          stageB.style.setProperty("--dk-stage-height", Math.round(stageHeight) + "px");
        }
        paneB.appendChild(stageB);
        descB = el("div", "dk-subdesc");
        paneB.appendChild(descB);
        paneB.style.display = "none";
        main.appendChild(paneB);
        main.__paneB = paneB;
        main.__titleA = titleA;
      }

      if (code) {
        var paneC = el("div", "dk-pane");
        var titleC = el("div", "dk-pane-title", code.title);
        paneC.appendChild(titleC);
        codeBox = el("div", "dk-code");
        if (Number.isFinite(stageHeight) && stageHeight >= 220) {
          codeBox.style.setProperty("--dk-stage-height", Math.round(stageHeight) + "px");
        }

        if (code.langs) {
          curLang = code.langs[readLang()] ? readLang() : (code.langs.java ? "java" : code.order[0]);
          if (code.order.length > 1) {
            langBar = el("div", "dk-langs");
            code.order.forEach(function (l) {
              var b = el("button", "dk-lang", LANG_NAMES[l] || l);
              b.type = "button";
              b.setAttribute("data-lang", l);
              b.onclick = function () { applyLang(l, true); };
              langBar.appendChild(b);
            });
            titleC.appendChild(langBar);
          }
        }
        paintCode();
        paneC.appendChild(codeBox);
        main.appendChild(paneC);
      }
      wrap.appendChild(main);
    } else {
      wrap.appendChild(stage);
    }

    var vars = el("div", "dk-vars");
    wrap.appendChild(vars);

    var invBar = null, invChips = [];
    if (invariants.length) {
      invBar = el("div", "dk-invs");
      invariants.forEach(function (inv) {
        var chip = el("span", "dk-inv");
        var mark = el("span", "mark", "·");
        var label = el("span", null, inv.label || "不变量");
        var why = el("span", "why");
        chip.appendChild(mark);
        chip.appendChild(label);
        chip.appendChild(why);
        invBar.appendChild(chip);
        invChips.push({ chip: chip, mark: mark, why: why });
      });
      wrap.appendChild(invBar);
    }

    var desc = el("div", "dk-desc");
    wrap.appendChild(desc);

    var bar = el("div", "dk-bar");
    var btnFirst = el("button", "dk-btn", "⏮ 开头");
    var btnPrev = el("button", "dk-btn", "◀ 上一步");
    var btnPlay = el("button", "dk-btn primary", "▶ 自动播放");
    var btnNext = el("button", "dk-btn", "下一步 ▶");
    var btnLast = el("button", "dk-btn", "末尾 ⏭");
    var progress = el("span", "dk-progress", "0 / 0");
    var speed = el("div", "dk-speed");
    var speeds = [[2, "0.5×"], [1, "1×"], [0.5, "2×"], [0.25, "4×"]];
    var speedIdx = 1;
    speeds.forEach(function (s, i) {
      var b = el("button", i === speedIdx ? "on" : null, s[1]);
      b.onclick = function () {
        speedIdx = i;
        [].forEach.call(speed.children, function (c) { c.classList.remove("on"); });
        b.classList.add("on");
      };
      speed.appendChild(b);
    });
    [btnFirst, btnPrev, btnPlay, btnNext, btnLast].forEach(function (b) { bar.appendChild(b); });
    bar.appendChild(el("span", "dk-progress", "　"));
    bar.appendChild(progress);
    bar.appendChild(el("span", null, "　"));
    bar.appendChild(speed);
    if (cfg.sizes && cfg.sizes.length > 1) {
      var resetBtn = el("button", "dk-btn", "↻ 重置");
      resetBtn.onclick = rebuild;
      bar.appendChild(resetBtn);
    }
    if (compare) {
      cmpToggle = el("label", "dk-toggle");
      var cbox = document.createElement("input");
      cbox.type = "checkbox";
      cmpToggle.appendChild(cbox);
      cmpToggle.appendChild(el("span", null, "并排看反例"));
      cbox.onchange = function () {
        compareOn = !!cbox.checked;
        if (main) {
          if (compareOn) main.classList.add("is-compare");
          else main.classList.remove("is-compare");
          if (main.__paneB) main.__paneB.style.display = compareOn ? "" : "none";
          if (main.__titleA) main.__titleA.style.display = compareOn ? "" : "none";
        }
        measureStage();
        show(idx);
        window.dispatchEvent(new CustomEvent("hot100:demo-rebuilt"));
      };
      bar.appendChild(cmpToggle);
    }
    wrap.appendChild(bar);

    var log = el("div", "dk-log");
    wrap.appendChild(log);

    var steps = [];
    var ctx = {
      stage: stage, vars: vars, descBox: desc,
      step: function (d, view, meta) {
        var m = meta || {};
        if (view && view.phase && !m.phase) m = Object.assign({}, m, { phase: view.phase });
        steps.push({
          desc: d, view: view, phase: m.phase || "update",
          duration: Number(m.duration || 0), pause: Number(m.pause || 0),
          line: m.line != null ? m.line : (view ? view.line : null)
        });
      },
      phase: function (type, d, view, meta) {
        view = view || {};
        view.phase = type;
        ctx.step(d, view, Object.assign({}, meta || {}, { phase: type }));
      },
      setVar: function (k, v) {
        var n = vars.querySelector ? vars.querySelector("[data-k='" + k + "']") : null;
        if (!n) { n = el("span", "dk-var"); n.dataset.k = k; vars.appendChild(n); }
        n.innerHTML = ""; n.appendChild(el("b", null, k + ": ")); n.appendChild(document.createTextNode(String(v)));
      },
      clearVars: function () { vars.textContent = ""; },
      log: function (s) { log.textContent = s; }
    };

    // 反例分支用同一套 step 协议，但不共享变量条/日志，避免两条时间线互相污染。
    var cmpSteps = [];
    var cmpCtx = {
      stage: stageB, vars: null, descBox: descB,
      step: function (d, view, meta) {
        var m = meta || {};
        cmpSteps.push({ desc: d, view: view, phase: m.phase || "update" });
      },
      phase: function (type, d, view, meta) {
        view = view || {};
        view.phase = type;
        cmpCtx.step(d, view, Object.assign({}, meta || {}, { phase: type }));
      },
      setVar: function () {}, clearVars: function () {}, log: function () {}
    };

    var idx = 0, timer = null, playing = false;

    function interval() {
      var current = steps[idx] || {};
      return Math.max(speeds[speedIdx][0] * 900, Number(current.duration || 0)) + Number(current.pause || 0);
    }
    function scheduleNext() {
      if (!playing || timer) return;
      timer = setTimeout(function () {
        timer = null;
        playTick();
        if (playing) scheduleNext();
      }, interval());
    }
    function reschedule() {
      if (!playing) return;
      if (timer) { clearTimeout(timer); timer = null; }
      scheduleNext();
    }
    function highlightCode(line) {
      if (!codeLines.length) return;
      var want = line == null ? [] : (Array.isArray(line) ? line : [line]);
      codeLines.forEach(function (node, i) {
        if (want.indexOf(i + 1) >= 0) node.classList.add("on");
        else node.classList.remove("on");
      });
    }
    function updateInvariants(view) {
      if (!invChips.length) return;
      invariants.forEach(function (inv, i) {
        var slot = invChips[i], result;
        try { result = view ? inv.test(view, ctx) : null; }
        catch (err) { result = null; }
        slot.chip.className = "dk-inv";
        if (result === true) { slot.chip.classList.add("ok"); slot.mark.textContent = "✓"; slot.why.textContent = ""; }
        else if (result === false) { slot.chip.classList.add("bad"); slot.mark.textContent = "✗"; slot.why.textContent = ""; }
        else if (typeof result === "string" && result) {
          slot.chip.classList.add("ok"); slot.mark.textContent = "✓"; slot.why.textContent = "· " + result;
        } else { slot.mark.textContent = "·"; slot.why.textContent = ""; }
      });
    }
    function show(i) {
      idx = Math.max(0, Math.min(steps.length - 1, i));
      window.__dk = { steps: steps, idx: idx, progressEl: progress, stageEl: stage };
      var s = steps[idx];
      if (!s) { progress.textContent = "0 / 0"; return; }
      var phase = String(s.phase || "update").replace(/[^a-zA-Z0-9_-]/g, "-");
      stage.dataset.phase = phase;
      stage.className = "dk-stage phase-" + phase;
      if (s.desc) desc.textContent = (idx + 1) + ". " + s.desc;
      else desc.textContent = "";
      paint(stage, s.view, cfg.render, ctx);
      highlightCode(s.line);
      updateInvariants(s.view);
      if (compareOn && stageB && cmpSteps.length) {
        var cs = cmpSteps[Math.min(idx, cmpSteps.length - 1)];
        stageB.className = "dk-stage phase-" + String(cs.phase || "update").replace(/[^a-zA-Z0-9_-]/g, "-");
        paint(stageB, cs.view, compare.render || cfg.render, cmpCtx);
        if (descB) descB.textContent = cs.desc || "";
      }
      progress.textContent = steps.length ? (idx + 1) + " / " + steps.length : "0 / 0";
      btnPrev.disabled = btnFirst.disabled = idx === 0;
      btnNext.disabled = btnLast.disabled = idx === steps.length - 1;
    }
    function rebuild() {
      stop();
      steps = [];
      cmpSteps = [];
      stage.textContent = ""; desc.textContent = ""; vars.textContent = ""; log.textContent = "";
      if (stageB) stageB.textContent = "";
      if (descB) descB.textContent = "";
      ctx.reset && ctx.reset();
      var size = sizeSel ? cfg.sizes[sizeSel.value] : null;
      try {
        cfg.build(ctx, size);
      } catch (err) {
        desc.textContent = "演示构建出错：" + (err && err.message ? err.message : err);
        desc.style.color = "var(--dk-err)";
        console.error("demo build error:", err);
        progress.textContent = "0 / 0";
        return;
      }
      if (compare) {
        try { compare.build(cmpCtx, size); }
        catch (err) {
          cmpSteps = [];
          console.error("compare build error:", err);
        }
      }
      idx = 0;
      btnPlay.textContent = "▶ 自动播放";
      measureStage();
      show(0);
      window.dispatchEvent(new CustomEvent("hot100:demo-rebuilt"));
    }

    /* ---- 舞台高度自适应 ----
       固定高度是为了让按钮不随播放上下跳，但常数是手估的，短演示下面就空一大片。
       改成：构建完成后把每一帧都量一遍，取最高的那一帧作为整轮的高度。
       播放期间高度依旧一动不动，而空白只剩最高帧真正需要的那点。
       cfg.stageHeight 从"固定值"变成"上限"，超过就让舞台自己滚。 */
    function naturalHeight(node, view, renderFn) {
      if (!node || typeof node.scrollHeight !== "number") return 0;
      var prevH = node.style.height, prevOv = node.style.overflow, prevVis = node.style.visibility;
      node.style.height = "auto";
      node.style.overflow = "hidden";
      node.style.visibility = "hidden";
      var h = 0;
      try {
        if (renderFn) { node.textContent = ""; renderFn(view, node, ctx); }
        h = node.scrollHeight || 0;
      } catch (e) { h = 0; }
      node.style.height = prevH;
      node.style.overflow = prevOv;
      node.style.visibility = prevVis;
      return h;
    }
    function measureStage() {
      if (!canMeasure(stage) || typeof stage.scrollHeight !== "number" || !steps.length) return;
      var ceiling = (Number.isFinite(stageHeight) && stageHeight >= 220) ? Math.round(stageHeight) : 560;
      // 步数很多时抽样，避免每次重建都做几十次布局。
      var span = Math.max(1, Math.ceil(steps.length / 60));
      var max = 0, i, h;
      for (i = 0; i < steps.length; i += span) {
        h = naturalHeight(stage, steps[i].view, cfg.render);
        if (h > max) max = h;
      }
      h = naturalHeight(stage, steps[steps.length - 1].view, cfg.render);
      if (h > max) max = h;
      if (compareOn && stageB && cmpSteps.length) {
        for (i = 0; i < cmpSteps.length; i++) {
          h = naturalHeight(stageB, cmpSteps[i].view, compare.render || cfg.render);
          if (h > max) max = h;
        }
      }
      if (codeBox && typeof codeBox.scrollHeight === "number") {
        h = naturalHeight(codeBox, null, null);
        if (h > max) max = h;
      }
      if (!max) return;
      var px = Math.min(ceiling, Math.max(220, Math.ceil(max) + 2));
      stage.style.setProperty("--dk-stage-height", px + "px");
      if (stageB) stageB.style.setProperty("--dk-stage-height", px + "px");
      if (codeBox) codeBox.style.setProperty("--dk-stage-height", px + "px");
    }

    function playTick() {
      if (idx >= steps.length - 1) { stop(); return; }
      show(idx + 1);
      if (idx >= steps.length - 1) stop();
    }
    function stop() { if (timer) { clearTimeout(timer); timer = null; } playing = false; btnPlay.textContent = "▶ 自动播放"; }

    btnPlay.onclick = function () {
      if (playing) { stop(); return; }
      if (idx >= steps.length - 1) show(0);
      playing = true; btnPlay.textContent = "⏸ 暂停";
      playTick();
      scheduleNext();
    };
    btnNext.onclick = function () { stop(); show(idx + 1); };
    btnPrev.onclick = function () { stop(); show(idx - 1); };
    btnFirst.onclick = function () { stop(); show(0); };
    btnLast.onclick = function () { stop(); show(steps.length - 1); };
    [].forEach.call(speed.children, function (b) {
      b.addEventListener("click", reschedule);
    });
    if (sizeSel) sizeSel.onchange = rebuild;
    document.addEventListener("keydown", function (e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "ArrowRight") { stop(); show(idx + 1); }
      if (e.key === "ArrowLeft") { stop(); show(idx - 1); }
      if (e.key === " ") { e.preventDefault(); btnPlay.click(); }
    });

    rebuild();
    window.addEventListener("pagehide", stop);
  }

  global.DemoKit = {
    mount: mount,
    el: el,
    // 生成带动画身份的元素：同一 key 在相邻两帧之间会被 FLIP 连起来。
    keyed: function (tag, key, cls, text) {
      var n = el(tag, cls, text);
      n.setAttribute("data-key", String(key));
      return n;
    },
    phases: ["compare", "swap_prepare", "swap_move", "swap_done", "pointer_move", "visit", "enqueue", "dequeue", "recursive_enter", "recursive_return", "save_next", "update", "done"]
  };
})(window);
