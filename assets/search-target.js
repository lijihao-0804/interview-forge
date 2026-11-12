/* Search-result target: ?q=... opens the matching chapter, highlights the
 * keyword in the reader, and scrolls that occurrence to the center. */
(function () {
  'use strict';

  var query = '';
  try { query = (new URLSearchParams(location.search).get('q') || '').trim(); } catch (_) {}
  if (!query) return;

  var needle = query;
  var lowerNeedle = needle.toLowerCase();

  if (!document.getElementById('search-target-style')) {
    var style = document.createElement('style');
    style.id = 'search-target-style';
    style.textContent = '.search-target-hit{background:#ffe08a;color:inherit;border-radius:3px;padding:0 2px;box-decoration-break:clone;-webkit-box-decoration-break:clone}';
    document.head.appendChild(style);
  }

  function acceptNode(node) {
    if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
    var parent = node.parentElement;
    if (!parent) return NodeFilter.FILTER_REJECT;
    if (/^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA)$/i.test(parent.tagName)) return NodeFilter.FILTER_REJECT;
    if (parent.closest && parent.closest('.search-target-hit')) return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }

  function highlight(root) {
    if (!root) return null;
    if (root.getAttribute('data-search-targeted')) {
      return root.querySelector('.search-target-hit');
    }
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: acceptNode });
    var nodes = [];
    var node;
    while ((node = walker.nextNode())) nodes.push(node);
    var first = null;
    nodes.forEach(function (textNode) {
      var text = textNode.nodeValue;
      var lower = text.toLowerCase();
      var at = lower.indexOf(lowerNeedle);
      if (at < 0) return;
      var fragment = document.createDocumentFragment();
      var pos = 0;
      while (at >= 0) {
        if (at > pos) fragment.appendChild(document.createTextNode(text.slice(pos, at)));
        var mark = document.createElement('mark');
        mark.className = 'search-target-hit';
        mark.textContent = text.slice(at, at + needle.length);
        fragment.appendChild(mark);
        if (!first) first = mark;
        pos = at + needle.length;
        at = lower.indexOf(lowerNeedle, pos);
      }
      if (pos < text.length) fragment.appendChild(document.createTextNode(text.slice(pos)));
      textNode.parentNode.replaceChild(fragment, textNode);
    });
    root.setAttribute('data-search-targeted', '1');
    return first;
  }

  function locate() {
    var root = document.querySelector('.reader-body')
      || document.querySelector('.markdown-body')
      || document.querySelector('.reader');
    if (!root) return;
    var hit = highlight(root);
    if (!hit) return;
    // Search navigation intentionally wins over resume-last-position.
    window.__readingPosRestoreUntil = 0;
    setTimeout(function () {
      hit.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
    }, 0);
  }

  function schedule() {
    setTimeout(locate, 0);
    setTimeout(locate, 120);
    setTimeout(locate, 500);
    setTimeout(locate, 1200);
    setTimeout(locate, 2000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule);
  } else {
    schedule();
  }
  window.addEventListener('load', schedule);
})();
