# 2026-11-15 上线后修订

本节描述基于 main `17fddea` 的本轮变化；下方原验证记录仅作历史参考。

后续语义修复基于 `f468324`：指定语言的「从未做过」按已记录提交/尝试判断，AC、WA 均计；不限语言不变。23 项针对性测试及 12 个子测试通过，浏览器以 Python WA / Java AC 合成记录验证候选数与实际组卷，并复查五种宽度、明暗主题。

- 删除中控台三张「从一道简单题开始 / 补齐一个知识点 / 还不确定学什么」卡片及专用样式，保留搜索与其他导航入口。首页生成模板把唯一的 `leetcodeSyncBtn` 移到「开始刷题」后；保留原事件、登录限制、忙碌与错误提示。
- 限时模拟增加语言选择。仅「从未做过」可选语言，Python、Java 等按现有 `submission_language_key` 规范化；按可信语言的已记录提交/尝试次数（`submits`）排除该语言的题，包括 AC 和 WA；不以通过轮数或日期聚合判断是否尝试过。未知语言、仅浏览及另一语言的提交不排除。不限语言保持旧范围定义。
- `/api/mock?preview=1` 与实际组卷共用候选过滤，预览不写考试记录或抽题历史。界面显示实际可抽数量、零候选提示和历史语言记录限制；不以用户偏好语言补写历史。
- 私有教学站默认从真正解压的独立目录提供；详见 [安装、安全与回滚](private-archive.md)。本轮只使用合成测试资料，未提交或部署真实附件。
- Shell 缓存版本更新为 `hot100-v33-20261115-mock-attempts`。

## 本轮验证

- 针对性 Python：48 passed、138 subtests passed（语言、私有目录权限/提取、导航、同步与失败状态）。
- Chromium + FastAPI：中控台/题库在 320、390、768、1920×1080、2560×1440 检查无横向溢出、明暗主题；同步按钮前后顺序、游客禁用、登录后可用及服务失败后恢复、搜索筛选、标记、模拟、会话失效通过。
- Python / Java 候选数与实际组卷结果通过真实 API 核对；模拟设置在 390、1920、2560 宽度截图，桌面六列、平板三/两列、手机单列。
- 目录模式浏览器：安装合成 ZIP 后删除 ZIP，四种视口通过；代码高亮、图表尺寸、脚本及历史数据字节保持、普通管理员/匿名拒绝通过。真实会话测试另覆盖撤销、过期、角色变化等。
- 变更页面内联 JavaScript 语法、Ruff E9/F821、diff 空白检查通过。
- 完整本地 Python 尝试：1534 passed、44 failed、2 skipped。失败日志均指向稀疏检出缺失的现有书籍/演示/生成页面或测试访问域名的 DNS 解析失败；本地完整结构检查与全部 JS 行为测试也被缺失书籍文件阻塞。不能把这些尝试表述为全量通过，完整检出由 PR 的 quality CI 验证。

本轮浏览器通过进程内 HTTP 传输运行，未验证真实 nginx/CDN、Service Worker 网络更新或生产部署；真实附件仍待操作者在私有服务器目录安装并验收。未触碰 Windows 工作目录或生产。

---

# 学习工作台体验改进与验证

## 改动范围

保留紫蓝主色、浅灰白圆角卡片与深色模式，优化中控台和 Hot 100 题库的实际学习流程。

- `cockpit.html`：根地址实际进入此页。新增题库 / 书架全文双范围搜索、可清除的本机上次搜索，以及简单题练习、系统学习、学习路线三条入口。搜索使用现有服务与页面参数，不新增后端接口。
- `tools/templates/dashboard.tpl`：题库加入难度筛选、题号 / 难度排序、卡片 / 紧凑列表切换；公开筛选保留在 URL，刷新与返回可恢复。私人进度条件不写入 URL。
- 默认先显示 24 题，可继续加载或显示全部；加载后键盘焦点进入首道新增题。无结果提供一键清除筛选；支持 `/` 聚焦搜索。
- 增加固定分区导航，直接到复习、模拟、薄弱清单和学习轨迹，并随滚动更新当前位置。保留所有旧功能和依赖 ID。
- 提供可清除的本机最近打开题目入口。只存公开题号，不伪造学习进度。
- 加载和连接失败时，统计与目标显示未读取状态，避免将未知数据展示为真实零值。
- 两页游客态已有登录入口，因此隐藏重复的浮动游客登录条，减少手机屏幕遮挡。登录后的账号控件保留。
- `index.html` 通过现有 `render_dashboard()` 生成；没有只修改生成产物。同步更新 `service-worker.js` 和权威版本常量为 `hot100-v30-20261115-study-workspace`。

## 自动化验证

以下针对性 Python 回归结果：**208 passed、44 subtests passed**。仅有现有 Starlette / AnyIO 弃用警告。

```sh
python -m pytest -q \
  tests/test_dashboard_leetcode_sync.py \
  tests/test_index_mock_settings.py \
  tests/test_ui_retry_contract.py \
  tests/test_navigation_policy.py \
  tests/test_cockpit_p0.py \
  tests/test_guest_access.py \
  tests/test_fastapi_routes.py \
  tests/test_public_mode_acceptance.py
node tests/test_guest_auth.js
node tests/test_time_utils.js
```

