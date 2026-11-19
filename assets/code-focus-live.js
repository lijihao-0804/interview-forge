(() => {
  "use strict";
  const get = id => document.getElementById(id);
  const renderCode = window.CodeFocusDisplay.mountReader();
  let published = null;
  let wantedVersion = 0;
  let events;
  let loading = false;
  let retry;
  let reconnect;
  let retryDelay = 2000;
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

  function visible() {
    return !suspended && !document.hidden && navigator.onLine;
  }

  function behind() {
    return !published || published.version < wantedVersion;
  }

  function showStatus() {
    if (!navigator.onLine) status("当前离线，联网后会恢复同步。");
    else if (behind()) status("正在读取发布内容…");
    else if (events?.readyState === EventSource.OPEN) status("已同步 · 等待下次发布");
    else status("正在连接发布通知…");
  }

  async function readLatest() {
    if (!visible() || loading || !behind()) return;
    clearTimeout(retry);
    loading = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    const requestedVersion = wantedVersion;
    try {
      const response = await fetch("/api/code-focus/publication", {
        cache: "no-store", credentials: "omit", signal: controller.signal,
      });
      if (!response.ok) throw new Error("Publication unavailable");
      display(await response.json());
      if (published.version < requestedVersion) throw new Error("Waiting for published version");
      retryDelay = 2000;
      showStatus();
    } catch {
      if (visible()) {
        status("暂时无法读取发布内容，正在重试。");
        retry = setTimeout(readLatest, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 60000);
      }
      return;
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
    // A second publish may have arrived during the fetch.
    if (behind()) readLatest();
  }

  function connect() {
    clearTimeout(reconnect);
    if (!visible()) {
      events?.close();
      events = null;
      clearTimeout(retry);
      if (!navigator.onLine) showStatus();
      return;
    }
    if (events) return;
    const stream = new EventSource("/api/code-focus/publication/events");
    events = stream;
    stream.addEventListener("open", showStatus);
    stream.addEventListener("publication", event => {
      if (events !== stream || !/^\d+$/.test(event.data)) return;
      const version = Number(event.data);
      if (!Number.isSafeInteger(version)) return;
      wantedVersion = Math.max(wantedVersion, version);
      if (behind()) readLatest();
      else showStatus();
    });
    stream.addEventListener("error", () => {
      if (events !== stream) return;
      status("发布通知连接中断，正在重新连接…");
      // Most disconnects reconnect natively. Some HTTP errors permanently close EventSource.
      if (stream.readyState === EventSource.CLOSED) {
        events = null;
        clearTimeout(reconnect);
        reconnect = setTimeout(connect, 15000);
      }
    });
    readLatest();
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
  window.addEventListener("pagehide", () => { suspended = true; connect(); });
  window.addEventListener("pageshow", () => { suspended = false; connect(); });
  document.addEventListener("visibilitychange", connect);
  window.addEventListener("online", connect);
  window.addEventListener("offline", connect);
  connect();
})();
