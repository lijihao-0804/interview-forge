# 永久管理员私有档案

入口位于管理后台页头。只有服务端确认当前会话属于永久管理员时才显示入口；页面、JSON、源码摘录、图片、脚本的每次直接请求都再次检查身份。普通 `admin` 角色不足以访问。

## 安装边界

公开仓库仅保存接入代码、通用样式和 BSD 许可的 highlight.js 11.11.1。用户提供的 ZIP、解压内容及包含正文的截图**不得提交仓库或放入任何公开静态目录**。

在已确认部署流程的服务器上，由操作者完成：

1. 将原始 ZIP 放在仓库和所有 Web 根目录之外，例如 `/srv/interview-forge-private/site.zip`。限制文件权限，仅服务账号和服务器管理员可读。不要解压到 `assets`、`pages`、`library` 或发布目录。
2. 在实际服务环境中设置 `INTERVIEW_FORGE_PRIVATE_ARCHIVE` 为 ZIP 的绝对路径；ZIP 应包含 `site/index.html`、`site/assets/` 和 `site/data/`。
3. 核对原有 `INTERVIEW_FORGE_PERMANENT_ADMIN_USERNAME`，必须是已有的永久管理员账号；不要为此改变其他账号权限。未配置时拒绝所有用户。
4. 按现有流程重启 FastAPI 服务。确保 `/api/` 经过应用、没有代理/CDN缓存，也没有其他站点暴露私有存储目录。纯 GitHub Pages 或纯静态托管不支持此功能。
5. 分别用未登录用户、普通用户、普通管理员和永久管理员请求 `/api/private-archive/index.html` 及 `/api/private-archive/data/manifest.json`，预期为 401、403、403、200；失效或撤销会话应立即拒绝后续请求。

服务端直接从 ZIP 读取指定成员，不解压、不建立公共索引、不返回任意文件。配置为仓库内文件（包括解析符号链接后位于仓库内）会拒绝。响应包括 `private, no-store`、`Vary: Cookie` 和 `nosniff`；不发 ETag 或 304。API 路径被现有 Service Worker 排除。旧版 Python HTTP 服务不会提供这些 API，必须使用 FastAPI。

已打开页面在重新聚焦、从浏览器历史恢复及周期检查时重新验证身份；撤销后清空页面并返回登录。已经合法发送给永久管理员的内容不能远程收回，浏览器内存中已打开内容也不是新的网络授权。不得把客户端隐藏当成访问控制。

## 展示与附件修复

附件原有 `assets/hljs.js` 实际包含重复页面脚本，缺少所需 DOM 后启动失败，同时重复声明全局变量。接入时仅在返回的 HTML 中替换这一依赖为本仓库固定版本的 highlight.js，并桥接其 `learningHighlighter` 名称。原始 ZIP 不修改。另在外层接入脚本中兼容原始资料的 `code.language-mermaid` 标记：补齐父级 `pre.mermaid`，让现有渲染器正确加载预生成 SVG 索引。

额外样式只影响外层学习阅读页面：沿用项目紫蓝色、限制宽屏正文宽度、约束流程图预览高度、保留放大与缩放、代码块独立滚动。Git 历史 iframe 的脚本、模板和数据不作修改。阅读页增加返回管理后台入口。

## 验证

```sh
python -m pytest -q tests/test_private_archive.py tests/test_workspace_layout.py
python -m scripts.check.private_archive_smoke /absolute/private/site.zip
```

权限测试使用临时真实 SQLite 会话表、散列会话 cookie，覆盖匿名/伪造/过期/停用会话、普通用户、普通管理员、永久管理员、角色变更、撤销会话、路径穿越和配置缺失。浏览器脚本使用真实 FastAPI 路由、测试身份，可选 `--output` 必须是仓库外的私有目录。附件始终不进入测试夹具或公开构建产物。

本次仅完成代码集成和本地验证；没有把私有附件上传服务器或部署。接入用户本地电脑时需先核对其未提交改动和现有部署流程，不能直接覆盖工作目录。

本次实际附件浏览器验证通过：18 个章节、64 份原始资料、1553 个语法高亮 token、29 个流程图，六种视口、九种历史视图；流程图放大/缩放/关闭和失效后的跳转通过。历史脚本、模板、数据与 ZIP 原件逐字节一致。
