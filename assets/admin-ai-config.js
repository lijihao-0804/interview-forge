(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function text(node, value) { node.textContent = value == null ? "—" : String(value); }
  function api(path, options) {
    return fetch(path, Object.assign({ headers: { "Content-Type": "application/json" }, cache: "no-store" }, options || {}))
      .then(function (r) { return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || "请求失败"); return data; }); });
  }
  function fail(error) { text($("admin-ai-config-status"), error && error.message ? error.message : "操作失败"); $("admin-ai-config-status").className = "msg error"; }
  function ok(message) { text($("admin-ai-config-status"), message || "已更新"); $("admin-ai-config-status").className = "msg ok"; }
  function renderProviders(data) {
    var list = $("admin-ai-providers"); list.textContent = "";
    (data.items || []).forEach(function (item) {
      var card = document.createElement("div"); card.className = "ai-config-card";
      var title = document.createElement("h3"); text(title, item.name + " · " + item.vendor); card.appendChild(title);
      var meta = document.createElement("div"); meta.className = "ai-config-meta";
      text(meta, item.protocol + " · " + item.base_url + " · Key " + (item.key_configured ? (item.key_hint || "已配置") : "未配置") + " · " + (item.enabled ? "启用" : "停用")); card.appendChild(meta);
      var actions = document.createElement("div"); actions.className = "ai-config-actions";
      [["测试连接", "/test", "POST"], ["获取模型", "/discover-models", "POST"]].forEach(function (action) { var button = document.createElement("button"); button.className = "ghost"; text(button, action[0]); button.onclick = function () { api("/api/admin/ai/providers/" + encodeURIComponent(item.id) + action[1], { method: action[2], body: action[2] === "POST" ? undefined : "{}" }).then(function (result) { ok(result.ok === false ? "连接失败：" + result.category : "操作完成"); if (action[1] === "/discover-models") renderModels(result); }).catch(fail); }; actions.appendChild(button); }); card.appendChild(actions); list.appendChild(card);
    });
  }
  function renderModels(data) { var list = $("admin-ai-models"); list.textContent = ""; (data.items || []).forEach(function (item) { var row = document.createElement("div"); row.className = "ai-config-meta"; text(row, item.model_id + " · " + (item.available ? "可用" : "已消失") + " · " + (item.capability_source || "unknown")); list.appendChild(row); }); }
  function renderProfiles(data) {
    var list = $("admin-ai-profiles"); list.textContent = "";
    (data.items || []).forEach(function (item) { var row = document.createElement("div"); row.className = "ai-config-meta"; text(row, item.business_key + " · " + item.provider_id + " / " + item.model_id + " · " + item.reasoning_mode + " · " + (item.enabled ? "启用" : "停用")); list.appendChild(row); });
  }
  function load() { return Promise.all([api("/api/admin/ai/providers"), api("/api/admin/ai/business-profiles")]).then(function (results) { renderProviders(results[0]); renderProfiles(results[1]); ok("配置已加载"); }).catch(fail); }
  document.addEventListener("DOMContentLoaded", function () {
    if (!$("admin-ai-config")) return;
    $("admin-ai-config-refresh").onclick = function () { load(); };
    $("admin-ai-provider-create").onclick = function () {
      var payload = { name: $("admin-ai-name").value.trim(), vendor: $("admin-ai-vendor").value.trim(), protocol: $("admin-ai-protocol").value, base_url: $("admin-ai-base-url").value.trim(), api_key: $("admin-ai-key").value };
      api("/api/admin/ai/providers", { method: "POST", body: JSON.stringify(payload) }).then(function () { $("admin-ai-key").value = ""; ok("Provider 已保存"); return load(); }).catch(fail);
    };
    $("admin-ai-profile-save").onclick = function () {
      var key = $("admin-ai-business").value;
      var payload = { provider_id: $("admin-ai-profile-provider").value.trim(), model_id: $("admin-ai-profile-model").value.trim(), reasoning_mode: $("admin-ai-reasoning-mode").value, reasoning_effort: $("admin-ai-reasoning-effort").value.trim() || null, reasoning_budget: $("admin-ai-reasoning-budget").value ? Number($("admin-ai-reasoning-budget").value) : null, enabled: true };
      api("/api/admin/ai/business-profiles/" + encodeURIComponent(key), { method: "PUT", body: JSON.stringify(payload) }).then(function () { ok("业务路由已保存"); return load(); }).catch(fail);
    };
    load();
  });
}());
