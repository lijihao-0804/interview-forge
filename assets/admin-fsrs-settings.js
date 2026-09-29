(function () {
  "use strict";

  var input = document.getElementById("fsrsDesiredRetention");
  var save = document.getElementById("fsrsRetentionSave");
  var status = document.getElementById("fsrsRetentionStatus");
  if (!input || !save || !status) return;

  function show(message, isError) {
    status.textContent = message;
    status.className = "msg" + (isError ? " error" : " ok");
  }

  async function request(method, body) {
    var response = await fetch("/api/admin/settings/fsrs-retention", {
      method: method,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    });
    if (response.status === 401) {
      window.location.replace("/pages/login.html?next=" + encodeURIComponent(window.location.pathname));
      throw new Error("登录状态已失效");
    }
    var payload = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(payload.error || "请求未完成");
    return payload;
  }

  async function load() {
    try {
      var payload = await request("GET");
      input.value = String(payload.desired_retention);
      show("当前全站目标保持率：" + Math.round(Number(payload.desired_retention) * 100) + "%", false);
    } catch (error) {
      show(error.message || "读取设置失败", true);
    }
  }

  save.addEventListener("click", async function () {
    var value = Number(input.value);
    if (!Number.isFinite(value) || value < 0.8 || value > 0.95) {
      show("请输入 0.80 到 0.95 之间的数值。", true);
      input.focus();
      return;
    }
    save.disabled = true;
    show("正在保存…", false);
    try {
      var payload = await request("POST", { desired_retention: value });
      input.value = String(payload.desired_retention);
      show("已保存：" + Math.round(payload.desired_retention * 100) + "%；仅影响之后的新评分。", false);
    } catch (error) {
      show(error.message || "保存设置失败", true);
    } finally {
      save.disabled = false;
    }
  });

  load();
})();