JavaScript 游客认证及时间工具行为测试通过。两页全部内联脚本通过 `node --check`，HTML ID 无重复，`git diff --check` 通过。再次执行 `render_dashboard()` 后 `index.html` 字节不变。

## 浏览器验证

新增可复现脚本 `scripts/check/frontend_workspace_smoke.py`。运行示例：

```sh
python -m pip install -r requirements-dev.txt playwright
python -m playwright install chromium --only-shell
python -m scripts.check.frontend_workspace_smoke --output /tmp/forge-ui
```

本次使用 Playwright 1.51.0 的 Chromium headless shell、中文 locale。真实 FastAPI 应用在进程内启动，浏览器 HTTP 请求通过 TestClient 进入真实路由；学习数据写入临时数据库，身份为测试夹具。运行结束自动清理临时学习数据库。

已验证：

- 游客不显示个人统计；公开题目、难度与专题筛选可用。
- 24 → 48 → 100 题分页、加载后的焦点、筛选后分页重置。
- 联合筛选、URL 刷新恢复、搜索无结果与清除、排序、列表偏好持久化。
- 最近打开题目恢复 / 清除、搜索快捷键。
- 中控台两种搜索目的地、上次搜索恢复 / 清除、简单题入口。
- 两页在 **320、390、768、1440 px** 下无页面横向溢出；浅色和深色截图检查。
- 登录夹具下，真实 `/api/mark` 写入并在刷新后恢复；失败写入恢复旧标记。
- 真实模拟接口组卷、开始和放弃；保留原有确认交互。
- bootstrap 返回 503 时显示未读取，重试后恢复实际统计。
- 身份失效后回到游客态，私人控件隐藏，公开筛选继续可用。
- 浏览器报告 **0 个页面 JavaScript 错误**。

截图和 `result.json` 由 `--output` 指定；本次保存在工作区旁的 `frontend-qa/`。

## 范围与限制

- 本次是大仓库的稀疏源码检出，按需恢复了所有 100 道题的 HTML、书架入口和预览资源；没有下载全部书籍媒体或执行全站重建。未运行整个 AI、工具预约和海量内容测试集。
- 普通 Chromium 因环境禁止 Unix socket 无法启动；本地服务监听与云浏览器间不能直连。因此使用 headless shell + 进程内真实 HTTP 传输验证。此方式禁用 Service Worker；缓存版本与生命周期更新契约由现有测试验证，未声称完成浏览器离线缓存升级实测。
- 登录身份由夹具提供，没有使用真实账号或发送注册邮件；天气、AI、力扣外部请求在浏览器测试中返回受控 503，不验证这些第三方服务。
- 没有修改认证策略、数据模型或外部服务逻辑，没有推送、发布、合并或创建 PR。

## 本地开发

```sh
python -m pip install -r requirements-dev.txt
python -c 'from scripts.build.build_hot100 import render_dashboard; render_dashboard()'
python tools/study_server.py --host 127.0.0.1 --port 8765
```

根地址为中控台；题库入口为 `/index.html`。若运行环境配置了 SOCKS 代理，还需安装 `httpx[socks]`。正常部署不依赖本次 QA 使用的进程内浏览器传输。

## 桌面适配与私有档案扩展

后续要求允许推送独立分支；前述“没有推送”仅描述首阶段。没有合并、创建 PR 或部署。

新增 `assets/workspace-layout.css`，保留所有原有颜色变量。中控台、题库、历史、收藏、工具、预约、力扣连接、通知、管理、练习、登录注册和 AI 对话采用不同的适宜宽度；书架与模块网格限制最大宽度，阅读页保留两侧目录、限制正文行宽，在较小宽度收起侧栏。AI 对话在大屏利用可用高度。两个 Python CSS 生成器嵌入同一份样式，生成的 site.css 和 library.css 同步，避免下次构建丢失调整。缓存版本为 `hot100-v31-20261115-desktop-layout`。

`scripts/check/desktop_layout_smoke.py` 已验证 19 个主要页面 × 7 种 CSS 视口，共 133 组：1920×1080、2560×1440、1536×864、1707×960、1280×720、768×1024、390×844。检查页面可见、横向溢出、正文宽度和大屏目录；另保留六个页面的深色截图。1536 和 1707 宽度用于模拟常见缩放后的布局空间，并非真实操作系统缩放或浏览器缩放测试。未发现页面 JavaScript 错误。

覆盖路径在脚本 PAGES 常量中可查，包括中控台、题库、书架入口、模块页、章节、一道题解、全文搜索、学习历史、收藏、力扣连接、练习、通知、工具、预约、AI 对话、登录、注册、指南和管理后台。未逐页遍历数百个书籍章节，也未重做年度报告、维护页、公告详情等专项页面；书籍页面通过共享生成样式受益。第三方服务成功态、真实部署代理和生产缓存仍未验证。

新增永久管理员私有档案，详见 [private-archive.md](private-archive.md)。公开仓库不包含用户附件原文；服务器需要另行配置仓库外的私有 ZIP。高亮依赖的修复不改变 Git 历史动画代码、模板和数据。

最终扩展回归：219 个 Python 测试和 121 个子测试通过；另外 6 个阅读生成器测试通过。学习流程浏览器脚本再次通过；游客认证及时间工具 Node 测试通过。私有档案的全部章节、原始资料和历史视图验证详见专项文档。
