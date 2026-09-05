/* InterviewForge 认证小部件（由 study_server 在 HTML 响应中注入）。
 * 行为：右下角浮动胶囊，展示当前登录用户与"退出"入口；
 * 仅管理员可见"管理后台"链接（/api/me 返回 role=admin 才渲染），普通用户看不到任何管理入口。 */
(function () {
  "use strict";
  fetch("/api/me", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (me) {
      if (!me || document.getElementById("forge-auth-pill")) return;

      var style = document.createElement("style");
      style.textContent =
        "#forge-auth-pill{position:fixed;right:16px;bottom:16px;z-index:9999;display:flex;align-items:center;gap:10px;" +
        "padding:6px 8px 6px 14px;border:1px solid #dfe4ee;border-radius:999px;background:rgba(255,255,255,.92);" +
        "box-shadow:0 8px 24px rgba(33,45,73,.16);font:13px/1.4 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#182235}" +
        "#forge-auth-pill .fap-name{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#66748a}" +
        "#forge-auth-pill a{color:#5654d4;text-decoration:none;font-weight:600}" +
        "#forge-auth-pill a:hover{color:#4543bd;text-decoration:underline}" +
        "#forge-auth-pill button{border:0;background:#eeedff;color:#4543bd;font:inherit;font-size:12px;font-weight:600;" +
        "padding:4px 12px;border-radius:999px;cursor:pointer}" +
        "#forge-auth-pill button:hover{background:#dedcfb}" +
        "@media (max-width:640px){#forge-auth-pill{right:10px;bottom:10px;padding:4px 6px 4px 10px}}";
      document.head.appendChild(style);

      var pill = document.createElement("div");
      pill.id = "forge-auth-pill";

      if (me.role === "admin") {
        var adminLink = document.createElement("a");
        adminLink.href = "/admin.html";
        adminLink.textContent = "管理后台";
        pill.appendChild(adminLink);
        var sep = document.createElement("span");
        sep.textContent = "·";
        sep.style.color = "#dfe4ee";
        pill.appendChild(sep);
      }

      var name = document.createElement("span");
      name.className = "fap-name";
      name.title = me.username;
      name.textContent = me.username;
      pill.appendChild(name);

      var logout = document.createElement("button");
      logout.type = "button";
      logout.textContent = "退出";
      logout.onclick = function () {
        logout.disabled = true;
        fetch("/api/logout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}"
        }).finally(function () { location.replace("/login.html"); });
      };
      pill.appendChild(logout);

      document.body.appendChild(pill);
    })
    .catch(function () { /* 服务未启动或网络异常时静默退出，不干扰页面 */ });
})();
