# 永久管理员私有档案

## 新增超级管理员资料

后续资料按主题直接放在本项目的 `library/<专题目录>/`，随项目提交 Git。新增专题时，沿用开发手记的书架入口和服务端鉴权方式：只有超级管理员能看到卡片，直接访问正文或附件也检查同一权限。普通书架目录默认可公开阅读，新专题应在发布时一并接入这项检查。

### InterviewForge 开发手记

报告文件直接位于 `library/development-history/`。超级管理员在学习书架选择「项目学习笔记」，再点击「InterviewForge 开发手记」后进入 `/library/development-history/index.html`，点击篇名才请求对应的 `chapters/*.html`。更新时直接替换这一目录下的页面和样式，无需单独设置环境变量。

入口位于 `/library/index.html` 学习书架的动态卡片（原管理后台页头入口已移除）。只有服务端确认当前会话属于指定永久管理员（超级管理员）且教学站可用时才返回卡片信息并显示；页面、JSON、源码摘录、图片、脚本的每次直接请求都再次检查身份。普通 `admin` 角色不足以访问。

### AgentHub 与 VoltEdu

AgentHub 的分片站点保存在 `library/agenthub/`，原书签 `/api/private-archive/index.html` 继续指向最新版。首页、近期进展、章节、历史图和源码分片使用同一身份校验。VoltEdu 的完整阅读站保存在 `library/voltedu-study/`，入口为 `/library/voltedu-study/index.html`。两个站点都直接随项目更新。

## 兼容旧部署的 AgentHub 外部附件安装方式

旧版外部附件的部署步骤如下。项目中存在 `library/agenthub/` 时，服务优先读取项目版本。

在已确认部署流程的服务器上，由操作者完成：

1. 新部署必须把附件**实际解压**成独立教学前端。将 ZIP 和目标 release 目录置于仓库及所有 Web 根目录外，例如 `/srv/interview-forge-private/releases/20261115/site`。父目录仅服务账号/管理员可写，建议权限 0700；不要放入 Git、`assets`、`pages`、`library` 或 nginx 静态 alias。
2. 在项目 Python 环境运行下面的安全安装器。它检查完整结构、成员白名单、路径穿越、重复名称、符号链接、文件/总容量上限，再解压到新建私有临时目录，最后原子更名。文件权限 0600、目录 0700；不会覆盖已有版本，也不改历史动画、源码、图表或媒体字节。

   ```sh
   python -m scripts.install_private_archive /private/incoming/site.zip /srv/interview-forge-private/releases/20261115/site
   ```

3. 设置 `INTERVIEW_FORGE_PRIVATE_ARCHIVE_DIR` 为上面的 **site 目录绝对路径**。服务读取已解压目录，ZIP 可移走；`INTERVIEW_FORGE_PRIVATE_ARCHIVE` 仅保留旧部署兼容。目录一旦配置，即使失效也不会偷偷退回 ZIP。
4. 核对 `INTERVIEW_FORGE_PERMANENT_ADMIN_USERNAME` 为指定固定账号，按现有流程重启 FastAPI。目录读取要求 Linux/POSIX 的 `openat` / `O_NOFOLLOW`；不支持的平台拒绝服务，不使用不安全替代。Windows 可准备原始附件，但应在服务器运行安装器和验证。
5. `/api/` 必须经过应用且绕过代理/CDN缓存；不可给私有目录配置公开 alias。测试游客/普通用户/其他管理员/永久管理员访问入口及 `data/manifest.json`，预期 401/403/403/200。缺少部署目录会显示不可用，不应回退为公开静态内容。

服务每次请求重新校验真实会话和永久管理员身份，逐层以不跟随符号链接的文件描述符打开目录；只读取白名单内的普通单链接文件，拒绝目录链接、文件链接、硬链接、设备/FIFO、越界路径及超限文件。配置在仓库内也会拒绝。响应为 `private, no-store`、`Vary: Cookie`、`nosniff`，不发 ETag/304，Service Worker 排除 API 路径。纯静态托管或旧版 Python HTTP 服务不支持此入口。

回滚：保留上一版已解压 release，把环境变量改回其绝对路径并重启服务；不要用符号链接切换。首次从 ZIP 迁移时，可清空目录变量并恢复原 ZIP 变量作为临时回滚。切换前后都检查授权/未授权访问和缓存头，旧目录保留到验收完成后再由操作者清理。

