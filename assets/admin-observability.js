(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function text(node, value) { node.textContent = value == null || value === "" ? "—" : String(value); }
  function fmtMs(value) { return value == null ? "—" : String(Math.round(Number(value))) + " ms"; }
  function fmtNumber(value) { return Number(value || 0).toLocaleString(); }
  function fmtTime(value) { return value == null || value === "" ? "—" : (window.InterviewForgeTime ? InterviewForgeTime.formatDateTime(value) : String(value)); }
  function fmtBucket(value) {
    if (value == null || value === "") return "—";
    var raw = String(value);
    return window.InterviewForgeTime
      ? (/^\d{4}-\d{2}-\d{2}$/.test(raw) ? InterviewForgeTime.formatDate(raw) : InterviewForgeTime.formatDateTime(raw))
      : raw;
  }
  function request(path) {
    return fetch(path, { credentials: "same-origin", cache: "no-store" }).then(function (response) {
      if (response.status === 401) { location.replace("/pages/login.html?next=" + encodeURIComponent(location.pathname)); throw new Error("登录状态已失效"); }
      return response.json().then(function (data) { if (!response.ok) throw new Error(data.error || "请求失败"); return data; });
    });
  }
  function card(label, value) { var node = document.createElement("div"); node.className = "admin-v2-card"; var strong = document.createElement("strong"); text(strong, value); var span = document.createElement("span"); text(span, label); node.appendChild(strong); node.appendChild(span); return node; }
  function fillDl(node, values) { node.textContent = ""; Object.keys(values).forEach(function (key) { var dt = document.createElement("dt"); var dd = document.createElement("dd"); text(dt, key); text(dd, values[key]); node.appendChild(dt); node.appendChild(dd); }); }
  function renderAnomalies(data) { var list = $("admin-overview-anomalies"); list.textContent = ""; var requests = data.requests || {}, exceptions = data.recent_exceptions || {}, tasks = data.tasks || {}; var items = []; if (Number(requests.error_5xx_24h || 0) > 0) items.push("HTTP 5xx：" + requests.error_5xx_24h + " 次"); if (Number(exceptions.ai_failed_24h || 0) > 0) items.push("AI 失败：" + exceptions.ai_failed_24h + " 次"); if (Number(exceptions.tool_errors_24h || 0) > 0) items.push("工具错误：" + exceptions.tool_errors_24h + " 次"); if (Number(tasks.failed || 0) > 0) items.push("失败任务：" + tasks.failed + " 个"); if (Number(tasks.degraded || 0) > 0) items.push("部分完成任务：" + tasks.degraded + " 个"); if (Number((data.storage || {}).disk_free || 0) > 0 && Number(data.storage.disk_free) < 512 * 1024 * 1024) items.push("磁盘剩余空间低于 512 MB"); if (!items.length) items.push("当前窗口未发现异常"); items.forEach(function (value) { var li = document.createElement("li"); text(li, value); list.appendChild(li); }); }
  function drawBars(node, values, key) { node.textContent = ""; var numbers = values.map(function (item) { return Number(item[key] || 0); }); var max = Math.max.apply(Math, numbers.concat([1])); values.forEach(function (item, index) { var bar = document.createElement("span"); bar.className = "admin-v2-chart-bar"; bar.style.height = Math.max(3, Math.round(numbers[index] / max * 56)) + "px"; bar.title = fmtBucket(item.bucket_start) + " · " + String(numbers[index]); node.appendChild(bar); }); }
  function fail(error) { var status = $("admin-v2-status"); status.className = "admin-v2-status error"; text(status, error && error.message ? error.message : "加载失败"); }
  function loadOverview() {
    return request("/api/admin/overview").then(function (data) {
      text($("admin-v2-status"), "已更新"); $("admin-v2-status").className = "admin-v2-status";
      var cards = $("admin-overview-cards"); cards.textContent = "";
      cards.appendChild(card("用户总数", data.users.total)); cards.appendChild(card("24 小时请求", data.requests.total_24h)); cards.appendChild(card("24 小时 AI 轮次", data.ai.turns_24h)); cards.appendChild(card("运行中任务", data.tasks.running));
      fillDl($("admin-overview-requests"), { "5xx": data.requests.error_5xx_24h, "错误率": (Number(data.requests.error_rate || 0) * 100).toFixed(2) + "%", "P95": fmtMs(data.requests.p95_ms) });
      fillDl($("admin-overview-ai"), { "成功率": (Number(data.ai.success_rate || 0) * 100).toFixed(2) + "%", "P95": fmtMs(data.ai.p95_ms), "输入 tokens": fmtNumber(data.ai.input_tokens), "输出 tokens": fmtNumber(data.ai.output_tokens) });
      fillDl($("admin-overview-system"), { "失败任务": data.tasks.failed, "最近 5xx": (data.recent_exceptions || {}).request_5xx_24h || 0, "AI 失败": (data.recent_exceptions || {}).ai_failed_24h || 0, "工具错误": (data.recent_exceptions || {}).tool_errors_24h || 0, "用户库": data.storage.user_db_bytes, "磁盘剩余": data.storage.disk_free, "版本": data.system.version });
      renderAnomalies(data);
    });
  }
  function loadUsage() {
    var windowValue = $("admin-usage-window").value;
    return Promise.all([
      request("/api/admin/ai/usage?window=" + encodeURIComponent(windowValue)),
      request("/api/admin/metrics/ai?window=" + encodeURIComponent(windowValue))
    ]).then(function (result) {
      var data = result[0], trend = result[1];
      var cards = $("admin-usage-cards"); cards.textContent = "";
      cards.appendChild(card("轮次", data.turns)); cards.appendChild(card("失败数", data.failed)); cards.appendChild(card("成功率", (Number(data.success_rate || 0) * 100).toFixed(2) + "%")); cards.appendChild(card("平均耗时", fmtMs(data.avg_latency_ms))); cards.appendChild(card("P50", fmtMs(data.p50_latency_ms))); cards.appendChild(card("TTFT P50", fmtMs(data.ttft_p50_ms))); cards.appendChild(card("TTFT P95", fmtMs(data.ttft_p95_ms))); cards.appendChild(card("TTFT 样本", data.ttft_count || 0)); cards.appendChild(card("Tool 错误", data.tool_errors || 0)); cards.appendChild(card("Memory 写入", data.memory_writes || 0)); cards.appendChild(card("费用覆盖率", Number(data.cost_coverage_percent || 0).toFixed(2) + "%")); cards.appendChild(card("估算费用", data.estimated_cost_usd == null ? "未配置" : "$" + data.estimated_cost_usd));
      var body = $("admin-usage-models"); body.textContent = ""; (data.models || []).forEach(function (item) { var tr = document.createElement("tr"); [item.provider_name, item.business_key, item.model, item.turns, fmtNumber(item.input_tokens), fmtNumber(item.output_tokens), fmtNumber(item.reasoning_tokens), item.estimated_cost_usd == null ? "—" : "$" + item.estimated_cost_usd].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); body.appendChild(tr); });
      var series = $("admin-ai-series"); series.textContent = ""; (trend.series || []).forEach(function (item) { var tr = document.createElement("tr"); [fmtBucket(item.bucket_start), item.turns, (Number(item.success_rate || 0) * 100).toFixed(2) + "%", fmtMs(item.p50_latency_ms), fmtMs(item.p95_latency_ms), fmtMs(item.ttft_p50_ms), fmtMs(item.ttft_p95_ms), fmtNumber(Number(item.input_tokens || 0) + Number(item.output_tokens || 0) + Number(item.reasoning_tokens || 0))].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); series.appendChild(tr); }); drawBars($("admin-ai-chart"), trend.series || [], "turns");
    });
  }
  function loadTraffic() {
    var windowValue = $("admin-traffic-window").value;
    return request("/api/admin/metrics/requests?window=" + encodeURIComponent(windowValue)).then(function (data) {
      var totals = data.totals || {}, cards = $("admin-traffic-cards"); cards.textContent = "";
      cards.appendChild(card("请求量", fmtNumber(totals.request_count))); cards.appendChild(card("5xx 错误率", (Number(totals["5xx_rate"] || 0) * 100).toFixed(2) + "%")); cards.appendChild(card("平均", fmtMs(totals.avg_ms))); cards.appendChild(card("P50", fmtMs(totals.p50_ms))); cards.appendChild(card("P95", fmtMs(totals.p95_ms))); cards.appendChild(card("P99", fmtMs(totals.p99_ms)));
      var series = $("admin-traffic-series"); series.textContent = ""; (data.series || []).forEach(function (item) { var tr = document.createElement("tr"); [fmtBucket(item.bucket_start), item.request_count, item["2xx"], item["3xx"], item["4xx"], item["5xx"], fmtMs(item.p50_ms), fmtMs(item.p95_ms), fmtMs(item.p99_ms)].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); series.appendChild(tr); }); drawBars($("admin-traffic-chart"), data.series || [], "request_count");
      var endpoints = $("admin-traffic-endpoints"); endpoints.textContent = ""; (data.endpoints || []).forEach(function (item) { var tr = document.createElement("tr"); [item.method, item.route, item.request_count, item.error_count, (Number(item.error_count || 0) / Math.max(1, Number(item.request_count || 0)) * 100).toFixed(2) + "%", item["5xx"], fmtMs(item.p95_ms)].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); endpoints.appendChild(tr); });
      var slowest = $("admin-traffic-slowest"); slowest.textContent = ""; (data.slowest_endpoints || []).forEach(function (item) { var tr = document.createElement("tr"); [item.method, item.route, item.request_count, fmtMs(item.p95_ms), fmtMs(item.p50_ms)].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); slowest.appendChild(tr); });
      var topErrors = $("admin-traffic-top-errors"); topErrors.textContent = ""; (data.top_errors || []).forEach(function (item) { var tr = document.createElement("tr"); [item.method, item.route, item.error_count, item["4xx"], item["5xx"], (Number(item.error_count || 0) / Math.max(1, Number(item.request_count || 0)) * 100).toFixed(2) + "%"].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); topErrors.appendChild(tr); });
    });
  }
  function loadTraces() {
    var query = "window=" + encodeURIComponent($("admin-trace-window").value) + "&limit=100";
    var username = $("admin-trace-username").value.trim(); var model = $("admin-trace-model").value.trim(); var status = $("admin-trace-status").value;
    if (username) query += "&username=" + encodeURIComponent(username); if (model) query += "&model=" + encodeURIComponent(model); if (status) query += "&status=" + encodeURIComponent(status);
    return request("/api/admin/ai/traces?" + query).then(function (data) { var body = $("admin-traces"); body.textContent = ""; (data.items || []).forEach(function (item) { var tr = document.createElement("tr"); tr.tabIndex = 0; tr.className = "admin-v2-clickable"; [fmtTime(item.finished_at), item.username, item.provider_name || item.provider, item.business_key, item.model, item.reasoning_mode || "—", item.status, item.error_code || "—", fmtMs(item.duration_ms), fmtNumber((item.input_tokens || 0) + (item.output_tokens || 0)), item.request_id].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); tr.onclick = function () { request("/api/admin/ai/traces/" + encodeURIComponent(item.trace_id) + "?username=" + encodeURIComponent(item.username)).then(function (detail) { var panel = $("admin-trace-detail"); panel.hidden = false; text(panel, JSON.stringify(detail, null, 2)); }).catch(fail); }; body.appendChild(tr); }); });
  }
  function loadLogs() {
    return request("/api/admin/logs?level=" + encodeURIComponent($("admin-log-level").value) + "&module=" + encodeURIComponent($("admin-log-module").value) + "&event=" + encodeURIComponent($("admin-log-event").value) + "&request_id=" + encodeURIComponent($("admin-log-request-id").value) + "&limit=100").then(function (data) { var body = $("admin-logs-table"); body.textContent = ""; (data.items || []).forEach(function (item) { var tr = document.createElement("tr"); tr.className = "admin-v2-clickable"; [fmtTime(item.time), item.level, item.module, item.event, item.request_id, item.status, fmtMs(item.elapsed_ms)].forEach(function (value) { var td = document.createElement("td"); text(td, value); tr.appendChild(td); }); tr.onclick = function () { var id = String(item.request_id || ""); if (!id) return; $("admin-trace-window").value = "24h"; var tab = document.querySelector('[data-admin-tab="traces"]'); if (tab) tab.click(); request("/api/admin/ai/traces?window=24h&request_id=" + encodeURIComponent(id) + "&limit=100").then(function (traceData) { var traceBody = $("admin-traces"); traceBody.textContent = ""; (traceData.items || []).forEach(function (trace) { var traceRow = document.createElement("tr"); [fmtTime(trace.finished_at), trace.username, trace.model, trace.status, fmtMs(trace.duration_ms), trace.request_id].forEach(function (value) { var cell = document.createElement("td"); text(cell, value); traceRow.appendChild(cell); }); traceBody.appendChild(traceRow); }); }).catch(fail); }; body.appendChild(tr); }); });
  }
  function bindChangeReload(id, loader) {
    var node = $(id);
    if (node) node.addEventListener("change", function () { loader().catch(fail); });
  }
  function loadTab(name) { var work = name === "overview" ? loadOverview() : name === "traffic" ? loadTraffic() : name === "usage" ? loadUsage() : name === "traces" ? loadTraces() : loadLogs(); work.catch(fail); }
  document.addEventListener("DOMContentLoaded", function () {
    if (!$("admin-observability")) return;
    document.querySelectorAll(".admin-topic-nav a").forEach(function (link) { link.addEventListener("click", function () { var target = link.getAttribute("href"); var map = { "#admin-traffic": "traffic", "#admin-ai": "usage", "#admin-logs": "logs" }; if (map[target]) { var tab = document.querySelector('[data-admin-tab="' + map[target] + '"]'); if (tab) tab.click(); } var opsMap = { "#admin-tools": "tasks", "#admin-system": "system" }; if (opsMap[target]) { var opsTab = document.querySelector('[data-ops-tab="' + opsMap[target] + '"]'); if (opsTab) opsTab.click(); } }); });
    document.querySelectorAll("[data-admin-tab]").forEach(function (button) { button.addEventListener("click", function () { var name = button.getAttribute("data-admin-tab"); document.querySelectorAll("[data-admin-tab]").forEach(function (item) { item.classList.toggle("active", item === button); }); document.querySelectorAll("[data-admin-panel]").forEach(function (item) { item.classList.toggle("active", item.getAttribute("data-admin-panel") === name); }); loadTab(name); }); });
    $("admin-traffic-refresh").onclick = function () { loadTraffic().catch(fail); }; $("admin-usage-refresh").onclick = function () { loadUsage().catch(fail); }; $("admin-trace-refresh").onclick = function () { loadTraces().catch(fail); }; $("admin-log-refresh").onclick = function () { loadLogs().catch(fail); };
    bindChangeReload("admin-traffic-window", loadTraffic); bindChangeReload("admin-usage-window", loadUsage); bindChangeReload("admin-trace-window", loadTraces); bindChangeReload("admin-trace-status", loadTraces); bindChangeReload("admin-log-level", loadLogs); loadOverview();
  });
})();
