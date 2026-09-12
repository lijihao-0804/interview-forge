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
    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = item.role === "assistant" ? markdown(item.content) : esc(item.content);
    node.appendChild(bubble);
    messages.appendChild(node);
    return node;
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
        if (name === "message.start") { state.assistantNode = renderMessage({ role: "assistant", content: "" }); state.assistantNode.querySelector(".bubble").textContent = ""; }
        else if (name === "message.delta" && state.assistantNode) { var bubble = state.assistantNode.querySelector(".bubble"); bubble.dataset.raw = (bubble.dataset.raw || "") + String(payload.delta || ""); bubble.innerHTML = markdown(bubble.dataset.raw); scrollBottom(); }
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
  document.getElementById("composer").addEventListener("submit", sendMessage);
  input.addEventListener("keydown", function (event) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.getElementById("composer").requestSubmit(); } });
  stop.addEventListener("click", function () { if (state.controller) state.controller.abort(); });
  loadSessions().catch(function (err) { setError(err.message || "读取会话失败"); list.innerHTML = '<div class="empty">读取失败，请刷新重试。</div>'; });
}());