已打开页面在重新聚焦、从浏览器历史恢复及周期检查时重新验证身份；撤销后清空页面并返回登录。已经合法发送给永久管理员的内容不能远程收回，浏览器内存中已打开内容也不是新的网络授权。不得把客户端隐藏当成访问控制。

## 展示与附件修复

附件原有 `assets/hljs.js` 实际包含重复页面脚本，缺少所需 DOM 后启动失败，同时重复声明全局变量。接入时仅在返回的 HTML 中替换这一依赖为本仓库固定版本的 highlight.js，并桥接其 `learningHighlighter` 名称。原始 ZIP 不修改。另在外层接入脚本中兼容原始资料的 `code.language-mermaid` 标记：补齐父级 `pre.mermaid`，让现有渲染器正确加载预生成 SVG 索引。

额外样式只影响外层学习阅读页面：沿用项目紫蓝色、限制宽屏正文宽度、约束流程图预览高度、保留放大与缩放、代码块独立滚动。Git 历史 iframe 的脚本、模板和数据不作修改。阅读页返回入口指向学习书架 `/library/index.html`。

## 验证

```sh
python -m pytest -q tests/test_private_archive.py tests/test_private_archive_install.py
python -m scripts.check.private_directory_smoke
python -m scripts.check.private_archive_smoke /absolute/private/site.zip
```

权限测试使用临时真实 SQLite 会话表、散列会话 cookie，覆盖匿名/伪造/过期/停用会话、普通用户、普通管理员、永久管理员、角色变更、撤销会话、路径穿越和配置缺失。浏览器脚本使用真实 FastAPI 路由、测试身份，可选 `--output` 必须是仓库外的私有目录。附件始终不进入测试夹具或公开构建产物。

本次仅完成代码集成和本地验证；没有把私有附件上传服务器或部署。接入用户本地电脑时需先核对其未提交改动和现有部署流程，不能直接覆盖工作目录。

前一轮 ZIP 兼容模式的实际附件浏览器验证通过：18 个章节、64 份原始资料、1553 个语法高亮 token、29 个流程图，六种视口、九种历史视图；流程图放大/缩放/关闭和失效后的跳转通过。历史脚本、模板、数据与 ZIP 原件逐字节一致。

目录模式本轮只使用独立临时目录内的合成教学夹具，不读取真实用户正文。安装后删除夹具 ZIP，再验证入口、脚本、JSON、语法高亮与图表尺寸，确保不是继续依赖 ZIP。真实附件由后续服务器安装流程提供；本轮不触碰生产。

## 书架动态入口

公开书架仅含空挂载点和通用展示脚本；名称和说明由带会话、`no-store` 的 `/api/private-archive-status` 返回，不读取教学正文、缩略图、目录或统计。卡片不加入公开模块数据、模块总数、搜索索引或 Service Worker 缓存。链接仍是 `/api/private-archive/index.html`，每个资源的服务端鉴权保持不变。

未登录、普通用户、普通管理员、配置缺失、不可用及请求失败均不显示卡片。切号事件、跨标签存储事件、恢复焦点和页面历史恢复会先清空再复查；页面隐藏/离开时移除 DOM，后台不保留可见卡片，前台每 30 秒复查撤销权限。请求超时/旧响应不会重新显示已撤销的卡片。仅使用合成会话和资料验证，不修改真实教学目录。

本轮验证：31 项权限/安装/书架/导航/缓存版本测试及 126 个子测试通过；Node 验证过期响应、身份变更、页面历史恢复、隐藏页清理、轮询撤销和 Service Worker API 绕过。Chromium 使用真实合成会话 cookie，覆盖游客/用户/普通管理员/超级管理员、可用/不可用/503、切号及角色撤销，以及 1920×1080、2560×1440、390×844 的明暗主题。公开模块数和筛选保持，教学页返回书架可用。只读取测试夹具，无真实身份或资料。

本地书架正文布局套件因稀疏检出缺少既有书籍/章节文件有 11 项未通过；相关文件未改动，完整检出的 PR quality CI 是最终全量验证。浏览器使用进程内 HTTP 传输，未模拟真实 nginx/CDN；API 的 no-store/Vary 和 Service Worker 绕过另有自动化验证。
