# InterviewForge：Cloudflare Tunnel 公网部署进度与后续计划

> 状态更新（2026-09-05 下午）：**公网已上线并完成安全增强部署**。
> https://hot100.xyz 已验证：登录门禁 307、API 401、HTTP→HTTPS 301、www 可用、
> Cookie 带 Secure、安全响应头生效、学习数据完好（98 题 / 365 天）。
> cloudflared 已注册为对端 Windows 服务（开机自启，QUIC 4 连接稳定）。
> 剩余待办：①管理员改为强密码（管理后台"账号安全"卡片自助操作）；
> ②观察公网访问速度，若首屏普遍 >10s 不可接受 → 启用第 4 节香港 VPS 方案。

---

## 1. 背景与选型

以下为选型过程存档，供回溯。

- 已购买域名 `hot100.xyz`（Dynadot），目标是把对端（局域网 Windows 主机）上的学习站发布到公网。
- 对端网络实测结论（2026-09-05）：
  - 出口公网 IP `112.2.68.39`（电信家宽，动态）；有 IPv6 但入站被防火墙拦，不可直接用；
  - **到 Cloudflare 边缘很慢**（单请求 7~15s），到国内站点快（Baidu 0.24s）；
  - **到 GitHub 传输常被重置**（`curl 28 Connection was reset`），对端 `git pull` 不可靠。
- 选型结论：先用**方案 2：Cloudflare Tunnel（零成本）**跑通公网访问；若速度不可接受，切
  方案 1（香港轻量 VPS + frp 隧道 + Caddy 自动 HTTPS，月费约 ¥30~40，国内访问快）。
  两个方案互不冲突，切换只需改域名 NS/DNS。

## 2. 当前状态（截至本文记录时）

### 已上线并验证的功能（对端与本机一致，代码 HEAD `ed865b2`）

| 功能 | 说明 |
|---|---|
| 登录认证 | `data/auth.db` 账户库；scrypt 密码哈希；服务端会话 Cookie（30 天）；登录 5 次失败锁 10 分钟 |
| 多用户隔离 | 每账号独立学习库 `data/users/<用户名>/hot100-study.db`，力扣凭证随库隔离 |
| 白名单注册 | 管理员在管理后台签发一次性注册码（`FORGE-XXXX-XXXX`）；"占码+建用户"原子事务 |
| 管理后台 | `/pages/admin.html`：注册码签发/吊销、用户列表/停用启用、重置密码（重置即踢下线） |
| 前端入口 | 右下角浮动胶囊（服务端注入 `assets/auth-widget.js`）；仅管理员可见"管理后台"链接 |
| 全站门禁 | 未登录页面 307 → `/pages/login.html`；API 401；管理页/管理 API 仅限 admin 角色 |

### 对端环境速查

| 项目 | 值 |
|---|---|
| 主机 | `DESKTOP-RDRAIIJ`，Windows，SSH 用户 `ljh` |
| 双网卡 | 有线 `192.168.5.234`（SSH/操作用这个）、WiFi `192.168.5.32`（同一台机器） |
| 服务 | `python tools/study_server.py --host 0.0.0.0 --port 8765 --quiet`（Start-Process 后台运行） |
| 访问 | `http://192.168.5.234:8765/`（局域网照常可用，公网走域名后两条通道并存） |
| 管理员 | 用户名 `2030309470`（密码未入档；**待办：上线后改为强密码**） |
| 数据 | `data/auth.db` + `data/users/<用户名>/hot100-study.db`，git 更新不会覆盖 |
| 仓库 | 对端 HEAD 同步到 `ed865b2`；`origin` 指向 GitHub |

### 已知坑与对策（重要）

1. **对端 `git pull` 会挂起/被重置** → 用 `docs/InterviewForge-SSH部署与版本更新指南.md` 第 7.2 节的
   **git bundle 离线更新**（本机 `git bundle create` → `scp` → 对端 `git pull <bundle>`）。
2. **SSH 多行 pwsh 脚本偶发卡死** → 拆成单行命令（`ssh ljh@$peer "cmd1; cmd2"`），单行稳定。
3. 对端 Windows 没有服务化管理 → `study_server.py` 重启后需要手动启动（或后续注册开机自启）。
4. 对端 SSH/启动命令需要 base64 + `pwsh -EncodedCommand` 时参考部署指南第 2 节的写法。

## 3. Cloudflare Tunnel 后续执行清单

### 3.1 用户侧（进行中 / 待完成）

- [x] 注册 Cloudflare，添加站点 `hot100.xyz`（Free 计划），获得两个 NS 地址
- [x] Dynadot → Nameservers → 改为 Cloudflare 的 NS（**当前正在等待生效**，通常几分钟~48h）
- [ ] Cloudflare 面板显示域名 **Active** 后：Zero Trust（one.dash.cloudflare.com）→
      Networks → Tunnels → Create a tunnel（Cloudflared）→ 命名 `interview-forge`
