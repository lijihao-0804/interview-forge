/* InterviewForge 反馈小部件（由 study_server 在 HTML 响应中注入）。
 * 右下角小圆圈（位于认证胶囊上方），点击弹出反馈面板；
 * 提交内容进入 auth.db 的 feedback 表，管理员在管理后台逐一处理。
 * 公开接口（未登录也可报"登录不了"），服务端按 IP 限 5 次/小时。 */
(function () {
  "use strict";
  if (document.getElementById("forge-fb-btn")) return;

  var style = document.createElement("style");
  style.textContent =
    "#forge-fb-btn{position:fixed;right:16px;bottom:58px;z-index:9998;width:38px;height:38px;border-radius:50%;" +
    "border:1px solid #dfe4ee;background:rgba(255,255,255,.94);box-shadow:0 6px 18px rgba(33,45,73,.18);" +
    "font-size:17px;line-height:36px;text-align:center;cursor:pointer;user-select:none;transition:transform .15s}" +
    "#forge-fb-btn:hover{transform:scale(1.1);background:#eeedff}" +
    "#forge-fb-panel{position:fixed;right:16px;bottom:106px;z-index:9999;width:min(320px,calc(100vw - 32px));" +
    "background:#fff;border:1px solid #dfe4ee;border-radius:14px;padding:16px;box-shadow:0 16px 44px rgba(33,45,73,.22);" +
    "font:14px/1.6 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#182235}" +
    "#forge-fb-panel h3{margin:0 0 4px;font-size:15px}" +
    "#forge-fb-panel .fap-page{font-size:11px;color:#66748a;margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
    "#forge-fb-panel textarea{width:100%;height:96px;resize:vertical;padding:8px 10px;border:1px solid #dfe4ee;" +
    "border-radius:8px;font:inherit;background:#fbfcff;box-sizing:border-box}" +
    "#forge-fb-panel input{width:100%;margin-top:8px;padding:7px 10px;border:1px solid #dfe4ee;border-radius:8px;" +
    "font:inherit;background:#fbfcff;box-sizing:border-box}" +
    "#forge-fb-panel .fap-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:10px}" +
    "#forge-fb-panel button{border:0;border-radius:8px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}" +
    "#forge-fb-panel .fap-send{background:#5654d4;color:#fff}" +
    "#forge-fb-panel .fap-send:hover{background:#4543bd}" +
    "#forge-fb-panel .fap-close{background:transparent;color:#66748a}" +
    "#forge-fb-panel .fap-hint{font-size:12px;color:#66748a;margin-top:6px;min-height:16px}" +
    "#forge-fb-panel .fap-hint.err{color:#b3372f}" +
    "#forge-fb-panel .fap-hint.ok{color:#157a52}" +
    "@media (max-width:640px){#forge-fb-btn{right:10px;bottom:52px}#forge-fb-panel{right:10px;bottom:100px}}";
  document.head.appendChild(style);

  var btn = document.createElement("div");
  btn.id = "forge-fb-btn";
  btn.title = "反馈问题";
  btn.textContent = "🐞";

  var panel = null;
  function closePanel() { if (panel) { panel.remove(); panel = null; } }

  btn.onclick = function () {
    if (panel) { closePanel(); return; }
    panel = document.createElement("div");
    panel.id = "forge-fb-panel";
    panel.innerHTML =
      '<h3>反馈问题 🐞</h3>' +
      '<div class="fap-page" title="' + location.href + '">页面：' + location.pathname + '</div>' +
      '<textarea id="fb-content" placeholder="遇到什么问题？（必填，1~2000 字）&#10;例如：某某页面打不开 / 复习日期不对 / 显示错乱…"></textarea>' +
      '<input id="fb-contact" placeholder="联系方式（选填：QQ / 微信 / 邮箱）" autocomplete="off">' +
      '<div class="fap-actions"><button class="fap-close" type="button">取消</button>' +
      '<button class="fap-send" type="button">提交反馈</button></div>' +
      '<div class="fap-hint" id="fb-hint"></div>';
    document.body.appendChild(panel);
    panel.querySelector(".fap-close").onclick = closePanel;
    panel.querySelector("#fb-content").focus();

    panel.querySelector(".fap-send").onclick = function () {
      var hint = panel.querySelector("#fb-hint");
      var send = panel.querySelector(".fap-send");
      var content = panel.querySelector("#fb-content").value.trim();
      if (!content) { hint.textContent = "请先填写问题描述"; hint.className = "fap-hint err"; return; }
      send.disabled = true;
      hint.textContent = "提交中…"; hint.className = "fap-hint";
      fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: content,
          contact: panel.querySelector("#fb-contact").value.trim(),
          page: location.pathname + location.search
        })
      }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
          if (res.ok) {
            hint.textContent = "已提交，感谢反馈！我们会尽快处理。";
            hint.className = "fap-hint ok";
            setTimeout(closePanel, 1500);
          } else {
            hint.textContent = res.data.error || "提交失败，请稍后再试";
            hint.className = "fap-hint err";
            send.disabled = false;
          }
        })
        .catch(function () {
          hint.textContent = "网络错误，请稍后再试";
          hint.className = "fap-hint err";
          send.disabled = false;
        });
    };
  };

  document.body.appendChild(btn);
})();
