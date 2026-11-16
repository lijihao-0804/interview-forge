# HydroOJ 部署与 ACM 化可行性评估（只读调研）

> 检查时间：2026-11-09。检查方式：SSH 登录 `hstgr-cloud` 只读查看；未安装软件、未改 nginx、未启动任何服务。

## 一、服务器环境快照

| 项目 | 现状 | 判断 |
|---|---|---|
| 操作系统 | Ubuntu 24.04.4 LTS，kernel 6.8 | ✅ 满足 Docker/Node 部署 |
| CPU | 4 vCPU（AMD EPYC 9355P） | ✅ 小型 OJ 够用；大规模并发需限流 |
| 内存 | 15 GiB 总量，检查时约 11 GiB 可用 | ✅ 够用；无 swap，需注意评测内存峰值 |
| 磁盘 | 根分区 193G，剩余约 163G（16% 使用） | ✅ 充足 |
| 架构 | x86_64 | ✅ |
| cgroup | cgroup v2 | ✅ 支持 Docker/容器资源限制 |
| Node.js | v22.22.0 | ✅ 已有；Docker 部署可忽略版本差异 |
| npm | 10.9.4 | ✅ |
| Docker | **未安装**，但 apt 有 `docker.io` 候选包 | ⚠️ 需要安装 Docker + Compose |
| MongoDB | **未安装**，Ubuntu apt 没有 `mongodb` 包 | ⚠️ 需用 Docker 起 Mongo，或加 MongoDB 官方源 |
| nginx | 1.24.0，active；已监听 80/443 | ✅ 可做反向代理 |
| 现有站点 | `hot100.xyz` / `www.hot100.xyz` 已占用 443；应用跑在 127.0.0.1:8765 | ✅ 不冲突，但新 OJ 需单独端口/子域名 |
| DNS | `oj.hot100.xyz` 当前没有解析记录 | ⚠️ 若用子域名需先加 DNS |
| 证书 | 现有证书是 `hot100.xyz`；没有 OJ 子域名证书 | ⚠️ 需申请新证书或配置泛域名 |
| 运行用户 | root，sudo 可用 | ✅ 有安装权限 |
| Docker Hub | 可连通（返回 401 是 registry 正常鉴权响应） | ✅ 可拉镜像 |
| 端口 27017 | 空闲 | ✅ 可跑 MongoDB |

### 关键结论

- **硬件和系统条件满足**：4C/15G/163G 空闲、Ubuntu 24.04、cgroup v2、Node 22 都够跑一个小型 HydroOJ。
- **当前还不是“开箱即用”**：Docker、MongoDB、OJ 子域名 DNS、TLS 证书都还没有；这些是可补的准备工作，不是硬阻塞。
- **不要和现有 `interview-forge` 共用同一进程/端口**：HydroOJ 应该单独用 Docker Compose 起一套 `hydro + mongo`，nginx 再反代到 `oj.hot100.xyz` 或独立端口。

## 二、HydroOJ 部署难度

### 结论：中等偏低，Docker 化后大概半天内能跑起来

有 Docker 经验的人：

1. 安装 Docker + Compose；
2. 用一个 `docker-compose.yml` 起 HydroOJ + MongoDB；
3. 配一个独立端口（如 8888）；
4. nginx 加 `oj.hot100.xyz` 反向代理；
5. 申请证书、初始化管理员、导入题目。

**顺利的话 2–4 小时可以有一个能登录的 HydroOJ**；如果域名、证书、备份、监控都要一起做，按半天到一天估算。

### 主要准备项

- Docker 未安装：apt 有 `docker.io` 候选包，可安装；
- MongoDB 未安装：建议直接跟着 Hydro 的 Docker Compose 起 Mongo 容器，避免 Ubuntu 24.04 上单独装 Mongo 的兼容问题；
- 域名/证书：`oj.hot100.xyz` 目前无 DNS；需要加 A 记录和证书；
- 反向代理：现有 nginx 结构简单，新增一个 server 块即可；
- 备份/资源限制：Mongo 数据卷、Docker CPU/内存限制、日志轮转。

### 不建议的做法

- 直接在现有 8765 端口旁边裸跑一个评测机，不做容器隔离；
- 把 MongoDB 暴露到公网；
- 让不可信代码在宿主机上直接执行；
- 在和生产站点同一容器里跑 judge。

