# DeepSeek Harness 学习笔记：一切皆插件的 Agent Harness

> 主题：DeepSeek Harness（DSH）是什么、相比其他工具的创新、插件化到底指什么、具体结构长什么样、有什么优势。  
> 事实基线：本地安装包 `@deepseek-ai/dsh` v0.1.0-rc.6（2026-08-14 核对）+ [官方 GitHub 仓库](https://github.com/deepseek-ai/deepseek-harness) + 网络公开资料。  
> 阅读提醒：DSH 仍是 v0.1 开发者预览版，接口与插件清单变化很快；本文档中的包名、命令和文件结构以核对当日为准。

## 目录

- [1. DeepSeek Harness 是什么](#1-deepseek-harness-是什么)
- [2. "论文"问题：哪些资料可核验](#2-论文问题哪些资料可核验)
- [3. 核心创新一：一切皆插件](#3-核心创新一一切皆插件)
- [4. 核心创新二：Profile + Bundle + Patch 组合模型](#4-核心创新二profile--bundle--patch-组合模型)
- [5. 插件化详解：Cordis 插件内核](#5-插件化详解cordis-插件内核)
- [6. 具体结构：目录与文件级拆解](#6-具体结构目录与文件级拆解)
- [7. 内置插件地图：按领域分组](#7-内置插件地图按领域分组)
- [8. Agent Presets：standard / code / minimal](#8-agent-presetsstandard--code--minimal)
- [9. 省 Token：工具结果裁剪与上下文压缩](#9-省-token工具结果裁剪与上下文压缩)
- [10. 自进化：Agent 能"改装自己"](#10-自进化agent-能改装自己)
- [11. 与其他工具的对比](#11-与其他工具的对比)
- [12. 优势总结](#12-优势总结)
- [13. 风险与不足（客观审查）](#13-风险与不足客观审查)
- [14. 快速上手](#14-快速上手)
- [15. 参考资料](#15-参考资料)
- [16. 审查记录](#16-审查记录)

---

## 1. DeepSeek Harness 是什么

DeepSeek Harness（简称 DSH）是 DeepSeek 开源的 **Agent Harness**（智能体运行环境/框架）。仓库标语是 **"Everything is a Plugin"**（一切皆插件）。它于 2026 年 8 月以 v0.1 开发者预览版形式开源，采用 MIT 许可证，发布后短时间内收获大量关注（媒体报道的首日 Star 数从 2.8 万到 5 万不等，不同文章口径不同）。

它的定位不是"又一个模型"或"又一个聊天工具"，而是把 **Agent 运行时本身**变成可组合、可编程、可被模型修改的系统：

```text
模型 + 工具 + Agent Loop + 会话 + 沙箱 + 审批 + 前端界面
        → 全部由插件组装而成
```

本机安装的 `@deepseek-ai/dsh` 包（v0.1.0-rc.6）描述为：*"dsh CLI: profile boot, plugin management, and the browser UI alias"*。也就是说，`dsh` 命令本身只是"启动器"，真正的能力全部来自它按 profile 组装起来的插件。

> 与其他笔记的关系：这是"Harness 层"的笔记。更抽象的 Agent 原理见《Agent 开发学习笔记》，具体框架用法见《LangChain 入门学习笔记》，另一类产品型 Harness（Hermes/OpenClaw/Codex/Claude Code）见同目录的《Hermes、OpenClaw、Codex 与 Claude Code》笔记。

---

## 2. "论文"问题：哪些资料可核验

先回答最容易被误解的问题：**DeepSeek Harness 目前没有一份可核验的官方学术论文（arXiv 编号）**。搜索到的与"论文"相关的线索如下，注意区分事实与传闻：

| 说法 | 来源 | 可核验性 |
|---|---|---|
| 官方架构文档 `docs/architecture.zh.md` | [GitHub 官方文档](https://github.com/deepseek-ai/deepseek-harness/blob/HEAD/docs/architecture.zh.md) | ✅ 官方仓库内可查 |
| 官方产品页"DeepSeek Harness 开发者预览版：一切皆插件" | [deepseek.com/harness](https://www.deepseek.com/harness/) | ✅ 官方 |
| 媒体报道："核心论文《Cordis：软件动态组合的编程范式》" | [locdd.com 转载](https://locdd.com/t/topic/80325)、[juejin 前端视角解读](https://juejin.cn/post/7673438154771824674)、[floatboat.ai Cordis 介绍](https://floatboat.ai/blog/cordis-plugin-framework) | ⚠️ 第三方报道，未能在 arXiv 检索到对应官方论文条目 |
| 媒体报道："底层来自与北大联合研究" | [网易转载](https://m.163.com/dy/article_v5/L48IS63F0511D6RL.html) | ⚠️ 第三方报道，未获官方确认 |
| arXiv 2606.01779《HarnessForge: Joint Harness and Policy Evolution for Adaptive Agent Systems》 | [arXiv](https://arxiv.org/abs/2606.01779) | ✅ 该论文确实存在，但它**不是** DeepSeek Harness 的官方论文，只是同主题（harness 演进）的另一篇工作 |

结论：**学习 DSH 最权威的资料是官方仓库、官方文档和官方产品页；"Cordis 编程范式论文""北大联合研究"属于媒体说法，需以官方发布为准。** 本笔记的技术细节均来自可核验的本地安装包与官方 README。

---

## 3. 核心创新一：一切皆插件

"一切皆插件"不是营销口号，而是可以逐层验证的架构事实。对照本机安装包，以下每一类能力都是独立插件包：

| 能力域 | 对应插件示例（本机 v0.1.0-rc.6 实测） |
|---|---|
| 模型接入 | `dsh-llm`、`dsh-llm-deepseek`、`dsh-llm-pi-ai`、`dsh-llm-retry` |
| Agent 循环 | `dsh-agent`、`dsh-agent-loop`、`dsh-agent-instructions`、`dsh-system-prompt` |
| 工具 | `dsh-tools`、`dsh-tool-fs`、`dsh-tool-bash`、`dsh-tool-pwsh`、`dsh-tool-str-replace-editor`、`dsh-tool-web`、`dsh-tool-subagent`、`dsh-tool-goal`、`dsh-tool-ralph`、`dsh-tool-workflow`、`dsh-tool-ask-user`、`dsh-tool-todo`、`dsh-tool-jobs`、`dsh-tool-skill` |
| 会话与持久化 | `dsh-session`、`dsh-session-persistence-jsonl`、`dsh-session-query-sqlite`、`dsh-session-checkpoint-policy`、`dsh-session-title` |
| 沙箱与审批 | `dsh-sandbox-local`、`dsh-bash-sandbox`、`dsh-pwsh-sandbox`、`dsh-sandbox-policy`、`dsh-user-approval`、`dsh-permission-presets` |
| 记忆与技能 | `dsh-skill`、`dsh-skill-filesystem`、`dsh-tool-skill` |
| 计划与目标 | `dsh-plan-mode`、`dsh-goal`、`dsh-goal-round-driver` |
| 子代理 | `dsh-subagent`、`dsh-subagent-fork-in-process`、`dsh-subagent-spawn-in-process` |
| 工作流 | `dsh-workflow`、`dsh-workflow-worker-thread` |
| 压缩（省 Token） | `dsh-compaction-basic`、`dsh-compaction-tool-result-pruner` |
| 前端界面 | `dsh-web-app`、`dsh-client-ui-*`（对话、轨迹、子代理、目标、任务、技能、插件管理等数十个 UI 插件）|
| 服务端 | `dsh-host-webserver`、`dsh-host-frontend-static`、`dsh-host-apiproxy`、`dsh-api-gateway` |
| 调度与后台任务 | `dsh-schedule`、`dsh-jobs-local`、`dsh-tool-jobs` |
| 其他横切 | `dsh-token-meter`、`dsh-time-context`、`dsh-tmux-context`、`dsh-credentials-local`、`dsh-mcp-client`、`cordis-plugin-hmr`、`cordis-plugin-timer` |

**"一切皆插件"的含义**：不仅工具是插件，连"模型怎么调用、Agent 循环怎么跑、会话怎么存、命令怎么审批、界面长什么样"都是插件。这意味着：

- **可裁剪**：不需要某能力就卸掉对应插件，而不是"装了一个大而全的软件"；
- **可替换**：模型供应商、工具实现、持久化后端都可替换；
- **可组合**：不同 profile 可以组装出完全不同的产品形态（极简双工具编码 Agent vs 完整 Web 界面）；
- **可被程序/模型修改**：配置是数据，插件是包，Agent 理论上可以改动自己的"身体"（见第 10 章）。

媒体报道把它比作"给 AI 装上可拆装的执行引擎"（[chinaz](https://www.chinaz.com/ainews/30334.shtml)）和"像玩乐高一样拼插件"（[界面新闻](https://www.jiemian.com/article/14922169.html)）。

---

## 4. 核心创新二：Profile + Bundle + Patch 组合模型

DSH 用 **Profile（档案）** 描述"我要一个什么样的 Agent 系统"，这是它和传统单体框架最不同的地方。官方 README 的定义：

> "profiles: ordered stacks of plugin-bundle patch layers under the user's own overrides"——在用户自己的覆盖之下，按顺序叠放的插件 bundle patch 层。

### 4.1 配置树的叠加顺序

配置从空根开始，依次叠加：

```text
空根
  → dsh.profile.bundles 中每个 bundle 的 patch（按列表顺序）
  → profile 自己的 cordis.patch.yml
  → home 级 $DSH_HOME/cordis.patch.yml
  → 命令行 --patch 指定的覆盖层
```

- **Patch 语义**：patch 按插件 `id` 定位，**整体替换**该行的 `config`（不是合并）；同一 id 多处写时"最后一次写入生效"（last write wins）。
- **可检查**：`dsh --dump-default-config` / `dsh --dump-config` 可以在不启动的情况下查看组合后的配置树。

### 4.2 入口模式（官方 README 实测）

| 命令 | 用途 |
|---|---|
| `dsh --profile <name>` | 启动 `$DSH_HOME/profiles/<name>` 下的指定 profile |
| `dsh --profile headless "job"` | 运行一个全新的持久化会话，打印最终答案后退出 |
| `dsh web` | `--profile web` 的别名（浏览器界面） |
| `dsh plugin --profile <name> <pnpm args>` | 在 profile 目录里转发给 pnpm 管理插件 |

启动器只解析自己的 flag，其后的参数交给被启动的 profile 中的应用插件解析（共享不可变快照，由 `dsh-cmdline` 插件提供）：

```sh
dsh --profile web --port 8080       # --port 属于 web 应用
dsh --profile headless "run the tests"
dsh web --help                      # 显示 web 应用的 flag，不是启动器的
dsh --help                          # 启动器自己的帮助
```

### 4.3 为什么这个模型是创新

传统框架是"一个库 + 一堆 API"，DSH 是"**一个内核 + 可声明式组装的系统**"。对比：

- LangChain：Runnable 组合的是**数据流**，框架本体不可拆；
- Claude Code / Codex：扩展机制（CLAUDE.md、Hooks、Plugins）是**产品内建功能**，产品骨架固定；
- DSH：**产品骨架本身就是插件组合**，"默认产品"只是某个 profile 而已。

---

## 5. 插件化详解：Cordis 插件内核

### 5.1 Cordis 是什么

DSH 的插件内核是 [`@deepseek-ai/cordis`](https://floatboat.ai/blog/cordis-plugin-framework)，v4.0.1，自述为 *"Meta-Framework for Modern JavaScript Applications"*（现代 JS 应用的元框架）。它源自 Koishi 生态的 Cordis 插件框架，DSH 在其上构建了一整套 Agent 运行时插件。媒体报道称"DeepSeek 把 Agent 拆成可进化机器，Cordis 为递归自我改进铺路"（[theblockbeats](https://en.theblockbeats.news/flash/361476)）。

Cordis 提供的关键机制：

- **插件注册与依赖解析**：插件通过 `provide`/`inject` 声明提供的服务与依赖，框架按需激活；
- **服务（Service）**：跨插件共享的能力边界，如 `ctx.fs`（文件系统 seam）、`ctx.get(...)`（按需获取服务）；
- **Realm（领域）**：解决"多个同名插件并存"的问题——服务行必须放在带 `isolate` realm 的 group 里，否则会发布到 root realm 造成进程级冲突（这是 `dsh-agent-presets` 挂载时的硬性校验）；
- **配置注入**：插件以 `id + name + config` 的 YAML 行形式被装载。

### 5.2 一个插件长什么样（实测）

以 `@deepseek-ai/dsh-tool-fs` 为例，它的 `package.json` 自述：*"Model-facing filesystem tools (read, write, edit) over the DeepSeek Harness filesystem seam (ctx.fs)"*。结构为：

```text
@deepseek-ai/dsh-tool-fs/
├─ package.json      # name / description / exports / peerDependencies
├─ lib/index.js      # 插件主入口
└─ lib/types/...     # 类型声明
```

关键点：

- 插件依赖的是 **peerDependencies**（`dsh-attachment`、`dsh-llm`、`dsh-sandbox`、`dsh-fs`、`dsh-session`、`dsh-tools`、`dsh-user-approval`、`cordis` 等），即"我运行在什么内核环境里"；
- 插件通过 `ctx.fs` 等 seam 与内核交互，不直接耦合具体实现（本地文件系统 vs 沙箱由上层 policy 决定）。

### 5.3 装载粒度：agent-plane 与 host-plane

官方标准预设（`agent.cordis.yml`）注释揭示了两种装载面：

- **Host 平面（host-plane）**：注册表本身、沙箱与审批栈、持久化、模型路由——"preset 不该拥有的东西"；
- **Agent 平面（agent-plane）**：每个 agent 会话的工具与提示词部分——"preset 拥有的东西"，按 standing scope 挂载一次，所有加入的会话按作用域继承。

例如 `tool-bash` 与 `tool-pwsh` 是**平台互斥**的：`disabled: !!js process.platform === 'win32'` / `!== 'win32'`，即 Windows 上启用 PowerShell、禁用 bash——这是"平台差异也是配置"的典型体现。

---

## 6. 具体结构：目录与文件级拆解

### 6.1 安装布局（本机实测）

```text
$DSH_HOME = C:\Users\<user>\.dsh
└─ profiles/
   └─ web/                        # dsh web 使用的 profile
      ├─ package.json             # 含 dsh.profile.bundles 清单
      ├─ cordis.yml               # profile 根（空条目列表，不要改它）
      ├─ cordis.patch.yml         # 用户自己的 patch 层（要改改这里）
      └─ pnpm-workspace.yaml      # 树外插件安装位置
```

`web` profile 的 `package.json`（实测）：

```json
{
  "name": "dsh-profile-web",
  "private": true,
  "dependencies": {},
  "dsh": {
    "profile": {
      "bundles": [
        "@deepseek-ai/dsh-base",
        "@deepseek-ai/dsh-web-app"
      ]
    }
  }
}
```

它的 `cordis.patch.yml` 默认为空数组 `[]`，注释明确写着：*"your patch layer for this dsh profile, applied after every bundle layer"*。

### 6.2 Bundle（组合包）

Bundle 是"一个 patch 文件 + 一组插件依赖"的集合：

- `@deepseek-ai/dsh-base`：每个 profile 的第一层，插入内核基础行（timer、hmr、llm、session、agent、sandbox、approval、compaction、subagent、goal、tools、skill 等）；
- `@deepseek-ai/dsh-web-app`：浏览器界面层（前端产物托管、web 提示词、bash 运行环境变量、URL 行）；
- `@deepseek-ai/dsh-headless`：无头模式。

Bundle 的声明方式（`dsh-base` 的 package.json 实测）：

```json
"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
```

### 6.3 Base patch 长什么样（实测片段）

`dsh-base/cordis.patch.yml` 是"一条 insert 装载一组插件行"：

```yaml
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'
    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config: { root: ['.'] }
    - id: llm
      name: '@deepseek-ai/dsh-llm'
    - id: session
      name: '@deepseek-ai/dsh-session'
    - id: typert
      name: '@deepseek-ai/dsh-typert-registry'
    - id: agent
      name: '@deepseek-ai/dsh-agent'
    # ...（沙箱、审批、会话、压缩、子代理、目标、工具等）
```

注释还说明：patch 会**整体替换**目标行的 `config`，因此"按模式不同取值"的行不放在 base 里，而由各模式 bundle 各自完整声明——保证一行最多由"一个 bundle 层 + 用户层"决定。

### 6.4 Agent Preset（agent 预设）

`config/agent-presets/` 下有 4 个预设目录（实测）：

| preset | 说明（preset.yml 实测） |
|---|---|
| `standard` | 标准模式：功能完整的编码 Agent，支持文件编辑、Shell、文件与网页检索、Skills、计划、目标、子代理和工作流（order 1） |
| `code` | 编码模式 |
| `minimal` | 极简模式：仅提供持久 bash 与 str_replace_editor 的双工具编码 Agent（order 3） |
| `cordis` | 面向 Cordis 插件开发（附 skills） |

每个预设由 `preset.yml`（名称/描述/顺序）+ `agent.cordis.yml`（agent 平面插件组合）组成。`standard` 的 `agent.cordis.yml` 按区块组织：identity（persona、agent-instructions）→ shell（tool-bash/tool-pwsh）→ filesystem → background jobs → skills → goals → plan mode。

---

## 7. 内置插件地图：按领域分组

基于本机 v0.1.0-rc.6 实测的 `node_modules/@deepseek-ai/` 清单（共 194 个包：185 个 `dsh-*` 插件 + 6 个 `cordis*` 内核相关 + 少量框架辅助包），按领域归类：

| 领域 | 代表插件 |
|---|---|
| 内核/框架 | `cordis`、`cordis-plugin-loader`、`cordis-plugin-hmr`、`cordis-plugin-timer`、`cordis-plugin-group`、`cordis-plugin-include` |
| Agent 核心 | `dsh-agent`、`dsh-agent-loop`、`dsh-agent-instructions`、`dsh-agent-tool-presentation`、`dsh-system-prompt`、`dsh-persona`、`dsh-agent-default-model` |
| 模型 | `dsh-llm`、`dsh-llm-deepseek`、`dsh-llm-pi-ai`、`dsh-llm-retry`、`dsh-llm-mock-server` |
| 会话 | `dsh-session`、`dsh-session-persistence-jsonl`、`dsh-session-query-sqlite`、`dsh-session-checkpoint-policy`、`dsh-session-title`(+llm)、`dsh-session-projection`(+cache)、`dsh-session-stats`、`dsh-session-telemetry-otel`、`dsh-session-log-export` |
| 工具 | `dsh-tools` 与 `dsh-tool-*` 全家（fs、fs-search、bash、pwsh、str-replace-editor、web、subagent、goal、ralph、workflow、ask-user、todo、jobs、skill、cordis、bash-persistent、subagent-control、subagent-report、call-timeout-policy） |
| 文件/沙箱 | `dsh-fs-local`、`dsh-fs-sandbox`、`dsh-fs-observation-policy`、`dsh-atomic-write`、`dsh-sandbox-local`、`dsh-bash-sandbox`、`dsh-pwsh-sandbox`、`dsh-sandbox-policy`、`dsh-sandbox-windows-acl` |
| 子代理/工作流 | `dsh-subagent`、`dsh-subagent-fork-in-process`、`dsh-subagent-in-process-driver`、`dsh-subagent-spawn-in-process`、`dsh-workflow`、`dsh-workflow-worker-thread` |
| 目标/计划 | `dsh-goal`、`dsh-goal-round-driver`、`dsh-plan-mode` |
| 技能 | `dsh-skill`、`dsh-skill-filesystem`、`dsh-skill-badge`、`dsh-tool-skill` |
| 压缩 | `dsh-compaction-basic`、`dsh-compaction-tool-result-pruner`、`dsh-output-retention`、`dsh-repeat-tool-reminder` |
| 后端/网关 | `dsh-api-gateway`、`dsh-api-remotes`、`dsh-host-webserver`、`dsh-host-frontend-static`、`dsh-host-apiproxy`、`dsh-host-plugin-inventory`、`dsh-mcp-client`、`dsh-web`、`dsh-web-app` |
| 前端 UI | `dsh-client-*`（runtime、web、web-react、ui-conversation、ui-trajectory、ui-subagent、ui-goal、ui-jobs、ui-skill、ui-workflow-run、ui-plugin-inventory、ui-settings-plugins、ui-model-selection、ui-permission-presets、ui-plan 等数十个） |
| 安全/凭据 | `dsh-user-approval`、`dsh-permission-presets`、`dsh-credentials-local`、`dsh-anonymous-user-id`、`dsh-scope`、`dsh-invariants` |
| 调度/后台 | `dsh-schedule`、`dsh-jobs-local`、`dsh-tool-jobs` |
| 其他 | `dsh-token-meter`、`dsh-time-context`、`dsh-tmux-context`、`dsh-cmdline`、`dsh-home-paths`、`dsh-launch-environment`、`dsh-brand`、`dsh-storage-*`、`dsh-spill-*`、`dsh-attachment-*`、`dsh-typert-*` |

> 社区插件生态已出现精选列表：[awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)，以及零基础插件开发教程（[hello-dsh](https://github.com/pingfanfan/hello-dsh)、[插件开发实战](https://www.cnblogs.com/pc2005/p/22477987)）。

---

## 8. Agent Presets：standard / code / minimal

DSH 把"Agent 的能力配方"也做成可声明配置。以 `standard` 预设为例，`agent.cordis.yml` 的组合逻辑（实测注释归纳）：

- **identity**：`persona`（提示词模板，`{{model}}`/`{{cwd}}` 由 agent 自身路由解析）+ `agent-instructions`（指令字节上限）；
- **shell**：bash 与 pwsh 按平台互斥启用；
- **filesystem**：`tool-fs` + `tool-fs-search` 注册进 host 的 tools 注册表；
- **background jobs**：只给模型侧控制工具（任务注册表留在 host 平面，按所属 agent 键控）；
- **skills**：`skill-filesystem`（本地根发现）+ `tool-skill`（目录与加载器）；
- **goals**：`tool-goal`（目标服务、会话驱动、`/goal` 命令都在 host 平面）；
- **plan mode**：用 `cordis:group` + `isolate: { planMode: true }` 隔离出计划模式（计划状态按 agent 生命周期）。

一句话总结：**preset 决定"这个 Agent 能干什么"，bundle 决定"这个 profile 运行在什么环境里"，patch 决定"用户怎么改"**。

---

## 9. 省 Token：工具结果裁剪与上下文压缩

"省 Token"是媒体反复强调的卖点之一（[搜狐](https://www.sohu.com/a/1062527577_115128)、[CSDN](https://csdnnews.blog.csdn.net/article/details/163747298)、[今日头条实测"成本差 7 倍"](https://www.toutiao.com/article/7672943765589328399/)）。从本机插件清单可以确认其技术路径是**插件化的压缩栈**：

- `dsh-compaction-basic`：基础上下文压缩（长会话摘要/裁剪策略）；
- `dsh-compaction-tool-result-pruner`：**工具结果裁剪**——把过大的工具输出从上下文里修剪掉，只保留摘要或引用，避免工具日志淹没关键约束；
- `dsh-output-retention`、`dsh-repeat-tool-reminder`：输出保留策略与重复工具提醒（减少无效循环）。

这与主流做法一致（Claude Code 的 auto-compact、Codex 的上下文压缩都是同类目标），DSH 的差异在于：**压缩策略本身也是插件**，可以替换、组合、按 profile 定制。第三方实测的"成本差 7 倍""只花 Claude Code 的 29%"属于特定任务、特定版本的对比数字，**不应作为普遍结论**（见第 13 章）。

---

## 10. 自进化：Agent 能"改装自己"

DSH 最引人注目的能力是 **Agent 可以修改自己的 Harness**：因为配置是数据、能力是插件，模型在获得授权的情况下可以：

- 修改 profile 的 `cordis.patch.yml`；
- 安装/卸载/更新插件（`dsh plugin ...` 转发 pnpm）；
- 创建或修改 Skill（`dsh-skill-filesystem`、`dsh-tool-skill`）；
- 调整自己的工具集、提示词、权限策略。

媒体报道称之为"自进化软件的雏形"（[腾讯新闻](https://news.qq.com/rain/a/20260814A048HD00)、[MarsBit](https://news.marsbit.co/20260814123610336831.html)、[TheBlockBeats](https://en.theblockbeats.news/flash/361476)）。"可进化机器（Evolvable Machine）"的说法由此而来：**Agent 不只是用工具完成任务，还能改变自己未来完成任务的方式**。

必须强调的安全约束（这也是 DSH 设计中的防线）：

- 自修改需要**审批**（`dsh-user-approval`）与**权限策略**（`dsh-permission-presets`）；
- 沙箱（`dsh-sandbox-*`）限制最坏影响范围；
- 社区已报告过安全边界问题（如 [GitHub Discussion #250：沙箱内模型可借 Web approval 回环通道自批准 `danger-full-access`](https://github.com/deepseek-ai/deepseek-harness/discussions/250)），说明"自修改能力"的治理是持续课题。

---

## 11. 与其他工具的对比

### 11.1 对照表

| 维度 | DeepSeek Harness | Claude Code | Codex | LangChain/LangGraph | Hermes/OpenClaw |
|---|---|---|---|---|---|
| 本质 | 开源 Agent Harness 框架 | 闭源编码 Agent 产品 | 闭源软件工程 Agent 体系 | Python 编排库/图运行时 | 开源个人 Agent/网关 |
| 模型绑定 | 模型无关（多 LLM 插件） | Claude 模型为主 | OpenAI 模型体系 | 模型无关 | 模型无关 |
| 架构核心 | 一切皆插件（Cordis 内核） | 产品内建扩展层（Hooks/Subagents/MCP） | 产品内建（CLI/IDE/App/Cloud） | Runnable/StateGraph 组合 | Gateway + 学习闭环 |
| 可裁剪性 | 强：profile 决定形态 | 弱：产品骨架固定 | 弱：产品骨架固定 | 中：库可选择性使用 | 中 |
| 可被 Agent 修改 | 强：配置即数据，可自修改 | 弱 | 弱 | 中（通过工具） | Hermes 有 Skill/Memory 自写 |
| 界面 | Web（浏览器）为主 | 终端/IDE | 终端/IDE/桌面/Cloud | 无固定 UI | CLI/TUI/消息渠道 |
| 平台 Shell | bash + PowerShell 双实现 | bash 为主 | bash | 不涉及 | 多后端 |
| 开源协议 | MIT | 否 | 否 | MIT | MIT |

### 11.2 与 Claude Code / Codex 的本质差异

Claude Code、Codex 的扩展（Hooks、CLAUDE.md、Plugins、Subagents）是**产品在固定骨架上开放的口子**；DSH 则是**骨架本身可组装**。官方定位也表明它"不想做下一个 Codex"（[搜狐](https://www.sohu.com/a/1062755615_313745)、[C114](https://www.c114.net.cn/industry/110905.html)）：它更像一个"可拼装的 Harness 平台"，编码 Agent 只是 standard 预设给出的默认形态之一。

### 11.3 与 LangChain 的差异

LangChain 解决"如何组合调用链"（数据流层面），DSH 解决"如何组装整个 Agent 运行系统"（系统层面）。二者甚至可能互补：DSH 的插件里可以有调用 LangChain 生态的插件，但定位不同——一个是库，一个是运行时。

### 11.4 与 Hermes/OpenClaw 的差异

Hermes 强调长期学习闭环，OpenClaw 强调多渠道 Gateway；DSH 不绑定这两种叙事，而是提供"能长出任何形态"的插件内核。同目录《Hermes、OpenClaw、Codex 与 Claude Code》笔记中的"Harness 决定实际能力"结论，在 DSH 身上体现得最彻底——DSH 把 Harness 本身产品化了。

---

## 12. 优势总结

1. **架构级插件化**：模型、循环、工具、会话、沙箱、审批、UI 全部可插拔，这是"一切皆插件"区别于"有插件机制"的关键；
2. **Profile 组合模型**：声明式组装（bundle patch 叠加 + 用户覆盖），`--dump-config` 可审计，改动可回查；
3. **模型无关**：多 LLM 插件并存，可路由可降级（`dsh-llm-retry`）；
4. **可裁剪到极致**：minimal preset 只有两个工具，standard 是完整编码 Agent，同一内核长出不同产品；
5. **平台适配是配置**：bash/PowerShell 双实现按平台启用，Windows 一等公民（相比多数 coding agent 的 Unix 偏向）；
6. **压缩栈插件化**：工具结果裁剪 + 基础压缩可组合，为省 Token 提供可替换方案；
7. **Web 优先的完整产品面**：前端 UI 本身插件化（数十个 `dsh-client-ui-*`），可定制界面；
8. **自进化潜力**：配置即数据 + 插件包管理，为"Agent 改装自己"提供了架构基础（需审批护栏）；
9. **MIT 开源**：可自由使用、修改、商业化（需遵守许可证）。

---

## 13. 风险与不足（客观审查）

写"优势"的同时必须写边界，以下为本笔记的客观审查结论：

1. **没有可核验的官方论文**：第 2 章已说明，"Cordis 编程范式论文""北大联合研究"均属媒体说法；正式学术背书缺失，长期价值需以官方发布为准。
2. **v0.1 开发者预览版**：接口、插件清单、配置格式都可能变；本文档所有包名/命令以 2026-08-14 本地安装版为准。
3. **学习成本**：realm/isolate、patch 覆盖语义（整体替换而非合并）、agent-plane/host-plane 双层装载，理解门槛高于"装个库就调用"。
4. **自修改的安全风险**：已出现沙箱审批回环的社区报告（[Discussion #250](https://github.com/deepseek-ai/deepseek-harness/discussions/250)）；"Agent 改自己"必须配审批、权限、审计和版本控制。
5. **插件供应链**：第三方插件 = 第三方代码，需像审查依赖一样审查（与 Hermes Skills 供应链风险同源）。
6. **"省 Token"数字不可直接引用**："成本差 7 倍""花 Claude Code 的 29%"是特定场景的第三方实测，变量（任务、模型、版本、并发）未受控，不能当普适结论。
7. **星标/热度数据口径不一**：不同文章报道首日 2.8 万～5 万星不等，热度可作参考，不是能力指标。
8. **生态早期**：插件数量已可观但成熟度参差，关键生产能力可能仍依赖官方包。

---

## 14. 快速上手

以下是最小行动路径（详细步骤以官方文档为准）：

```sh
# 1. 安装（npm 全局或项目内）
npm install -g @deepseek-ai/dsh

# 2. 首次使用自动初始化 web / headless profile
dsh web --help          # web profile 首次使用会从模板初始化

# 3. 查看组合后的配置树（不启动）
dsh --profile web --dump-config

# 4. 安装/管理插件（转发给 pnpm）
dsh plugin --profile web add <plugin-name>

# 5. 无头模式跑一个任务
dsh --profile headless "explain what a Harness is"
```

官方入口：[deepseek.com/harness](https://www.deepseek.com/harness/) | [GitHub 仓库](https://github.com/deepseek-ai/deepseek-harness) | [官方架构文档](https://github.com/deepseek-ai/deepseek-harness/blob/HEAD/docs/architecture.zh.md)

---

## 15. 参考资料

### 官方（可核验）

- [GitHub：deepseek-ai/deepseek-harness（Everything is a Plugin）](https://github.com/deepseek-ai/deepseek-harness)
- [官方架构文档 architecture.zh.md](https://github.com/deepseek-ai/deepseek-harness/blob/HEAD/docs/architecture.zh.md)
- [官方产品页：DeepSeek Harness 开发者预览版](https://www.deepseek.com/harness/)
- 本地安装包 `@deepseek-ai/dsh` v0.1.0-rc.6 的 README/package.json/配置与插件清单（本文档结构章节的直接依据）

### 第三方解读（注意区分报道与事实）

- [DeepSeek Harness 拆解：一套能拼装的 Agent 架构（网易）](https://www.163.com/dy/article/L4AHS9B70518R7MO.html)
- [一切皆插件：DeepSeek Harness 的架构哲学，以及与主流 Agent 的对比](https://www.cnblogs.com/qq8864/articles/22479803)
- [DeepSeek Harness vs Codex vs Claude Code：三款 AI 编程 Harness 深度对比](https://my.oschina.net/u/9487999/blog/19739544)
- [DeepSeek Harness 开源：一切皆插件、省 Token、Agent 还能改装自己（CSDN）](https://csdnnews.blog.csdn.net/article/details/163747298)
- [DeepSeek 把 Harness 开源了：模型、工具、Agent Loop 全是插件（InfoQ）](https://www.infoq.cn/article/de9AljWc4ejW2KAyW8dD)
- [DeepSeek 的 Harness，为何是一头黑色鲸鱼？（36氪）](https://www.36kr.com/p/3938566998834308)
- [Cordis — The Plugin Kernel Behind DeepSeek Harness（FloatBoat）](https://floatboat.ai/blog/cordis-plugin-framework)
- [DeepSeek Harness 核心论文发布：Cordis 软件动态组合的编程范式（转载，未获官方确认）](https://locdd.com/t/topic/80325)
- [DeepSeek 开源 Harness 智能体框架：一切皆插件，底层来自与北大联合研究（转载，未获官方确认）](https://m.163.com/dy/article_v5/L48IS63F0511D6RL.html)
- [DeepSeek Harness 开源首日 28k Star：一切皆插件、省 Token、Agent 还能改装自己（搜狐）](https://www.sohu.com/a/1062527577_115128)
- [社区安全讨论：sandbox 内模型可通过 Web approval 回环通道自批准 danger-full-access](https://github.com/deepseek-ai/deepseek-harness/discussions/250)
- [awesome-dsh-plugin：DSH 插件精选列表](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin)
- [hello-dsh：零基础插件开发教程（含 22 个中文技能实例）](https://github.com/pingfanfan/hello-dsh)
- [DeepSeek Harness 插件开发实战：从设计理念到 npm 发布](https://www.cnblogs.com/pc2005/p/22477987)
- [HarnessForge（arXiv 2606.01779，同主题但非 DSH 官方论文）](https://arxiv.org/abs/2606.01779)

---

## 16. 审查记录

> 本笔记撰写完成后，按"事实准确性 → 引用 → 格式 → 表述"四个维度做了自审，结论如下：

1. **事实准确性**：第 3～8 章的所有包名、命令、目录结构、preset 说明均来自本机 `v0.1.0-rc.6` 安装包的直接读取（package.json、README、cordis.patch.yml、agent.cordis.yml），非转述；第 2 章对"论文/北大联合研究"明确标注为不可核验的第三方说法，未当作事实陈述。
2. **引用**：第三方数据（星标数、省 token 比例、热度）均标注来源并提示"口径不一/不可作普遍结论"；官方链接指向仓库与官方文档。
3. **格式**：代码围栏配对、目录锚点与标题一致、表格完整（撰写后已复核）。
4. **表述**：对"自进化""省 Token"等营销色彩词汇做了限定（"潜力""特定场景实测"），避免夸大；风险章节独立成章，与优势并置。

**已知局限**：本文档无法访问官方 GitHub 仓库全文（本机网络沙箱限制），`docs/architecture.zh.md` 的深层内容以搜索摘要与本地包为准；如后续获得仓库全文，应更新第 4～6 章细节。任何新版本发布后，包名与结构以 `dsh --dump-config` 输出为准。
