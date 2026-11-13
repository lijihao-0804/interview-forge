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

  function getAuthClient() {
    if (window.InterviewForgeAuth && window.InterviewForgeAuth.ready) return Promise.resolve(window.InterviewForgeAuth);
    return new Promise(function (resolve, reject) {
      function ready() {
        document.removeEventListener("interviewforge:auth-ready", ready);
        window.clearTimeout(timer);
        if (window.InterviewForgeAuth && window.InterviewForgeAuth.ready) resolve(window.InterviewForgeAuth);
        else reject(new Error("登录状态暂时不可用，请刷新页面后重试"));
      }
      var timer = window.setTimeout(function () {
        document.removeEventListener("interviewforge:auth-ready", ready);
        reject(new Error("登录状态确认超时，请刷新页面后重试"));
      }, 12000);
      document.addEventListener("interviewforge:auth-ready", ready, { once: true });
    });
  }

  function setControlsEnabled(enabled) {
    markSelect.disabled = !enabled;
    weakButton.disabled = !enabled;
    Array.prototype.forEach.call(ratingButtons, function (button) { button.disabled = !enabled; });
    var fav = document.getElementById("solutionFavoriteToggle");
    if (fav) fav.disabled = !enabled;
    if (historyButton) historyButton.disabled = !enabled;
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

  function paintGuest(reason) {
    summary.textContent = reason === "error"
      ? "暂时无法确认登录状态；题解仍可阅读"
      : "游客可阅读题解；登录后可记录复习、薄弱题和收藏";
    due.textContent = "登录后同步学习状态";
    paintMark("");
    panel.classList.add("is-auth-required");
    setControlsEnabled(true);
  }

  function paintAuthenticated() {
    panel.classList.remove("is-auth-required");
    setControlsEnabled(true);
  }

  async function loadProgress() {
    summary.textContent = "正在确认登录状态…";
    due.textContent = "请稍候";
    setControlsEnabled(false);
    try {
      var auth = await getAuthClient();
      var session = await auth.ready;
      if (session.status !== "authenticated") {
        paintGuest(session.status);
        return;
      }
      var response = await fetch("/api/problem/" + problemId + "/progress", {
        credentials: "same-origin", cache: "no-store"
      });
      if (response.status === 401) {
        auth.handleUnauthorized("记录本题学习进度");
        paintGuest("guest");
        return;
      }
      if (!response.ok) throw new Error("暂时无法读取学习记录");
      paintProgress(await response.json());
      paintAuthenticated();
    } catch (error) {
      summary.textContent = error.message || "暂时无法读取学习记录；可稍后刷新重试";
      due.textContent = "未同步";
      panel.classList.add("is-auth-required");
      setControlsEnabled(true);
    }
  }

  async function requireUser(feature) {
    var auth = await getAuthClient();
    return auth.requireUser(feature);
  }

  async function protectedFetch(path, options, feature) {
    var auth = await getAuthClient();
    return auth.fetchProtected(path, options, feature);
  }

  async function recordReview(rating, button) {
    try { await requireUser("记录本题复习评分"); }
    catch (_) { return; }
    Array.prototype.forEach.call(ratingButtons, function (item) { item.disabled = true; });
    notify("正在保存本次复习评分…", "");
    try {
      var response = await protectedFetch("/api/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ problem_id: problemId, rating: rating })
      }, "记录本题复习评分");
      var result = await response.json().catch(function () { return {}; });
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
      var response = await protectedFetch("/api/submissions?problem_id=" + encodeURIComponent(problemId), {
        cache: "no-store"
      }, "查看提交记录");
      if (!response.ok) throw new Error("暂时无法读取提交记录，请稍后重试");
      var payload = await response.json();
      renderSubmissionHistory(payload.items || []);
    } catch (error) {
      historyPanel.textContent = error.code === "AUTH_REQUIRED"
        ? "游客可阅读题解；登录后可查看自己的提交记录。"
        : (error.message || "暂时无法读取提交记录，请稍后重试");
    }
  }

  async function saveMark(nextMark) {
    var previous = currentMark;
    try { await requireUser("标记题目学习状态"); }
    catch (_) { markSelect.value = previous; return; }
    paintMark(nextMark);
    markSelect.disabled = true;
    weakButton.disabled = true;
    try {
      var response = await protectedFetch("/api/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: "problem", target_id: String(problemId), mark: nextMark })
      }, "标记题目学习状态");
      var result = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(result.error || "标记保存失败");
      paintMark(nextMark);
      notify(nextMark ? "已更新本题标记" : "已清除本题标记", "success");
    } catch (error) {
      paintMark(previous);
      if (error.code !== "AUTH_REQUIRED") notify(error.message || "标记保存失败，请稍后重试", "error");
    } finally {
      markSelect.disabled = false;
      weakButton.disabled = false;
    }
  }

  markSelect.addEventListener("change", function () { saveMark(markSelect.value); });
  weakButton.addEventListener("click", function () { saveMark(currentMark === "weak" ? "" : "weak"); });

  var favButton = document.getElementById("solutionFavoriteToggle");
  if (favButton) {
    function paintFav(on) {
      favButton.setAttribute("aria-pressed", on ? "true" : "false");
      favButton.textContent = on ? "⭐ 已收藏" : "⭐ 收藏";
      favButton.classList.toggle("on", !!on);
      favButton.disabled = false;
    }
    paintFav(false);
    getAuthClient().then(function (auth) { return auth.ready; }).then(function (session) {
      if (session.status !== "authenticated") return;
      return fetch("/api/favorites", { credentials: "same-origin", cache: "no-store" }).then(function (r) {
        return r.ok ? r.json() : {};
      }).then(function (d) { paintFav(Array.isArray(d.ids) && d.ids.indexOf("problem:" + problemId) >= 0); });
    }).catch(function () { });
    favButton.addEventListener("click", async function () {
      try { await requireUser("收藏题解"); }
      catch (_) { return; }
      favButton.disabled = true;
      var titleEl = document.querySelector("h1");
      try {
        var response = await protectedFetch("/api/favorites/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target_type: "problem",
            target_id: String(problemId),
            module_id: "hot100",
            module_title: "Hot 100 算法刷题",
            title: titleEl ? titleEl.textContent.trim() : ("题目 " + problemId),
            url: location.pathname + location.search
          })
        }, "收藏题解");
        var res = await response.json().catch(function () { return {}; });
        if (!response.ok) throw new Error(res.error || "收藏失败");
        paintFav(res.favorited);
        notify(res.favorited ? "已加入收藏，可在「我的收藏」查看" : "已取消收藏");
      } catch (error) {
        if (error.code !== "AUTH_REQUIRED") notify(error.message || "操作失败，请重试", "error");
        favButton.disabled = false;
      }
    });
  }

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
