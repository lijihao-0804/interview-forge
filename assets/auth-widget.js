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
        "padding:6px 8px 6px 14px;border:1px solid var(--line,#dfe4ee);border-radius:999px;background:color-mix(in srgb,var(--surface,var(--panel,#fff)) 92%,transparent);" +
        "box-shadow:0 8px 24px rgba(33,45,73,.16);font:13px/1.4 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:var(--text,#182235)}" +
        "#forge-auth-pill .fap-name{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted,#66748a)}" +
        "#forge-auth-pill a{color:var(--brand,#5654d4);text-decoration:none;font-weight:600}" +
        "#forge-auth-pill a:hover{color:var(--brand-strong,#4543bd);text-decoration:underline}" +
        "#forge-auth-pill .fap-chat,#forge-auth-pill .fap-name{cursor:pointer}" +
        "#forge-auth-pill .fap-name{border:0;padding:0;background:transparent;font:inherit}" +
        "#forge-auth-pill button{border:0;background:var(--brand-soft,#eeedff);color:var(--brand-strong,#4543bd);font:inherit;font-size:12px;font-weight:600;" +
        "padding:4px 12px;border-radius:999px;cursor:pointer}" +
        "#forge-auth-pill .fap-name{padding:0;background:transparent;color:var(--muted,#66748a);font-size:13px;font-weight:400}" +
        "#forge-auth-pill button:hover{background:color-mix(in srgb,var(--brand-soft,#eeedff) 82%,var(--brand,#5654d4))}" +
        "@keyframes forge-panel-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.forge-panel{animation:none}}.forge-panel{position:fixed;right:16px;bottom:58px;z-index:9999;width:min(360px,calc(100vw - 32px));animation:forge-panel-in .2s cubic-bezier(.22,1,.36,1);" +
        "background:var(--surface,var(--panel,#fff));border:1px solid var(--line,#dfe4ee);border-radius:14px;box-shadow:0 16px 44px rgba(33,45,73,.22);" +
        "font:14px/1.6 -apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:var(--text,#182235);display:flex;flex-direction:column}" +
        ".forge-panel .fp-head{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line,#dfe4ee)}" +
        ".forge-panel .fp-head h3{margin:0;font-size:14px}" +
        ".forge-panel .fp-head .fp-sub{font-size:11px;color:var(--muted,#66748a);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
        ".forge-panel .fp-head .fp-close{margin-left:auto;border:0;background:transparent;color:var(--muted,#66748a);cursor:pointer;font-size:14px;padding:2px 6px}" +
        ".forge-panel .fcp-older{display:flex;align-items:center;justify-content:center;min-height:30px;padding:4px 12px;border-bottom:1px solid var(--line,#dfe4ee);font-size:12px;color:var(--muted,#66748a)}" +
        ".forge-panel .fcp-older button{border:0;background:transparent;color:var(--brand,#5654d4);font:inherit;font-weight:600;cursor:pointer;padding:3px 8px;border-radius:7px}" +
        ".forge-panel .fcp-older button:hover{background:var(--brand-soft,#eeedff)}.forge-panel .fcp-older button:disabled{cursor:default;opacity:.65}" +
        ".forge-panel .fcp-status{min-height:18px;padding:0 12px 5px;color:var(--muted,#66748a);font-size:12px}" +
        "@media (max-width:640px){#forge-auth-pill{right:10px;bottom:calc(10px + env(safe-area-inset-bottom));padding:4px 6px 4px 10px}" +
        ".forge-panel{right:10px;bottom:calc(58px + env(safe-area-inset-bottom))}}";
      document.head.appendChild(style);

      function closePanels(except) {
        ["forge-chat-panel", "forge-profile"].forEach(function (id) {
          if (id !== except) {
            var p = document.getElementById(id);
            if (p) {
              p.remove();
              if (id === "forge-profile") profilePanel = null;
              if (id === "forge-chat-panel") {
                chatState.generation += 1;
                chatState.pollAgain = false;
              }
            }
          }
        });
        if (except !== "forge-chat-panel" && chatTimer) { clearInterval(chatTimer); chatTimer = null; }
      }

      /* ===================== 悬浮聊天室（公屏） ===================== */
      var chatTimer = null;
      var chatState = {
        oldestId: null, latestId: -1, hasOlder: true, olderLoading: false,
        myName: "", myRole: "user", messages: [], messageById: Object.create(null),
        pollInFlight: false, pollAgain: false, sendInFlight: false,
        generation: 0
      };
      var CHAT_COLORS = ["#5654d4", "#157a52", "#a85b00", "#b3372f", "#4543bd", "#0f766e"];
      var unread = 0, seenId = -1, unreadTimer = null, unreadInFlight = false, baseTitle = document.title;
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
          chatState.generation += 1;
          chatState.pollAgain = false;
          return;
        }
        closePanels("forge-chat-panel");
        chatState.generation += 1;
        var panelGeneration = chatState.generation;
        chatState.myName = me.username;
        chatState.myRole = me.role;
        chatState.oldestId = null;
        chatState.latestId = -1;    // 重置增量游标：重新加载最近 50 条，否则旧游标导致面板卡在加载中
        chatState.hasOlder = true;
        chatState.olderLoading = false;
        chatState.messages = [];
        chatState.messageById = Object.create(null);
        chatState.pollInFlight = false;
        chatState.pollAgain = false;
        chatState.sendInFlight = false;
        setUnread(0);               // 打开面板即视为全部已读
        var panel = document.createElement("div");
        panel.id = "forge-chat-panel";
        panel.className = "forge-panel";
        panel.style.height = "min(480px, 70vh)";
        panel.innerHTML =
          '<div class="fp-head"><h3>聊天室</h3><span class="fp-sub">公屏 · 所有人可见 · 请文明发言</span>' +
          '<button class="fp-close" type="button">✕</button></div>' +
          '<div class="fcp-older"><button id="fcp-load-older" type="button">加载更早消息</button><span id="fcp-older-state" aria-live="polite" hidden></span></div>' +
          '<div id="fcp-msgs" style="flex:1;overflow-y:auto;padding:12px 12px 4px;display:flex;flex-direction:column;gap:9px;background:var(--surface,var(--panel,#fff))">' +
          '<div style="color:var(--muted,#66748a);font-size:13px;padding:8px">加载中…</div></div>' +
          '<div class="fcp-status" id="fcp-status" aria-live="polite"></div>' +
          '<div style="display:flex;gap:8px;padding:10px 12px 12px;border-top:1px solid var(--line,#dfe4ee)">' +
          '<input id="fcp-input" maxlength="500" placeholder="说点什么…（Enter 发送）" autocomplete="off" style="flex:1;min-width:0;padding:8px 11px;border:1px solid var(--line,#dfe4ee);border-radius:9px;font:inherit;color:var(--text,#182235);background:var(--surface-softer,var(--soft,#fbfcff))">' +
          '<button id="fcp-send" style="border:0;border-radius:9px;padding:8px 15px;font:inherit;font-weight:600;cursor:pointer;background:var(--brand,#5654d4);color:#fff">发送</button></div>';
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
          img.src = "/api/avatar/" + encodeURIComponent(username);
          return img;
        }
        function fmtDivider(iso) {
          var d = new Date(iso);
          var hm = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
          if (d.toDateString() === new Date().toDateString()) return hm;
          return (d.getMonth() + 1) + "-" + d.getDate() + " " + hm;
        }
        function setChatStatus(message, isError) {
          var status = panel.querySelector("#fcp-status");
          if (!status) return;
          status.textContent = message || "";
          status.style.color = isError ? "var(--danger,#c1363e)" : "var(--muted,#66748a)";
        }
        function mergeMessages(items) {
          var changed = false;
          (items || []).forEach(function (m) {
            if (m == null || m.id == null || chatState.messageById[m.id]) return;
            chatState.messageById[m.id] = m;
            chatState.messages.push(m);
            changed = true;
          });
          if (!changed) return false;
          chatState.messages.sort(function (a, b) { return a.id - b.id; });
          // 服务端只保留 2000 条；客户端保留完整同等窗口，支持连续向前浏览且不裁掉刚加载的旧消息。
          if (chatState.messages.length > 2000) {
            var removed = chatState.messages.splice(0, chatState.messages.length - 2000);
            removed.forEach(function (m) { delete chatState.messageById[m.id]; });
          }
          chatState.oldestId = chatState.messages.length ? chatState.messages[0].id : null;
          chatState.latestId = chatState.messages.length ? chatState.messages[chatState.messages.length - 1].id : -1;
          return true;
        }
        function appendMessageNode(m, previousTime) {
          var isSelf = m.username === chatState.myName;
          var ts = new Date(m.created_at).getTime();
          // 时间分隔根据完整有序模型重算，跨分页批次仍保持正确。
          if (previousTime == null || !Number.isFinite(previousTime) || !Number.isFinite(ts) || ts - previousTime > 5 * 60 * 1000) {
            var divider = el("div", null, fmtDivider(m.created_at));
            divider.style.cssText = "text-align:center;font-size:11px;color:var(--muted,#8a97ab);margin:4px 0";
            msgs.appendChild(divider);
          }
          var row = el("div");
          row.style.cssText = "display:flex;gap:8px;max-width:100%;align-items:flex-start;" +
            (isSelf ? "flex-direction:row-reverse;" : "");
          row.appendChild(avaNode(m.username, m.nickname));
          var body = el("div");
          body.style.cssText = "min-width:0;background:" + (isSelf ? "var(--brand-soft,#eeedff)" : "var(--surface-soft,var(--soft,#f8f9fd))") +
            ";border:1px solid var(--line,#dfe4ee);border-radius:10px;padding:6px 10px;width:fit-content;" +
            "max-width:82%;align-self:" + (isSelf ? "flex-end" : "flex-start") + ";" +
            (isSelf ? "text-align:left;" : "");
          var meta = el("div");
          meta.style.cssText = "font-size:11px;color:var(--muted,#66748a);display:flex;gap:6px;align-items:center;";
          if (!isSelf) meta.appendChild(el("span", null, m.nickname || m.username));
          if (meta.children.length) { meta.style.marginBottom = "2px"; body.appendChild(meta); }
          var txt = el("div", null, m.content);
          txt.style.cssText = "overflow-wrap:anywhere;white-space:pre-wrap";
          body.appendChild(txt);
          row.appendChild(body);
          msgs.appendChild(row);
          return ts;
        }
        function renderMessages(scrollMode, oldHeight, oldTop) {
          msgs.textContent = "";
          if (!chatState.messages.length) {
            var hint = el("div", null, "还没有人发言，来抢沙发！");
            hint.style.cssText = "color:var(--muted,#66748a);font-size:13px;padding:8px";
            msgs.appendChild(hint);
          } else {
            var previousTime = null;
            chatState.messages.forEach(function (m) { previousTime = appendMessageNode(m, previousTime); });
          }
          if (scrollMode === "bottom") msgs.scrollTop = msgs.scrollHeight;
          else if (scrollMode === "prepend") msgs.scrollTop = Math.max(0, msgs.scrollHeight - oldHeight + oldTop);
          else if (scrollMode === "preserve") msgs.scrollTop = oldTop;
        }
        function setOlderState(message, isError) {
          var button = panel.querySelector("#fcp-load-older");
          var state = panel.querySelector("#fcp-older-state");
          if (!button || !state) return;
          button.disabled = chatState.olderLoading || !chatState.hasOlder;
          button.hidden = !chatState.hasOlder;
          button.textContent = chatState.olderLoading ? "加载中…" : (isError ? "重新加载" : "加载更早消息");
          state.hidden = !message;
          state.textContent = message || "";
          state.dataset.error = isError ? "1" : "0";
          state.style.color = isError ? "var(--danger,#c1363e)" : "var(--muted,#66748a)";
        }
        function loadOlder() {
          if (chatState.olderLoading || !chatState.hasOlder || chatState.oldestId == null) return;
          chatState.olderLoading = true;
          var generation = panelGeneration;
          setOlderState("正在加载更早消息…", false);
          fetch("/api/chat/messages?before=" + chatState.oldestId + "&limit=50", { cache: "no-store" })
            .then(function (r) {
              if (r.status === 401) { authGone(); return null; }
              if (!r.ok) throw new Error("older messages request failed");
              return r.json();
            })
            .then(function (d) {
              if (!d || generation !== chatState.generation || !document.body.contains(panel)) return;
              var oldHeight = msgs.scrollHeight;
              var oldTop = msgs.scrollTop;
              var changed = mergeMessages(d.items);
              chatState.hasOlder = d.has_older === true;
              if (changed) renderMessages("prepend", oldHeight, oldTop);
              setOlderState(chatState.hasOlder ? "" : "没有更早消息了", false);
            })
            .catch(function () {
              if (generation === chatState.generation && document.body.contains(panel)) {
                setOlderState("加载失败，点击重试", true);
              }
            })
            .finally(function () {
              if (generation !== chatState.generation) return;
              chatState.olderLoading = false;
              var state = panel.querySelector("#fcp-older-state");
              if (state && state.dataset.error === "1") {
                setOlderState("加载失败，请重试", true);
              } else {
                setOlderState(chatState.hasOlder ? "" : "没有更早消息了", false);
              }
            });
        }
        function poll() {
          if (chatState.pollInFlight) { chatState.pollAgain = true; return; }
          chatState.pollInFlight = true;
          var generation = panelGeneration;
          var cursor = chatState.latestId;
          var isInit = cursor < 0;
          setChatStatus("", false);
          fetch("/api/chat/messages?after=" + cursor, { cache: "no-store" })
            .then(function (r) {
              if (r.status === 401) { authGone(); return null; }
              if (!r.ok) throw new Error("chat messages request failed");
              return r.json();
            })
            .then(function (d) {
              if (generation !== chatState.generation || !document.body.contains(panel)) return;
              if (!d) return;
              var nearBottom = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 90;
              var oldTop = msgs.scrollTop;
              var changed = mergeMessages(d.items);
              if (isInit) chatState.hasOlder = d.has_older === true;
              if (changed || isInit) renderMessages(isInit || nearBottom ? "bottom" : "preserve", 0, oldTop);
              setOlderState(chatState.hasOlder ? "" : "没有更早消息了", false);
            })
            .catch(function () {
              if (generation === chatState.generation && document.body.contains(panel)) {
                setChatStatus("聊天室连接暂时不可用，请稍后重试", true);
              }
            })
            .finally(function () {
              if (generation !== chatState.generation) return;
              chatState.pollInFlight = false;
              if (chatState.pollAgain) { chatState.pollAgain = false; poll(); }
            });
        }
        panel.querySelector("#fcp-load-older").onclick = function () {
          loadOlder();
        };
        msgs.addEventListener("scroll", function () {
          if (msgs.scrollTop < 64) loadOlder();
        }, { passive: true });
        function send() {
          var input = panel.querySelector("#fcp-input");
          var btn = panel.querySelector("#fcp-send");
          var content = input.value.trim();
          if (!content || chatState.sendInFlight) return;
          chatState.sendInFlight = true;
          var sendGeneration = panelGeneration;
          btn.disabled = true;
          setChatStatus("发送中…", false);
          fetch("/api/chat/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: content }) })
            .then(function (r) {
              if (r.status === 401) { authGone(); return null; }
              return r.json().then(function (d) { return { ok: r.ok, data: d }; });
            })
            .then(function (res) {
              if (sendGeneration !== chatState.generation || !document.body.contains(panel)) return;
              if (!res) return;
              if (!res.ok) { setChatStatus(res.data.error || "发送失败，请稍后重试", true); return; }
              input.value = "";
              setChatStatus("", false);
              poll();
            })
            .catch(function () {
              if (sendGeneration === chatState.generation && document.body.contains(panel)) {
                setChatStatus("发送失败，请检查网络后重试", true);
              }
            })
            .finally(function () {
              if (sendGeneration !== chatState.generation) return;
              chatState.sendInFlight = false;
              btn.disabled = false;
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
        if (exist) { exist.remove(); profilePanel = null; return; }
        closePanels("forge-profile");
        var panel = document.createElement("div");
        panel.id = "forge-profile";
        panel.className = "forge-panel";
        panel.style.display = "block";
        profilePanel = panel;
        panel.innerHTML =
          '<div class="fp-head"><h3>昵称与头像</h3><span class="fp-sub">' + me.username + '</span>' +
          '<button class="fp-close" type="button">✕</button></div>' +
          '<div style="padding:12px 14px 14px">' +
          '<div style="display:flex;gap:10px;align-items:center;margin-bottom:10px">' +
          '<span id="fpr-ava-box"></span>' +
          '<input type="file" id="fpr-file" accept="image/png,image/jpeg,image/webp" style="font-size:12px;max-width:160px">' +
          '</div>' +
          '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap">' +
      '<span style="font-size:12px;color:#66748a;flex:none">题解语言</span>' +
      '<span id="fpr-lang" style="display:flex;gap:5px;flex-wrap:wrap"></span>' +
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

    var LANGS = [["java", "Java"], ["cpp", "C++"], ["python", "Python"], ["go", "Go"], ["c", "C"]];
    var langBox = panel.querySelector("#fpr-lang");
    function currentLang() {
      try { return localStorage.getItem("forge-lang") || (me.lang || "java"); } catch (e) { return (me.lang || "java"); }
    }
    function renderLangPills() {
      langBox.textContent = "";
      LANGS.forEach(function (pair) {
        var b = document.createElement("button");
        b.type = "button";
        b.textContent = pair[1];
        var on = currentLang() === pair[0];
        b.style.cssText = "border:1px solid #dfe4ee;border-radius:999px;padding:4px 12px;font:inherit;font-size:12px;" +
          "cursor:pointer;background:" + (on ? "#5654d4" : "transparent") + ";" +
          "color:" + (on ? "#fff" : "#66748a") + ";" +
          "font-weight:" + (on ? "700" : "500");
        b.onclick = function () {
          try { localStorage.setItem("forge-lang", pair[0]); } catch (e) { }
          me.lang = pair[0];
          fetch("/api/profile", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lang: pair[0] }) });
          document.dispatchEvent(new CustomEvent("forge-lang-change", { detail: { lang: pair[0] } }));
          renderLangPills();
          hint.textContent = "题解语言已设为 " + pair[1]; hint.style.color = "#157a52";
        };
        langBox.appendChild(b);
      });
    }
    renderLangPills();

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

      var chatLink = document.createElement("button");
      chatLink.type = "button";
      chatLink.setAttribute("aria-label", "打开聊天室");
      chatLink.className = "fap-chat";
      chatLink.textContent = "聊天室";
      chatLink.onclick = function () { toggleChat(); };
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
        adminLink.target = "_blank";
        adminLink.rel = "noopener noreferrer";
        adminLink.textContent = "管理后台";
        pill.appendChild(adminLink);
        var sep = document.createElement("span");
        sep.textContent = "·";
        sep.style.color = "#dfe4ee";
        pill.appendChild(sep);
      }

      var name = document.createElement("button");
      name.type = "button";
      name.setAttribute("aria-label", "设置昵称与头像");
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
        if (unreadInFlight) return;
        unreadInFlight = true;
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
          }).catch(function () {}).finally(function () { unreadInFlight = false; });
      }, 15000);
    });
})();
