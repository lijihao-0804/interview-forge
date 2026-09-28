(function () {
  "use strict";

  var panel = document.getElementById("solutionProgress");
  if (!panel) return;
  var problemId = Number(panel.getAttribute("data-problem-id"));
  var summary = document.getElementById("solutionProgressSummary");
  var due = document.getElementById("solutionProgressDue");
  var markSelect = document.getElementById("solutionProgressMark");
  var weakButton = document.getElementById("solutionWeakToggle");
  var historyButton = document.getElementById("solutionProgressHistoryButton");
  var historyPanel = document.getElementById("solutionProgressHistory");
  var toast = document.getElementById("solutionProgressToast");
  var ratingButtons = panel.querySelectorAll("[data-review-rating]");
  var currentMark = "";

  function notify(message, kind) {
    if (window.InterviewForgeUI) window.InterviewForgeUI.showToast(toast, message, kind);
    else { toast.textContent = message; toast.className = "toast" + (kind === "error" ? " error" : ""); }
  }

  function paintMark(mark) {
    currentMark = mark || "";
    markSelect.value = currentMark;
    weakButton.setAttribute("aria-pressed", currentMark === "weak" ? "true" : "false");
    weakButton.textContent = currentMark === "weak" ? "取消薄弱" : "标记薄弱";
  }

  function paintProgress(data) {
    var rounds = Number(data.rounds || 0);
    var submitText = Number(data.submits || 0)
      ? " · AC " + Number(data.ac_submits || 0) + " / 提交 " + Number(data.submits || 0)
      : " · 尚无提交记录";
    summary.textContent = "已完成 " + rounds + " 轮" + submitText;
    due.textContent = data.next_due ? "下次复习：" + data.next_due : "下次复习：—";
    paintMark(data.mark || "");
  }

  async function loadProgress() {
    try {
      var response = await fetch("/api/problem/" + problemId + "/progress", { cache: "no-store" });
      if (response.status === 401) {
        var next = window.location.pathname + window.location.search + window.location.hash;
        window.location.replace("/pages/login.html?next=" + encodeURIComponent(next));
        return;
      }
      if (!response.ok) throw new Error("暂时无法读取学习记录");
      paintProgress(await response.json());
      markSelect.disabled = false;
      weakButton.disabled = false;
      Array.prototype.forEach.call(ratingButtons, function (button) { button.disabled = false; });
    } catch (_) {
      summary.textContent = "暂时无法读取学习记录；可稍后刷新重试";
      markSelect.disabled = true;
      weakButton.disabled = true;
      Array.prototype.forEach.call(ratingButtons, function (button) { button.disabled = true; });
    }
  }

  async function recordReview(rating, button) {
    Array.prototype.forEach.call(ratingButtons, function (item) { item.disabled = true; });
    notify("正在保存本次复习评分…", "");
    try {
      var response = await fetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ problem_id: problemId, rating: rating })
      });
      var result = await response.json().catch(function () { return {}; });
      if (response.status === 401) { redirectToLogin(); return; }
      if (!response.ok) throw new Error(result.error || "复习记录失败");
      await loadProgress();
      var ratingLabel = { again: "忘了", hard: "有点困难", good: "记得", easy: "很轻松" }[result.rating_name]
        || button.textContent.trim();
      notify(result.already_reviewed_today
        ? "今天已记录过本题评分，沿用「" + ratingLabel + "」；下次复习：" + result.next_due
        : "已记录「" + ratingLabel + "」；下次复习：" + result.next_due, "success");
    } catch (error) {
      notify(error.message || "复习记录失败，请稍后重试", "error");
      Array.prototype.forEach.call(ratingButtons, function (item) { item.disabled = false; });
    }
  }

  function redirectToLogin() {
    var next = window.location.pathname + window.location.search + window.location.hash;
    window.location.replace("/pages/login.html?next=" + encodeURIComponent(next));
  }

  function renderSubmissionHistory(items) {
    historyPanel.replaceChildren();
    var accepted = (items || []).filter(function (item) { return item.status === "ac"; }).slice(0, 20);
    if (!accepted.length) {
      historyPanel.textContent = "最近 50 条提交中还没有 AC 记录。";
      return;
    }
    var list = document.createElement("ul");
    accepted.forEach(function (item) {
      var row = document.createElement("li");
      var time = window.InterviewForgeTime
        ? window.InterviewForgeTime.formatDateTime(item.submitted_at)
        : String(item.submitted_at || "").replace("T", " ").slice(0, 16);
      row.textContent = time + (item.lang ? " · " + item.lang : "") + (item.source ? " · " + item.source : "");
      list.appendChild(row);
    });
    historyPanel.appendChild(list);
    var note = document.createElement("span");
    note.textContent = "显示最近 50 条提交中的 AC，最多 20 条。";
    historyPanel.appendChild(note);
  }

  async function loadSubmissionHistory() {
    historyPanel.textContent = "正在读取 AC 提交记录…";
    try {
      var response = await fetch("/api/submissions?problem_id=" + encodeURIComponent(problemId), { cache: "no-store" });
      if (response.status === 401) { redirectToLogin(); return; }
      if (!response.ok) throw new Error("暂时无法读取提交记录，请稍后重试");
      var payload = await response.json();
      renderSubmissionHistory(payload.items || []);
    } catch (error) {
      historyPanel.textContent = error.message || "暂时无法读取提交记录，请稍后重试";
    }
  }

  async function saveMark(nextMark) {
    var previous = currentMark;
    paintMark(nextMark);
    markSelect.disabled = true;
    weakButton.disabled = true;
    try {
      var response = await fetch("/api/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: "problem", target_id: String(problemId), mark: nextMark })
      });
      var result = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(result.error || "标记保存失败");
      paintMark(nextMark);
      notify(nextMark ? "已更新本题标记" : "已清除本题标记", "success");
    } catch (error) {
      paintMark(previous);
      notify(error.message || "标记保存失败，请稍后重试", "error");
    } finally {
      markSelect.disabled = false;
      weakButton.disabled = false;
    }
  }

  markSelect.addEventListener("change", function () { saveMark(markSelect.value); });
  weakButton.addEventListener("click", function () { saveMark(currentMark === "weak" ? "" : "weak"); });
  Array.prototype.forEach.call(ratingButtons, function (button) {
    button.addEventListener("click", function () {
      recordReview(Number(button.getAttribute("data-review-rating")), button);
    });
  });
  if (historyButton && historyPanel) {
    historyButton.addEventListener("click", function () {
      var expanded = historyButton.getAttribute("aria-expanded") === "true";
      historyButton.setAttribute("aria-expanded", expanded ? "false" : "true");
      historyPanel.hidden = expanded;
      if (!expanded) loadSubmissionHistory();
    });
  }
  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.key.toLowerCase() !== "m") return;
    var target = event.target;
    if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(target.tagName))) return;
    event.preventDefault();
    weakButton.click();
  });

  loadProgress();
})();
