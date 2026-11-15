# 永久管理员私有档案

入口位于管理后台页头。只有服务端确认当前会话属于永久管理员时才显示入口；页面、JSON、源码摘录、图片、脚本的每次直接请求都再次检查身份。普通 `admin` 角色不足以访问。

## 安装边界

公开仓库仅保存接入代码、通用样式和 BSD 许可的 highlight.js 11.11.1。用户提供的 ZIP、解压内容及包含正文的截图**不得提交仓库或放入任何公开静态目录**。

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

额外样式只影响外层学习阅读页面：沿用项目紫蓝色、限制宽屏正文宽度、约束流程图预览高度、保留放大与缩放、代码块独立滚动。Git 历史 iframe 的脚本、模板和数据不作修改。阅读页增加返回管理后台入口。

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
