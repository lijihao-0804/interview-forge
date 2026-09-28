(function (root) {
  "use strict";

  function showToast(element, message, kind, duration) {
    if (!element) return;
    element.textContent = String(message || "");
    element.className = "toast" + (kind === "success" ? " success" : kind === "error" ? " error" : "");
    element.setAttribute("role", kind === "error" ? "alert" : "status");
    if (element._ifToastTimer) root.clearTimeout(element._ifToastTimer);
    if (kind === "success" && duration !== 0) {
      element._ifToastTimer = root.setTimeout(function () {
        element.textContent = "";
        element.className = "toast";
      }, Number(duration) > 0 ? Number(duration) : 2500);
    }
  }

  function renderError(container, message, retryLabel, onRetry) {
    if (!container) return;
    var panel = root.document.createElement("div");
    panel.className = "ui-error";
    var text = root.document.createElement("span");
    text.textContent = String(message || "暂时无法加载，请稍后重试。");
    panel.appendChild(text);
    if (typeof onRetry === "function") {
      var button = root.document.createElement("button");
      button.type = "button";
      button.className = "round-button";
      button.textContent = String(retryLabel || "重试");
      button.setAttribute("data-retry", "");
      button.addEventListener("click", onRetry);
      panel.appendChild(button);
    }
    container.replaceChildren(panel);
  }

  function renderSkeleton(container, count, className) {
    if (!container) return;
    var fragment = root.document.createDocumentFragment();
    var size = Math.max(1, Math.min(12, Number(count) || 1));
    for (var i = 0; i < size; i += 1) {
      var item = root.document.createElement("div");
      item.className = className || "skeleton";
      item.setAttribute("aria-hidden", "true");
      fragment.appendChild(item);
    }
    container.replaceChildren(fragment);
  }

  root.InterviewForgeUI = Object.freeze({
    showToast: showToast,
    renderError: renderError,
    renderSkeleton: renderSkeleton
  });
})(window);
