# InterviewForge：SSH 部署到另一台主机与版本更新指南

> 本指南只做一件事：把 InterviewForge 学习站部署到局域网对端主机，并支持以后版本更新。
> 对端 IP 由路由器 DHCP 分配，**可能变化**，因此每次运行前先执行第 0 步获取对端 IP。
> 不涉及多机任务分发，也不覆盖星地仿真项目。

---

## 0. 运行前：先获取对端 IP（每次都要做）

对端计算机名固定为 `DESKTOP-RDRAIIJ`，IP 可能随 DHCP 变化（本指南成文时为 `192.168.5.234`，早期文档中的 `192.168.5.222` 已过时）。

### 方式 A（推荐）：按计算机名解析

```powershell
ping -4 -n 1 DESKTOP-RDRAIIJ
```

即使显示"请求超时"，输出第一行也已给出解析到的 IP，例如：

```text
正在 Ping DESKTOP-RDRAIIJ.local [192.168.5.234] ...
```

### 方式 B：扫描网段（名称解析失败时用）

先在本机看自己网段（`ipconfig`），再扫描该网段并查 ARP 表：

```powershell
$subnet = "192.168.5"   # 按本机实际网段修改
1..254 | ForEach-Object {
    Start-Process -WindowStyle Hidden ping -ArgumentList @("-n","1","-w","100","$subnet.$_") | Out-Null
}
Start-Sleep 3
arp -a | Select-String "$subnet\.\d+" | ForEach-Object { $_.Line.Trim() }
```

中文系统 ARP 状态列显示为"动态"；对端开机在线时其 IP 会出现在列表中。

### 确认并固定到会话变量

拿到 IP 后，在本机 PowerShell 会话里设置变量并验证就是那台机器：

```powershell
$peer = "192.168.5.234"      # 换成你刚解析到的 IP
ssh ljh@$peer "hostname"     # 应输出 DESKTOP-RDRAIIJ
```

> `$peer` 只在当前会话有效：新开终端后必须先重新执行 `$peer = ...`，再跑后面的命令。
> 本指南后续所有命令统一使用 `$peer`，不再写死 IP。

> 对端有**有线 + WiFi 双网卡**（成文时有线 `192.168.5.234`、WiFi `192.168.5.32`），
> 同一台机器：学习站监听 `0.0.0.0:8765`，两个 IP 都能打开页面；
> SSH 操作建议固定走有线 `192.168.5.234`，避免一半命令走一个网卡造成假象。

---

## 1. 固定环境（沿用你已配好的 SSH）

| 项目 | 值 |
|---|---|
| 本机 | 与对端同网段的 Windows 主机（IP 不要求固定） |
| 对端 | `ljh@$peer`（IP 见第 0 步），SSH 端口 `22` |
| 对端计算机名 | `DESKTOP-RDRAIIJ` |
| 对端部署目录 | `C:\Users\ljh\interview-forge\` |
| 对端数据目录 | `C:\Users\ljh\interview-forge\data\`（SQLite 只在对端生成，不入库） |
| 源码仓库 | `https://github.com/lijihao-0804/interview-forge.git` |
| 访问地址 | `http://$peer:8765/` |

验证免密连接（第 0 步已验证过可跳过）：

```powershell
ssh ljh@$peer "echo CONNECT_OK"
```

---

## 2. 首次部署（推荐 git clone，以后更新最简单）

远程默认 Shell 是 PowerShell，为避免引号问题，统一用 base64 传命令。

### 2.1 确认对端有 Python

```powershell
$inner = 'python --version'
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

需要 Python 3.10+。

### 2.2 克隆项目到对端

```powershell
$inner = @'
if (-not (Test-Path "C:\Users\ljh\interview-forge\.git")) {
    git clone https://github.com/lijihao-0804/interview-forge.git "C:\Users\ljh\interview-forge"
} else {
    Set-Location "C:\Users\ljh\interview-forge"
    git pull origin main
}
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

首次运行时服务会自动创建 `data/hot100-study.db`，不需要手工建库。

---

## 3. 放行对端防火墙

```powershell
$inner = 'netsh advfirewall firewall add rule name="InterviewForge 8765" dir=in action=allow protocol=TCP localport=8765'
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

如果提示需要管理员权限，请在对端"以管理员身份运行 PowerShell"执行上面这条 `netsh` 命令。

---

## 4. 启动服务

### 4.1 先手动前台测试

```powershell
$inner = 'Set-Location "C:\Users\ljh\interview-forge"; python tools\study_server.py --host 0.0.0.0 --port 8765'
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

看到"Interview Forge"和"SQLite 数据库已连接"说明启动成功。

### 4.2 后台运行（SSH 断开后继续运行）

在对端执行：

```powershell
$inner = @'
Set-Location "C:\Users\ljh\interview-forge"
Start-Process -FilePath "python" -ArgumentList @(
    "tools\study_server.py",
    "--host", "0.0.0.0",
    "--port", "8765",
    "--quiet"
) -WorkingDirectory "C:\Users\ljh\interview-forge" -WindowStyle Hidden
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

验证：

```powershell
ssh ljh@$peer "netstat -ano | findstr :8765"
```

浏览器访问：

```text
http://192.168.5.234:8765/    # 即 http://$peer:8765/，IP 以第 0 步探测结果为准
```

---

## 5. 版本更新

InterviewForge 生成后的 HTML/样式/脚本都已提交到 GitHub，所以日常更新只需在对端拉取。

```powershell
$inner = @'
Set-Location "C:\Users\ljh\interview-forge"
git pull origin main
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

