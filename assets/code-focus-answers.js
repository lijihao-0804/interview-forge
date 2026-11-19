(() => {
  "use strict";

  const input = document.getElementById("answer-input");
  const groups = document.getElementById("answer-groups");
  const count = document.getElementById("answer-count");

  function draftKey() {
    const prefix = "hot100.codeFocus.answers.";
    const savedScope = history.state?.codeFocusAnswerScope;
    if (typeof savedScope === "string") return prefix + savedScope;
    let scope = "standalone";
    if (document.referrer) {
      const from = new URL(document.referrer);
      if (from.origin === location.origin && from.pathname === "/books/ai-exam/acm-playground.html") {
        scope = "acm:" + (from.searchParams.get("id") || "");
      }
    }
    try {
      history.replaceState({ ...history.state, codeFocusAnswerScope: scope }, "");
    } catch { /* The referrer still identifies this visit. */ }
    return prefix + scope;
  }

  const key = draftKey();
  try { input.value = sessionStorage.getItem(key) || ""; } catch { /* Start with an empty sheet. */ }

  function render(save) {
    const answers = input.value.match(/[a-zA-Zａ-ｚＡ-Ｚ]+/g) || [];
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
    let status = answers.length ? `共 ${answers.length} 题` : "";
    if (save) {
      try {
        if (input.value) sessionStorage.setItem(key, input.value);
        else sessionStorage.removeItem(key);
      } catch {
        status += " 答案草稿未能保存";
      }
    }
    if (count.textContent !== status) count.textContent = status;
  }

  render(false);
  input.addEventListener("input", event => {
    if (!event.isComposing) render(true);
  });
  input.addEventListener("compositionend", () => render(true));
})();
