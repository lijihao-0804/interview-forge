(() => {
  "use strict";

  const input = document.getElementById("answer-input");
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
    window.CodeFocusDisplay.renderAnswers(input.value);
    if (save) {
      try {
        if (input.value) sessionStorage.setItem(key, input.value);
        else sessionStorage.removeItem(key);
      } catch {
        count.textContent += " 答案草稿未能保存";
      }
    }
  }

  render(false);
  input.addEventListener("input", event => {
    if (!event.isComposing) render(true);
  });
  input.addEventListener("compositionend", () => render(true));
})();
