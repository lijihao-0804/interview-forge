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
