(() => {
  "use strict";

  const get = id => document.getElementById(id);
  const input = get("source-code");
  const language = get("language");
  const reader = get("reader");
  const sheet = get("sheet");
  const draftKey = "hot100.codeFocus.draft";
  const transferKey = "hot100.codeFocus.transfer";
  const renderCode = window.CodeFocusDisplay.mountReader();
  const supported = Array.from(language.options, option => option.value);
  let awaitingPaste = new URLSearchParams(location.search).get("transfer") === "unavailable";
  let source = "";
  let saveTimer;

  function load(key) {
    try { return JSON.parse(sessionStorage.getItem(key)); } catch { return null; }
  }

  function save() {
    clearTimeout(saveTimer);
    if (awaitingPaste) return;
    try {
      sessionStorage.setItem(draftKey, JSON.stringify({ code: source, language: language.value, editing: reader.hidden }));
    } catch {
      if (source) get("notice").textContent = "浏览器未能保存当前草稿，刷新或关闭前请复制代码。";
    }
  }

  function showEditor(editing, focus) {
    get("editor").hidden = !editing;
    reader.hidden = editing;
    get("edit").hidden = editing;
    get("copy").hidden = editing;
    get("read").hidden = !editing;
    get("read").disabled = !source.length;
    get("notice").textContent = "";
    if (editing) {
      if (focus) input.focus({ preventScroll: true });
    } else {
      renderCode(source, language.value);
      if (focus) sheet.focus({ preventScroll: true });
    }
    if (focus) window.scrollTo(0, 0);
    save();
  }

  const transferred = load(transferKey);
  try { sessionStorage.removeItem(transferKey); } catch { /* Storage may be disabled. */ }
  const previous = awaitingPaste ? null : (transferred && typeof transferred.code === "string" ? transferred : load(draftKey));
  if (previous && typeof previous.code === "string") {
    source = previous.code;
    input.value = source;
    const lang = String(previous.language || "").toLowerCase();
    language.value = supported.includes(lang) ? lang : (lang === "python3" ? "python" : "auto");
  }
  if (document.referrer) {
    const from = new URL(document.referrer);
    if (from.origin === location.origin && from.pathname === "/books/ai-exam/acm-playground.html") {
      const back = get("back");
      back.href = from.href;
      back.title = "返回 ACM 编辑器";
      back.setAttribute("aria-label", back.title);
    }
  }
  showEditor(!source || previous?.editing === true, false);
  if (awaitingPaste) {
    get("notice").textContent = "浏览器未能带入这段代码，可返回 ACM 编辑器复制后粘贴。";
  }
  input.addEventListener("input", () => {
    if (awaitingPaste) {
      awaitingPaste = false;
      get("notice").textContent = "";
      history.replaceState(history.state, "", location.pathname);
    }
    source = input.value;
    get("read").disabled = !source.length;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 250);
  });
  language.addEventListener("change", save);
  window.addEventListener("pagehide", save);
  get("edit").addEventListener("click", () => showEditor(true, true));
  get("read").addEventListener("click", () => showEditor(false, true));
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && source) {
      event.preventDefault();
      showEditor(false, true);
    }
  });
  get("copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(source);
      get("notice").textContent = "已复制全部代码";
    } catch {
      showEditor(true, true);
      input.select();
      get("notice").textContent = "代码已选中，可使用系统复制。";
    }
  });
})();
