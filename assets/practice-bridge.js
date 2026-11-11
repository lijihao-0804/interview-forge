(function () {
  'use strict';
  // Inject a "run code" button on question pages that expose practice metadata.
  // This intentionally does not read code from URL; the playground receives a
  // short id and obtains the context from sessionStorage on the same origin.
  if (!/^\/books\/ai-exam\//.test(location.pathname) || /\/acm-playground\.html$/.test(location.pathname)) return;

  var CONTEXT_KEY = 'interviewforge.practice.context';
  var CONTEXT_PREFIX = 'interviewforge.practice.context:';
  var META_URL = '/books/ai-exam/practice-meta.json';
  var metaPromise = null;

  function loadMeta() {
    if (!metaPromise) {
      metaPromise = fetch(META_URL, { credentials: 'same-origin', cache: 'no-store' })
        .then(function (response) { return response.ok ? response.json() : []; })
        .then(function (items) {
          var map = {};
          (Array.isArray(items) ? items : []).forEach(function (item) {
            if (item && item.url) map['/books/ai-exam/' + String(item.url).replace(/^\/+/, '')] = item;
          });
          return map;
        })
        .catch(function () { return {}; });
    }
    return metaPromise;
  }

  function addStyle() {
    if (document.getElementById('practice-bridge-style')) return;
    var style = document.createElement('style');
    style.id = 'practice-bridge-style';
    style.textContent = '.practice-run-btn{display:inline-flex;align-items:center;gap:5px;margin:4px 0 8px;padding:6px 11px;border:1px solid #5654d4;border-radius:8px;background:#5654d4;color:#fff;font:12.5px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;cursor:pointer}.practice-run-btn:hover{background:#4341b8}.practice-run-btn:disabled{opacity:.5;cursor:default}';
    document.head.appendChild(style);
  }

  function headingLanguage(pre) {
    var el = pre.parentElement;
    if (!el) return '';
    // Walk backwards over headings/paragraphs until the previous section.
    var cursor = el.previousElementSibling;
    var scanned = 0;
    while (cursor && scanned < 8) {
      var text = (cursor.textContent || '').trim().toLowerCase();
      if (cursor.tagName === 'H3') {
        if (text.indexOf('java') >= 0) return 'java';
        if (text.indexOf('python') >= 0) return 'python';
      }
      if (cursor.tagName === 'H2' && text.indexOf('代码') >= 0) break;
      cursor = cursor.previousElementSibling;
      scanned += 1;
    }
    var code = (pre.textContent || '').trim();
    if (/public\s+(?:final\s+)?class\b/.test(code) || /^\s*import\s+java\./m.test(code)) return 'java';
    if (/^\s*(def|class|import|from)\b/m.test(code)) return 'python';
    return '';
  }

  function addButtons() {
    addStyle();
    loadMeta().then(function (metaMap) {
      var pagePath = location.pathname;
      try { pagePath = decodeURIComponent(pagePath); } catch (_) {}
      var meta = metaMap[pagePath] || metaMap[location.pathname];
      if (!meta || !meta.codes) return;
      var blocks = document.querySelectorAll('div.codehilite > pre');
      Array.prototype.forEach.call(blocks, function (pre) {
        var language = headingLanguage(pre);
        if (!language || !meta.codes[language]) return;
        if (pre.parentElement && pre.parentElement.getAttribute('data-practice-ready')) return;
        if (!Array.isArray(meta.samples) || !meta.samples.length) return;
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'practice-run-btn';
        button.textContent = '▶ 运行代码';
        button.title = '在 ACM 模拟 IDE 中打开这道题';
        button.addEventListener('click', function () {
          var context = {
            id: meta.id || meta.url,
            title: meta.title || document.title,
            url: meta.url || location.pathname.replace('/books/ai-exam/', ''),
            language: language,
            codes: meta.codes,
            samples: meta.samples
          };
          try {
            localStorage.setItem(CONTEXT_PREFIX + context.id, JSON.stringify(context));
            sessionStorage.setItem(CONTEXT_KEY, JSON.stringify(context));
          } catch (_) {}
          var url = '/books/ai-exam/acm-playground.html?id=' + encodeURIComponent(context.id) + '&lang=' + encodeURIComponent(language);
          window.open(url, '_blank');
        });
        pre.parentElement.setAttribute('data-practice-ready', '1');
        pre.parentElement.parentNode.insertBefore(button, pre.parentElement);
      });
    });
  }

  var ready = window.requestIdleCallback || function (fn) { setTimeout(fn, 120); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { ready(addButtons); });
  else ready(addButtons);
})();