- [ ] 复制安装命令里的 **token**（`cloudflared service install <TOKEN>` 中那串）
- [ ] 隧道的 Public Hostname 添加两条映射（保存后自动建 CNAME）：
      - `hot100.xyz` → HTTP → `localhost:8765`
      - `www.hot100.xyz` → HTTP → `localhost:8765`
- [ ] SSL/TLS → Edge Certificates → 打开 **Always Use HTTPS**
- [ ] 把 token 交给开发者（或自行在对端执行 3.2 第 2 步的安装命令）

### 3.2 开发者侧（拿到 token 后执行，全程 SSH 到 `ljh@192.168.5.234`）

1. **安装 cloudflared**（对端连 GitHub 不稳，本机下载再传）：
   ```powershell
   # 本机：下载官方 msi
   curl -L -o $env:TEMP\cloudflared-windows-amd64.msi `
     https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi
   scp $env:TEMP\cloudflared-windows-amd64.msi ljh@192.168.5.234:cloudflared.msi
   # 对端：静默安装并验证（单行）
   ssh ljh@192.168.5.234 "msiexec /i $HOME\cloudflared.msi /qn; & `"C:\Program Files (x86)\cloudflared\cloudflared.exe`" --version"
   ```
2. **注册 Windows 服务**（开机自启、断线自动重连）：
   ```powershell
   ssh ljh@192.168.5.234 "cloudflared service install <TOKEN>"
   # 若 SSH 会话权限不足（Service install 需要管理员），备选：计划任务 SYSTEM 启动，
   # 或请用户在对端 RDP 里手动跑一次该命令并点 UAC 确认。
   ```
3. **端到端验证**（本机执行）：
   - `curl -sI https://hot100.xyz` → 期望 `HTTP/2 307` 且 Location 指向 `/pages/login.html`；
   - 管理员账号登录 → 验证书架页 / 学习记录页 / 管理后台均 200；
   - `https://hot100.xyz/api/health` 未登录应 401（门禁在公网同样生效）。
4. **兼容性收尾**：
   - 视测试结果把 `https://hot100.xyz` 加入 `tools/study_server.py` 的 CORS 白名单
     （涉及 `do_OPTIONS`、`send_json` 两处元组），否则书签脚本/扩展跨源提交记录会失败；
   - 建议把 `study_server.py` 也注册开机自启（对端重启后域名服务自动恢复），
     与 cloudflared 服务一起在重启后做一次"重启恢复演练"。
5. **安全收尾**：改强管理员密码（管理后台没有改自己密码的功能，可用
   `--create-admin` 幂等重建？不行——它不重置密码；需用 3.2 的 reset-password API
   思路：`POST /api/admin/users/reset-password` 对管理员账号不适用（仅用户），
   因此要么临时加 API，要么本地脚本直改 `auth.db`，实现时二选一）。

### 3.3 验收标准

- 公网 `https://hot100.xyz` 未登录只能看到登录页；注册需有效注册码；
- 局域网 `192.168.5.234:8765` 不受影响；
- 对端断电重启后：cloudflared 服务自启，`study_server` 自启（若第 4 步完成），
  域名恢复可访问；
- 速度可接受（若首屏普遍 >10s 且不可忍 → 启动方案 1）。

## 4. 备选方案（速度不可接受时启用）

香港轻量云服务器 + frp 反向隧道 + Caddy 自动 HTTPS：

- 架构：`用户 → hot100.xyz(A → VPS IP) → Caddy(TLS, 80/443) → frps → 隧道 → 对端 frpc → localhost:8765`
- 对端只需主动外连 VPS，无需公网 IP / 端口映射 / 备案（香港）；
- 成本：腾讯云/阿里云轻量 HK 约 ¥30~40/月；顺带解决对端访问 GitHub 不稳的问题
  （git 可走 VPS 加速）；
- 迁移方式：Dynadot/CF 把 DNS 从 CF 代理切为 A 记录指向 VPS 即可，服务端零改动。

## 5. 上线前安全清单（公网暴露后必查）

- [ ] 管理员密码改为强密码（见 3.2 第 5 步的实现说明）
- [ ] Cloudflare 打开 Always Use HTTPS；浏览器访问 `http://hot100.xyz` 应 301 到 https
- [ ] 注册码只发给目标用户（公网下注册码就是白名单门槛）
- [ ] 力扣凭证现在随用户库隔离存储；提醒用户域名通道下同样只存本机（对端）
- [ ] 观察对端 `data/users/*/` 是否出现异常注册（管理后台用户列表核对）
