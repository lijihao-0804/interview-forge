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

  var state = { glossary: null, index: null, style: "underline", trigger: "hover", root: null };
  var pop = null;       // 单例浮层
  var activeEl = null;  // 当前打开的术语

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

  function collectTextNodes(root) {
    var out = [];
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (isSkipped(node)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = walker.nextNode())) out.push(n);
    return out;
  }

  function annotate() {
    if (!state.root || !state.index) return 0;
    var re = buildRegex(state.index);
    if (!re) return 0;
    var nodes = collectTextNodes(state.root);
    var count = 0;
    var seenFirst = {};   // 记录每个主词是否已出现过，供 inline 风格首现高亮
    nodes.forEach(function (node) {
      var text = node.nodeValue;
      re.lastIndex = 0;
      var m, last = 0, frag = null;
      while ((m = re.exec(text))) {
        if (!frag) frag = document.createDocumentFragment();
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var word = m[0];
        var entry = state.index[word] || {};
        var span = document.createElement("span");
        span.className = "glossary-term " + (STYLE_CLASS[state.style] || "gt-underline");
        span.textContent = word;
        span.setAttribute("data-gkey", word);
        span.setAttribute("role", "button");
        span.setAttribute("tabindex", "0");
        span.setAttribute("aria-label", word + "：查看术语解释");
        var mainTerm = entry.term || word;
        if (!seenFirst[mainTerm]) {
          seenFirst[mainTerm] = 1;
          span.setAttribute("data-first", "1");
        }
        frag.appendChild(span);
        last = m.index + word.length;
        count++;
      }
      if (frag) {
        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
      }
    });
    return count;
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

  function loadGlossary(url) {
    return fetch(url, { cache: "force-cache" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)); })
      .then(function (d) { state.glossary = d.entries || []; state.index = d.index || {}; return d; });
  }

  window.GlossaryEngine = {
    init: function (opts) {
      opts = opts || {};
      state.root = opts.root || document.querySelector(".reader-body") || document.body;
      state.style = opts.style || "underline";
      state.trigger = opts.trigger || "hover";
      ensurePop();
      var p = opts.glossary
        ? Promise.resolve().then(function () { state.glossary = opts.glossary.entries || []; state.index = opts.glossary.index || {}; })
        : loadGlossary(opts.glossaryUrl || "/assets/glossary.json");
      return p.then(function () {
        var n = annotate();
        bind();
        return { annotated: n, terms: (state.glossary || []).length };
      });
    }
  };
})();
