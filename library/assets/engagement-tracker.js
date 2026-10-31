/* 学习行为埋点：学习时长心跳 + 搜索关键词上报。
 *
 * 设计参考 GA4 的 engagement time：只在页面可见时计时，每 30 秒上报一次，
 * 页面隐藏/卸载时补报最后不足 30 秒的部分，避免「挂机刷时长」和丢数据。
 *
 * 页面类型自动识别：
 *   - 题解页：[data-problem-id]（.solution-progress 面板）
 *   - 书架章节页：内联注入的 window.contentId / window.moduleId
 */
(function () {
  "use strict";
  if (window.__ENGAGEMENT_TRACKER__) return;
  window.__ENGAGEMENT_TRACKER__ = true;

  var HEARTBEAT_MS = 30000;
  var MAX_SINGLE_SECONDS = 3600;

  function detectTarget() {
    var panel = document.querySelector("[data-problem-id]");
    if (panel) {
      var pid = panel.getAttribute("data-problem-id");
      if (pid) return { type: "problem", id: String(pid), module: null };
    }
    // 章节页用内联 `const contentId/moduleId` 注入，顶层 const 不会挂到 window 上，
    // 只能用 typeof 探测标识符本身。
    if (typeof contentId !== "undefined" && typeof moduleId !== "undefined") {
      return { type: "content", id: String(contentId), module: String(moduleId) };
    }
    var main = document.querySelector("main[data-content-id]");
    if (main) {
      return {
        type: "content",
        id: main.getAttribute("data-content-id"),
        module: main.getAttribute("data-module-id"),
      };
    }
    return null;
  }

  function post(path, body) {
    try {
      return fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        keepalive: true,
        credentials: "same-origin",
      }).catch(function () {});
    } catch (e) {
      return Promise.resolve();
    }
  }

  // ---------- 学习时长 ----------
  var target = detectTarget();
  var pendingSeconds = 0;
  var lastTick = 0;
  var timer = null;

  function accumulate() {
    if (!lastTick) { lastTick = Date.now(); return; }
    var now = Date.now();
    var delta = (now - lastTick) / 1000;
    lastTick = now;
    if (delta > 0 && delta < 300) pendingSeconds += delta; // 超过 5 分钟视为休眠，丢弃
  }

  function flush() {
    accumulate();
    var seconds = Math.round(pendingSeconds);
    if (!target || seconds < 1) { pendingSeconds = 0; return; }
    pendingSeconds = 0;
    post("/api/study/duration", {
      target_type: target.type,
      target_id: target.id,
      module_id: target.module,
      seconds: Math.min(seconds, MAX_SINGLE_SECONDS),
    });
  }

  function startTimer() {
    if (timer || !target) return;
    lastTick = Date.now();
    timer = setInterval(function () {
      if (document.visibilityState === "visible") flush();
    }, HEARTBEAT_MS);
  }

  function stopTimer() {
    if (timer) { clearInterval(timer); timer = null; }
    lastTick = 0;
  }

  if (target) {
    startTimer();
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") { flush(); stopTimer(); }
      else { startTimer(); }
    });
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);
  }

  // ---------- 搜索关键词 ----------
  var SEARCH_SELECTORS = ["#shelfSearch", "#searchInput", "#search"];
  var reportedKeyword = "";

  function reportKeyword(input, source) {
    var keyword = String(input.value || "").trim();
    if (keyword.length < 2) return;
    if (keyword === reportedKeyword) return;
    reportedKeyword = keyword;
    post("/api/search/events", { keyword: keyword, source: source });
  }

  function attachSearch(input, source) {
    if (!input || input.__engagementBound) return;
    input.__engagementBound = true;
    var timerId = null;
    input.addEventListener("input", function () {
      if (timerId) clearTimeout(timerId);
      timerId = setTimeout(function () { reportKeyword(input, source); }, 1500);
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        if (timerId) clearTimeout(timerId);
        reportKeyword(input, source);
      }
    });
    // 失焦时也算一次「确定的搜索」
    input.addEventListener("blur", function () { reportKeyword(input, source); });
  }

  function initSearch() {
    SEARCH_SELECTORS.forEach(function (selector) {
      var input = document.querySelector(selector);
      if (input) attachSearch(input, selector.replace("#", ""));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSearch);
  } else {
    initSearch();
  }
})();
