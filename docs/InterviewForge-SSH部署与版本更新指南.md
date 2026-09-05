# InterviewForge：后端部署与版本更新指南（VPS 版）

> **当前唯一正式后端**：Hostinger 吉隆坡 VPS（`hstgr-cloud`，76.13.217.130）。
> 域名 `hot100.xyz` / `www.hot100.xyz` 已 A 记录直连该机（Cloudflare DNS，灰色云仅解析）。
> 旧的局域网对端 `ljh@192.168.5.234`（Cloudflare Tunnel）已退役为**备用方案**，见附录 B。
> 本文档是日常运维的唯一依据；这台服务器是**与他人共用**的，第 4 节的红线务必遵守。

---

## 1. 当前架构速查（2026-09-05 起生效）

| 项目 | 值 |
|---|---|
| 连接方式 | `ssh hstgr-cloud`（本机 `~/.ssh/config` 已配好，密钥登录；IP 直连亦可：`ssh root@76.13.217.130`） |
| 系统 | Ubuntu 24.04，4C/15G/193G，Hostname `srv1432512.hstgr.cloud` |
| 应用目录 | `/opt/interview-forge`（git 仓库，运行用户 `forge`——无 sudo、无登录 shell） |
| 服务单元 | `systemd` 的 `interview-forge.service`，监听 `127.0.0.1:8765`，开机自启、崩溃自动拉起 |
| 反向代理 | nginx：我们的站点文件 **`/etc/nginx/sites-available/hot100`**（软链到 sites-enabled），反代 8765 |
| HTTPS | Let's Encrypt 证书，`certbot --nginx` 签发，**自动续期**（勿手动折腾） |
| 数据 | `/opt/interview-forge/data/`：`auth.db`（账户）+ `users/<用户名>/hot100-study.db`（各人学习库），**不入 git** |
| 访问 | `https://hot100.xyz`（公网）；登录门禁/注册码白名单/管理后台与旧版完全一致 |

### 这台机器上别人的东西（一口都不能碰）

- nginx 的 `dashboard` 站点及 `/etc/nginx/` 下除 `sites-available/hot100` 外的**所有**文件；
- `filebrowser`（公网 8899 端口）、`openclaw-gateway`（本机 18789~18792）；
- 同学的 SSH 会话与其 `RemoteForward` 隧道、`/root` 下他的文件、系统级配置（防火墙、sshd 等）。

---

## 2. 日常版本更新（唯一常用操作）

生成的 HTML/静态资源都已提交 GitHub，**VPS 上不跑构建**，更新 = 拉代码 + 重启服务：

```bash
ssh hstgr-cloud
cd /opt/interview-forge
git pull origin main
systemctl restart interview-forge
systemctl is-active interview-forge
curl -s https://hot100.xyz/api/health        # 期望 {"ok": true}
```

说明：

- 只改了纯文档/前端静态页时，`git pull` 后**不需要重启**（nginx 直接发新文件）；改了 `tools/`（服务端）才需要 `systemctl restart`。
- 拿不准就 restart，秒级完成、无副作用。

---

## 3. 红线：只改我们的项目

这台服务器与他人共用，每次操作前对照本节：

**允许做的（全部与项目相关）**

- `/opt/interview-forge` 内的 git 操作（pull / log / checkout 回滚）；
- `systemctl start|stop|restart|status interview-forge`；
- `journalctl -u interview-forge` 看日志；
- certbot 的日常续期（自动，不要手动改其配置）。

**禁止做的（除非服务器主人明确同意）**

- 修改/删除 `/etc/nginx/` 下除 `sites-available/hot100` 之外的任何文件；即使只改 `hot100` 这一个文件，也必须 `nginx -t` 通过后再 `systemctl reload nginx`；
- kill / restart 任何非 `interview-forge` 的进程或服务；
- 动 8899、18789~18792、80（他站点的部分）等端口上的东西；
- 修改防火墙、sshd、系统时间等全局配置；
- 在仓库外随意装软件；装依赖前先确认确属项目所需并记录在本文档。

**一条原则**：每条命令执行前问自己"这会碰到别人的东西吗"，拿不准就不执行、先问。

---

## 4. 回滚

```bash
ssh hstgr-cloud
cd /opt/interview-forge
git log --oneline -10          # 找要回退到的提交
git reset --hard <commit>      # 或 git checkout <commit> -- .
systemctl restart interview-forge
```

