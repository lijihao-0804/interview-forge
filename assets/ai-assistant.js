(function () {
  "use strict";

  var state = { sessions: [], current: null, controller: null, assistantNode: null };
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
    var text = esc(value);
    var blocks = [];
    text = text.replace(/```([\w-]*)\n?([\s\S]*?)```/g, function (_, lang, code) {
      blocks.push("<pre><code" + (lang ? " data-language=\"" + esc(lang) + "\"" : "") + ">" + code.replace(/\n$/, "") + "</code></pre>");
      return "\u0000BLOCK" + (blocks.length - 1) + "\u0000";
    });
    text = text.split(/\n\n+/).map(function (part) {
      if (/^\s*[-*] /.test(part)) {
        return "<ul>" + part.split(/\n/).map(function (line) { return "<li>" + inline(line.replace(/^\s*[-*] /, "")) + "</li>"; }).join("") + "</ul>";
      }
      return "<p>" + inline(part).replace(/\n/g, "<br>") + "</p>";
    }).join("");
    text = text.replace(/\u0000BLOCK(\d+)\u0000/g, function (_, index) { return blocks[Number(index)]; });
    return text;
  }

  function inline(value) {
    return value.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
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
  function scrollBottom() { messages.scrollTop = messages.scrollHeight; }

  function renderMemories(items) {
    if (!items.length) { memoryList.innerHTML = '<div class="memory-empty">暂时没有保存的长期记忆。</div>'; return; }
    memoryList.textContent = "";
    items.forEach(function (item) {
      var row = document.createElement("div"); row.className = "memory-item";
      var content = document.createElement("div"); content.className = "memory-item-content";
      var text = document.createElement("div"); text.className = "memory-item-text";
      text.textContent = (memoryKinds[item.kind] || "记忆") + "：" + String(item.display_text || "");
      var meta = document.createElement("div"); meta.className = "memory-item-meta";
      meta.textContent = (item.source_type === "explicit" ? "你明确告诉我的" : "根据对话推断") + " · " + String(item.updated_at || "");
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
      return '<button class="session-item ' + (item.id === state.current ? "active" : "") + '" type="button" data-session="' + esc(item.id) + '"><span class="session-title">' + esc(item.title) + '</span><span class="session-time">' + esc(item.updated_at || "") + '</span></button>';
    }).join("");
    list.querySelectorAll("[data-session]").forEach(function (node) { node.addEventListener("click", function () { selectSession(node.getAttribute("data-session")); }); });
  }

  function renderMessage(item) {
    var node = document.createElement("div");
    node.className = "message " + (item.role === "user" ? "user" : "assistant");
    var content = document.createElement("div");
    content.className = "message-content";
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = item.role === "assistant" ? markdown(item.content) : esc(item.content);
    content.appendChild(bubble);
    node.appendChild(content);
    messages.appendChild(node);
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
    return node;
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
    var label = payload.display_name || toolLabels[toolName] || "工具信息";
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
    state.current = id;
    state.assistantNode = null;
    setError("");
    renderSessions();
    var payload = await api("/api/chat/sessions/" + encodeURIComponent(id) + "/messages");
    title.textContent = payload.session.title;
    messages.innerHTML = "";
    (payload.items || []).forEach(renderMessage);
    input.disabled = false; send.disabled = false; status.textContent = "已连接";
    try { localStorage.setItem("forge-ai-session", id); } catch (_) { }
    scrollBottom();
  }

  async function loadSessions() {
    var payload = await api("/api/chat/sessions");
    state.sessions = payload.items || [];
    renderSessions();
    if (!state.sessions.length) return;
    var saved = null; try { saved = localStorage.getItem("forge-ai-session"); } catch (_) { }
    await selectSession(state.sessions.some(function (item) { return item.id === saved; }) ? saved : state.sessions[0].id);
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
    setError(""); input.value = ""; renderMessage({ role: "user", content: text });
    state.controller = new AbortController(); setBusy(true); scrollBottom();
    try {
      var response = await fetch("/api/chat/sessions/" + encodeURIComponent(state.current) + "/stream", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }), signal: state.controller.signal });
      if (!response.ok) { var failed = await response.json().catch(function () { return {}; }); throw new Error(failed.error || "发送失败"); }
      var reader = response.body.getReader(), decoder = new TextDecoder(), buffer = "";
      function onEvent(name, payload) {
        if (name === "message.start") { state.assistantNode = renderAssistantTurn(); state.assistantNode.querySelector(".bubble").textContent = ""; }
        else if (name === "message.delta" && state.assistantNode) { var bubble = state.assistantNode.querySelector(".bubble"); bubble.dataset.raw = (bubble.dataset.raw || "") + String(payload.delta || ""); bubble.innerHTML = markdown(bubble.dataset.raw); scrollBottom(); }
        else if (name === "tool.start" || name === "tool.done" || name === "tool.error") { updateToolStatus(name, payload || {}); scrollBottom(); }
        else if (name === "message.done") { status.textContent = "已连接"; }
        else if (name === "error") { setError(payload.message || "AI 暂时不可用"); }
      }
      while (true) { var part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, { stream: true }); buffer = parseSse(buffer, onEvent); }
      parseSse(buffer + "\n\n", onEvent);
      await loadSessions();
    } catch (err) { if (err.name !== "AbortError") setError(err.message || "发送失败"); }
    finally { state.controller = null; setBusy(false); state.assistantNode = null; }
  }

  document.getElementById("newSession").addEventListener("click", function () { newSession().catch(function (err) { setError(err.message); }); });
  memoryButton.addEventListener("click", function () { memoryDialog.showModal(); loadMemories().catch(function (err) { memoryList.textContent = err.message || "读取失败"; }); });
  memoryClose.addEventListener("click", function () { memoryDialog.close(); });
  document.getElementById("composer").addEventListener("submit", sendMessage);
  input.addEventListener("keydown", function (event) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.getElementById("composer").requestSubmit(); } });
  stop.addEventListener("click", function () { if (state.controller) state.controller.abort(); });
  loadSessions().catch(function (err) { setError(err.message || "读取会话失败"); list.innerHTML = '<div class="empty">读取失败，请刷新重试。</div>'; });
}());
