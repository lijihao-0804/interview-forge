(function () {
  "use strict";

  var embedded = new URLSearchParams(window.location.search).get("embedded") === "1";
  document.body.classList.toggle("embedded", embedded);
  var state = {
    sessions: [], current: null, controller: null, assistantNode: null,
    account: "", phase: "loading", pending: null, pendingBySession: Object.create(null),
    recoveryTimer: null, pageContext: null,
    pageContextWaiters: Object.create(null), contextRequestSerial: 0, sessionLoadSerial: 0,
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
  var retryTurn = document.getElementById("retryTurn");
  var editTurn = document.getElementById("editTurn");
  var memoryButton = document.getElementById("memoryButton");
  var memoryDialog = document.getElementById("memoryDialog");
  var memoryList = document.getElementById("memoryList");
  var memoryClose = document.getElementById("memoryClose");
  var authPromise = null;
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

  function authError() {
    var problem = new Error("登录后才能使用 AI 助手");
    problem.code = "AUTH_REQUIRED";
    return problem;
  }

  function showAuthGate() {
    if (document.getElementById("ai-auth-gate")) return;
    input.disabled = true;
    send.disabled = true;
    status.textContent = "游客模式";
    var next = location.pathname + location.search + location.hash;
    var gate = document.createElement("section");
    gate.id = "ai-auth-gate";
    gate.setAttribute("role", "dialog");
    gate.setAttribute("aria-modal", "true");
    gate.innerHTML = '<div class="ai-auth-card"><h2>登录后使用 AI 助手</h2>' +
      '<p>AI 对话、记忆和个人学习上下文属于账号私有数据。游客仍可返回题解、书架和搜索继续阅读。</p>' +
      '<div class="ai-auth-actions"><a href="/index.html">返回首页</a>' +
      '<a href="/pages/register.html?next=' + encodeURIComponent(next) + '">注册</a>' +
      '<a class="primary" href="/pages/login.html?next=' + encodeURIComponent(next) + '">登录</a></div></div>';
    docsBodyAppendGate(gate);
  }

  function docsBodyAppendGate(gate) {
    if (!document.getElementById("ai-auth-style")) {
      var style = document.createElement("style");
      style.id = "ai-auth-style";
      style.textContent = "#ai-auth-gate{position:fixed;inset:0;z-index:10020;display:grid;place-items:center;padding:20px;background:rgba(12,18,30,.58);backdrop-filter:blur(4px)}.ai-auth-card{width:min(100%,440px);padding:26px;border-radius:16px;background:var(--panel,#fff);color:var(--text,#182235);border:1px solid var(--line,#dce2ec);box-shadow:0 24px 70px rgba(10,14,22,.3);font:15px/1.65 system-ui,'Microsoft YaHei',sans-serif}.ai-auth-card h2{margin:0;font-size:21px}.ai-auth-card p{margin:10px 0 0;color:var(--muted,#647188)}.ai-auth-actions{display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap;margin-top:20px}.ai-auth-actions a{padding:8px 13px;border:1px solid var(--line,#dce2ec);border-radius:9px;color:inherit;text-decoration:none;font-weight:650}.ai-auth-actions a.primary{background:var(--brand,#5654d4);border-color:var(--brand,#5654d4);color:#fff}";
      document.head.appendChild(style);
    }
    document.body.appendChild(gate);
    gate.querySelector(".primary").focus();
  }

  function ensureAuthenticated() {
    if (!authPromise) {
      authPromise = fetch("/api/me", { credentials: "same-origin", cache: "no-store" })
        .then(function (response) {
          if (response.status === 401) return false;
          if (!response.ok) throw new Error("暂时无法确认登录状态，请稍后重试");
          return response.json().then(function (user) {
            state.account = user && user.username || "";
            return !!state.account;
          });
        })
        .catch(function () { return false; });
    }
    return authPromise.then(function (authenticated) {
      if (!authenticated) showAuthGate();
      return authenticated;
    });
  }

  async function api(path, options) {
    if (!(await ensureAuthenticated())) throw authError();
    var response = await fetch(path, Object.assign({ credentials: "same-origin", cache: "no-store" }, options || {}));
    if (response.status === 401) {
      authPromise = Promise.resolve(false);
      showAuthGate();
      throw authError();
    }
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) {
      var failure = new Error(payload.error || "请求失败");
      failure.status = response.status;
      failure.category = payload.error_category;
      throw failure;
    }
    return payload;
  }

  function setError(value) { error.textContent = value || ""; }
  function setPhase(phase) {
    state.phase = phase;
    var ready = phase === "ready" && !!state.current;
    input.disabled = !ready;
    send.disabled = !ready;
    send.hidden = phase === "retry" || phase === "check";
    stop.hidden = phase !== "preparing" && phase !== "stream";
    stop.disabled = !!(state.pending && state.pending.cancelRequested);
    retryTurn.hidden = phase !== "retry" && phase !== "check";
    retryTurn.textContent = phase === "retry" ? "重试原消息" : "检查状态";
    editTurn.hidden = phase !== "retry";
    var labels = { loading: "读取会话中…", ready: "已连接", preparing: "正在发送…",
      stream: "生成中…", checking: "正在核对原请求…", active: "原请求仍在处理…",
      retry: "等待重试", check: "等待核对" };
    status.textContent = labels[phase];
  }
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
    list.querySelectorAll("[data-session]").forEach(function (node) {
      node.addEventListener("click", function () {
        var id = node.getAttribute("data-session");
        if (id !== state.current || state.phase === "loading") {
          selectSession(id).catch(function (err) { if (id === state.current) setError(err.message); });
        }
      });
    });
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

  function librarySourceUrl(raw) {
    if (typeof raw !== "string" || !/^\/(?:library|books)\//.test(raw)) return "";
    try {
      var path = decodeURIComponent(raw);
      if (!path.endsWith(".html") || /[%?#\\:\u0000-\u001f\u007f]/.test(path)) return "";
      if (path.split("/").slice(1).some(function (part) { return !part || part[0] === "."; })) return "";
      return raw;
    } catch (_) { return ""; }
  }

  function renderLibrarySources(content, sources) {
    if (!Array.isArray(sources) || !sources.length || content.querySelector(".library-sources")) return;
    var links = document.createElement("ul");
    sources.forEach(function (source) {
      var url = source && librarySourceUrl(source.url);
      if (!url || typeof source.title !== "string" || !source.title) return;
      var link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = (source.module_title ? source.module_title + " · " : "") + source.title;
      var row = document.createElement("li");
      row.appendChild(link);
      links.appendChild(row);
    });
    if (!links.childElementCount) return;
    var group = document.createElement("details");
    group.className = "library-sources";
    group.open = links.childElementCount <= 3;
    var summary = document.createElement("summary");
    summary.textContent = "本轮检索资料（" + links.childElementCount + "）";
    group.appendChild(summary);
    group.appendChild(links);
    content.insertBefore(group, content.querySelector(".message-time"));
  }

  function renderContextDetails(content, turnId) {
    if (!turnId || !state.current || content.querySelector(".context-details")) return;
    var sessionId = state.current;
    var details = document.createElement("details");
    details.className = "context-details";
    var summary = document.createElement("summary");
    summary.textContent = "上下文使用情况";
    var body = document.createElement("div");
    var labels = { learning: "学情", memory: "长期记忆", memory_persistence: "记忆保存状态",
      recent_actions: "操作状态", current_page: "当前页面", legacy_context: "参考资料" };
    details.append(summary, body);
    content.appendChild(details);

    function line(text) {
      var item = document.createElement("p");
      item.textContent = text;
      body.appendChild(item);
    }
    var loading = false, loaded = false;
    details.addEventListener("toggle", async function () {
      if (!details.open || loading || loaded) return;
      loading = true;
      body.textContent = "正在读取…";
      try {
        var report = await api("/api/chat/sessions/" + encodeURIComponent(sessionId) +
          "/turns/" + encodeURIComponent(turnId) + "/context");
        body.textContent = "";
        var prep = report.preparation || {};
        if (typeof prep.history_message_count === "number")
          line("准备上下文时，从 " + prep.history_message_count + " 条历史消息中选出 " + (prep.history_selected_count || 0) +
            " 条相关消息" + (prep.summary_present ? "，含历史摘要。" : "。"));
        if (prep.history_archived_count) line("较早的 " + prep.history_archived_count + " 条消息可按需回查。");
        if (prep.context_blocks && prep.context_blocks.length)
          line("准备阶段纳入：" + prep.context_blocks.map(function (key) { return labels[key]; }).join("、"));
        if (prep.context_blocks_shortened && prep.context_blocks_shortened.length)
          line("使用精简版：" + prep.context_blocks_shortened.map(function (key) { return labels[key]; }).join("、"));
        if (prep.context_blocks_rejected && prep.context_blocks_rejected.length)
          line("预算不足，未载入：" + prep.context_blocks_rejected.map(function (key) { return labels[key]; }).join("、"));
        (report.rounds || []).forEach(function (round) {
          var facts = [];
          if (typeof round.admitted_prompt_tokens === "number")
            facts.push((round.admitted === false ? "超过预算的输入估算 " : "输入估算 ") + round.admitted_prompt_tokens + " token");
          if (typeof round.provider_input_tokens === "number") facts.push("供应商报告 " + round.provider_input_tokens + " token");
          if (round.masked_tool_result_count) {
            var saved = round.tool_result_tokens_saved ? "，共节省约 " + round.tool_result_tokens_saved + " token" : "";
            facts.push("压缩 " + round.masked_tool_result_count + " 个旧工具结果" + saved);
          }
          if (round.budget_rejected_tool_result_count) facts.push(round.budget_rejected_tool_result_count + " 个工具结果超出预算");
          if (round.omitted_exchange_count) facts.push("省略 " + round.omitted_exchange_count + " 组历史");
          if (facts.length) line("第 " + round.round + " 次请求：" + facts.join("，"));
        });
        if (!body.childElementCount) line("这次回答没有详细的上下文指标。");
        loaded = true;
      } catch (err) {
        body.textContent = err.status === 404 ? "这次回答没有可用的上下文记录。" : "暂时未能读取，收起后展开可重试。";
        loaded = err.status === 404;
      } finally {
        loading = false;
      }
    });
  }

  function renderHistorySources(content, sources) {
    if (!Array.isArray(sources) || !sources.length || !state.current || content.querySelector(".history-source")) return;
    var session = state.current;
    sources.forEach(function (source) {
      if (!source || !Number.isSafeInteger(source.message_id) || !Number.isSafeInteger(source.offset) ||
          !Number.isInteger(source.length) || !/^[0-9a-f]{64}$/.test(source.sha256)) return;
      var details = document.createElement("details");
      details.className = "history-source";
      var summary = document.createElement("summary");
      summary.textContent = "核对原话 · 消息 #" + source.message_id;
      var quote = document.createElement("blockquote");
      details.append(summary, quote);
      content.insertBefore(details, content.querySelector(".message-time"));
      var loading = false, loaded = false;
      details.addEventListener("toggle", async function () {
        if (!details.open || loading || loaded) return;
        loading = true;
        quote.textContent = "正在读取原文…";
        try {
          var result = await api(sessionPath(session) + "/messages/" + source.message_id + "/excerpt?offset=" +
            source.offset + "&length=" + source.length + "&sha256=" + source.sha256);
          quote.textContent = result.excerpt;
          loaded = true;
        } catch (err) {
          loaded = err.status === 404;
          quote.textContent = loaded ? "这段原文已无法核对。" : "暂时无法读取，收起后展开可重试。";
        } finally { loading = false; }
      });
    });
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
    if (item.role === "assistant" && item.metadata) {
      renderLibrarySources(content, item.metadata.library_sources);
      renderHistorySources(content, item.metadata.history_sources);
      renderContextDetails(content, item.metadata.stream_message_id);
    }
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
      row.textContent = "✓ " + (payload.display || "已获取" + label);
    } else {
      row.className = "tool-status-item error";
      row.textContent = "× " + String(payload.message || "工具暂时不可用");
    }
  }

  function sessionPath(id) { return "/api/chat/sessions/" + encodeURIComponent(id); }

  function storageKey(sessionId) {
    var prefix = "forge-ai:" + encodeURIComponent(state.account);
    return sessionId ? prefix + ":pending:" + encodeURIComponent(sessionId) : prefix + ":selected";
  }

  function readPending(id) {
    if (state.pendingBySession[id]) return state.pendingBySession[id];
    try {
      var turn = JSON.parse(sessionStorage.getItem(storageKey(id)));
      if (turn && turn.sessionId === id && typeof turn.body === "string") {
        var body = JSON.parse(turn.body);
        if (typeof turn.key === "string" && body.client_request_id === turn.key && typeof body.message === "string" &&
            /^[A-Za-z0-9._:-]{1,128}$/.test(turn.key)) {
          state.pendingBySession[id] = turn;
          return turn;
        }
      }
    } catch (_) { /* Tab storage may be unavailable. */ }
    return null;
  }

  function rememberTurn(turn) {
    state.pendingBySession[turn.sessionId] = turn;
    state.pending = turn;
    try { sessionStorage.setItem(storageKey(turn.sessionId), JSON.stringify(turn)); } catch (_) { }
  }

  function forgetTurn(turn) {
    if (state.pending !== turn) return;
    state.pending = null;
    delete state.pendingBySession[turn.sessionId];
    try { sessionStorage.removeItem(storageKey(turn.sessionId)); } catch (_) { }
  }

  function isSelected(id, serial) { return state.current === id && state.sessionLoadSerial === serial; }

  async function reloadCurrentSession() {
    var id = state.current, serial = state.sessionLoadSerial;
    if (!id || state.controller) return;
    var path = sessionPath(id);
    var results = await Promise.all([api(path + "/messages"), api(path + "/actions?status=pending")]);
    if (!isSelected(id, serial) || state.controller) return;
    var payload = results[0];
    title.textContent = payload.session.title;
    var selected = state.sessions.find(function (item) { return item.id === id; });
    if (selected) { selected.title = payload.session.title; renderSessions(); }
    var fragment = document.createDocumentFragment();
    (payload.items || []).forEach(function (item) { renderMessage(item, fragment); });
    if (state.assistantNode) cancelStreamRender(state.assistantNode.querySelector(".bubble"));
    state.assistantNode = null;
    messages.replaceChildren(fragment);
    renderPendingActions(results[1].items || []);
    scheduleScrollBottom();
  }

  async function selectSession(id) {
    var serial = ++state.sessionLoadSerial;
    window.clearTimeout(state.recoveryTimer);
    if (state.controller) state.controller.abort();
    state.controller = null;
    if (state.assistantNode) cancelStreamRender(state.assistantNode.querySelector(".bubble"));
    state.assistantNode = null;
    state.current = id;
    state.pending = readPending(id);
    state.autoFollow = true;
    input.value = "";
    messages.replaceChildren();
    setError("");
    setPhase("loading");
    renderSessions();
    try { sessionStorage.setItem(storageKey(), id); } catch (_) { }
    try { localStorage.setItem(storageKey(), id); } catch (_) { }
    if (state.pending) {
      await recoverTurn(state.pending, serial);
    } else {
      await reloadCurrentSession();
      if (isSelected(id, serial)) setPhase("ready");
    }
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
    var saved = null;
    try { saved = sessionStorage.getItem(storageKey()); } catch (_) { }
    try { saved = saved || localStorage.getItem(storageKey()) || localStorage.getItem("forge-ai-session"); } catch (_) { }
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

  async function newSession() {
    setError("");
    var item = await api("/api/chat/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    state.sessions.unshift(item);
    await selectSession(item.id);
    input.focus();
  }

  async function readEvents(body, signal, onEvent) {
    var reader = body.getReader(), decoder = new TextDecoder();
    var buffer = "", name = "message", data = [], terminal = false;
    function consume(chunk, atEnd) {
      buffer += chunk;
      var start = 0, breaks = /\r\n|\r|\n/g, match;
      while ((match = breaks.exec(buffer))) {
        if (!atEnd && match[0] === "\r" && breaks.lastIndex === buffer.length) break;
        var line = buffer.slice(start, match.index);
        start = breaks.lastIndex;
        if (!line) {
          if (data.length) {
            onEvent(name, JSON.parse(data.join("\n")));
            if (name === "message.done" || name === "error") { terminal = true; break; }
          }
          name = "message";
          data = [];
        } else if (line.indexOf("event:") === 0) {
          name = line.slice(6).trim();
        } else if (line.indexOf("data:") === 0) {
          data.push(line.slice(5).replace(/^ /, ""));
        }
      }
      buffer = buffer.slice(start);
    }
    function cancel() { reader.cancel().catch(function () {}); }
    signal.addEventListener("abort", cancel, { once: true });
    try {
      while (!signal.aborted && !terminal) {
        var part = await reader.read();
        if (part.done) { consume(decoder.decode(), true); break; }
        consume(decoder.decode(part.value, { stream: true }), false);
      }
    } finally {
      signal.removeEventListener("abort", cancel);
      cancel();
      reader.releaseLock();
    }
  }

  async function recoverTurn(turn, serial, attempt, reason) {
    function current() { return state.pending === turn && isSelected(turn.sessionId, serial); }
    if (!current()) return;
    window.clearTimeout(state.recoveryTimer);
    setPhase("checking");
    try {
      var result;
      try {
        result = await api(sessionPath(turn.sessionId) + "/requests/" + encodeURIComponent(turn.key));
      } catch (err) {
        if (err.status !== 404 || err.category !== "chat_request_not_found") throw err;
        result = { status: "retryable" };
      }
      if (!current()) return;
      if (result.status === "in_progress") {
        if (!attempt) await reloadCurrentSession();
        if (!current()) return;
        setPhase("active");
        setError(turn.cancelRequested ? "已请求停止，正在等服务器确认结果。" : "连接已中断，正在等待原请求的结果。");
        var next = (attempt || 0) + 1;
        state.recoveryTimer = window.setTimeout(function () {
          recoverTurn(turn, serial, next, reason);
        }, Math.min(1000 * Math.pow(2, Math.min(next - 1, 3)), 8000));
        return;
      }
      if (["completed", "retryable", "interrupted"].indexOf(result.status) < 0) throw new Error();
      // A terminal status is only useful once both committed messages and pending actions are visible.
      await reloadCurrentSession();
      if (!current()) return;
      if (result.status === "retryable" && !turn.cancelRequested) {
        input.value = JSON.parse(turn.body).message;
        setError((reason ? reason.replace(/[。.!]+$/, "") + "。" : "") + "可重试原消息，或编辑后作为新消息发送。");
        setPhase("retry");
        return;
      }
      input.value = "";
      forgetTurn(turn);
      setPhase("ready");
      if (result.status === "interrupted") {
        var details = [];
        if (result.action_recorded) details.push("此轮已记录操作，待确认的操作会显示在会话中。");
        if (result.memory_saved) details.push("已保存的记忆可在“记忆”中查看。");
        setError("本轮回答已中断。" + (details.join("") || "此轮已保存操作或记忆。"));
      }
      else if (turn.cancelRequested && result.status === "retryable") setError("已停止生成。");
      else setError("");
    } catch (err) {
      if (!current() || err.code === "AUTH_REQUIRED") return;
      setPhase("check");
      setError("暂时无法核对原请求，恢复连接后可检查状态。");
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (!state.current || state.phase !== "ready" || state.pending) return;
    var text = input.value.trim(); if (!text) return;
    var id = state.current, serial = state.sessionLoadSerial;
    var controller = new AbortController();
    state.controller = controller;
    setPhase("preparing");
    setError("");
    resetStreamDiagnostics();
    try {
      var pageContext = await requestFreshPageContext();
      if (!isSelected(id, serial) || controller.signal.aborted) return;
      var key = Array.from(window.crypto.getRandomValues(new Uint8Array(16)), function (byte) {
        return byte.toString(16).padStart(2, "0");
      }).join("");
      var requestBody = { client_request_id: key, message: text };
      if (pageContext) requestBody.page_context = pageContext;
      var turn = { sessionId: id, key: key, body: JSON.stringify(requestBody), cancelRequested: false };
      rememberTurn(turn);
      await streamTurn(turn);
    } catch (err) {
      if (isSelected(id, serial)) setError(err.message || "发送失败");
    } finally {
      if (state.controller === controller) {
        state.controller = null;
        setPhase("ready");
      }
    }
  }

  async function streamTurn(turn) {
    var serial = state.sessionLoadSerial, controller = new AbortController();
    state.controller = controller;
    state.autoFollow = messages.scrollHeight - messages.scrollTop - messages.clientHeight <= AUTO_FOLLOW_THRESHOLD;
    input.value = "";
    var userNode = renderMessage({ role: "user", content: JSON.parse(turn.body).message });
    var completed = false, streamError = "";
    setPhase("stream");
    setError("");
    scheduleScrollBottom();
    try {
      var response = await fetch(sessionPath(turn.sessionId) + "/stream", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: turn.body, signal: controller.signal
      });
      if (state.controller !== controller) return;
      if (response.status === 401) { authPromise = Promise.resolve(false); showAuthGate(); throw authError(); }
      if (!response.ok) {
        var failed = await response.json().catch(function () { return {}; });
        var failure = new Error(failed.error || "发送失败");
        failure.category = failed.error_category;
        throw failure;
      }
      if (!response.body || !(response.headers.get("Content-Type") || "").includes("text/event-stream")) {
        throw new Error("服务器未返回对话流");
      }
      function onEvent(name, payload) {
        if (state.controller !== controller || controller.signal.aborted || completed || streamError) return;
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
          completed = true;
          if (state.assistantNode) {
            finalizeAssistant(state.assistantNode.querySelector(".bubble"));
            setMessageTime(state.assistantNode, payload && payload.created_at);
            renderLibrarySources(state.assistantNode.querySelector(".message-content"), payload && payload.library_sources);
            renderHistorySources(state.assistantNode.querySelector(".message-content"), payload && payload.history_sources);
            renderContextDetails(state.assistantNode.querySelector(".message-content"), payload && payload.message_id);
            scheduleScrollBottom();
          }
        }
        else if (name === "error") { streamError = payload.message || "AI 暂时不可用"; }
      }
      await readEvents(response.body, controller.signal, onEvent);
    } catch (err) {
      if (state.controller !== controller) return;
      if (err.code === "AUTH_REQUIRED") { state.controller = null; return; }
      if (err.category === "idempotency_conflict") {
        state.controller = null;
        forgetTurn(turn);
        try { await reloadCurrentSession(); } catch (_) { }
        if (isSelected(turn.sessionId, serial)) {
          setPhase("ready");
          input.value = JSON.parse(turn.body).message;
          setError("该请求标识已用于其他内容。请核对会话后再发送。");
        }
        return;
      }
      if (err.name !== "AbortError") streamError = err.name === "TypeError" ? "连接中断" : (err.message || "连接中断");
    }
    if (state.controller !== controller) return;
    state.controller = null;
    if (completed && state.assistantNode) {
      state.assistantNode = null;
      forgetTurn(turn);
      setPhase("ready");
      try { await refreshSessionList(); } catch (_) { /* The committed reply is already displayed. */ }
    } else {
      await recoverTurn(turn, serial, 0, streamError);
    }
  }

  document.getElementById("newSession").addEventListener("click", function () { newSession().catch(function (err) { setError(err.message); }); });
  memoryButton.addEventListener("click", function () { memoryDialog.showModal(); loadMemories().catch(function (err) { memoryList.textContent = err.message || "读取失败"; }); });
  memoryClose.addEventListener("click", function () { memoryDialog.close(); });
  document.getElementById("composer").addEventListener("submit", sendMessage);
  input.addEventListener("keydown", function (event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      document.getElementById("composer").requestSubmit();
    }
  });
  stop.addEventListener("click", function () {
    if (!state.controller) return;
    if (state.pending) {
      state.pending.cancelRequested = true;
      rememberTurn(state.pending);
    }
    stop.disabled = true;
    state.controller.abort();
  });
  retryTurn.addEventListener("click", function () {
    if (!state.pending) return;
    if (state.phase === "check") recoverTurn(state.pending, state.sessionLoadSerial);
    else if (state.phase === "retry") streamTurn(state.pending);
  });
  editTurn.addEventListener("click", function () {
    if (state.phase !== "retry" || !state.pending) return;
    forgetTurn(state.pending);
    setError("");
    setPhase("ready");
    input.focus();
  });
  window.addEventListener("online", function () {
    if (state.pending && state.phase === "check") recoverTurn(state.pending, state.sessionLoadSerial);
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
  ensureAuthenticated().then(function (authenticated) {
    if (!authenticated) {
      list.innerHTML = '<div class="empty">登录后可查看 AI 会话。</div>';
      return;
    }
    return loadSessions();
  }).catch(function (err) {
    if (err.code !== "AUTH_REQUIRED") setError(err.message || "读取会话失败");
    list.innerHTML = '<div class="empty">读取失败，请刷新重试。</div>';
  });
}());