数据（`data/`）不在 git 内，回滚代码不会影响任何学习记录。

---

## 5. 数据备份

```bash
# 在本机执行：把整份数据拉回来（先停服务最稳妥，停启都是秒级）
ssh hstgr-cloud "systemctl stop interview-forge; tar -czf /tmp/forge-data.tgz -C /opt/interview-forge data; systemctl start interview-forge"
scp hstgr-cloud:/tmp/forge-data.tgz "$TEMP/forge-data.tgz"
ssh hstgr-cloud "rm /tmp/forge-data.tgz"
```

建议每月备份一次；`data/` 同时含账户库与全部学习记录，丢了无法从 git 恢复。

---

## 6. 故障排查

| 现象 | 处理 |
|---|---|
| 网站打不开（超时/拒连） | `ssh hstgr-cloud` 后 `systemctl status interview-forge`；`curl -s 127.0.0.1:8765/api/health` 分辨是应用挂了还是 nginx 问题 |
| 502 Bad Gateway | study_server 没起来：看 `journalctl -u interview-forge -n 50`；常见为代码语法错（pull 前本机务必先跑通） |
| 证书过期告警 | `certbot renew --dry-run` 检查自动续期；正常情况无需干预 |
| 更新后还是旧页面 | 浏览器 `Ctrl+Shift+R` 强刷；PWA 用户重开一次页面（缓存版本号在 `service-worker.js` 的 VERSION） |
| git pull 冲突 | VPS 上只应有 git 内容：`git status` 查看改动，`git checkout -- .` 丢弃本地改动后重拉 |
| 登录报"尝试次数过多" | 登录防爆破（5 次锁 10 分钟）；VPS 重启服务可清零：`systemctl restart interview-forge` |

---

## 7. 附录 A：VPS 初始部署存档（2026-09-05 已完成，供机器重建时参考）

1. 专用用户：`useradd -r -d /home/forge -s /usr/sbin/nologin forge`；
2. 代码：`mkdir /opt/interview-forge && chown forge:forge` → `sudo -u forge git clone https://github.com/lijihao-0804/interview-forge.git /opt/interview-forge`；
3. 数据：从旧对端打包 `data/` 传输解压，`chown -R forge:forge data`；
4. 服务单元 `/etc/systemd/system/interview-forge.service`（User=forge，ExecStart=`python3 tools/study_server.py --host 127.0.0.1 --port 8765 --quiet`，Restart=on-failure）；
5. nginx：`/etc/nginx/sites-available/hot100`（listen 80 → 443 由 certbot 自动改造；`proxy_pass http://127.0.0.1:8765`，带 X-Real-IP / X-Forwarded-For / X-Forwarded-Proto）；
6. 证书：`certbot --nginx -d hot100.xyz -d www.hot100.xyz`；
7. DNS：Cloudflare 面板把 `hot100.xyz` 与 `www` 改为 A 记录 `76.13.217.130`、**灰色云（仅 DNS）**。

重建时按 1→7 顺序即可，全程不触碰机器上其他服务。

---

## 8. 附录 B：备用方案——旧局域网对端（ljh@192.168.5.234，Cloudflare Tunnel）

状态：**仍在运行但已非正式后端**，域名已不指向它。完整指南见本文档的 git 历史
（`git log --diff-filter=M -- "*SSH*"` 找旧版），要点备份如下：

- 免密 SSH：`ssh ljh@192.168.5.234`（对端 IP 可能漂移，按计算机名 `DESKTOP-RDRAIIJ` 解析；该机双网卡，有线 .234 / WiFi .32）；
- 更新代码**不能直接 `git pull`**（对端到 GitHub 传输常被重置），用 bundle：本机
  `git bundle create t.bundle <对端HEAD>..main` → `scp` → 对端 `git pull t.bundle main`；
- 服务启停：杀 8765 端口进程 + `Start-Process python tools\study_server.py --host 0.0.0.0 --port 8765 --quiet`（PowerShell，base64 传命令见 git 历史详版）；
- 若要重新启用该后端：在 Cloudflare DNS 把两条记录改回 CNAME（隧道仍在 Zero Trust 里存活）；
  **注意两边的 `data/` 各自独立，切换后学习记录不互通**，切换前先备份合并。
