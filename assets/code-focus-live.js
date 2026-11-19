(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const refreshInterval = 30000;
  const renderCode = window.CodeFocusDisplay.mountReader();
  let published = null;
  let etag = "";
  let timer;
  let nextCheck = 0;
  let retryDelay = refreshInterval;
  let inFlight = false;
  let suspended = false;

  function status(text) {
    if (get("sync-status").textContent !== text) get("sync-status").textContent = text;
  }

  function display(next) {
    if (!Number.isSafeInteger(next.version) || typeof next.code !== "string" ||
        typeof next.answers !== "string" || typeof next.language !== "string") {
      throw new Error("Invalid publication");
    }
    if (published && next.version <= published.version) return;
    if (!published || next.answers !== published.answers) {
      const total = window.CodeFocusDisplay.renderAnswers(next.answers);
      get("answer-strip").hidden = total === 0;
    }
    if (!published || next.code !== published.code || next.language !== published.language) {
      get("reader").hidden = !next.code;
      get("copy").disabled = !next.code;
      renderCode(next.code, next.language);
    }
    get("empty-publication").hidden = !!next.code || !get("answer-strip").hidden;
    published = next;
  }

  function schedule() {
    clearTimeout(timer);
    if (suspended || document.hidden || inFlight) return;
    if (!navigator.onLine) {
      status("当前离线，联网后会恢复同步。");
      return;
    }
    timer = setTimeout(refresh, Math.max(0, nextCheck - Date.now()));
  }

  async function refresh() {
    if (suspended || document.hidden || inFlight) return;
    inFlight = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch("/api/code-focus/publication", {
        cache: "no-store", credentials: "omit", signal: controller.signal,
        headers: etag ? { "If-None-Match": etag } : {},
      });
      if (response.status !== 304) {
        if (!response.ok) throw new Error("Publication unavailable");
        display(await response.json());
        etag = response.headers.get("ETag") || "";
      }
      status("已同步 · 每 30 秒检查更新");
      retryDelay = refreshInterval;
    } catch {
      status("暂时无法同步，稍后会自动重试。");
      retryDelay = Math.min(retryDelay * 2, 120000);
    } finally {
      clearTimeout(timeout);
      inFlight = false;
      nextCheck = Date.now() + retryDelay;
      schedule();
    }
  }

  get("copy").addEventListener("click", async () => {
    if (!published?.code) return;
    try {
      await navigator.clipboard.writeText(published.code);
      get("notice").textContent = "已复制全部代码";
    } catch {
      get("notice").textContent = "浏览器未允许复制，可选中下方代码手动复制。";
    }
  });
  window.addEventListener("pagehide", () => { suspended = true; clearTimeout(timer); });
  window.addEventListener("pageshow", () => { suspended = false; schedule(); });
  document.addEventListener("visibilitychange", schedule);
  window.addEventListener("online", schedule);
  window.addEventListener("offline", schedule);
  schedule();
})();
