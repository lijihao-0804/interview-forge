(function () {
  "use strict";
  var state = { presets: [], providers: [], profiles: [], modelsByProvider: {}, selectedProvider: "", editingProviderId: "" };
  function $(id) { return document.getElementById(id); }
  function text(node, value) { node.textContent = value == null ? "—" : String(value); }
  function api(path, options) {
    return fetch(path, Object.assign({ headers: { "Content-Type": "application/json" }, cache: "no-store" }, options || {}))
      .then(function (r) { return r.json().then(function (data) { if (!r.ok) throw new Error(data.error || "请求失败"); return data; }); });
  }
  function fail(error) { text($("admin-ai-config-status"), error && error.message ? error.message : "操作失败"); $("admin-ai-config-status").className = "msg error"; }
  function ok(message) { text($("admin-ai-config-status"), message || "已更新"); $("admin-ai-config-status").className = "msg ok"; }
  function option(select, value, label, disabled) { var item = document.createElement("option"); item.value = value; item.textContent = label; item.disabled = !!disabled; select.appendChild(item); return item; }
  function selectedProvider() { return state.providers.find(function (item) { return item.id === state.selectedProvider; }) || null; }
  function presetChanged() {
    var preset = state.presets.find(function (item) { return item.key === $("admin-ai-preset").value; });
    if (!preset) return;
    $("admin-ai-vendor").value = preset.vendor || "";
    $("admin-ai-protocol").value = preset.protocol || "openai_chat";
    $("admin-ai-base-url").value = preset.default_base_url || "";
    $("admin-ai-models-path").value = preset.models_path || "/models";
  }
  function loadModels(providerId, selectedModel) {
    if (!providerId) return Promise.resolve();
    return api("/api/admin/ai/providers/" + encodeURIComponent(providerId) + "/models").then(function (data) {
      state.modelsByProvider[providerId] = data.items || [];
      renderModels(data);
      renderRoutingModels(providerId, selectedModel);
      return data;
    });
  }
  function renderProviders(data) {
    state.providers = data.items || [];
    var list = $("admin-ai-providers"); list.textContent = "";
    var routeProvider = $("admin-ai-profile-provider"); routeProvider.textContent = "";
    state.providers.forEach(function (item) {
      option(routeProvider, item.id, item.name + " · " + item.vendor + (item.enabled ? "" : "（停用）"), !item.enabled);
      var card = document.createElement("div"); card.className = "ai-config-card";
      var title = document.createElement("h3"); text(title, item.name + " · " + item.vendor); card.appendChild(title);
      var meta = document.createElement("div"); meta.className = "ai-config-meta";
      text(meta, item.protocol + " · " + item.base_url + " · " + (item.network_scope || "unknown") + " · Key " + (item.key_configured ? (item.key_hint || "已配置") : "未配置") + " · " + (item.enabled ? "启用" : "停用")); card.appendChild(meta);
      var actions = document.createElement("div"); actions.className = "ai-config-actions";
      function button(label, handler) { var b = document.createElement("button"); b.className = "ghost"; text(b, label); b.onclick = handler; actions.appendChild(b); }
      button("编辑", function () { state.editingProviderId = item.id; $("admin-ai-name").value = item.name; $("admin-ai-vendor").value = item.vendor; $("admin-ai-protocol").value = item.protocol; $("admin-ai-base-url").value = item.base_url; $("admin-ai-models-path").value = item.models_path || "/models"; $("admin-ai-provider-create").textContent = "更新 Provider"; window.scrollTo(0, 0); });
      button(item.enabled ? "停用" : "启用", function () { api("/api/admin/ai/providers/" + encodeURIComponent(item.id), { method: "PUT", body: JSON.stringify({ enabled: !item.enabled }) }).then(function () { ok("Provider 状态已更新"); return load(); }).catch(fail); });
      button("测试连接", function () { api("/api/admin/ai/providers/" + encodeURIComponent(item.id) + "/test", { method: "POST" }).then(function (result) { ok(result.ok ? "连接成功" : "连接失败：" + result.category); }).catch(fail); });
      button("获取模型", function () { state.selectedProvider = item.id; $("admin-ai-model-provider").value = item.id; loadModels(item.id).then(function () { ok("模型列表已更新"); }).catch(fail); });
      button("替换 Key", function () { var key = window.prompt("输入新 API Key（不会回显）", ""); if (key === null) return; api("/api/admin/ai/providers/" + encodeURIComponent(item.id), { method: "PUT", body: JSON.stringify({ api_key: key }) }).then(function () { ok("API Key 已替换"); return load(); }).catch(fail); });
      button("删除", function () { if (!window.confirm("确认删除该 Provider？")) return; api("/api/admin/ai/providers/" + encodeURIComponent(item.id), { method: "DELETE" }).then(function () { ok("Provider 已删除"); return load(); }).catch(fail); });
      card.appendChild(actions); list.appendChild(card);
    });
    if (!state.selectedProvider && state.providers[0]) state.selectedProvider = state.providers[0].id;
    routeProvider.value = state.selectedProvider || "";
  }
  function renderModels(data) {
    var list = $("admin-ai-models"); list.textContent = "";
    var provider = selectedProvider();
    if (!provider) { text(list, "选择 Provider 后加载模型"); return; }
    (data.items || []).forEach(function (item) {
      var row = document.createElement("div"); row.className = "ai-config-card";
      var title = document.createElement("div"); title.className = "ai-config-meta"; text(title, item.model_id + " · " + (item.available ? "可用" : "已消失") + " · " + (item.enabled ? "启用" : "停用") + " · " + (item.capability_source || "unknown")); row.appendChild(title);
      var controls = document.createElement("div"); controls.className = "ai-config-actions";
      var toggle = document.createElement("button"); toggle.className = "ghost"; text(toggle, item.enabled ? "停用" : "启用"); toggle.onclick = function () { api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/models/" + encodeURIComponent(item.model_id), { method: "PUT", body: JSON.stringify({ enabled: !item.enabled }) }).then(function () { return loadModels(provider.id); }).then(function () { ok("模型状态已更新"); }).catch(fail); }; controls.appendChild(toggle);
      var override = document.createElement("button"); override.className = "ghost"; text(override, "能力覆盖"); override.onclick = function () { var raw = window.prompt("输入 capabilities JSON", JSON.stringify(item.capabilities || {})); if (raw === null) return; var caps; try { caps = JSON.parse(raw); } catch (e) { fail(new Error("capabilities JSON 无效")); return; } api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/models/" + encodeURIComponent(item.model_id), { method: "PUT", body: JSON.stringify({ capabilities: caps }) }).then(function () { return loadModels(provider.id); }).then(function () { ok("模型能力已更新"); }).catch(fail); }; controls.appendChild(override);
      row.appendChild(controls); list.appendChild(row);
    });
    if (!data.items || !data.items.length) text(list, "暂无模型，请自动发现或手工添加");
  }
  function renderRoutingModels(providerId, selectedModel) {
    var select = $("admin-ai-profile-model"); select.textContent = "";
    (state.modelsByProvider[providerId] || []).forEach(function (item) { if (item.enabled && item.available) option(select, item.model_id, item.display_name || item.model_id, false); });
    if (selectedModel) select.value = selectedModel;
    updateReasoningControls();
  }
  function updateReasoningControls() {
    var providerId = $("admin-ai-profile-provider").value;
    var modelId = $("admin-ai-profile-model").value;
    var model = (state.modelsByProvider[providerId] || []).find(function (item) { return item.model_id === modelId; });
    var caps = model && model.capabilities || {};
    var supported = caps.reasoning === true;
    var modes = Array.isArray(caps.reasoning_modes) ? caps.reasoning_modes : null;
    $("admin-ai-reasoning-mode").disabled = !model;
    Array.prototype.forEach.call($("admin-ai-reasoning-mode").options, function (item) { item.disabled = modes ? modes.indexOf(item.value) < 0 : (!supported && item.value !== "auto"); });
    $("admin-ai-reasoning-effort").disabled = !supported || $("admin-ai-reasoning-mode").value !== "effort";
    $("admin-ai-reasoning-budget").disabled = !supported || caps.reasoning_budget !== true || $("admin-ai-reasoning-mode").value !== "budget";
  }
  function renderProfiles(data) {
    state.profiles = data.items || [];
    var list = $("admin-ai-profiles"); list.textContent = "";
    state.profiles.forEach(function (item) { var row = document.createElement("div"); row.className = "ai-config-meta"; var provider = state.providers.find(function (p) { return p.id === item.provider_id; }); text(row, item.business_key + " · " + (provider ? provider.name : "Provider") + " / " + item.model_id + " · " + item.reasoning_mode + " · " + (item.enabled ? "启用" : "停用")); list.appendChild(row); });
  }
  function load() {
    return Promise.all([api("/api/admin/ai/provider-presets"), api("/api/admin/ai/providers"), api("/api/admin/ai/business-profiles")]).then(function (results) {
      state.presets = results[0].items || [];
      var preset = $("admin-ai-preset"); preset.textContent = ""; state.presets.forEach(function (item) { option(preset, item.key, item.display_name); }); if (state.presets.length && !preset.value) preset.value = state.presets[0].key; presetChanged();
      renderProviders(results[1]); renderProfiles(results[2]);
      var profile = state.profiles.find(function (item) { return item.business_key === $("admin-ai-business").value; });
      if (profile) { $("admin-ai-profile-provider").value = profile.provider_id; state.selectedProvider = profile.provider_id; return loadModels(profile.provider_id, profile.model_id).then(function () { $("admin-ai-reasoning-mode").value = profile.reasoning_mode || "auto"; $("admin-ai-reasoning-effort").value = profile.reasoning_effort || ""; $("admin-ai-reasoning-budget").value = profile.reasoning_budget || ""; updateReasoningControls(); }); }
      if (state.selectedProvider) return loadModels(state.selectedProvider);
    }).then(function () { ok("配置已加载"); }).catch(fail);
  }
  document.addEventListener("DOMContentLoaded", function () {
    if (!$("admin-ai-config")) return;
    $("admin-ai-preset").onchange = presetChanged;
    $("admin-ai-config-refresh").onclick = function () { load(); };
    $("admin-ai-provider-create").onclick = function () {
      var payload = { name: $("admin-ai-name").value.trim(), vendor: $("admin-ai-vendor").value.trim(), protocol: $("admin-ai-protocol").value, base_url: $("admin-ai-base-url").value.trim(), models_path: $("admin-ai-models-path").value.trim() || "/models", api_key: $("admin-ai-key").value };
      var path = state.editingProviderId ? "/api/admin/ai/providers/" + encodeURIComponent(state.editingProviderId) : "/api/admin/ai/providers";
      var method = state.editingProviderId ? "PUT" : "POST";
      if (!payload.api_key) delete payload.api_key;
      api(path, { method: method, body: JSON.stringify(payload) }).then(function () { $("admin-ai-key").value = ""; state.editingProviderId = ""; $("admin-ai-provider-create").textContent = "保存 Provider"; ok("Provider 已保存"); return load(); }).catch(fail);
    };
    $("admin-ai-model-add").onclick = function () {
      var providerId = state.selectedProvider || $("admin-ai-profile-provider").value; var modelId = $("admin-ai-model-id").value.trim(); var raw = $("admin-ai-model-capabilities").value.trim(); var caps = {};
      if (raw) { try { caps = JSON.parse(raw); } catch (e) { fail(new Error("capabilities JSON 无效")); return; } }
      if (!providerId || !modelId) { fail(new Error("请先选择 Provider 并填写 model id")); return; }
      api("/api/admin/ai/providers/" + encodeURIComponent(providerId) + "/models", { method: "POST", body: JSON.stringify({ model_id: modelId, capabilities: caps }) }).then(function () { return loadModels(providerId); }).then(function () { ok("模型已添加"); }).catch(fail);
    };
    $("admin-ai-profile-provider").onchange = function () { state.selectedProvider = this.value; loadModels(this.value).catch(fail); };
    $("admin-ai-profile-model").onchange = updateReasoningControls;
    $("admin-ai-reasoning-mode").onchange = updateReasoningControls;
    $("admin-ai-profile-save").onclick = function () {
      var key = $("admin-ai-business").value; var payload = { provider_id: $("admin-ai-profile-provider").value, model_id: $("admin-ai-profile-model").value, reasoning_mode: $("admin-ai-reasoning-mode").value, reasoning_effort: $("admin-ai-reasoning-effort").value.trim() || null, reasoning_budget: $("admin-ai-reasoning-budget").value ? Number($("admin-ai-reasoning-budget").value) : null, enabled: true };
      api("/api/admin/ai/business-profiles/" + encodeURIComponent(key), { method: "PUT", body: JSON.stringify(payload) }).then(function () { ok("业务路由已保存"); return load(); }).catch(fail);
    };
    $("admin-ai-business").onchange = function () { load(); };
    load();
  });
}());
