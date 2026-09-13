(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function text(node, value) { node.textContent = value == null || value === "" ? "—" : String(value); }
  function fmtMs(value) { return value == null ? "—" : String(Math.round(Number(value))) + " ms"; }
  function fmtNumber(value) { return Number(value || 0).toLocaleString(); }
  function request(path) {
    return fetch(path, { credentials: "same-origin", cache: "no-store" }).then(function (response) {
      return response.json().then(function (data) { if (!response.ok) throw new Error(data.error || "请求失败"); return data; });
    });
  }
  function card(label, value) { var node = document.createElement("div"); node.className = "admin-v2-card"; var strong = document.createElement("strong"); text(strong, value); var span = document.createElement("span"); text(span, label); node.appendChild(strong); node.appendChild(span); return node; }
  function fillDl(node, values) { node.textContent = ""; Object.keys(values).forEach(function (key) { var dt = document.createElement("dt"); var dd = document.createElement("dd"); text(dt, key); text(dd, values[key]); node.appendChild(dt); node.appendChild(dd); }); }
  function fail(error) { var status = $("admin-v2-status"); status.className = "admin-v2-status error"; text(status, error && error.message ? error.message : "加载失败"); }
  function loadOverview() {
    return request("/api/admin/overview").then(function (data) {
      text($("admin-v2-status"), "已更新"); $("admin-v2-status").className = "admin-v2-status";
      var cards = $("admin-overview-cards"); cards.textContent = "";
      cards.appendChild(card("用户总数", data.users.total)); cards.appendChild(card("24 小时请求", data.requests.total_24h)); cards.appendChild(card("24 小时 AI 轮次", data.ai.turns_24h)); cards.appendChild(card("运行中任务", data.tasks.running));
      fillDl($("admin-overview-requests"), { "5xx": data.requests.error_5xx_24h, "错误率": (Number(data.requests.error_rate || 0) * 100).toFixed(2) + "%", "P95": fmtMs(data.requests.p95_ms) });
      fillDl($("admin-overview-ai"), { "成功率": (Number(data.ai.success_rate || 0) * 100).toFixed(2) + "%", "P95": fmtMs(data.ai.p95_ms), "输入 tokens": fmtNumber(data.ai.input_tokens), "输出 tokens": fmtNumber(data.ai.output_tokens) });
      fillDl($("admin-overview-system"), { "失败任务": data.tasks.failed, "用户库": data.storage.user_db_bytes, "磁盘剩余": data.storage.disk_free, "版本": data.system.version });
    });
  }
  function loadUsage() {
    var windowValue = $("admin-usage-window").value;
    return request("/api/admin/ai/usage?window=" + encodeURIComponent(windowValue)).then(function (data) {
      var cards = $("admin-usage-cards"); cards.textContent = "";
      cards.appendChild(card("轮次", data.turns)); cards.appendChild(card("成功率", (Number(data.success_rate || 0) * 100).toFixed(2) + "%")); cards.appendChild(card("平均耗时", fmtMs(data.avg_latency_ms))); cards.appendChild(card("估算费用", data.estimated_cost_usd == null ? "未配置" : "$" + data.estimated_cost_usd));
      var body = $("admin-usage-models"); body.textContent = ""; (data.models || []).forEach(function (item) { var tr = document.createElement("tr"); [item.model, item.turns, fmtNumber(item.input_tokens), fmtNumber(item.output_tokens), item.estimated_cost_usd == null ? "—" : "$" + item.estimated_cost_usd].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); body.appendChild(tr); });
    });
  }
  function loadTraces() {
    return request("/api/admin/ai/traces?window=" + encodeURIComponent($("admin-trace-window").value) + "&limit=100").then(function (data) { var body = $("admin-traces"); body.textContent = ""; (data.items || []).forEach(function (item) { var tr = document.createElement("tr"); tr.tabIndex = 0; tr.className = "admin-v2-clickable"; [item.finished_at, item.username, item.model, item.status, fmtMs(item.duration_ms), fmtNumber((item.input_tokens || 0) + (item.output_tokens || 0)), item.request_id].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); tr.onclick = function () { request("/api/admin/ai/traces/" + encodeURIComponent(item.trace_id) + "?username=" + encodeURIComponent(item.username)).then(function (detail) { var panel = $("admin-trace-detail"); panel.hidden = false; text(panel, JSON.stringify(detail, null, 2)); }).catch(fail); }; body.appendChild(tr); }); });
  }
  function loadLogs() {
    return request("/api/admin/logs?level=" + encodeURIComponent($("admin-log-level").value) + "&limit=100").then(function (data) { var body = $("admin-logs"); body.textContent = ""; (data.items || []).forEach(function (item) { var tr = document.createElement("tr"); [item.time, item.level, item.module, item.event, item.request_id, item.status, fmtMs(item.elapsed_ms)].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); body.appendChild(tr); }); });
  }
  function loadTab(name) { var work = name === "overview" ? loadOverview() : name === "usage" ? loadUsage() : name === "traces" ? loadTraces() : loadLogs(); work.catch(fail); }
  document.addEventListener("DOMContentLoaded", function () {
    if (!$("admin-observability")) return;
    document.querySelectorAll("[data-admin-tab]").forEach(function (button) { button.addEventListener("click", function () { var name = button.getAttribute("data-admin-tab"); document.querySelectorAll("[data-admin-tab]").forEach(function (item) { item.classList.toggle("active", item === button); }); document.querySelectorAll("[data-admin-panel]").forEach(function (item) { item.classList.toggle("active", item.getAttribute("data-admin-panel") === name); }); loadTab(name); }); });
    $("admin-usage-refresh").onclick = loadUsage; $("admin-trace-refresh").onclick = loadTraces; $("admin-log-refresh").onclick = loadLogs; loadOverview();
  });
})();