> ⚠️ 如果 pull **长时间无输出**，或报 `curl 28 Recv failure: Connection was reset`：
> 这是对端到 GitHub 的传输被中途重置（`Test-NetConnection` 只测 TCP 握手，测不出此问题），
> 此时**不要反复重试**，直接改用第 7.2 节的 git bundle 离线更新，几分钟即可完成。

如果更新的是服务端代码（`tools/study_server.py`）或静态资源版本号，需要重启服务：

```powershell
$inner = @'
$conn = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid2 = $conn.OwningProcess
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$pid2"
    if ($p.CommandLine -like "*study_server.py*") {
        Stop-Process -Id $pid2 -Force
    }
}
Set-Location "C:\Users\ljh\interview-forge"
Start-Process -FilePath "python" -ArgumentList @(
    "tools\study_server.py",
    "--host", "0.0.0.0",
    "--port", "8765",
    "--quiet"
) -WorkingDirectory "C:\Users\ljh\interview-forge" -WindowStyle Hidden
'@
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

---

## 6. 数据不会丢失

学习记录按账号分库存放（多用户版本起）：

```text
C:\Users\ljh\interview-forge\data\auth.db                          # 账号库（用户/会话/注册码）
C:\Users\ljh\interview-forge\data\users\<用户名>\hot100-study.db   # 每个账号的独立学习库
```

`data/` 已被 `.gitignore` 排除，`git pull` / bundle 更新都不会覆盖它们。以后升级/回滚都不需要备份学习数据，但建议定期把 `data\` 整个目录复制一份到本机。

---

## 7. 如果对端无法访问 GitHub

### 7.1 现象与判断

对端 `git pull` 长时间无输出/挂起，最后报 `curl 28 Recv failure: Connection was reset`。
原因是对端到 GitHub 的**数据传输被中途重置**（`Test-NetConnection github.com -Port 443`
返回 True 只说明 TCP 握手能通，测不出这个问题）。出现此现象不要反复重试，直接用 7.2。

### 7.2 推荐：git bundle 增量离线更新（2026-09 实测可用）

思路：本机把待更新的提交打成 bundle 文件 → scp 传到对端 → 对端从 bundle 拉取。
只传 Git 对象，不碰对端工作区的 `data/` 与未跟踪文件。

```powershell
# ① 先停对端服务（见第 5 节重启脚本的前半段），并查对端当前 HEAD
ssh ljh@$peer "cd C:\Users\ljh\interview-forge; git log --oneline -1"
# 输出例如 27d469f —— 它就是 bundle 的基线

# ② 本机：以对端 HEAD 为基线打增量 bundle（提交数不限，几十 KB 起）
cd E:\interview-forge
git bundle create $env:TEMP\forge-update.bundle 27d469f..main

# ③ 传到对端
scp $env:TEMP\forge-update.bundle ljh@${peer}:forge-update.bundle

# ④ 对端：校验并从 bundle 拉取
ssh ljh@$peer "cd C:\Users\ljh\interview-forge; git bundle verify $HOME\forge-update.bundle; git pull $HOME\forge-update.bundle main; git log --oneline -1"

# ⑤ 清理对端与本机的 bundle，然后按第 5 节重启服务
ssh ljh@$peer "Remove-Item $HOME\forge-update.bundle"
```

首次部署且对端连 `git clone` 都不通时，可打**全量** bundle 代替 GitHub：

```powershell
git bundle create $env:TEMP\forge-full.bundle --all
scp $env:TEMP\forge-full.bundle ljh@${peer}:forge-full.bundle
ssh ljh@$peer "git clone $HOME\forge-full.bundle C:\Users\ljh\interview-forge"
```

> bundle 传完即可删除；对端拉取后其 `origin` 仍指向 GitHub，
> 网络恢复时照常 `git pull origin main` 即可，无需额外处理。

### 7.3 备选：tar | ssh 流式整包

整目录覆盖式同步，**不推荐日常使用**：对端默认 Shell 是 PowerShell，管道里的二进制
tar 流有被污染的风险，仅在没有 git 的极端情况下考虑；且它按文件覆盖，可能把对端
`.git` 弄成不一致状态。

```powershell
cd E:\interview-forge
tar -cf - --exclude=.git --exclude=data --exclude=.build-cache.json --exclude=__pycache__ --exclude="*.pyc" . |
  ssh ljh@$peer "tar -xf - -C C:\Users\ljh\interview-forge"
```

首次需先在对端创建目录：

```powershell
$inner = 'New-Item -ItemType Directory -Force -Path "C:\Users\ljh\interview-forge"'
$b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($inner))
ssh ljh@$peer "pwsh -NoProfile -EncodedCommand $b64"
```

---

## 8. 故障排查

| 现象 | 处理 |
|---|---|
| `Connection timed out` | 多半是对端 IP 变了（DHCP 重新分配），回第 0 步重新探测 IP 并更新 `$peer`（对端双网卡，优先用有线地址） |
| `Permission denied` | 按桌面 SSH 指南重新把本机公钥加入对端 `administrators_authorized_keys` |
| 22 端口不通 | 确认 IP 没变后，对端 `Start-Service sshd`，并放行 22 |
| 8765 打不开 | 对端防火墙放行 8765；确认服务监听 `0.0.0.0:8765` |
| `git pull` 挂起或 `Connection was reset` | 对端到 GitHub 传输被重置，改用第 7.2 节 git bundle 离线更新 |
| SSH 多行 pwsh 脚本偶发卡住 | 拆成单行命令重试（`ssh ljh@$peer "命令1; 命令2"`），单行更稳 |
| 更新后还是旧页面 | `Ctrl + Shift + R` 强刷，或更新 Service Worker 后重开（PWA 缓存版本在 service-worker.js 的 VERSION） |
| 想回滚 | 在对端 `git log --oneline` 找旧提交，`git checkout <commit> .` 后重启服务 |