## 三、我们的题支持 ACM 模式难吗

### 先分清两件事

1. **ACM 比赛/榜单模式**：HydroOJ 本身支持 ACM 赛制，创建比赛时选择 ACM 计分即可。这个不难。
2. **自动判题**：每道题必须有完整测试数据、时间/内存限制、输出校验方式。这个才是主要工作量。

### 当前题库情况

检查 `assets/ai-exam-coding.json`：

- 共 **132 道**题；
- **132 道都有题解代码**；
- **119 道有样例相关段落**（“样例 / 样例 1 / 样例 2 / 样例 3”）；
- `codes` 字段里大量是“样例输入 + 样例输出 + 参考代码”的组合，例如第一题是 3 组数据，第二题是 2 组样例加代码；
- 但**没有看到结构化的隐藏测试数据字段**（没有 `testcase` / `input` / `output` 目录或专门字段）。

### 结论

- **把题面导入 HydroOJ：不难**。题面、输入输出描述、样例、参考代码可以脚本转换。
- **让它像真正 ACM 机试一样自动判题：中等偏难，主要难在测试数据，不是 HydroOJ**。
- 如果只用样例当测试用例，虽然能跑起来，但很容易被硬编码/猜答案，不适合正式考试。
- 我们的题里有一部分是标准 stdin/stdout，另一部分是 JSON 输入、机器学习任务（如 PCA、Apriori），后者还需要自定义 checker 或运行封装。

### 建议的落地节奏

**第一阶段（MVP，1–2 天）**

- 选 10–20 道最典型、标准输入输出的题；
- 把题面转成 Hydro Markdown；
- 每题补 3–5 组隐藏测试；
- 建一个 ACM 模式的练习赛，验证判题、榜单、语言支持。

**第二阶段（扩展到 132 道，约 1–3 周，取决于测试数据质量）**

- 优先补高频题和容易自动生成数据的题；
- 对 JSON/ML 题单独做 checker；
- 用参考代码批量跑生成数据，但需要人工抽查边界和随机种子。

**如果只是要“体验 ACM 模式”，不做严格判题**：

- 一天内可以先搭 Hydro + 导入题面 + 样例测试；
- 但这只能用于练习，不建议作为正式考试/筛选系统。

## 四、推荐部署方案

```text
外网 443
  └─ nginx（现有）
       ├─ hot100.xyz        → 127.0.0.1:8765  interview-forge（保持不变）
       └─ oj.hot100.xyz     → 127.0.0.1:8888  HydroOJ（新增）

Docker 网络
  ├─ hydro-server（Node/Hydro）
  └─ mongo（仅内部网络，不暴露公网）
```

### 建议

- HydroOJ 使用 Docker Compose，MongoDB 只绑定内部网络；
- judge 容器限制 CPU/内存/PID，不允许挂载宿主机目录；
- nginx 新加 `oj.hot100.xyz`，单独申请证书；
- 先做 10–20 题试点，不要一次导入 132 题；
- 如果目标是正式招聘/考试，建议直接用 **牛客企业版 / 赛码网** 的监考与防作弊能力；自建 Hydro 更适合内部练习和模拟赛。

## 五、一句话回答

**部署 HydroOJ 不难，服务器硬件也够；真正难的是把 132 道题补成有隐藏测试数据、可自动判题的 ACM 题，而不是把 Hydro 装起来。** 当前服务器缺 Docker、MongoDB、OJ 子域名和证书，这些都能补；建议先做 10–20 题试点。

## 六、本次检查的环境命令（只读）

已查看：

- `/etc/os-release`、`uname -a`
- `nproc`、`lscpu`、`free -h`、`df -h`
- `docker --version`、`docker compose version`
- `systemctl is-active docker nginx interview-forge`
- `ss -tlnp`（80/443/8765/27017 等）
- nginx `sites-enabled` 与 `hot100` 配置
- `apt-cache policy docker.io`
- `curl` 检查 Docker Hub/GitHub 连通性
- `getent hosts oj.hot100.xyz`
- `assets/ai-exam-coding.json` 字段与样例统计

未执行任何安装、启动、配置或文件修改。
