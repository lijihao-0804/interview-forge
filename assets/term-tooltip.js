/* 术语注释引擎（服务端词典驱动，用户不可增删）
 * ------------------------------------------------------------------
 * 用法：
 *   GlossaryEngine.init({
 *     root: document.querySelector('.reader-body'),
 *     glossaryUrl: '/assets/glossary.json',
 *     style: 'underline' | 'badge' | 'inline',   // 三种视觉风格
 *     trigger: 'hover' | 'click'                 // 触发方式
 *   })
 *
 * 设计要点：
 *  · 只标注正文纯文本节点，跳过 code / pre / a / 标题 / 已有标注
 *  · 长词优先匹配，避免 RAG 命中 RAGFlow 的子串
 *  · 英文词加词边界；中文按原样匹配
 *  · 浮层单例复用，定位到术语下方，自动避免越界
 */
(function () {
  "use strict";

  var STYLE_CLASS = { underline: "gt-underline", badge: "gt-badge", inline: "gt-inline" };
  var SKIP_TAGS = new Set(["CODE", "PRE", "A", "H1", "H2", "H3", "H4", "H5", "H6",
                           "SCRIPT", "STYLE", "TEXTAREA", "INPUT", "BUTTON", "SVG"]);

  var state = { glossary: null, index: null, style: "underline", trigger: "hover", root: null,
              scopeKey: "", density: "once", regex: null, annotateToken: 0 };   // density: once=一本书一次 | all=全部标注
  var pop = null;       // 单例浮层
  var activeEl = null;  // 当前打开的术语


  // ---- 已标注次数记录：让「一本书只标一次」跨章节生效 ----
  var SEEN_PREFIX = "glossarySeen:v1:";
  function seenKey() { return SEEN_PREFIX + (state.scopeKey || "global"); }
  function loadSeen() {
    try { return JSON.parse(localStorage.getItem(seenKey()) || "{}"); } catch (e) { return {}; }
  }
  function saveSeen(obj) {
    try { localStorage.setItem(seenKey(), JSON.stringify(obj)); } catch (e) {}
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function escapeReg(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  function buildRegex(index) {
    var keys = Object.keys(index).filter(Boolean).sort(function (a, b) { return b.length - a.length; });
    if (!keys.length) return null;
    var parts = keys.map(function (k) {
      var esc2 = escapeReg(k);
      // 纯英文/数字开头的词加词边界，避免词中命中
      if (/^[A-Za-z0-9]/.test(k)) return "\\b" + esc2 + "\\b";
      // 两个汉字的短词极易成为其他词的子串（如「字节流」里的「节流」），
      // 要求其前面不是汉字，宁可少标也不错标。
      if (/^[\u4e00-\u9fff]{2}$/.test(k)) return "(?<![\u4e00-\u9fff])" + esc2;
      return esc2;
    });
    return new RegExp("(" + parts.join("|") + ")", "g");
  }

  function isSkipped(node) {
    var el = node.parentElement;
    while (el) {
      if (SKIP_TAGS.has(el.tagName)) return true;
      if (el.classList && el.classList.contains("glossary-term")) return true;
      if (el === state.root) break;
      el = el.parentElement;
    }
    return false;
  }

  // 按 h2 小节分组收集文本节点：返回 [{node, section}]。
  // section 从 0 开始，每遇到一个 h2 递增，用于实现「一节最多标一次」。
  function collectTextNodes(root) {
    var out = [];
    var ctx = { section: 0 };
    function walk(el) {
      if (el.nodeType === 3) {
        if (el.nodeValue && el.nodeValue.trim() && !isSkipped(el)) {
          out.push({ node: el, section: ctx.section });
        }
        return;
      }
      if (el.nodeType !== 1) return;
      // 先判断标题：小节边界必须在「跳过标签」之前处理，
      // 否则 h3 会被 SKIP_TAGS 拦掉、section 永远停在 0。
      if (el.tagName === "H2" || el.tagName === "H3") { ctx.section++; return; }
      if (SKIP_TAGS.has(el.tagName)) return;                       // code/pre/a 等整体跳过
      if (el.classList && el.classList.contains("glossary-term")) return;
      var kids = el.childNodes;
      for (var i = 0; i < kids.length; i++) walk(kids[i]);
    }
    walk(root);
    return out;
  }

  // 处理一个文本节点切片；返回新增标注数量。
  function annotateSlice(items, start, end, re, seenFirst) {
    var count = 0;
    for (var i = start; i < end; i += 1) {
      var item = items[i];
      var node = item.node;
      if (!node || !node.parentNode) continue;
      var text = node.nodeValue;
      re.lastIndex = 0;
      var m, last = 0, frag = null;
      while ((m = re.exec(text))) {
        if (!frag) frag = document.createDocumentFragment();
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var word = m[0];
        var entry = state.index[word] || {};
        var mainTerm0 = entry.term || word;
        // 去重粒度：同一页面内，同一术语最多标注一次。
        // 这样单页不会满屏标记，且每次打开页面都能重新看到注释（不落盘）。
        // density=all 时不做去重（用户主动查看全部）。
        var secKey = mainTerm0;
        if (state.density !== "all" && seenFirst[secKey]) {
          frag.appendChild(document.createTextNode(word));
          last = m.index + word.length;
          continue;
        }
        seenFirst[secKey] = 1;
        var span = document.createElement("span");
        span.className = "glossary-term " + (STYLE_CLASS[state.style] || "gt-underline");
        span.textContent = word;
        span.setAttribute("data-gkey", word);
        span.setAttribute("role", "button");
        span.setAttribute("tabindex", "0");
        span.setAttribute("aria-label", word + "：查看术语解释");
        // 页内首次出现（去重后必然首次），供 inline 风格高亮
        span.setAttribute("data-first", "1");
        frag.appendChild(span);
        last = m.index + word.length;
        count++;
      }
      if (frag) {
        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
      }
    }
    return count;
  }

  // 首屏优先 + 分片：先同步处理前 120 个文本节点，其余在浏览器空闲时
  // 按时间预算继续；这样超长章节不会在 DOMContentLoaded 阶段形成长任务。
  function annotateProgressive() {
    if (!state.root || !state.index) return 0;
    var re = state.regex || (state.regex = buildRegex(state.index));
    if (!re) return 0;
    var token = ++state.annotateToken;
    var items = collectTextNodes(state.root);
    if (!items.length) return 0;
    var seenFirst = {};
    var firstEnd = Math.min(items.length, 120);
    var count = annotateSlice(items, 0, firstEnd, re, seenFirst);
    var index = firstEnd;
    var schedule = window.requestIdleCallback || function (callback) {
      return setTimeout(function () { callback({ timeRemaining: function () { return 8; } }); }, 1);
    };
    function run(deadline) {
      if (token !== state.annotateToken) return;
      var remaining = deadline && typeof deadline.timeRemaining === "function"
        ? deadline.timeRemaining() : 8;
      var chunkSize = remaining > 4 ? 120 : 40;
      var end = Math.min(items.length, index + chunkSize);
      count += annotateSlice(items, index, end, re, seenFirst);
      index = end;
      if (index < items.length) schedule(run, { timeout: 800 });
    }
    if (index < items.length) schedule(run, { timeout: 800 });
    return count;
  }

  function annotate() {
    return annotateProgressive();
  }

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div");
    pop.className = "glossary-pop";
    pop.setAttribute("role", "dialog");
    pop.hidden = true;
    document.body.appendChild(pop);
    // 点外部关闭
    document.addEventListener("click", function (e) {
      if (pop.hidden) return;
      if (pop.contains(e.target)) return;
      if (activeEl && activeEl.contains(e.target)) return;
      hidePop();
    }, true);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !pop.hidden) hidePop();
    });
    window.addEventListener("resize", function () { if (!pop.hidden && activeEl) positionPop(activeEl); });
    window.addEventListener("scroll", function () { if (!pop.hidden && activeEl) positionPop(activeEl); }, { passive: true });
    return pop;
  }

  function renderPop(key, el) {
    var entry = state.index[key];
    if (!entry) return;
    ensurePop();
    var abbrLine = entry.abbr ? '<span class="gp-abbr">' + esc(entry.abbr) + "</span>" : "";
    var catLine = entry.category ? '<span class="gp-cat">' + esc(entry.category) + "</span>" : "";
    pop.innerHTML =
      '<div class="gp-head"><strong class="gp-term">' + esc(entry.term) + "</strong>" +
        abbrLine + catLine + "</div>" +
      '<p class="gp-def">' + esc(entry.definition) + "</p>" +
      (entry.detail ? '<p class="gp-detail">' + esc(entry.detail) + "</p>" : "") +
      '<button type="button" class="gp-close" aria-label="关闭">×</button>';
    pop.querySelector(".gp-close").addEventListener("click", hidePop);
    pop.hidden = false;
    activeEl = el;
    el.classList.add("gt-active");
    positionPop(el);
  }

  function positionPop(el) {
    var r = el.getBoundingClientRect();
    var pw = pop.offsetWidth, ph = pop.offsetHeight;
    var margin = 8;
    var left = r.left + r.width / 2 - pw / 2;
    left = Math.max(margin, Math.min(left, window.innerWidth - pw - margin));
    var top = r.bottom + 8;
    var placement = "bottom";
    if (top + ph > window.innerHeight - margin) {
      top = r.top - ph - 8;
      placement = "top";
    }
    pop.style.left = Math.round(left) + "px";
    pop.style.top = Math.round(top) + "px";
    pop.setAttribute("data-placement", placement);
    // 箭头水平对齐术语中心
    var arrowX = Math.round(Math.min(Math.max(r.left + r.width / 2 - left, 14), pw - 14));
    pop.style.setProperty("--arrow-x", arrowX + "px");
  }

  function hidePop() {
    if (pop) pop.hidden = true;
    if (activeEl) { activeEl.classList.remove("gt-active"); activeEl = null; }
  }

  function bind() {
    var root = state.root;
    if (!root) return;
    if (state.trigger === "hover") {
      var hoverTimer = null;
      root.addEventListener("mouseover", function (e) {
        var t = e.target.closest && e.target.closest(".glossary-term");
        if (!t) return;
        clearTimeout(hoverTimer);
        hoverTimer = setTimeout(function () { renderPop(t.getAttribute("data-gkey"), t); }, 120);
      });
      root.addEventListener("mouseout", function (e) {
        var t = e.target.closest && e.target.closest(".glossary-term");
        if (!t) return;
        clearTimeout(hoverTimer);
        // 移入浮层时不关闭：给一点延迟，交由浮层自身的 mouseenter 取消
        hoverTimer = setTimeout(function () {
          if (pop && !pop.hidden && !pop.matches(":hover")) hidePop();
        }, 220);
      });
      if (pop) {
        pop.addEventListener("mouseenter", function () { clearTimeout(hoverTimer); });
        pop.addEventListener("mouseleave", function () { hidePop(); });
      }
    }
    // 点击始终可用（移动端 / 键盘）
    root.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest(".glossary-term");
      if (!t) return;
      if (activeEl === t && pop && !pop.hidden) { hidePop(); return; }
      renderPop(t.getAttribute("data-gkey"), t);
    });
    root.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var t = e.target.closest && e.target.closest(".glossary-term");
      if (!t) return;
      e.preventDefault();
      renderPop(t.getAttribute("data-gkey"), t);
    });
  }


  // ---- 密度切换控件：右下角小浮标 + 弹出面板 ----
  var ctl = null, ctlPanel = null;
  function mountControls() {
    if (ctl) return;
    ctl = document.createElement("div");
    ctl.className = "glossary-ctl";
    ctl.innerHTML = '<button type="button" class="gc-btn" aria-label="术语注释设置" title="术语注释设置">Aa</button>';
    ctlPanel = document.createElement("div");
    ctlPanel.className = "gc-panel";
    ctlPanel.hidden = true;
    ctl.appendChild(ctlPanel);
    document.body.appendChild(ctl);
    renderPanel();
    ctl.querySelector(".gc-btn").addEventListener("click", function (e) {
      e.stopPropagation();
      ctlPanel.hidden = !ctlPanel.hidden;
    });
    document.addEventListener("click", function (e) {
      if (ctl && !ctl.contains(e.target)) ctlPanel.hidden = true;
    });
  }
  function renderPanel() {
    if (!ctlPanel) return;
    var isAll = state.density === "all";
    ctlPanel.innerHTML =
      '<div class="gc-title">术语注释</div>' +
      '<button type="button" class="gc-opt' + (!isAll ? " on" : "") + '" data-d="once">' +
        '<b>每节一次（推荐）</b><span>每个小节里同一术语只标一次，最清爽</span></button>' +
      '<button type="button" class="gc-opt' + (isAll ? " on" : "") + '" data-d="all">' +
        '<b>全部显示</b><span>所有出现处都标注（含同一小节内重复）</span></button>' +
      '<button type="button" class="gc-reset">重新标注本页</button>';
    ctlPanel.querySelectorAll(".gc-opt").forEach(function (b) {
      b.addEventListener("click", function () {
        state.density = b.dataset.d;
        try { localStorage.setItem("glossaryDensity:v1", state.density); } catch (e) {}
        renderPanel();
        reannotate();
      });
    });
    var reset = ctlPanel.querySelector(".gc-reset");
    if (reset) reset.addEventListener("click", function () {
      reannotate();
    });
  }
  // 重新标注：还原原文后重建（依赖原始 HTML 备份）
  function reannotate() {
    if (window.__glossaryOriginalHTML && state.root) {
      state.root.innerHTML = window.__glossaryOriginalHTML;
    }
    var n = annotate();
    return n;
  }

  function loadGlossary(url) {
    return fetch(url, { cache: "force-cache" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (d) { state.glossary = d.entries || []; state.index = d.index || {}; state.regex = null; return d; });
  }

  window.GlossaryEngine = {
    init: function (opts) {
      opts = opts || {};
      state.root = opts.root || document.querySelector(".reader-body") || document.body;
      state.style = opts.style || "underline";
      state.trigger = opts.trigger || "hover";
      state.scopeKey = opts.scopeKey || "";
      // 密度偏好存本地：用户切到「全部显示」后，同一本书后续章节沿用
      var savedDensity = null;
      try { savedDensity = localStorage.getItem("glossaryDensity:v1"); } catch (e) {}
      state.density = opts.density || savedDensity || "once";
      if (opts.controls !== false) mountControls();
      ensurePop();
      var p = opts.glossary
        ? Promise.resolve().then(function () { state.glossary = opts.glossary.entries || []; state.index = opts.glossary.index || {}; })
        : loadGlossary(opts.glossaryUrl || "/assets/glossary.json");
      return p.then(function () {
        // 备份原始 HTML，切密度/重置时可无损还原
        window.__glossaryOriginalHTML = state.root ? state.root.innerHTML : "";
        var n = annotate();
        bind();
        return { annotated: n, terms: (state.glossary || []).length };
      });
    }
  };
})();
