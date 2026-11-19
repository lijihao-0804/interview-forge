(() => {
  "use strict";

  const get = id => document.getElementById(id);
  const code = get("source-code");
  const language = get("language");
  const answers = get("answer-input");
  const status = get("save-status");
  const retry = get("retry");
  const conflict = get("conflict");
  const publicUrl = "/api/code-focus/publication";
  const editUrl = "/api/admin/code-focus/publication";
  let saved = null;
  let latest = null;
  let retryAction = null;
  let busy = false;
  let composing = false;
  let timer;
  let firstEdit = null;
  let lastEdit = 0;

  function fieldValue(field, previous) {
    // A textarea displays CRLF as LF. Preserve untouched text received from other clients.
    if (previous?.includes("\r") && field.value === previous.replace(/\r\n?/g, "\n")) return previous;
    return field.value;
  }

  function draft() {
    return {
      code: fieldValue(code, saved?.code),
      language: language.value,
      answers: fieldValue(answers, saved?.answers),
    };
  }

  function sameContent(a, b) {
    return a.code === b.code && a.language === b.language && a.answers === b.answers;
  }

  function message(text, needsAttention = false) {
    if (status.textContent !== text) status.textContent = text;
    status.toggleAttribute("data-attention", needsAttention);
  }

  function showSaved() {
    message(saved.version ? `已保存并公开 · 版本 ${saved.version}` : "尚未发布内容");
  }

  function showAnswers() {
    window.CodeFocusDisplay.renderAnswers(answers.value);
  }

  function loadFields(publication) {
    code.value = publication.code;
    language.value = publication.language;
    answers.value = publication.answers;
    for (const field of [code, language, answers]) field.disabled = false;
    saved = publication;
    firstEdit = null;
    showAnswers();
    showSaved();
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
      if (!Number.isSafeInteger(data.version) || data.version < 0 ||
          typeof data.code !== "string" || typeof data.answers !== "string" ||
          !Array.from(language.options).some(option => option.value === data.language)) {
        throw new Error("Invalid publication");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  function failed(error, action, text) {
    let reason = "请检查网络连接后重试。";
    if (error.status === 401 || error.status === 403) reason = "请在另一标签页登录管理员账号后重试。";
    else if (error.status === 413) reason = "内容过大，发布请求限 1 MiB。请缩短后重试。";
    else if (error.status) reason = `服务器返回 ${error.status}，请重试。`;
    message(text + reason, true);
    retryAction = action;
    retry.hidden = false;
  }

  async function load(forConflict = false) {
    busy = true;
    message(forConflict ? "版本已更新，正在读取线上内容以供核对…" : "正在读取已发布内容…");
    try {
      const publication = await request(publicUrl);
      if (!forConflict || sameContent(draft(), publication)) {
        loadFields(publication);
        return;
      }
      latest = publication;
      get("remote-version").textContent = `查看线上版本 ${latest.version}`;
      get("remote-language").textContent = Array.from(language.options).find(option => option.value === latest.language).text;
      get("remote-answers").textContent = latest.answers || "（空）";
      get("remote-code").textContent = latest.code || "（空）";
      conflict.hidden = false;
      message("其他编辑已发布。本页输入已保留，核对后可选择要保留的内容。", true);
    } catch (error) {
      failed(error, () => load(forConflict), forConflict ? "未保存，无法读取冲突版本。" : "无法读取已发布内容。");
    } finally {
      busy = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (!saved || busy || latest || retryAction || composing) return;
    if (sameContent(draft(), saved)) {
      firstEdit = null;
      showSaved();
      return;
    }
    if (document.hidden) {
      save();
      return;
    }
    message("有未保存的修改，等待自动保存…");
    const now = Date.now();
    firstEdit ??= now;
    const deadline = Math.min(lastEdit + 1500, firstEdit + 8000);
    timer = setTimeout(save, Math.max(0, deadline - now));
  }

  async function save() {
    clearTimeout(timer);
    const outgoing = { version: saved.version, ...draft() };
    firstEdit = null;
    busy = true;
    message("正在保存并发布…");
    try {
      saved = await request(editUrl, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(outgoing),
      });
    } catch (error) {
      if (error.status === 409) await load(true);
      else failed(error, save, "未保存。");
      return;
    } finally {
      busy = false;
    }
    // Inputs may have changed after this request started. Keep the live fields intact.
    schedule();
  }

  function edited() {
    lastEdit = Date.now();
    firstEdit ??= lastEdit;
    schedule();
  }

  for (const field of [code, answers]) {
    field.addEventListener("compositionstart", () => {
      composing = true;
      clearTimeout(timer);
    });
    field.addEventListener("compositionend", () => {
      composing = false;
      if (field === answers) showAnswers();
      edited();
    });
    field.addEventListener("input", event => {
      if (event.isComposing || composing) return;
      if (field === answers) showAnswers();
      edited();
    });
  }
  language.addEventListener("change", edited);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) schedule();
  });
  retry.addEventListener("click", () => {
    const action = retryAction;
    retryAction = null;
    retry.hidden = true;
    if (action) action();
  });
  get("use-remote").addEventListener("click", () => {
    loadFields(latest);
    latest = null;
    conflict.hidden = true;
  });
  get("use-local").addEventListener("click", () => {
    saved = latest;
    latest = null;
    conflict.hidden = true;
    save();
  });
  window.addEventListener("beforeunload", event => {
    if (saved && (busy || retryAction || latest || !sameContent(draft(), saved))) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  load();
})();
