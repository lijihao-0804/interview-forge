(function (global) {
  "use strict";

  function pageType(path) {
    if (/\/books\/hot100\/03-题解\//.test(path)) return "problem";
    if (/\/library\/hot200-extra\/chapter-\d+\.html$/.test(path)) return "problem";
    if (/\/library\/[^/]+\/chapter-\d+\.html$/.test(path)) return "library/chapter";
    if (/\/cockpit\.html$/.test(path)) return "cockpit";
    if (/\/pages\/history\.html$/.test(path)) return "history";
    if (/\/pages\/leetcode-connect\.html$/.test(path)) return "leetcode";
    if (/\/guide\.html$/.test(path)) return "guide";
    return "other";
  }

  function visibleHeading() {
    var best = null;
    var bestDistance = Infinity;
    Array.prototype.forEach.call(document.querySelectorAll("h1,h2,h3"), function (heading) {
      var rect = heading.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight * 0.82) return;
      var distance = Math.abs(rect.top - Math.min(window.innerHeight * 0.22, 180));
      if (distance < bestDistance) {
        best = heading.textContent || "";
        bestDistance = distance;
      }
    });
    return best ? best.replace(/\s+/g, " ").trim().slice(0, 300) : null;
  }

  function selectedText() {
    var selection = global.getSelection ? global.getSelection() : null;
    var value = selection ? String(selection.toString() || "") : "";
    value = value.replace(/\s+/g, " ").trim();
    if (!value) return null;
    return value.length <= 2000 ? value : value.slice(0, 990) + " […] " + value.slice(-990);
  }

  function problemId(path) {
    if (pageType(path) !== "problem") return null;
    if (/\/library\/hot200-extra\//.test(path)) {
      var item = document.querySelector("[data-content-id^='hot200-extra:']");
      var id = item && /^hot200-extra:(\d+)$/.exec(item.getAttribute("data-content-id"));
      return id ? Number(id[1]) : null;
    }
    var match = path.match(/\/([^/]+)\.html$/);
    var number = match && match[1].match(/^(\d{1,6})-/);
    return number ? Number(number[1]) : null;
  }

  function getPageContext() {
    var path = global.location.pathname || "/";
    try { path = decodeURI(path); } catch (_) {}
    var root = document.querySelector("[data-content-id]");
    var practice = path === "/books/ai-exam/acm-playground.html";
    var exercise = practice && document.getElementById("problem-context");
    var nativeId = exercise && !exercise.hidden && /^hot(?:100|200)-([1-9]\d{0,5})$/.exec(
      new URLSearchParams(global.location.search).get("id") || ""
    );
    var context = {
      path: path,
      title: String(document.title || path).slice(0, 200),
      page_type: nativeId ? "problem" : pageType(path),
      problem_id: nativeId ? Number(nativeId[1]) : problemId(path),
      content_id: root ? root.getAttribute("data-content-id") : null,
      heading: nativeId ? exercise.textContent.trim().slice(0, 300) : visibleHeading(),
      // Source code and runner output are shared only through the explicit editor attachment.
      selected_text: practice ? null : selectedText()
    };
    Object.keys(context).forEach(function (key) {
      if (context[key] == null || context[key] === "") delete context[key];
    });
    return context;
  }

  global.InterviewForgeAI = global.InterviewForgeAI || {};
  global.InterviewForgeAI.getPageContext = getPageContext;
}(window));
