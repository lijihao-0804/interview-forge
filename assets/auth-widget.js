/* InterviewForge 认证胶囊 + 悬浮聊天室 + 个人资料（由 study_server 在 HTML 响应中注入）。
 * 胶囊：聊天室入口（悬浮窗）/ 管理后台（仅管理员可见）/ 用户名（点击设置昵称与头像）/ 退出。
 * 聊天室：自研轻量公屏（轮询增量），自己的消息靠右、别人的靠左，消息保留最近 2000 条。 */
(function () {
  "use strict";
  if (document.getElementById("forge-auth-pill")) return;
  fetch("/api/me", { cache: "no-store" })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (me) {
      if (!me || document.getElementById("forge-auth-pill")) return;

      var style = document.createElement("style");
      style.textContent =
        "#forge-auth-pill{position:fixed;right:16px;bottom:16px;z-index:9998;display:flex;align-items:center;gap:10px;" +
        "padding:6px 8px 6px 14px;border:1px solid #dfe4ee;border-radius:999px;background:rgba(255,255,255,.92);" +
        "box-shadow:0 8px 24px rgba(33,45,73,.16);font:13px/1.4 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#182235}" +
        "#forge-auth-pill .fap-name{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#66748a}" +
        "#forge-auth-pill a{color:#5654d4;text-decoration:none;font-weight:600}" +
        "#forge-auth-pill a:hover{color:#4543bd;text-decoration:underline}" +
        "#forge-auth-pill .fap-chat,#forge-auth-pill .fap-name{cursor:pointer}" +
        "#forge-auth-pill button{border:0;background:#eeedff;color:#4543bd;font:inherit;font-size:12px;font-weight:600;" +
        "padding:4px 12px;border-radius:999px;cursor:pointer}" +
        "#forge-auth-pill button:hover{background:#dedcfb}" +
        ".forge-panel{position:fixed;right:16px;bottom:58px;z-index:9999;width:min(360px,calc(100vw - 32px));" +
        "background:#fff;border:1px solid #dfe4ee;border-radius:14px;box-shadow:0 16px 44px rgba(33,45,73,.22);" +
        "font:14px/1.6 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#182235;display:flex;flex-direction:column}" +
        ".forge-panel .fp-head{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid #dfe4ee}" +
        ".forge-panel .fp-head h3{margin:0;font-size:14px}" +
        ".forge-panel .fp-head .fp-sub{font-size:11px;color:#66748a;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        ".forge-panel .fp-head .fp-close{margin-left:auto;border:0;background:transparent;color:#66748a;cursor:pointer;font-size:14px;padding:2px 6px}" +
        "@media (max-width:640px){#forge-auth-pill{right:10px;bottom:10px;padding:4px 6px 4px 10px}" +
        ".forge-panel{right:10px;bottom:58px}}";
      document.head.appendChild(style);

      function closePanels(except) {
        ["forge-chat-panel", "forge-profile"].forEach(function (id) {
          if (id !== except) { var p = document.getElementById(id); if (p) p.remove(); }
        });
        if (except !== "forge-chat-panel" && chatTimer) { clearInterval(chatTimer); chatTimer = null; }
      }

      /* ===================== 悬浮聊天室（公屏） ===================== */
      var chatTimer = null;
      var chatState = { lastId: -1, lastTime: null, myName: "", myRole: "user" };
      var CHAT_COLORS = ["#5654d4", "#157a52", "#a85b00", "#b3372f", "#4543bd", "#0f766e"];
      var unread = 0, seenId = -1, unreadTimer = null, baseTitle = document.title;
      function setUnread(n) {
        unread = n;
        var b = document.getElementById("fap-unread");
        if (b) { b.textContent = n > 0 ? String(n) : ""; b.style.display = n > 0 ? "inline-block" : "none"; }
        document.title = n > 0 ? "(" + n + ") " + baseTitle : baseTitle;
      }
      function authGone() {
        location.replace("/pages/login.html?next=" + encodeURIComponent(location.pathname + location.search));
      }

      function toggleChat() {
        var exist = document.getElementById("forge-chat-panel");
        if (exist) {
          exist.remove();
          if (chatTimer) { clearInterval(chatTimer); chatTimer = null; }
          return;
        }
        closePanels("forge-chat-panel");
        chatState.myName = me.username;
        chatState.myRole = me.role;
        chatState.lastId = -1;      // 重置增量游标：重新加载最近 50 条，否则旧游标导致面板卡在加载中
        chatState.lastTime = null;
        setUnread(0);               // 打开面板即视为全部已读
        var panel = document.createElement("div");
        panel.id = "forge-chat-panel";
        panel.className = "forge-panel";
        panel.style.height = "min(480px, 70vh)";
        panel.innerHTML =
          '<div class="fp-head"><h3>聊天室</h3><span class="fp-sub">公屏 · 所有人可见 · 请文明发言</span>' +
          '<button class="fp-close" type="button">✕</button></div>' +
          '<div id="fcp-msgs" style="flex:1;overflow-y:auto;padding:12px 12px 4px;display:flex;flex-direction:column;gap:9px">' +
          '<div style="color:#66748a;font-size:13px;padding:8px">加载中…</div></div>' +
          '<div style="display:flex;gap:8px;padding:10px 12px 12px">' +
          '<input id="fcp-input" maxlength="500" placeholder="说点什么…（Enter 发送）" autocomplete="off" style="flex:1;min-width:0;padding:8px 11px;border:1px solid #dfe4ee;border-radius:9px;font:inherit;background:#fbfcff">' +
          '<button id="fcp-send" style="border:0;border-radius:9px;padding:8px 15px;font:inherit;font-weight:600;cursor:pointer;background:#5654d4;color:#fff">发送</button></div>';
        document.body.appendChild(panel);
        panel.querySelector(".fp-close").onclick = function () { toggleChat(); };

        var msgs = panel.querySelector("#fcp-msgs");
        function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
        function avaNode(username, nickname) {
          var img = el("img");
          img.style.cssText = "flex:0 0 30px;width:30px;height:30px;border-radius:50%;object-fit:cover;border:1px solid #dfe4ee";
          img.alt = nickname;
          img.onerror = function () {
            var d = el("div", null, (nickname || username || "?").slice(0, 1).toUpperCase());
            d.style.cssText = "flex:0 0 30px;width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;" +
              "color:#fff;font-weight:700;font-size:14px;background:" + CHAT_COLORS[(username || "").length % CHAT_COLORS.length];
            img.replaceWith(d);
          };
          img.src = "/api/avatar/" + encodeURIComponent(username) + "?t=" + Date.now();
          return img;
        }
        function fmtDivider(iso) {
          var d = new Date(iso);
          var hm = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
          if (d.toDateString() === new Date().toDateString()) return hm;
          return (d.getMonth() + 1) + "-" + d.getDate() + " " + hm;
        }
        function addMessage(m, isInit) {
          var nearBottom = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 90;
          var isSelf = m.username === chatState.myName;
          // QQ 式时间分隔：距上一条消息超过 5 分钟（或本批首条）时居中显示一次时间
          var ts = new Date(m.created_at).getTime();
          if (!chatState.lastTime || ts - chatState.lastTime > 5 * 60 * 1000) {
            var divider = el("div", null, fmtDivider(m.created_at));
            divider.style.cssText = "text-align:center;font-size:11px;color:#8a97ab;margin:4px 0";
            msgs.appendChild(divider);
          }
          chatState.lastTime = ts;
          var row = el("div");
          row.style.cssText = "display:flex;gap:8px;max-width:100%;align-items:flex-start;" +
            (isSelf ? "flex-direction:row-reverse;" : "");
          row.appendChild(avaNode(m.username, m.nickname));
          var body = el("div");
          body.style.cssText = "min-width:0;background:" + (isSelf ? "#eeedff" : "#f8f9fd") +
            ";border:1px solid #dfe4ee;border-radius:10px;padding:6px 10px;width:fit-content;" +
            "max-width:82%;align-self:" + (isSelf ? "flex-end" : "flex-start") + ";" +
            (isSelf ? "text-align:left;" : "");
          var meta = el("div");
          meta.style.cssText = "font-size:11px;color:#66748a;display:flex;gap:6px;align-items:center;";
          if (!isSelf) meta.appendChild(el("span", null, m.nickname || m.username));
          if (meta.children.length) { meta.style.marginBottom = "2px"; body.appendChild(meta); }
          var txt = el("div", null, m.content);
          txt.style.cssText = "overflow-wrap:anywhere;white-space:pre-wrap";
          body.appendChild(txt);
          row.appendChild(body);
          msgs.appendChild(row);
          while (msgs.children.length > 300) msgs.removeChild(msgs.firstChild);
          if (isInit || nearBottom) msgs.scrollTop = msgs.scrollHeight;
        }
        function poll() {
          fetch("/api/chat/messages?after=" + chatState.lastId, { cache: "no-store" })
            .then(function (r) { if (r.status === 401) { authGone(); return null; } return r.json(); })
            .then(function (d) {
              if (!d) return;
              if (chatState.lastId < 0) {
                msgs.textContent = "";
                if (!d.items.length) {
                  var hint = el("div", null, "还没有人发言，来抢沙发！");
                  hint.style.cssText = "color:#66748a;font-size:13px;padding:8px";
                  msgs.appendChild(hint);
                }
              }
              d.items.forEach(function (m) { addMessage(m, chatState.lastId < 0); });
              if (d.items.length) chatState.lastId = d.items[d.items.length - 1].id;
            }).catch(function () {});
        }
        function send() {
          var input = panel.querySelector("#fcp-input");
          var btn = panel.querySelector("#fcp-send");
          var content = input.value.trim();
          if (!content) return;
          btn.disabled = true;
          fetch("/api/chat/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: content }) })
            .then(function (r) { if (r.status === 401) { authGone(); return null; } return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (res) {
              if (!res) return;
              btn.disabled = false;
              if (!res.ok) { alert(res.data.error || "发送失败"); return; }
              input.value = "";
              poll();
            });
        }
        panel.querySelector("#fcp-send").onclick = send;
        panel.querySelector("#fcp-input").addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
        poll();
        chatTimer = setInterval(poll, 3000);
      }

      /* ===================== 个人资料（昵称 + 头像） ===================== */
      var profilePanel = null;
      function toggleProfile() {
        var exist = document.getElementById("forge-profile");
        if (exist) { exist.remove(); return; }
        closePanels("forge-profile");
        var panel = document.createElement("div");
        panel.id = "forge-profile";
        panel.className = "forge-panel";
        panel.style.display = "block";
        panel.innerHTML =
          '<div class="fp-head"><h3>昵称与头像</h3><span class="fp-sub">' + me.username + '</span>' +
          '<button class="fp-close" type="button">✕</button></div>' +
          '<div style="padding:12px 14px 14px">' +
          '<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">' +
          '<span id="fpr-ava-box"></span>' +
          '<input type="file" id="fpr-file" accept="image/png,image/jpeg,image/webp" style="font-size:12px;max-width:160px">' +
          '</div>' +
          '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">' +
          '<input type="text" id="fpr-nick" maxlength="16" placeholder="昵称（1~16 字，留空显示用户名）" style="flex:1;min-width:0;padding:7px 10px;border:1px solid #dfe4ee;border-radius:8px;font:inherit;background:#fbfcff">' +
          '<button id="fpr-save" style="border:0;border-radius:8px;padding:7px 13px;font:inherit;font-weight:600;cursor:pointer;background:#5654d4;color:#fff">保存</button>' +
          '</div>' +
          '<button id="fpr-clear" style="border:1px solid #dfe4ee;background:transparent;color:#66748a;border-radius:8px;padding:5px 11px;font:inherit;cursor:pointer">清除头像</button>' +
          '<div id="fpr-hint" style="font-size:12px;color:#66748a;margin-top:6px;min-height:16px"></div></div>';
        document.body.appendChild(panel);
        panel.querySelector(".fp-close").onclick = function () { toggleProfile(); };
        var hint = panel.querySelector("#fpr-hint");
        var avaBox = panel.querySelector("#fpr-ava-box");

        function renderAva(url) {
          avaBox.textContent = "";
          var makeInit = function () {
            var d = document.createElement("div");
            d.textContent = (me.nickname || me.username).slice(0, 1).toUpperCase();
            d.style.cssText = "width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;" +
              "color:#fff;font-weight:700;background:#5654d4";
            avaBox.appendChild(d);
          };
          if (url) {
            var img = document.createElement("img");
            img.style.cssText = "width:48px;height:48px;border-radius:50%;object-fit:cover;border:1px solid #dfe4ee";
            img.onerror = makeInit;
            img.src = url;
            avaBox.appendChild(img);
          } else makeInit();
        }
        fetch("/api/avatar/" + encodeURIComponent(me.username) + "?t=" + Date.now())
          .then(function (r) {
            if (r.ok) r.blob().then(function (b) { renderAva(URL.createObjectURL(b)); });
            else renderAva(null);
          })
          .catch(function () { renderAva(null); });
        fetch("/api/profile", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (p) {
          if (profilePanel) panel.querySelector("#fpr-nick").value = p.nickname || "";
        });

        function callProfile(body) {
          return fetch("/api/profile", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); });
        }
        panel.querySelector("#fpr-save").onclick = function () {
          hint.textContent = "保存中…"; hint.style.color = "#66748a";
          callProfile({ nickname: panel.querySelector("#fpr-nick").value }).then(function (res) {
            if (!res.ok) { hint.textContent = res.data.error || "保存失败"; hint.style.color = "#b3372f"; return; }
            me.nickname = res.data.nickname;
            name.textContent = me.nickname || me.username;
            hint.textContent = "已保存"; hint.style.color = "#157a52";
          });
        };
        panel.querySelector("#fpr-clear").onclick = function () {
          callProfile({ avatar: "" }).then(function (res) {
            if (!res.ok) { hint.textContent = res.data.error || "操作失败"; hint.style.color = "#b3372f"; return; }
            renderAva(null);
            hint.textContent = "头像已清除"; hint.style.color = "#157a52";
          });
        };
        panel.querySelector("#fpr-file").addEventListener("change", function () {
          var file = this.files && this.files[0];
          if (!file) return;
          hint.textContent = "处理中…"; hint.style.color = "#66748a";
          var reader = new FileReader();
          reader.onload = function () {
            var img = new Image();
            img.onload = function () {
              var canvas = document.createElement("canvas");
              canvas.width = 64; canvas.height = 64;
              var ctx = canvas.getContext("2d");
              var side = Math.min(img.width, img.height);
              ctx.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 64, 64);
              var dataUrl = canvas.toDataURL("image/jpeg", 0.85);
              callProfile({ avatar: dataUrl }).then(function (res) {
                if (!res.ok) { hint.textContent = res.data.error || "上传失败"; hint.style.color = "#b3372f"; return; }
                renderAva(dataUrl);
                hint.textContent = "头像已更新"; hint.style.color = "#157a52";
              });
            };
            img.src = reader.result;
          };
          reader.readAsDataURL(file);
        });
      }

      /* ===================== 胶囊本体 ===================== */
      var pill = document.createElement("div");
      pill.id = "forge-auth-pill";

      var chatLink = document.createElement("a");
      chatLink.className = "fap-chat";
      chatLink.textContent = "聊天室";
      chatLink.onclick = function (e) { e.preventDefault(); toggleChat(); };
      var unreadBadge = document.createElement("span");
      unreadBadge.id = "fap-unread";
      unreadBadge.style.cssText = "display:none;background:#b3372f;color:#fff;border-radius:99px;padding:0 6px;font-size:10px;font-weight:700;margin-left:4px";
      chatLink.appendChild(unreadBadge);
      pill.appendChild(chatLink);
      var sep0 = document.createElement("span");
      sep0.textContent = "·";
      sep0.style.color = "#dfe4ee";
      pill.appendChild(sep0);

      if (me.role === "admin") {
        var adminLink = document.createElement("a");
        adminLink.href = "/pages/admin.html";
        adminLink.textContent = "管理后台";
        pill.appendChild(adminLink);
        var sep = document.createElement("span");
        sep.textContent = "·";
        sep.style.color = "#dfe4ee";
        pill.appendChild(sep);
      }

      var name = document.createElement("span");
      name.className = "fap-name";
      name.title = "点击设置昵称与头像";
      name.textContent = me.nickname || me.username;
      name.onclick = toggleProfile;
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
        }).finally(function () { location.replace("/pages/login.html"); });
      };
      pill.appendChild(logout);

      document.body.appendChild(pill);

      // ---- 聊天未读感知：面板关闭时每 15 秒探针一次；401 视为会话过期跳登录 ----
      fetch("/api/chat/messages?after=-1&limit=1", { cache: "no-store" })
        .then(function (r) { if (r.status === 401) { authGone(); return null; } return r.json(); })
        .then(function (d) { if (d && d.items && d.items.length) seenId = d.items[0].id; })
        .catch(function () {});
      unreadTimer = setInterval(function () {
        if (document.getElementById("forge-chat-panel")) return;   // 面板自身在轮询
        fetch("/api/chat/messages?after=" + seenId + "&limit=50", { cache: "no-store" })
          .then(function (r) {
            if (r.status === 401) { authGone(); return null; }
            return r.json().then(function (d) { return { status: r.status, data: d }; });
          })
          .then(function (res) {
            if (!res || !res.data) return;
            var fromOthers = res.data.items.filter(function (m) { return m.username !== me.username; });
            if (fromOthers.length) setUnread(unread + fromOthers.length);
            if (res.data.items.length) seenId = res.data.items[res.data.items.length - 1].id;
          }).catch(function () {});
      }, 15000);
    });
})();
