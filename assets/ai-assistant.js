(function () {
  "use strict";

  var embedded = new URLSearchParams(window.location.search).get("embedded") === "1";
  document.body.classList.toggle("embedded", embedded);
  var state = {
    sessions: [], current: null, controller: null, assistantNode: null,
    cancelRequested: false, streamFailed: false, streamCompleted: false, pageContext: null,
    pageContextWaiters: Object.create(null), contextRequestSerial: 0,
    autoFollow: true, scrollFrame: null,
    streamDiagnostics: { delta_count: 0, render_count: 0, max_render_ms: 0 }
  };
  var STREAM_RENDER_INTERVAL = 100;
  var AUTO_FOLLOW_THRESHOLD = 120;
  var STREAM_DIAGNOSTICS_ENABLED = window.__INTERVIEW_FORGE_STREAM_DIAGNOSTICS__ === true;
  if (STREAM_DIAGNOSTICS_ENABLED) window.__interviewForgeStreamDiagnostics = state.streamDiagnostics;
  var list = document.getElementById("sessionList");
  var messages = document.getElementById("messages");
  var title = document.getElementById("chatTitle");
  var status = document.getElementById("status");
  var error = document.getElementById("error");
  var input = document.getElementById("messageInput");
  var send = document.getElementById("send");
  var stop = document.getElementById("stop");
  var memoryButton = document.getElementById("memoryButton");
  var memoryDialog = document.getElementById("memoryDialog");
  var memoryList = document.getElementById("memoryList");
  var memoryClose = document.getElementById("memoryClose");
  var toolLabels = { get_weather: "天气信息", get_learning_context: "学习情况", get_problem: "题目信息" };
  var memoryKinds = { preference: "偏好", goal: "目标", constraint: "约束", learning_context: "学习背景" };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function markdown(value) {
    var lines = String(value == null ? "" : value).replace(/\r\n?/g, "\n").split("\n");
    var html = [];
    function isTableSeparator(line) { return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line); }
    function cells(line) { return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (item) { return item.trim(); }); }
    function table(start) {
      var headers = cells(lines[start]); var row = start + 2; var rows = [];
      while (row < lines.length && lines[row].trim() && lines[row].indexOf("|") >= 0) { rows.push(cells(lines[row])); row += 1; }
      var out = "<div class=\"markdown-table-wrap\"><table><thead><tr>" + headers.map(function (cell) { return "<th>" + inline(cell) + "</th>"; }).join("") + "</tr></thead><tbody>";
      out += rows.map(function (items) { return "<tr>" + headers.map(function (_, index) { return "<td>" + inline(items[index] || "") + "</td>"; }).join("") + "</tr>"; }).join("");
      return { html: out + "</tbody></table></div>", next: row };
    }
    function list(start, ordered) {
      var tag = ordered ? "ol" : "ul"; var out = ["<" + tag + ">"]; var index = start;
      while (index < lines.length) {
        var match = lines[index].match(ordered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/);
        if (!match) break;
        out.push("<li>" + inline(match[1]) + "</li>"); index += 1;
      }
      return { html: out.join("") + "</" + tag + ">", next: index };
    }
    var i = 0;
    while (i < lines.length) {
      if (!lines[i].trim()) { i += 1; continue; }
      if (/^\s*```/.test(lines[i])) {
        var lang = lines[i].replace(/^\s*```/, "").trim(); var code = []; i += 1;
        while (i < lines.length && !/^\s*```/.test(lines[i])) { code.push(lines[i]); i += 1; }
        if (i < lines.length) i += 1;
        html.push("<pre><code" + (lang ? " data-language=\"" + esc(lang) + "\"" : "") + ">" + esc(code.join("\n")) + "</code></pre>"); continue;
      }
      var heading = lines[i].match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) { html.push("<h" + heading[1].length + ">" + inline(heading[2]) + "</h" + heading[1].length + ">"); i += 1; continue; }
      if (/^\s*(\*{3,}|-{3,}|_{3,})\s*$/.test(lines[i])) { html.push("<hr>"); i += 1; continue; }
      if (i + 1 < lines.length && lines[i].indexOf("|") >= 0 && isTableSeparator(lines[i + 1])) { var renderedTable = table(i); html.push(renderedTable.html); i = renderedTable.next; continue; }
      if (/^\s*[-*+]\s+/.test(lines[i])) { var unordered = list(i, false); html.push(unordered.html); i = unordered.next; continue; }
      if (/^\s*\d+[.)]\s+/.test(lines[i])) { var ordered = list(i, true); html.push(ordered.html); i = ordered.next; continue; }
      if (/^\s*>\s?/.test(lines[i])) { var quote = []; while (i < lines.length && /^\s*>/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, "")); i += 1; } html.push("<blockquote>" + inline(quote.join("\n")).replace(/\n/g, "<br>") + "</blockquote>"); continue; }
      var paragraph = [lines[i]]; i += 1;
      while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6})\s+/.test(lines[i]) && !/^\s*```/.test(lines[i]) && !/^\s*[-*+]\s+/.test(lines[i]) && !/^\s*\d+[.)]\s+/.test(lines[i]) && !/^\s*>/.test(lines[i])) { paragraph.push(lines[i]); i += 1; }
      html.push("<p>" + inline(paragraph.join("\n")).replace(/\n/g, "<br>") + "</p>");
    }
    return html.join("");
  }

  function inline(value) {
    var text = esc(value);
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+[^)]*)?\)/g, function (_, label, url) {
      var decoded = String(url).replace(/&amp;/g, "&"); var safe = /^(https?:\/\/|mailto:|\/|#)/i.test(decoded) && !/^(javascript|data|vbscript):/i.test(decoded);
      return safe ? "<a href=\"" + esc(decoded) + "\" target=\"_blank\" rel=\"noopener noreferrer\">" + label + "</a>" : label;
    });
    return text.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/__([^_]+)__/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>").replace(/(^|[^_])_([^_]+)_/g, "$1<em>$2</em>");
  }

  async function api(path, options) {
    var response = await fetch(path, Object.assign({ credentials: "same-origin", cache: "no-store" }, options || {}));
    if (response.status === 401) {
      location.replace("/pages/login.html?next=" + encodeURIComponent(location.pathname));
      throw new Error("登录状态已失效");
    }
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(payload.error || "请求失败");
    return payload;
  }

  function setError(value) { error.textContent = value || ""; }
  function setBusy(value) { input.disabled = !state.current || value; send.disabled = !state.current || value; stop.hidden = !value; status.textContent = value ? "生成中…" : (state.current ? "已连接" : "未连接"); }
  function resetStreamDiagnostics() {
    if (!STREAM_DIAGNOSTICS_ENABLED) return;
    state.streamDiagnostics.delta_count = 0;
    state.streamDiagnostics.render_count = 0;
    state.streamDiagnostics.max_render_ms = 0;
  }
  function updateAutoFollow() {
    var distance = messages.scrollHeight - messages.scrollTop - messages.clientHeight;
    state.autoFollow = distance <= AUTO_FOLLOW_THRESHOLD;
  }

  function scheduleScrollBottom() {
    if (!state.autoFollow || state.scrollFrame != null) return;
    var run = function () {
      state.scrollFrame = null;
      if (state.autoFollow) messages.scrollTop = messages.scrollHeight;
    };
    state.scrollFrame = window.requestAnimationFrame
      ? window.requestAnimationFrame(run)
      : window.setTimeout(run, 16);
  }

  function cancelStreamRender(bubble) {
    if (!bubble || bubble._streamRenderTimer == null) return;
    window.clearTimeout(bubble._streamRenderTimer);
    bubble._streamRenderTimer = null;
  }

  function renderStreamPreview(bubble) {
    if (!bubble) return;
    var started = performance.now();
    bubble.textContent = bubble._rawText || "";
    bubble._lastStreamRenderAt = Date.now();
    state.streamDiagnostics.render_count += 1;
    state.streamDiagnostics.max_render_ms = Math.max(
      state.streamDiagnostics.max_render_ms, performance.now() - started
    );
    scheduleScrollBottom();
  }

  function scheduleStreamRender(bubble) {
    if (!bubble || bubble._streamRenderTimer != null) return;
    var elapsed = Date.now() - (bubble._lastStreamRenderAt || 0);
    var delay = Math.max(0, STREAM_RENDER_INTERVAL - elapsed);
    bubble._streamRenderTimer = window.setTimeout(function () {
      bubble._streamRenderTimer = null;
      renderStreamPreview(bubble);
    }, delay);
  }

  function finalizeAssistant(bubble) {
    if (!bubble) return;
    cancelStreamRender(bubble);
    bubble.innerHTML = markdown(bubble._rawText || "");
    bubble.classList.remove("streaming");
    if (state.autoFollow) scheduleScrollBottom();
  }

  function actionHost(node) {
    if (node._actionHost) return node._actionHost;
    var host = document.createElement("div");
    host.className = "action-host";
    node.querySelector(".message-content").appendChild(host);
    node._actionHost = host;
    return host;
  }

  function setActionState(card, text) {
    var stateText = card.querySelector(".action-state");
    if (stateText) stateText.textContent = text;
  }

  function finishActionCard(card, className, text) {
    card.className = "action-card " + className;
    card.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
    var actions = card.querySelector(".action-actions");
    if (actions) actions.hidden = true;
    setActionState(card, text);
  }

  function actionTaskId(payload) {
    var result = payload && payload.result;
    var data = result && result.data;
    return String(
      (data && data.task_id) ||
      (result && result.task_id) ||
      ""
    );
  }

  function notifyLearningDataUpdated() {
    try {
      window.parent.postMessage({ type: "interviewforge:learning-data-updated" }, window.location.origin);
    } catch (_) { /* 独立页面没有可通知的父页面 */ }
  }

  function watchLeetCodeSync(card, taskId) {
    var startedAt = Date.now();
    var maxWaitMs = 180000;
    setActionState(card, "⏳ 已确认，正在同步 LeetCode 数据…");

    function poll() {
      api("/api/leetcode/sync/status?task_id=" + encodeURIComponent(taskId)).then(function (payload) {
        var logs = Array.isArray(payload.logs) ? payload.logs : [];
        var lastLog = logs.length ? String((logs[logs.length - 1] || {}).text || "") : "";
        if (payload.running) {
          setActionState(card, "⏳ " + (lastLog || "正在同步 LeetCode 数据…"));
          if (Date.now() - startedAt >= maxWaitMs) {
            finishActionCard(card, "success", "✓ 同步仍在后台运行，完成后可刷新学习数据");
            return;
          }
          window.setTimeout(poll, 1000);
          return;
        }
        if (payload.error) {
          finishActionCard(card, "error", "× " + String(payload.error));
          return;
        }
        var result = payload.result || {};
        var added = Number(result.submissions_added || 0);
        var solved = Number(result.solved_added || 0);
        finishActionCard(card, "success", "✓ 同步完成：新增提交 " + added + " 条，新增已解决 " + solved + " 题");
        notifyLearningDataUpdated();
        reloadCurrentSession().catch(function () {});
      }).catch(function (err) {
        finishActionCard(card, "error", "× " + String(err.message || "同步状态读取失败"));
      });
    }

    poll();
  }

  function decideAction(card, actionId, decision) {
    card.querySelectorAll("button").forEach(function (button) { button.disabled = true; });
    setActionState(card, decision === "confirm" ? "正在确认操作…" : "正在取消操作…");
    api("/api/chat/actions/" + encodeURIComponent(actionId) + "/" + decision, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}"
    }).then(function (payload) {
      if (decision === "confirm" && payload.ok && payload.status === "succeeded") {
        var taskId = actionTaskId(payload);
        if (taskId && payload.result && payload.result.tool === "sync_leetcode") {
          card.className = "action-card success";
          var actions = card.querySelector(".action-actions");
          if (actions) actions.hidden = true;
          watchLeetCodeSync(card, taskId);
        } else {
          finishActionCard(card, "success", "✓ " + String(payload.display || "操作已完成"));
        }
      } else if (decision === "cancel" && payload.ok) {
        finishActionCard(card, "cancelled", "已取消");
      } else {
        finishActionCard(card, "error", "× " + String(payload.display || "操作未完成"));
      }
    }).catch(function (err) {
      finishActionCard(card, "error", "× " + String(err.message || "操作暂时不可用"));
    });
  }

  function renderActionCard(action, host) {
    var card = document.createElement("div"); card.className = "action-card";
    var heading = document.createElement("strong"); heading.textContent = String(action.display_name || "需要确认的操作");
    var text = document.createElement("div"); text.className = "action-description";
    text.textContent = "AI 希望执行：" + String(action.message || action.confirmation_text || "该操作");
    var stateText = document.createElement("div"); stateText.className = "action-state";
    var actions = document.createElement("div"); actions.className = "action-actions";
    var confirm = document.createElement("button"); confirm.className = "button primary"; confirm.type = "button"; confirm.textContent = "确认";
    var cancel = document.createElement("button"); cancel.className = "button"; cancel.type = "button"; cancel.textContent = "取消";
    confirm.addEventListener("click", function () { decideAction(card, action.action_id, "confirm"); });
    cancel.addEventListener("click", function () { decideAction(card, action.action_id, "cancel"); });
    actions.appendChild(confirm); actions.appendChild(cancel);
    card.appendChild(heading); card.appendChild(text); card.appendChild(stateText); card.appendChild(actions);
    host.appendChild(card);
    return card;
  }

  function renderPendingActions(items) {
    items.forEach(function (item) {
      var node = document.createElement("div"); node.className = "message assistant";
      var content = document.createElement("div"); content.className = "message-content";
      node.appendChild(content); messages.appendChild(node);
      renderActionCard(item, actionHost(node));
    });
  }

  function renderMemories(items) {
    if (!items.length) { memoryList.innerHTML = '<div class="memory-empty">暂时没有保存的长期记忆。</div>'; return; }
    memoryList.textContent = "";
    items.forEach(function (item) {
      var row = document.createElement("div"); row.className = "memory-item";
      var content = document.createElement("div"); content.className = "memory-item-content";
      var text = document.createElement("div"); text.className = "memory-item-text";
      text.textContent = (memoryKinds[item.kind] || "记忆") + "：" + String(item.display_text || "");
      var meta = document.createElement("div"); meta.className = "memory-item-meta";
      meta.textContent = (item.source_type === "explicit" ? "你明确告诉我的" : "根据对话推断") + " · " + (window.InterviewForgeTime ? InterviewForgeTime.formatDateTime(item.updated_at) : String(item.updated_at || ""));
      content.appendChild(text); content.appendChild(meta);
      var remove = document.createElement("button"); remove.className = "button"; remove.type = "button"; remove.textContent = "删除";
      remove.addEventListener("click", function () {
        remove.disabled = true;
        api("/api/chat/memories/" + encodeURIComponent(item.id), { method: "DELETE" })
          .then(function () { loadMemories(); })
          .catch(function () { remove.disabled = false; });
      });
      row.appendChild(content); row.appendChild(remove); memoryList.appendChild(row);
    });
  }

  async function loadMemories() {
    var payload = await api("/api/chat/memories");
    renderMemories(payload.items || []);
  }

  function renderSessions() {
    if (!state.sessions.length) { list.innerHTML = '<div class="empty">还没有会话，点击“新建”。</div>'; return; }
    list.innerHTML = state.sessions.map(function (item) {
      var updated = window.InterviewForgeTime ? InterviewForgeTime.formatDateTime(item.updated_at) : String(item.updated_at || "");
      return '<button class="session-item ' + (item.id === state.current ? "active" : "") + '" type="button" data-session="' + esc(item.id) + '"><span class="session-title">' + esc(item.title) + '</span><span class="session-time">' + esc(updated) + '</span></button>';
    }).join("");
    list.querySelectorAll("[data-session]").forEach(function (node) { node.addEventListener("click", function () { selectSession(node.getAttribute("data-session")); }); });
  }

  function formatMessageTime(value) {
    if (!value) return "";
    try {
      return window.InterviewForgeTime
        ? InterviewForgeTime.formatDateTime(value)
        : String(value);
    } catch (_) {
      return String(value);
    }
  }

  function setMessageTime(node, value) {
    if (!node || !value) return;
    var time = node.querySelector(".message-time");
    if (!time) return;
    time.textContent = formatMessageTime(value);
    time.hidden = !time.textContent;
    time.setAttribute("title", time.textContent);
  }

  function renderMessage(item, target) {
    var node = document.createElement("div");
    node.className = "message " + (item.role === "user" ? "user" : "assistant");
    var content = document.createElement("div");
    content.className = "message-content";
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = item.role === "assistant" ? markdown(item.content) : esc(item.content);
    var time = document.createElement("div");
    time.className = "message-time";
    time.hidden = !item.created_at;
    time.textContent = formatMessageTime(item.created_at);
    content.appendChild(bubble);
    content.appendChild(time);
    node.appendChild(content);
    (target || messages).appendChild(node);
    return node;
  }

  function renderAssistantTurn() {
    var node = renderMessage({ role: "assistant", content: "" });
    var content = node.querySelector(".message-content");
    var toolStatus = document.createElement("div");
    toolStatus.className = "tool-status";
    toolStatus.setAttribute("aria-live", "polite");
    content.appendChild(toolStatus);
    node._toolRows = Object.create(null);
    node._toolStatus = toolStatus;
    actionHost(node);
    return node;
  }

  function ensureAssistantNode() {
    if (!state.assistantNode) state.assistantNode = renderAssistantTurn();
    return state.assistantNode;
  }

  function updateToolStatus(name, payload) {
    if (!state.assistantNode || !state.assistantNode._toolStatus) return;
    var callKey = String(payload.call_id || name || "tool");
    var row = state.assistantNode._toolRows[callKey];
    if (!row) {
      row = document.createElement("div");
      row.className = "tool-status-item";
      state.assistantNode._toolRows[callKey] = row;
      state.assistantNode._toolStatus.appendChild(row);
    }
    var toolName = String(payload.name || "");
    var label = payload.display_name || row.dataset.label || toolLabels[toolName] || "工具";
    if (name === "tool.start") row.dataset.label = label;
    if (name === "tool.start") {
      row.className = "tool-status-item pending";
      row.textContent = "○ 正在查询" + label + "…";
    } else if (name === "tool.done") {
      row.className = "tool-status-item done";
      row.textContent = "✓ 已获取" + label;
    } else {
      row.className = "tool-status-item error";
      row.textContent = "× " + String(payload.message || "工具暂时不可用");
    }
  }

  async function selectSession(id) {
    if (state.controller) state.controller.abort();
    if (state.assistantNode) cancelStreamRender(state.assistantNode.querySelector(".bubble"));
    state.current = id;
    state.assistantNode = null;
    setError("");
    renderSessions();
    var payload = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/messages");
    title.textContent = payload.session.title;
    var fragment = document.createDocumentFragment();
    (payload.items || []).forEach(function (item) { renderMessage(item, fragment); });
    messages.replaceChildren(fragment);
    var actions = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/actions?status=pending");
    renderPendingActions(actions.items || []);
    input.disabled = false; send.disabled = false; status.textContent = "已连接";
    try { localStorage.setItem("forge-ai-session", id); } catch (_) { }
    state.autoFollow = true;
    scheduleScrollBottom();
  }

  async function refreshSessionList() {
    var payload = await api("/api/chat/sessions");
    state.sessions = payload.items || [];
    renderSessions();
    var current = state.sessions.find(function (item) { return item.id === state.current; });
    if (current) title.textContent = current.title;
  }

  async function loadSessions() {
    await refreshSessionList();
    if (!state.sessions.length) return;
    var saved = null; try { saved = localStorage.getItem("forge-ai-session"); } catch (_) { }
    await selectSession(state.sessions.some(function (item) { return item.id === saved; }) ? saved : state.sessions[0].id);
  }

  function currentPageContext() {
    if (state.pageContext) return state.pageContext;
    try {
      return window.InterviewForgeAI && window.InterviewForgeAI.getPageContext
        ? window.InterviewForgeAI.getPageContext() : null;
    } catch (_) { return null; }
  }

  function requestFreshPageContext() {
    if (!embedded || !window.parent || window.parent === window) return Promise.resolve(currentPageContext());
    var requestId = "page-context-" + Date.now() + "-" + (++state.contextRequestSerial);
    return new Promise(function (resolve) {
      var settled = false;
      var timer = window.setTimeout(function () {
        if (settled) return;
        settled = true;
        delete state.pageContextWaiters[requestId];
        resolve(state.pageContext || null);
      }, 250);
      state.pageContextWaiters[requestId] = function (context) {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        delete state.pageContextWaiters[requestId];
        resolve(context || null);
      };
      window.parent.postMessage({
        type: "interviewforge:request-page-context",
        request_id: requestId
      }, window.location.origin);
    });
  }

  async function reloadCurrentSession() {
    var id = state.current;
    if (!id) return;
    if (state.assistantNode) cancelStreamRender(state.assistantNode.querySelector(".bubble"));
    state.controller = null;
    try { await selectSession(id); } catch (err) { setError(err.message || "读取会话失败"); }
  }

  async function newSession() {
    setError("");
    var item = await api("/api/chat/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    state.sessions.unshift(item); state.current = item.id; renderSessions(); await selectSession(item.id); input.focus();
  }

  function parseSse(buffer, onEvent) {
    var frames = buffer.split("\n\n");
    var rest = frames.pop();
    frames.forEach(function (frame) {
      var name = "message", data = "";
      frame.split("\n").forEach(function (line) { if (line.indexOf("event:") === 0) name = line.slice(6).trim(); if (line.indexOf("data:") === 0) data += line.slice(5).trim(); });
      if (data) { try { onEvent(name, JSON.parse(data)); } catch (_) { } }
    });
    return rest;
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (!state.current || state.controller) return;
    var text = input.value.trim(); if (!text) return;
    setError("");
    resetStreamDiagnostics();
    state.autoFollow = messages.scrollHeight - messages.scrollTop - messages.clientHeight <= AUTO_FOLLOW_THRESHOLD;
    input.value = ""; var userNode = renderMessage({ role: "user", content: text });
    state.streamFailed = false; state.streamCompleted = false;
    state.controller = new AbortController(); setBusy(true); scheduleScrollBottom();
    try {
      // The drawer receives context asynchronously. Ask for a fresh snapshot
      // immediately before sending so scroll/selection changes are current.
      var pageContext = await requestFreshPageContext();
      var requestBody = { message: text };
      if (pageContext) requestBody.page_context = pageContext;
      var response = await fetch("/api/chat/sessions/" + encodeURIComponent(state.current) + "/stream", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestBody), signal: state.controller.signal });
      if (!response.ok) { var failed = await response.json().catch(function () { return {}; }); throw new Error(failed.error || "发送失败"); }
      var reader = response.body.getReader(), decoder = new TextDecoder(), buffer = "";
      function onEvent(name, payload) {
        if (name === "message.start") {
          setMessageTime(userNode, payload && payload.created_at);
          state.assistantNode = renderAssistantTurn();
          var startedBubble = state.assistantNode.querySelector(".bubble");
          startedBubble._rawText = "";
          startedBubble.classList.add("streaming");
          startedBubble.textContent = "";
        }
        else if (name === "message.delta" && state.assistantNode) {
          var bubble = state.assistantNode.querySelector(".bubble");
          bubble._rawText = (bubble._rawText || "") + String(payload.delta || "");
          state.streamDiagnostics.delta_count += 1;
          scheduleStreamRender(bubble);
        }
        else if (name === "tool.start" || name === "tool.done" || name === "tool.error") { updateToolStatus(name, payload || {}); scheduleScrollBottom(); }
        else if (name === "tool.confirmation_required") {
          // A confirmation is durable server state.  If a browser misses the
          // preceding message.start frame, still materialize the card instead
          // of silently dropping the only actionable event.
          renderActionCard(payload || {}, actionHost(ensureAssistantNode()));
          scheduleScrollBottom();
        }
        else if (name === "message.done") {
          state.streamCompleted = true;
          if (state.assistantNode) {
            finalizeAssistant(state.assistantNode.querySelector(".bubble"));
            setMessageTime(state.assistantNode, payload && payload.created_at);
          }
          status.textContent = "已连接";
        }
        else if (name === "error") { state.streamFailed = true; setError(payload.message || "AI 暂时不可用"); }
      }
      while (true) { var part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); buffer = parseSse(buffer, onEvent); }
      parseSse(buffer + "\n\n", onEvent);
      if (state.streamFailed || !state.streamCompleted) {
        var streamError = error.textContent;
        await reloadCurrentSession();
        setError(streamError || "AI 响应不完整，请重试");
      } else {
        await refreshSessionList();
      }
    } catch (err) {
      if (err.name === "AbortError" && state.cancelRequested) {
        state.cancelRequested = false;
        await reloadCurrentSession();
      } else if (err.name !== "AbortError") {
        var networkError = err.message || "发送失败";
        await reloadCurrentSession();
        setError(networkError);
      }
    }
    finally { state.controller = null; setBusy(false); state.assistantNode = null; }
  }

  document.getElementById("newSession").addEventListener("click", function () { newSession().catch(function (err) { setError(err.message); }); });
  memoryButton.addEventListener("click", function () { memoryDialog.showModal(); loadMemories().catch(function (err) { memoryList.textContent = err.message || "读取失败"; }); });
  memoryClose.addEventListener("click", function () { memoryDialog.close(); });
  document.getElementById("composer").addEventListener("submit", sendMessage);
  input.addEventListener("keydown", function (event) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.getElementById("composer").requestSubmit(); } });
  stop.addEventListener("click", function () {
    if (state.controller) { state.cancelRequested = true; state.controller.abort(); }
  });
  messages.addEventListener("scroll", updateAutoFollow, { passive: true });
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin || !event.data) return;
    if (event.data.type === "interviewforge:page-context") {
      state.pageContext = event.data.context || null;
      if (event.data.request_id && state.pageContextWaiters[event.data.request_id]) {
        state.pageContextWaiters[event.data.request_id](state.pageContext);
      }
    }
  });
  if (embedded) requestFreshPageContext();
  loadSessions().catch(function (err) { setError(err.message || "读取会话失败"); list.innerHTML = '<div class="empty">读取失败，请刷新重试。</div>'; });
}());
