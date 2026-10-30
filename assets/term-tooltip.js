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
              scopeKey: "", density: "once" };   // density: once=一本书一次 | all=全部标注
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
    var seenFirst = {};   // 本章内是否已出现过，供 inline 风格首现高亮
    var seen = state.density === "all" ? null : loadSeen();   // 跨章节累计次数
    nodes.forEach(function (node) {
      var text = node.nodeValue;
      re.lastIndex = 0;
      var m, last = 0, frag = null;
      while ((m = re.exec(text))) {
        if (!frag) frag = document.createDocumentFragment();
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        var word = m[0];
        var entry = state.index[word] || {};
        var mainTerm0 = entry.term || word;
        // 章内去重：同一章里同一术语只标一次（保证单页不会满屏标记）
        if (seenFirst[mainTerm0]) {
          frag.appendChild(document.createTextNode(word));
          last = m.index + word.length;
          continue;
        }
        // 跨章额度：偏门词(multi)一本书内最多 3 章标注，普通词(once)只标第一次。
        if (seen) {
          var cap = entry.spread === "multi" ? 3 : 1;
          var used = seen[mainTerm0] || 0;
          if (used >= cap) {
            frag.appendChild(document.createTextNode(word));
            last = m.index + word.length;
            continue;
          }
          seen[mainTerm0] = used + 1;
        }
        seenFirst[mainTerm0] = 1;
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
    if (seen) saveSeen(seen);
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
        '<b>仅首次（推荐）</b><span>一本书里每个术语只标一次，最清爽</span></button>' +
      '<button type="button" class="gc-opt' + (isAll ? " on" : "") + '" data-d="all">' +
        '<b>每章都标</b><span>不受跨章节限制（同章内仍只标一次）</span></button>' +
      '<button type="button" class="gc-reset">重置本书已读标记</button>';
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
      try { localStorage.removeItem(seenKey()); } catch (e) {}
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
      .then(function (d) { state.glossary = d.entries || []; state.index = d.index || {}; return d; });
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
