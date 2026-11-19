(() => {
  "use strict";

  const get = id => document.getElementById(id);
  const languageNames = {
    plaintext: "纯文本", python: "Python", java: "Java", cpp: "C++", c: "C",
    go: "Go", javascript: "JavaScript", typescript: "TypeScript", rust: "Rust", kotlin: "Kotlin", sql: "SQL"
  };

  function renderAnswers(raw) {
    const groups = get("answer-groups");
    const answers = raw.match(/[a-zA-Zａ-ｚＡ-Ｚ]+/g) || [];
    const fragment = document.createDocumentFragment();
    for (let start = 0; start < answers.length; start += 5) {
      const group = document.createElement("ol");
      group.className = "answer-group";
      group.start = start + 1;
      const end = Math.min(start + 5, answers.length);
      group.setAttribute("aria-label", `第 ${start + 1} 至 ${end} 题`);
      for (let i = start; i < end; i++) {
        const item = document.createElement("li");
        item.className = "answer-item";
        const number = document.createElement("span");
        number.className = "answer-number";
        number.textContent = String(i + 1);
        const value = document.createElement("span");
        value.className = "answer-value";
        value.textContent = answers[i].normalize("NFKC").toUpperCase();
        item.append(number, value);
        group.append(item);
      }
      fragment.append(group);
    }
    groups.replaceChildren(fragment);
    groups.hidden = answers.length === 0;
    const label = answers.length ? `共 ${answers.length} 题` : "";
    const count = get("answer-count");
    if (count.textContent !== label) count.textContent = label;
    return answers.length;
  }

  function mountReader() {
    const reader = get("reader");
    const sheet = get("sheet");
    const fontKey = "hot100.codeFocus.fontSize";
    let rows = [];
    let size = 16;
    let frame = 0;

    function setSize(next) {
      size = Math.max(12, Math.min(32, next));
      document.documentElement.style.setProperty("--code-size", size + "px");
      get("size-value").textContent = size + " px";
      get("smaller").disabled = size === 12;
      get("larger").disabled = size === 32;
      queueLayout();
    }

    // A highlighted string can span several original lines. Walk its text nodes
    // and carry token classes across newlines, keeping one readable row per line.
    function renderCode(source, syntax) {
      if (!source) {
        rows = [];
        sheet.replaceChildren();
        return;
      }
      const text = source.replace(/\r\n?/g, "\n");
      const highlighter = window.hljs;
      if (syntax === "auto" && highlighter && text.length <= 120000) {
        const subset = Object.keys(languageNames).filter(name => name !== "plaintext" && highlighter.getLanguage(name));
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
      // These grammars leave ordinary calls and many operators as unscoped text.
      // Keep the extra spans within typical snippets; large pastes retain native scopes.
      const accentCalls = (syntax === "python" || syntax === "java") && text.length <= 32000;
      // Consume other words whole so an identifier suffix cannot masquerade as a call.
      const callOrOperator = /([$_\p{ID_Start}][$_\p{ID_Continue}]*)(?=[ \t]*\()|([!%&*+\-/<=>^|~]+)|[$_\p{ID_Continue}]+/gu;
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
        if (node.nodeType === Node.TEXT_NODE) {
          const value = node.data;
          if (accentCalls && (!classes || classes === "hljs-params")) {
            let offset = 0;
            for (const match of value.matchAll(callOrOperator)) {
              if (!match[1] && !match[2]) continue;
              appendText(value.slice(offset, match.index), classes);
              appendText(match[0], match[1] ? "hljs-title function_" : "hljs-operator");
              offset = match.index + match[0].length;
            }
            appendText(value.slice(offset), classes);
          } else {
            appendText(value, classes);
          }
          return;
        }
        const nested = node.nodeName === "SPAN" ? node.className || classes : classes;
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
      get("syntax").textContent = languageNames[syntax] || "纯文本";
      get("line-count").textContent = rows.length + " 行";
      layout();
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

    try {
      const stored = Number.parseInt(localStorage.getItem(fontKey), 10);
      if (Number.isFinite(stored)) size = stored;
    } catch { /* Use the initial size. */ }
    setSize(size);
    for (const [id, delta] of [["smaller", -1], ["larger", 1]]) {
      get(id).addEventListener("click", () => {
        setSize(size + delta);
        try { localStorage.setItem(fontKey, String(size)); } catch { /* Size still applies in memory. */ }
      });
    }
    window.addEventListener("resize", queueLayout);
    const answerStrip = get("answer-strip");
    if (answerStrip && window.ResizeObserver) new ResizeObserver(queueLayout).observe(answerStrip);
    document.fonts?.ready.then(queueLayout);
    return renderCode;
  }

  window.CodeFocusDisplay = { mountReader, renderAnswers };
})();
