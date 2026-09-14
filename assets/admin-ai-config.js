(function () {
  "use strict";

  var BUSINESS = {
    chat: { label: "Chat", description: "用户日常 AI 对话" },
    learning_analysis: { label: "学习分析", description: "一键分析学习情况并定制复习建议" },
    memory_extraction: { label: "Memory 提取", description: "从对话中提取可长期保留的学习偏好" }
  };
  var CAPABILITIES = [
    ["streaming", "流式"],
    ["tools", "工具"],
    ["structured_output", "结构化输出"],
    ["reasoning", "推理"]
  ];
  var state = {
    presets: [], capabilityProfiles: [], providers: [], profiles: [], modelsByProvider: {},
    selectedProvider: "", editingProviderId: "", editingModel: null,
    routeBusinessKey: "", modelErrors: {}
  };

  function $(id) { return document.getElementById(id); }
  function text(node, value) { node.textContent = value == null ? "—" : String(value); }
  function api(path, options) {
    return fetch(path, Object.assign({ headers: { "Content-Type": "application/json" }, cache: "no-store" }, options || {}))
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || "请求失败");
          return data;
        });
      });
  }
  function setStatus(kind, message) {
    var node = $("admin-ai-config-status");
    if (!node) return;
    node.className = "ai-config-status status-" + (kind || "neutral");
    text(node, message);
  }
  function setMessage(id, message, kind) {
    var node = $(id);
    if (!node) return;
    node.className = "ai-dialog-message" + (kind ? " " + kind : "");
    text(node, message || "");
  }
  function option(select, value, label, disabled) {
    var item = document.createElement("option");
    item.value = value; item.textContent = label; item.disabled = !!disabled;
    select.appendChild(item); return item;
  }
  function emptyOption(select, label) {
    option(select, "", label, true); select.value = "";
  }
  function selectedProvider() {
    return state.providers.find(function (item) { return item.id === state.selectedProvider; }) || null;
  }
  function providerById(id) {
    return state.providers.find(function (item) { return item.id === id; }) || null;
  }
  function modelsFor(id) { return state.modelsByProvider[id] || []; }
  function modelFor(providerId, modelId) {
    return modelsFor(providerId).find(function (item) { return item.model_id === modelId; }) || null;
  }
  function capabilitySourceLabel(source) {
    return {
      manual: "管理员覆盖",
      provider: "Provider 声明",
      official_catalog: "官方目录",
      protocol: "协议基线",
      unknown: "未知"
    }[source] || "未知";
  }
  function capabilityProfile(key) {
    return state.capabilityProfiles.find(function (item) { return item.key === key; }) || null;
  }
  function renderCapabilityProfileSelect(selectedKey) {
    var select = $("admin-ai-capability-profile");
    if (!select) return;
    var current = selectedKey || select.value;
    select.textContent = "";
    if (!state.capabilityProfiles.length) {
      emptyOption(select, "暂无可用能力 Profile");
      return;
    }
    state.capabilityProfiles.forEach(function (item) {
      option(select, item.key, item.display_name || item.key);
    });
    select.value = current && capabilityProfile(current) ? current : state.capabilityProfiles[0].key;
    var profile = capabilityProfile(select.value);
    text($("admin-ai-capability-profile-note"), profile ? profile.description : "");
  }
  function showDialog(id) {
    var dialog = $(id);
    if (dialog && typeof dialog.showModal === "function") dialog.showModal();
  }
  function closeDialog(id) {
    var dialog = $(id);
    if (dialog && dialog.open) dialog.close();
  }
  function runButton(button, workingText, task) {
    var previous = button.textContent;
    button.disabled = true; button.textContent = workingText;
    return task().then(function (value) {
      button.disabled = false; button.textContent = previous; return value;
    }, function (error) {
      button.disabled = false; button.textContent = previous; throw error;
    });
  }
  function statusInfo(provider) {
    if (!provider.enabled) return { label: "已停用", cls: "disabled" };
    if (!provider.last_test_status) return { label: "未测试", cls: "untested" };
    if (provider.last_test_status === "ok") return { label: "正常", cls: "ok" };
    return { label: "异常", cls: "error" };
  }
  function badge(label, cls) {
    var node = document.createElement("span");
    node.className = "ai-badge" + (cls ? " " + cls : ""); text(node, label); return node;
  }
  function actionButton(label, handler, extraClass) {
    var button = document.createElement("button");
    button.type = "button"; button.className = extraClass || "ghost"; text(button, label);
    button.onclick = handler; return button;
  }
  function emptyState(container, title, description, actionLabel, action) {
    container.textContent = "";
    var wrapper = document.createElement("div"); wrapper.className = "ai-empty-state";
    var heading = document.createElement("strong"); text(heading, title); wrapper.appendChild(heading);
    var detail = document.createElement("p"); text(detail, description); wrapper.appendChild(detail);
    if (actionLabel && action) wrapper.appendChild(actionButton(actionLabel, action));
    container.appendChild(wrapper);
  }

  function updateSummary() {
    $("admin-ai-provider-count").textContent = String(state.providers.length);
    var modelCount = Object.keys(state.modelsByProvider).reduce(function (total, id) { return total + modelsFor(id).length; }, 0);
    $("admin-ai-model-count").textContent = String(modelCount);
    $("admin-ai-route-count").textContent = String(state.profiles.filter(function (item) { return item.enabled; }).length);
  }
  function activateTab(name) {
    document.querySelectorAll("[data-ai-tab]").forEach(function (button) { button.classList.toggle("active", button.getAttribute("data-ai-tab") === name); });
    document.querySelectorAll("[data-ai-panel]").forEach(function (panel) { panel.classList.toggle("active", panel.getAttribute("data-ai-panel") === name); });
    if (name === "models") renderModels();
  }

  function presetChanged() {
    var preset = state.presets.find(function (item) { return item.key === $("admin-ai-preset").value; });
    if (!preset) return;
    $("admin-ai-vendor").value = preset.vendor || "";
    $("admin-ai-protocol").value = preset.protocol || "openai_chat";
    $("admin-ai-base-url").value = preset.default_base_url || "";
    $("admin-ai-models-path").value = preset.models_path || "/models";
    renderCapabilityProfileSelect(preset.capability_profile || "generic_openai_compatible");
  }
  function renderPresetSelect(selectedKey) {
    var select = $("admin-ai-preset");
    if (!select) return;
    var current = selectedKey || select.value;
    select.textContent = "";
    if (!state.presets.length) {
      option(select, "", "暂无可用 Provider 类型", true);
      select.value = "";
      return;
    }
    state.presets.forEach(function (preset) {
      option(select, preset.key, preset.display_name || preset.key);
    });
    select.value = current && state.presets.some(function (preset) { return preset.key === current; }) ? current : state.presets[0].key;
  }
  function presetForProvider(provider) {
    return state.presets.find(function (item) { return item.vendor === provider.vendor && item.protocol === provider.protocol; }) ||
      state.presets.find(function (item) { return item.protocol === provider.protocol; });
  }
  function resetProviderForm() {
    state.editingProviderId = "";
    $("admin-ai-provider-dialog-title").textContent = "添加供应商";
    $("admin-ai-provider-save").textContent = "保存";
    $("admin-ai-provider-form").reset();
    $("admin-ai-clear-key-wrap").hidden = true;
    $("admin-ai-clear-key").checked = false;
    renderPresetSelect();
    if (state.presets.length) presetChanged();
    else renderCapabilityProfileSelect();
    setMessage("admin-ai-provider-message", "");
  }
  function openProviderDialog(provider, focusKey) {
    resetProviderForm();
    if (provider) {
      state.editingProviderId = provider.id;
      $("admin-ai-provider-dialog-title").textContent = "编辑供应商";
      $("admin-ai-provider-save").textContent = "保存修改";
      var preset = presetForProvider(provider);
      if (preset) $("admin-ai-preset").value = preset.key;
      $("admin-ai-name").value = provider.name || "";
      $("admin-ai-vendor").value = provider.vendor || "";
      $("admin-ai-protocol").value = provider.protocol || "openai_chat";
      renderCapabilityProfileSelect(provider.capability_profile || (preset && preset.capability_profile) || "generic_openai_compatible");
      $("admin-ai-base-url").value = provider.base_url || "";
      $("admin-ai-models-path").value = provider.models_path || "/models";
      $("admin-ai-clear-key-wrap").hidden = !provider.key_configured;
    }
    showDialog("admin-ai-provider-dialog");
    if (focusKey) window.setTimeout(function () { $("admin-ai-key").focus(); }, 0);
  }

  function renderProviders() {
    var list = $("admin-ai-providers"); list.textContent = "";
    if (!state.providers.length) {
      emptyState(list, "尚未配置 AI Provider", "添加供应商后即可获取模型并配置业务路由。", "+ 添加供应商", function () { openProviderDialog(); });
      return;
    }
    state.providers.forEach(function (provider) {
      var info = statusInfo(provider);
      var card = document.createElement("article"); card.className = "ai-provider-card";
      var header = document.createElement("div"); header.className = "ai-card-header";
      var title = document.createElement("div"); title.className = "ai-card-title";
      var h = document.createElement("h4"); text(h, provider.name); title.appendChild(h);
      var subtitle = document.createElement("p"); text(subtitle, provider.vendor + " · " + provider.protocol); title.appendChild(subtitle);
      var stateBadge = document.createElement("span"); stateBadge.className = "ai-status-badge " + info.cls; text(stateBadge, "● " + info.label); header.appendChild(title); header.appendChild(stateBadge); card.appendChild(header);
      var stats = document.createElement("div"); stats.className = "ai-provider-stats";
      var modelStat = document.createElement("div"); var modelCount = modelsFor(provider.id).length; text(modelStat, modelCount + " 个模型"); stats.appendChild(modelStat);
      var testStat = document.createElement("div"); text(testStat, provider.last_test_latency_ms == null ? "最近测试 —" : "最近测试 " + Math.round(Number(provider.last_test_latency_ms)) + " ms"); stats.appendChild(testStat);
      var keyStat = document.createElement("div"); text(keyStat, provider.key_configured ? "Key 已配置" : "Key 未配置"); stats.appendChild(keyStat); card.appendChild(stats);
      var meta = document.createElement("p"); meta.className = "ai-card-meta"; text(meta, "网络：" + (provider.network_scope || "unknown") + " · " + (provider.last_test_at ? "测试于 " + provider.last_test_at : "尚未测试")); card.appendChild(meta);
      var actions = document.createElement("div"); actions.className = "ai-config-actions";
      actions.appendChild(actionButton("测试", function () {
        var button = this;
        runButton(button, "测试中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/test", { method: "POST" }); }).then(function (result) {
          provider.last_test_status = result.ok ? "ok" : result.category; provider.last_test_latency_ms = result.latency_ms; renderProviders(); setStatus(result.ok ? "ok" : "partial", result.ok ? "配置正常" : "部分异常：连接测试失败");
        }).catch(function (error) { setStatus("partial", error.message); });
      }));
      actions.appendChild(actionButton("同步模型", function () {
        var button = this;
        runButton(button, "同步中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/discover-models", { method: "POST" }); }).then(function (result) {
          if (!result.ok) { setStatus("partial", "部分异常：" + result.category); return; }
          state.selectedProvider = provider.id; state.modelsByProvider[provider.id] = result.items || []; renderProviders(); renderModels(); renderRouteCards(); updateSummary(); setStatus("ok", "配置正常");
        }).catch(function (error) { setStatus("partial", error.message); });
      }));
      actions.appendChild(actionButton("编辑", function () { openProviderDialog(provider); }));
      actions.appendChild(actionButton("替换 Key", function () { openProviderDialog(provider, true); }));
      actions.appendChild(actionButton(provider.enabled ? "停用" : "启用", function () {
        var button = this;
        runButton(button, "处理中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id), { method: "PUT", body: JSON.stringify({ enabled: !provider.enabled }) }); }).then(function () { return load(); }).then(function () { setStatus("ok", "配置正常"); }).catch(function (error) { setStatus("partial", error.message); });
      }));
      actions.appendChild(actionButton("删除", function () {
        if (!window.confirm("确认删除该 Provider？正在使用中的 Provider 无法删除。")) return;
        var button = this;
        runButton(button, "删除中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id), { method: "DELETE" }); }).then(function () { state.selectedProvider = ""; return load(); }).then(function () { setStatus("ok", "配置正常"); }).catch(function (error) { setStatus("partial", error.message); });
      }));
      card.appendChild(actions); list.appendChild(card);
    });
  }

  function loadModels(providerId, selectedModel) {
    if (!providerId) return Promise.resolve({ items: [] });
    return api("/api/admin/ai/providers/" + encodeURIComponent(providerId) + "/models").then(function (data) {
      state.modelsByProvider[providerId] = data.items || [];
      state.modelErrors[providerId] = "";
      if (selectedModel) state.routeSelectedModel = selectedModel;
      renderProviders(); renderModels(); updateSummary();
      return data;
    }).catch(function (error) { state.modelErrors[providerId] = error.message; throw error; });
  }
  function loadAllModels() {
    state.modelErrors = {};
    return Promise.all(state.providers.map(function (provider) { return loadModels(provider.id).catch(function () { return null; }); }));
  }
  function renderModelProviderSelect() {
    var select = $("admin-ai-model-provider-select");
    var current = state.selectedProvider || (state.providers[0] && state.providers[0].id) || "";
    select.textContent = "";
    if (!state.providers.length) { emptyOption(select, "暂无 Provider，请先添加"); state.selectedProvider = ""; return; }
    state.providers.forEach(function (provider) { option(select, provider.id, provider.name + " · " + provider.vendor, !provider.enabled); });
    select.value = current; state.selectedProvider = select.value || current;
  }
  function renderModels() {
    renderModelProviderSelect();
    var body = $("admin-ai-models"); body.textContent = "";
    var provider = selectedProvider();
    if (!provider) { var row = document.createElement("tr"); var cell = document.createElement("td"); cell.colSpan = 5; text(cell, "暂无 Provider，请先在“供应商”中添加。"); row.appendChild(cell); body.appendChild(row); return; }
    var query = $("admin-ai-model-search").value.trim().toLowerCase();
    var items = modelsFor(provider.id).filter(function (item) { return !query || (item.model_id + " " + (item.display_name || "")).toLowerCase().indexOf(query) >= 0; });
    if (!items.length) {
      var empty = document.createElement("tr"); var emptyCell = document.createElement("td"); emptyCell.colSpan = 5; text(emptyCell, query ? "没有匹配的模型" : "暂无模型，可同步 Provider 模型或手工添加"); empty.appendChild(emptyCell); body.appendChild(empty); return;
    }
    items.forEach(function (item) {
      var row = document.createElement("tr");
      var id = document.createElement("td"); var strong = document.createElement("strong"); text(strong, item.model_id); id.appendChild(strong); if (item.display_name && item.display_name !== item.model_id) { var name = document.createElement("small"); text(name, item.display_name); id.appendChild(name); } row.appendChild(id);
      var caps = document.createElement("td"); CAPABILITIES.forEach(function (pair) { if (item.capabilities && item.capabilities[pair[0]] === true) caps.appendChild(badge(pair[1])); }); if (!caps.childNodes.length) caps.appendChild(badge("能力未声明", "muted")); row.appendChild(caps);
      var status = document.createElement("td"); var discoveryClass = item.available && item.enabled && item.last_test_status === "passed" ? "ok" : item.available && item.enabled ? "muted" : "disabled"; status.appendChild(badge(item.available && item.enabled ? "● 已发现" : (item.available ? "○ 已停用" : "○ 未发现"), discoveryClass)); var verification = document.createElement("small"); var verificationText = item.last_test_status === "passed" ? "已验证" : item.last_test_status === "failed" ? "测试失败：" + (item.last_test_category || "unknown") : "未测试"; text(verification, "模型验证：" + verificationText + (item.last_test_ttft_ms == null ? "" : " · TTFT " + Math.round(Number(item.last_test_ttft_ms)) + " ms")); status.appendChild(verification); row.appendChild(status);
      var source = document.createElement("td"); text(source, capabilitySourceLabel(item.capability_source));
      if (item.capability_verified_at) { var verified = document.createElement("small"); text(verified, "验证：" + item.capability_verified_at); source.appendChild(verified); }
      if (item.capability_profile) { var catalog = document.createElement("small"); text(catalog, "Profile：" + item.capability_profile + (item.capability_catalog_version ? " / " + item.capability_catalog_version : "")); source.appendChild(catalog); }
      if (item.canonical_model) { var alias = document.createElement("small"); text(alias, "旧名称 · 实际映射至 " + item.canonical_model); id.appendChild(alias); }
      if (item.capability_source === "unknown") { var warning = document.createElement("small"); text(warning, "已发现，但显式能力尚未验证；默认仅允许 Auto"); source.appendChild(warning); }
      row.appendChild(source);
      var actions = document.createElement("td"); actions.appendChild(actionButton("测试模型", function () {
        if (!window.confirm("将发送一次很短的真实流式请求，可能消耗少量额度。继续吗？")) return;
        var button = this; runButton(button, "测试中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/models/" + encodeURIComponent(item.model_id) + "/test", { method: "POST" }); }).then(function (result) { item.last_test_status = result.status; item.last_test_category = result.category; item.last_test_ttft_ms = result.ttft_ms; item.last_test_latency_ms = result.latency_ms; renderModels(); setStatus(result.ok ? "ok" : "partial", result.ok ? "模型已验证" : "模型测试失败：" + result.category); }).catch(function (error) { setStatus("partial", error.message); });
      })); actions.appendChild(actionButton("编辑", function () { openModelDialog(provider.id, item); })); actions.appendChild(actionButton(item.enabled ? "停用" : "启用", function () {
        var button = this; runButton(button, "处理中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/models/" + encodeURIComponent(item.model_id), { method: "PUT", body: JSON.stringify({ enabled: !item.enabled }) }); }).then(function () { return loadModels(provider.id); }).catch(function (error) { setStatus("partial", error.message); });
      })); row.appendChild(actions); body.appendChild(row);
    });
  }
  function setChecked(id, value) { $(id).checked = !!value; }
  function checked(id) { return $(id).checked; }
  function renderModelReasoningEditor() { $("admin-ai-reasoning-editor").hidden = !checked("admin-ai-cap-reasoning"); }
  function fillModelCapabilities(caps) {
    caps = caps || {};
    setChecked("admin-ai-cap-streaming", caps.streaming); setChecked("admin-ai-cap-tools", caps.tools); setChecked("admin-ai-cap-structured", caps.structured_output); setChecked("admin-ai-cap-reasoning", caps.reasoning);
    var modes = Array.isArray(caps.reasoning_modes) ? caps.reasoning_modes : [];
    setChecked("admin-ai-cap-mode-auto", modes.indexOf("auto") >= 0); setChecked("admin-ai-cap-mode-off", modes.indexOf("off") >= 0); setChecked("admin-ai-cap-mode-effort", modes.indexOf("effort") >= 0); setChecked("admin-ai-cap-mode-budget", modes.indexOf("budget") >= 0); setChecked("admin-ai-cap-budget", caps.reasoning_budget === true);
    document.querySelectorAll("#admin-ai-effort-grid input").forEach(function (input) { input.checked = Array.isArray(caps.reasoning_efforts) && caps.reasoning_efforts.indexOf(input.value) >= 0; });
    $("admin-ai-model-capabilities").value = JSON.stringify(caps, null, 2); renderModelReasoningEditor();
  }
  function openModelDialog(providerId, item) {
    state.editingModel = item ? { providerId: providerId, modelId: item.model_id } : { providerId: providerId, modelId: "" };
    $("admin-ai-model-dialog-title").textContent = item ? "编辑模型" : "手工添加模型";
    $("admin-ai-model-id").value = item ? item.model_id : ""; $("admin-ai-model-id").readOnly = !!item;
    $("admin-ai-model-display-name").value = item && item.display_name !== item.model_id ? (item.display_name || "") : "";
    $("admin-ai-model-enabled").checked = !item || item.enabled;
    fillModelCapabilities(item ? item.capabilities : {}); setMessage("admin-ai-model-message", ""); showDialog("admin-ai-model-dialog");
  }
  function collectCapabilities() {
    var raw = $("admin-ai-model-capabilities").value.trim(); var caps = {};
    if (raw) { try { caps = JSON.parse(raw); } catch (error) { setMessage("admin-ai-model-message", "Capability JSON 格式不正确。", "error"); return null; } }
    if (!caps || typeof caps !== "object" || Array.isArray(caps)) { setMessage("admin-ai-model-message", "Capability JSON 必须是对象。", "error"); return null; }
    caps.streaming = checked("admin-ai-cap-streaming"); caps.tools = checked("admin-ai-cap-tools"); caps.structured_output = checked("admin-ai-cap-structured"); caps.reasoning = checked("admin-ai-cap-reasoning");
    if (caps.reasoning) {
      caps.reasoning_modes = []; [["admin-ai-cap-mode-auto", "auto"], ["admin-ai-cap-mode-off", "off"], ["admin-ai-cap-mode-effort", "effort"], ["admin-ai-cap-mode-budget", "budget"]].forEach(function (pair) { if (checked(pair[0])) caps.reasoning_modes.push(pair[1]); });
      caps.reasoning_efforts = []; document.querySelectorAll("#admin-ai-effort-grid input:checked").forEach(function (input) { caps.reasoning_efforts.push(input.value); }); caps.reasoning_budget = checked("admin-ai-cap-budget");
    } else { caps.reasoning_modes = []; caps.reasoning_efforts = []; caps.reasoning_budget = false; }
    $("admin-ai-model-capabilities").value = JSON.stringify(caps, null, 2); return caps;
  }

  function renderRouteProviders(selectedId) {
    var select = $("admin-ai-profile-provider"); select.textContent = "";
    if (!state.providers.length) { emptyOption(select, "暂无 Provider，请先添加"); return; }
    state.providers.forEach(function (provider) { option(select, provider.id, provider.name + " · " + provider.vendor, !provider.enabled); });
    if (selectedId) select.value = selectedId;
    if (!select.value && state.providers.length) select.value = state.providers[0].id;
  }
  function renderRouteModels(providerId, selectedId) {
    var select = $("admin-ai-profile-model"); select.textContent = "";
    modelsFor(providerId).forEach(function (item) { if (item.enabled && item.available) option(select, item.model_id, item.display_name || item.model_id); });
    if (!select.options.length) emptyOption(select, providerId ? "暂无可用模型，请先同步或添加" : "请先选择 Provider");
    if (selectedId) select.value = selectedId;
    updateReasoningControls();
  }
  function updateReasoningControls() {
    var model = modelFor($("admin-ai-profile-provider").value, $("admin-ai-profile-model").value); var caps = model && model.capabilities || {};
    var modes = Array.isArray(caps.reasoning_modes) ? caps.reasoning_modes : ["auto"];
    var modelAvailable = !!model;
    var mode = $("admin-ai-reasoning-mode"); var previousMode = mode.value;
    mode.textContent = "";
    (modelAvailable ? modes : ["auto"]).forEach(function (item) { option(mode, item, item === "auto" ? "Auto" : item === "off" ? "Off" : item === "effort" ? "Effort" : "Budget"); });
    mode.value = modes.indexOf(previousMode) >= 0 ? previousMode : (modes.indexOf("auto") >= 0 ? "auto" : (modes[0] || "auto"));
    mode.disabled = !modelAvailable;
    var effortAllowed = Array.isArray(caps.reasoning_efforts) ? caps.reasoning_efforts : [];
    var effort = $("admin-ai-reasoning-effort"); var previousEffort = effort.value; effort.textContent = "";
    if (!effortAllowed.length) option(effort, "", "该模型未声明 Effort", true);
    else effortAllowed.forEach(function (item) { option(effort, item, String(item).toUpperCase() === "XHIGH" ? "XHigh" : String(item).charAt(0).toUpperCase() + String(item).slice(1)); });
    effort.value = effortAllowed.indexOf(previousEffort) >= 0 ? previousEffort : (effortAllowed[0] || "");
    effort.disabled = !modelAvailable || mode.value !== "effort" || !effortAllowed.length;
    $("admin-ai-reasoning-budget").disabled = !modelAvailable || mode.value !== "budget" || caps.reasoning_budget !== true;
    text($("admin-ai-reasoning-note"), modelAvailable && model.capability_source === "unknown" ? "显式推理能力尚未验证，当前仅允许 Auto。" : modelAvailable ? "仅显示当前模型已验证的 Reasoning 能力。" : "请先选择可用模型。");
  }
  function renderRouteCards() {
    var list = $("admin-ai-profiles"); list.textContent = "";
    Object.keys(BUSINESS).forEach(function (key) {
      var profile = state.profiles.find(function (item) { return item.business_key === key; }); var provider = profile && providerById(profile.provider_id); var card = document.createElement("article"); card.className = "ai-route-card";
      var header = document.createElement("div"); header.className = "ai-card-header"; var title = document.createElement("div"); title.className = "ai-card-title"; var h = document.createElement("h4"); text(h, BUSINESS[key].label); title.appendChild(h); var desc = document.createElement("p"); text(desc, BUSINESS[key].description); title.appendChild(desc); var stateBadge = document.createElement("span"); stateBadge.className = "ai-status-badge " + (profile && profile.enabled ? "ok" : "untested"); text(stateBadge, profile && profile.enabled ? "● 已启用" : "○ 未配置"); header.appendChild(title); header.appendChild(stateBadge); card.appendChild(header);
      var route = document.createElement("p"); route.className = "ai-route-target"; text(route, profile && provider ? provider.name + " / " + profile.model_id : "未配置"); card.appendChild(route);
      var strategy = document.createElement("p"); strategy.className = "ai-card-meta"; text(strategy, profile ? "Reasoning · " + (profile.reasoning_mode || "auto") + (profile.reasoning_effort ? " · " + profile.reasoning_effort : "") : "保存后将用于该业务"); card.appendChild(strategy);
      card.appendChild(actionButton("编辑", function () { openRouteDialog(key, profile); })); list.appendChild(card);
    });
  }
  function openRouteDialog(key, profile) {
    state.routeBusinessKey = key; $("admin-ai-route-dialog-title").textContent = "编辑 " + BUSINESS[key].label + " 路由"; text($("admin-ai-route-description"), BUSINESS[key].description); setMessage("admin-ai-route-message", "");
    renderRouteProviders(profile && profile.provider_id); var providerId = $("admin-ai-profile-provider").value; return loadModels(providerId).catch(function () { return null; }).then(function () {
      renderRouteModels(providerId, profile && profile.model_id); $("admin-ai-reasoning-mode").value = profile && profile.reasoning_mode || "auto"; $("admin-ai-reasoning-effort").value = profile && profile.reasoning_effort || "high"; $("admin-ai-reasoning-budget").value = profile && profile.reasoning_budget || ""; $("admin-ai-route-enabled").checked = !profile || profile.enabled; updateReasoningControls(); showDialog("admin-ai-route-dialog");
    });
  }

  function renderAll() { renderPresetSelect(); renderProviders(); renderModelProviderSelect(); renderModels(); renderRouteProviders(); renderRouteCards(); updateSummary(); }
  function settle(promise) { return promise.then(function (value) { return { ok: true, value: value }; }, function (error) { return { ok: false, error: error }; }); }
  function load() {
    setStatus("neutral", "加载中…");
    return Promise.all([settle(api("/api/admin/ai/provider-presets")), settle(api("/api/admin/ai/providers")), settle(api("/api/admin/ai/business-profiles"))]).then(function (results) {
      var errors = 0;
      if (results[0].ok) { state.presets = results[0].value.items || []; state.capabilityProfiles = results[0].value.capability_profiles || []; } else errors++;
      if (results[1].ok) state.providers = results[1].value.items || []; else errors++;
      if (results[2].ok) state.profiles = results[2].value.items || []; else errors++;
      if (!state.selectedProvider || !providerById(state.selectedProvider)) state.selectedProvider = state.providers[0] ? state.providers[0].id : "";
      renderAll();
      return loadAllModels().then(function () {
        renderAll();
        var modelErrors = state.providers.filter(function (provider) { return !!state.modelErrors[provider.id]; }).length;
        var totalErrors = errors + modelErrors;
        setStatus(totalErrors ? "partial" : "ok", errors === 3 ? "加载失败" : totalErrors ? "部分异常" : "配置正常");
      });
    }).catch(function () { setStatus("error", "加载失败"); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("admin-ai-config")) return;
    document.querySelectorAll("[data-ai-tab]").forEach(function (button) { button.onclick = function () { activateTab(button.getAttribute("data-ai-tab")); }; });
    $("admin-ai-preset").onchange = presetChanged;
    $("admin-ai-capability-profile").onchange = function () {
      var profile = capabilityProfile(this.value);
      text($("admin-ai-capability-profile-note"), profile ? profile.description : "");
    };
    $("admin-ai-provider-add").onclick = function () { openProviderDialog(); };
    document.querySelectorAll("[data-close-dialog]").forEach(function (button) { button.onclick = function () { closeDialog(button.getAttribute("data-close-dialog")); }; });
    $("admin-ai-provider-form").onsubmit = function (event) {
      event.preventDefault(); setMessage("admin-ai-provider-message", "");
      var payload = { name: $("admin-ai-name").value.trim(), vendor: $("admin-ai-vendor").value.trim(), protocol: $("admin-ai-protocol").value, capability_profile: $("admin-ai-capability-profile").value, base_url: $("admin-ai-base-url").value.trim(), models_path: $("admin-ai-models-path").value.trim() || "/models" };
      var key = $("admin-ai-key").value; if (key) payload.api_key = key; if ($("admin-ai-clear-key").checked) payload.clear_api_key = true;
      var path = state.editingProviderId ? "/api/admin/ai/providers/" + encodeURIComponent(state.editingProviderId) : "/api/admin/ai/providers";
      var method = state.editingProviderId ? "PUT" : "POST"; var button = $("admin-ai-provider-save");
      runButton(button, "保存中…", function () { return api(path, { method: method, body: JSON.stringify(payload) }); }).then(function () { closeDialog("admin-ai-provider-dialog"); return load(); }).then(function () { setStatus("ok", "配置正常"); }).catch(function (error) { setMessage("admin-ai-provider-message", error.message, "error"); setStatus("partial", "部分异常"); });
    };
    $("admin-ai-model-provider-select").onchange = function () { state.selectedProvider = this.value; loadModels(this.value).catch(function (error) { setStatus("partial", error.message); }); };
    $("admin-ai-model-search").oninput = renderModels;
    $("admin-ai-model-sync").onclick = function () {
      var provider = selectedProvider(); if (!provider) { setStatus("partial", "请先添加 Provider"); return; }
      var button = this; runButton(button, "同步中…", function () { return api("/api/admin/ai/providers/" + encodeURIComponent(provider.id) + "/discover-models", { method: "POST" }); }).then(function (result) { if (!result.ok) throw new Error("同步失败：" + result.category); state.modelsByProvider[provider.id] = result.items || []; renderAll(); setStatus("ok", "配置正常"); }).catch(function (error) { setStatus("partial", error.message); });
    };
    $("admin-ai-model-add").onclick = function () { var provider = selectedProvider(); if (!provider) { setStatus("partial", "请先添加 Provider"); return; } openModelDialog(provider.id); };
    $("admin-ai-model-form").onsubmit = function (event) {
      event.preventDefault(); var caps = collectCapabilities(); if (!caps || !state.editingModel) return;
      var providerId = state.editingModel.providerId; var modelId = $("admin-ai-model-id").value.trim(); if (!modelId) { setMessage("admin-ai-model-message", "Model ID 不能为空。", "error"); return; }
      var payload = { display_name: $("admin-ai-model-display-name").value.trim(), enabled: checked("admin-ai-model-enabled"), capabilities: caps }; var editing = !!state.editingModel.modelId; var path = "/api/admin/ai/providers/" + encodeURIComponent(providerId) + "/models" + (editing ? "/" + encodeURIComponent(state.editingModel.modelId) : ""); var button = $("admin-ai-model-save");
      runButton(button, "保存中…", function () { return api(path, { method: editing ? "PUT" : "POST", body: JSON.stringify(editing ? { display_name: payload.display_name, enabled: payload.enabled, capabilities: payload.capabilities } : { model_id: modelId, display_name: payload.display_name, enabled: payload.enabled, capabilities: payload.capabilities }) }); }).then(function () { closeDialog("admin-ai-model-dialog"); return loadModels(providerId); }).then(function () { setStatus("ok", "配置正常"); }).catch(function (error) { setMessage("admin-ai-model-message", error.message, "error"); setStatus("partial", "部分异常"); });
    };
    $("admin-ai-cap-reasoning").onchange = renderModelReasoningEditor;
    $("admin-ai-profile-provider").onchange = function () { renderRouteModels(this.value); loadModels(this.value).catch(function (error) { setMessage("admin-ai-route-message", error.message, "error"); }); };
    $("admin-ai-profile-model").onchange = updateReasoningControls; $("admin-ai-reasoning-mode").onchange = updateReasoningControls;
    $("admin-ai-route-form").onsubmit = function (event) {
      event.preventDefault(); var providerId = $("admin-ai-profile-provider").value; var modelId = $("admin-ai-profile-model").value; if (!providerId || !modelId) { setMessage("admin-ai-route-message", "请先配置并选择可用模型。", "error"); return; }
      var mode = $("admin-ai-reasoning-mode").value; var payload = { provider_id: providerId, model_id: modelId, reasoning_mode: mode, reasoning_effort: mode === "effort" ? $("admin-ai-reasoning-effort").value : null, reasoning_budget: mode === "budget" ? Number($("admin-ai-reasoning-budget").value) : null, enabled: checked("admin-ai-route-enabled") }; var button = $("admin-ai-profile-save");
      runButton(button, "保存中…", function () { return api("/api/admin/ai/business-profiles/" + encodeURIComponent(state.routeBusinessKey), { method: "PUT", body: JSON.stringify(payload) }); }).then(function () { closeDialog("admin-ai-route-dialog"); return load(); }).then(function () { setStatus("ok", "配置正常"); }).catch(function (error) { setMessage("admin-ai-route-message", error.message, "error"); setStatus("partial", "部分异常"); });
    };
    load();
  });
}());
