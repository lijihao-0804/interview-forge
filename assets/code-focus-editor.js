(() => {
  "use strict";

  const get = id => document.getElementById(id);
  const code = get("source-code");
  const language = get("language");
  const answers = get("answer-input");
  const status = get("save-status");
  const publish = get("publish");
  const retry = get("retry");
  const conflict = get("conflict");
  const draftKey = "hot100.codeFocus.publisher.draft.v1";
  const languageOptions = Array.from(language.options);
  let published = null;
  let baseVersion = 0;
  let fieldSource = null;
  let activity = "loading";
  let errorMessage = "";
  let storageFailed = false;
  let composing = false;

  function fieldValue(field, previous) {
    // Textareas display CRLF as LF. Keep the original line endings in untouched fields.
    if (previous?.includes("\r") && field.value === previous.replace(/\r\n?/g, "\n")) return previous;
    return field.value;
  }

  function draft() {
    return {
      version: baseVersion,
      code: fieldValue(code, fieldSource?.code),
      language: language.value,
      answers: fieldValue(answers, fieldSource?.answers),
    };
  }

  function valid(data) {
    return data && Number.isSafeInteger(data.version) && data.version >= 0 &&
      typeof data.code === "string" && typeof data.answers === "string" &&
      languageOptions.some(option => option.value === data.language);
  }

  function sameContent(a, b) {
    return a.code === b.code && a.language === b.language && a.answers === b.answers;
  }

  function storedDraft() {
    try {
      const data = JSON.parse(sessionStorage.getItem(draftKey));
      return valid(data) ? data : null;
    } catch {
      return null;
    }
  }

  function remember() {
    if (!published) return;
    const current = draft();
    try {
      // Even reverting to the old content is a new edit while a publish is in flight.
      if (activity || baseVersion !== published.version || !sameContent(current, published)) {
        sessionStorage.setItem(draftKey, JSON.stringify(current));
      } else {
        sessionStorage.removeItem(draftKey);
      }
      storageFailed = false;
    } catch {
      storageFailed = true;
    }
  }

  function loadFields(content) {
    fieldSource = content;
    baseVersion = content.version;
    code.value = content.code;
    language.value = content.language;
    answers.value = content.answers;
    for (const field of [code, language, answers]) field.disabled = false;
    window.CodeFocusDisplay.renderAnswers(answers.value);
  }

  function render() {
    const differs = published && !sameContent(draft(), published);
    const needsReview = published && baseVersion !== published.version;
    publish.disabled = Boolean(!differs || composing || needsReview || activity);
    retry.hidden = activity !== "load-failed";
    conflict.hidden = !needsReview;
    let message = errorMessage;
    if (activity === "loading") message = "正在读取已发布内容…";
    else if (activity === "publishing") message = "正在发布点击时的内容…";
    else if (!message && needsReview) message = "线上已有新版本。请核对内容后选择要保留的版本。";
    else if (!message && differs) message = storageFailed ? "有未发布的修改。浏览器无法保留草稿，离开前请备份。" : "有未发布的修改";
    else if (!message && published) message = published.version ? `已发布 · 版本 ${published.version}` : "尚未发布内容";
    if (status.textContent !== message) status.textContent = message;
    status.toggleAttribute("data-attention", Boolean(errorMessage || needsReview || (differs && storageFailed)));
  }

  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(url, {
        credentials: "same-origin", cache: "no-store", ...options, signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error();
        error.status = response.status;
        throw error;
      }
      const data = await response.json();
      if (!valid(data)) throw new Error("Invalid publication");
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  function reason(error) {
    if (error.status === 401 || error.status === 403) return "请在另一标签页登录管理员账号后重试。";
    if (error.status === 413) return "内容过大，发布请求限 1 MiB。请缩短后再次点击发布。";
    if (error.status) return `服务器返回 ${error.status}，请重试。`;
    return "请检查网络连接后重试。";
  }

  async function load() {
    activity = "loading";
    errorMessage = "";
    render();
    try {
      const remote = await request("/api/code-focus/publication");
      if (!published) loadFields(storedDraft() || remote);
      published = remote;
      if (sameContent(draft(), remote)) baseVersion = remote.version;
      if (baseVersion !== remote.version) {
        get("remote-version").textContent = `查看线上版本 ${remote.version}`;
        get("remote-language").textContent = languageOptions.find(option => option.value === remote.language).text;
        get("remote-answers").textContent = remote.answers || "（空）";
        get("remote-code").textContent = remote.code || "（空）";
      }
      activity = "";
      remember();
    } catch (error) {
      activity = "load-failed";
      errorMessage = "无法读取已发布内容。" + reason(error);
    }
    render();
  }

  publish.addEventListener("click", async () => {
    if (publish.disabled) return;
    const outgoing = draft();
    activity = "publishing";
    errorMessage = "";
    render();
    try {
      published = await request("/api/admin/code-focus/publish", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(outgoing),
      });
      baseVersion = published.version;
    } catch (error) {
      if (error.status === 409) {
        await load();
        return;
      }
      // A lost response can follow a successful commit. Check before dropping or retrying the draft.
      if (!error.status || error.status >= 500) {
        await load();
        if (activity || published.version !== outgoing.version) return;
      }
      errorMessage = "发布未确认。" + reason(error);
    }
    activity = "";
    remember();
    render();
  });

  function edited() {
    if (!activity) errorMessage = "";
    remember();
    render();
  }

  for (const field of [code, answers]) {
    field.addEventListener("compositionstart", () => {
      composing = true;
      render();
    });
    field.addEventListener("compositionend", () => {
      composing = false;
      if (field === answers) window.CodeFocusDisplay.renderAnswers(answers.value);
      edited();
    });
    field.addEventListener("input", event => {
      if (event.isComposing || composing) return;
      if (field === answers) window.CodeFocusDisplay.renderAnswers(answers.value);
      edited();
    });
  }
  language.addEventListener("change", edited);
  retry.addEventListener("click", load);
  get("use-remote").addEventListener("click", () => {
    loadFields(published);
    edited();
  });
  get("use-local").addEventListener("click", () => {
    baseVersion = published.version;
    edited();
    publish.focus();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) remember();
  });
  window.addEventListener("pagehide", remember);
  window.addEventListener("beforeunload", event => {
    remember();
    if (storageFailed && published && (activity || !sameContent(draft(), published))) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  load();
})();
