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
 * ctx 提供：step(desc, view)、setVar(k, v)、log(text)。
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
.dk-stage{min-height:190px;padding:18px;border:1px solid var(--dk-line);border-radius:var(--dk-radius);
background:var(--dk-panel);overflow-x:auto}
.dk-desc{margin:12px 2px 6px;padding:10px 14px;border-radius:10px;background:var(--dk-brand-soft);
color:var(--dk-brand-strong);font-weight:600;min-height:42px;display:flex;align-items:center}
.dk-vars{display:flex;gap:8px;flex-wrap:wrap;margin:0 2px 12px}
.dk-var{font-size:12.5px;padding:3px 10px;border-radius:8px;background:var(--dk-soft);
border:1px solid var(--dk-line);color:var(--dk-muted)}
.dk-var b{color:var(--dk-text);font-weight:700}
.dk-bar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:14px 0 6px}
.dk-btn{border:1px solid var(--dk-line);background:var(--dk-panel);color:var(--dk-text);border-radius:9px;
padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}
.dk-btn:hover{border-color:var(--dk-brand);color:var(--dk-brand)}
.dk-btn.primary{background:var(--dk-brand);border-color:var(--dk-brand);color:#fff}
.dk-btn.primary:hover{background:var(--dk-brand-strong)}
.dk-btn:disabled{opacity:.45;cursor:not-allowed}
.dk-progress{font-size:13px;color:var(--dk-muted);font-variant-numeric:tabular-nums}
.dk-speed{display:flex;gap:4px}
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
font-variant-numeric:tabular-nums;position:relative;transition:all .25s}
.dk-cell .idx{position:absolute;top:-20px;left:50%;transform:translateX(-50%);
font-size:11px;color:var(--dk-muted);font-weight:400}
.dk-cell.hot{border-color:var(--dk-brand);background:var(--dk-brand-soft);color:var(--dk-brand-strong);
transform:translateY(-3px);box-shadow:0 6px 14px rgba(86,84,212,.25)}
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
.dk-ptr{position:absolute;top:-38px;left:50%;transform:translateX(-50%);font-size:12px;font-weight:700;
color:var(--dk-brand);white-space:nowrap}
.dk-ptr::after{content:"▼";display:block;text-align:center;font-size:10px;color:var(--dk-brand)}
.dk-ptr.up::after{content:"▲";transform:rotate(180deg)}
.dk-note{font-size:12px;color:var(--dk-muted);margin-top:6px}
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

  function mount(cfg) {
    var wrap = document.getElementById("app") || document.body;
    wrap.textContent = "";
    wrap.classList.add("dk-wrap");

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
    wrap.appendChild(stage);

    var vars = el("div", "dk-vars");
    wrap.appendChild(vars);

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
      bar.appendChild(resetBtn);
    }
    wrap.appendChild(bar);

    var log = el("div", "dk-log");
    wrap.appendChild(log);

    var steps = [];
    var ctx = {
      stage: stage, vars: vars, descBox: desc,
      step: function (d, view) { steps.push({ desc: d, view: view }); },
      setVar: function (k, v) {
        var n = vars.querySelector("[data-k='" + k + "']");
        if (!n) { n = el("span", "dk-var"); n.dataset.k = k; vars.appendChild(n); }
        n.innerHTML = ""; n.appendChild(el("b", null, k + ": ")); n.appendChild(document.createTextNode(String(v)));
      },
      clearVars: function () { vars.textContent = ""; },
      log: function (s) { log.textContent = s; }
    };

    var idx = 0, timer = null, playing = false;

    function interval() { return speeds[speedIdx][0] * 900; }
    function show(i) {
      idx = Math.max(0, Math.min(steps.length - 1, i));
      window.__dk = { steps: steps, idx: idx, progressEl: progress, stageEl: stage };
      var s = steps[idx];
      if (s.desc) desc.textContent = (idx + 1) + ". " + s.desc;
      else desc.textContent = "";
      stage.textContent = "";
      if (s.view) {
        try { cfg.render(s.view, stage, ctx); }
        catch (err) {
          console.error("render error:", err);
          stage.textContent = "渲染出错：" + (err && err.message ? err.message : err);
        }
      }
      progress.textContent = steps.length ? (idx + 1) + " / " + steps.length : "0 / 0";
      btnPrev.disabled = btnFirst.disabled = idx === 0;
      btnNext.disabled = btnLast.disabled = idx === steps.length - 1;
    }
    function rebuild() {
      steps = [];
      stage.textContent = ""; desc.textContent = ""; vars.textContent = ""; log.textContent = "";
      ctx.reset && ctx.reset();
      try {
        cfg.build(ctx, sizeSel ? cfg.sizes[sizeSel.value] : null);
      } catch (err) {
        desc.textContent = "演示构建出错：" + (err && err.message ? err.message : err);
        desc.style.color = "var(--dk-err)";
        console.error("demo build error:", err);
        progress.textContent = "0 / 0";
        return;
      }
      idx = 0; playing = false;
      btnPlay.textContent = "▶ 自动播放";
      show(0);
    }
    function playTick() {
      if (idx >= steps.length - 1) { stop(); return; }
      show(idx + 1);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } playing = false; btnPlay.textContent = "▶ 自动播放"; }

    btnPlay.onclick = function () {
      if (playing) { stop(); return; }
      if (idx >= steps.length - 1) show(0);
      playing = true; btnPlay.textContent = "⏸ 暂停";
      timer = setInterval(playTick, interval());
      playTick();
    };
    btnNext.onclick = function () { stop(); show(idx + 1); };
    btnPrev.onclick = function () { stop(); show(idx - 1); };
    btnFirst.onclick = function () { stop(); show(0); };
    btnLast.onclick = function () { stop(); show(steps.length - 1); };
    if (sizeSel) sizeSel.onchange = rebuild;
    document.addEventListener("keydown", function (e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "ArrowRight") { stop(); show(idx + 1); }
      if (e.key === "ArrowLeft") { stop(); show(idx - 1); }
      if (e.key === " ") { e.preventDefault(); btnPlay.click(); }
    });

    rebuild();
  }

  global.DemoKit = { mount: mount, el: el };
})(window);
