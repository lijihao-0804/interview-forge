(() => {
  "use strict";

  const get = id => document.getElementById(id);
  const input = get("source-code");
  const language = get("language");
  const reader = get("reader");
  const sheet = get("sheet");
  const draftKey = "hot100.codeFocus.draft";
  const transferKey = "hot100.codeFocus.transfer";
  const fontKey = "hot100.codeFocus.fontSize";
  const supported = Array.from(language.options, option => option.value);
  let awaitingPaste = new URLSearchParams(location.search).get("transfer") === "unavailable";
  let source = "";
  let rows = [];
  let size = 16;
  let frame = 0;
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

  function setSize(next) {
    size = Math.max(12, Math.min(32, next));
    document.documentElement.style.setProperty("--code-size", size + "px");
    get("size-value").textContent = size + " px";
    get("smaller").disabled = size === 12;
    get("larger").disabled = size === 32;
    queueLayout();
  }

  function syncTheme() {
    try {
      const theme = localStorage.getItem("forge-theme");
      if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;
      else delete document.documentElement.dataset.theme;
    } catch { /* CSS follows the system theme. */ }
  }

  // A highlighted string can span several original lines. Walk its text nodes
  // and carry token classes across newlines, keeping one readable row per line.
  function renderSource() {
    const text = source.replace(/\r\n?/g, "\n");
    const highlighter = window.hljs;
    let syntax = language.value;
    if (syntax === "auto" && highlighter && text.length <= 120000) {
      const subset = supported.filter(name => name !== "plaintext" && highlighter.getLanguage(name));
      syntax = highlighter.highlightAuto(text.slice(0, 4096), subset).language || "plaintext";
    }
    let highlighted = null;
    if (highlighter && highlighter.getLanguage(syntax) && syntax !== "plaintext" && text.length <= 120000) {
      const template = document.createElement("template");
      template.innerHTML = highlighter.highlight(text, { language: syntax, ignoreIllegals: true }).value;
      highlighted = template.content;
    }
    rows = [];
    let lineText;
    function newLine() {
      const row = document.createElement("div");
      row.className = "code-line";
      row.dataset.line = String(rows.length + 1);
      lineText = document.createElement("span");
      lineText.className = "line-text";
      row.append(lineText);
      rows.push(row);
    }
    function appendText(value, classes) {
      const pieces = value.split("\n");
      pieces.forEach((piece, index) => {
        if (index) newLine();
        if (!piece) return;
        if (!classes) { lineText.append(piece); return; }
        const span = document.createElement("span");
        span.className = classes;
        span.textContent = piece;
        lineText.append(span);
      });
    }
    function walk(node, classes) {
      if (node.nodeType === Node.TEXT_NODE) { appendText(node.data, classes); return; }
      const nested = node.nodeName === "SPAN" ? (classes + " " + node.className).trim() : classes;
      for (const child of node.childNodes) walk(child, nested);
    }
    newLine();
    if (highlighted) walk(highlighted, "");
    else appendText(text, "");
    const col = document.createElement("div");
    col.className = "code-column";
    for (const row of rows) col.append(row);
    sheet.replaceChildren(col);
    sheet.style.setProperty("--gutter", (String(rows.length).length + .5) + "ch");
    get("syntax").textContent = Array.from(language.options).find(option => option.value === syntax && syntax !== "auto")?.text || "纯文本";
    get("line-count").textContent = rows.length + " 行";
  }

  // Balance by rendered height. A wrapped 200-character line and an empty line
  // occupy different space; both must stay intact when the next column starts.
  function partition(heights, count) {
    let remaining = heights.reduce((sum, h) => sum + h, 0);
    const ends = [];
    let start = 0;
    let tallest = 0;
    for (let c = 0; c < count; c++) {
      const left = count - c;
      const limit = heights.length - left + 1;
      const target = remaining / left;
      let end = start;
      let used = 0;
      while (end < limit) {
        const next = heights[end];
        if (left > 1 && end > start && Math.abs(used - target) <= Math.abs(used + next - target)) break;
        used += next;
        end++;
      }
      ends.push(end);
      tallest = Math.max(tallest, used);
      remaining -= used;
      start = end;
    }
    return { ends, tallest };
  }

  function layout() {
    if (reader.hidden || !rows.length) return;
    const style = getComputedStyle(sheet);
    const width = sheet.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const gap = parseFloat(style.columnGap);
    const maxColumns = Math.max(1, Math.min(3, rows.length, Math.floor((width + gap) / (size * 32 + gap))));
    const available = Math.max(size * 5, window.innerHeight - (sheet.getBoundingClientRect().top + window.scrollY)
      - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom));
    let best;
    for (let count = 1; count <= maxColumns; count++) {
      sheet.style.setProperty("--columns", count);
      const choice = partition(rows.map(row => row.getBoundingClientRect().height), count);
      if (!best || choice.tallest < best.tallest) best = choice;
      if (best.tallest <= available) break;
    }
    const columns = best.ends.length;
    sheet.style.setProperty("--columns", columns);
    let start = 0;
    const changed = sheet.children.length !== columns || best.ends.some((end, i) => sheet.children[i]?.lastElementChild !== rows[end - 1]);
    if (changed) {
      const fragment = document.createDocumentFragment();
      for (const end of best.ends) {
        const col = document.createElement("div");
        col.className = "code-column";
        for (; start < end; start++) col.append(rows[start]);
        fragment.append(col);
      }
      sheet.replaceChildren(fragment);
    }
    get("column-status").textContent = columns === 1 ? "单栏" : columns + " 栏 · 从左列向右读";
  }

  function queueLayout() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(layout);
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
      renderSource();
      layout();
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
  syncTheme();
  window.addEventListener("storage", event => { if (event.key === "forge-theme") syncTheme(); });
  try {
    const stored = Number.parseInt(localStorage.getItem(fontKey), 10);
    if (Number.isFinite(stored)) size = stored;
  } catch { /* Use the initial size. */ }
  setSize(size);
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
  for (const [id, delta] of [["smaller", -1], ["larger", 1]]) {
    get(id).addEventListener("click", () => {
      setSize(size + delta);
      try { localStorage.setItem(fontKey, String(size)); } catch { /* Size still applies in memory. */ }
    });
  }
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
  window.addEventListener("resize", queueLayout);
  document.fonts?.ready.then(queueLayout);
})();
