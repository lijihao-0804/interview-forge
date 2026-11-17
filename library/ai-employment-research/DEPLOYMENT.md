# 网站执行者：上线 v4.0.0

将本目录整体部署到现有就业调研入口，或独立静态路由`/research/jobs/`。入口为`index.html`，所有资源采用相对路径。保留`assets/`、`data/`、`reports/`、`tools/`、维护文档与期次归档的目录关系。接入现有网站可先用独立路由，导航进入研究结论用`index.html#view=research`。

真实数据截面仍为2026-11-17，v4是可视化与技术处理版本。研究页包含按当前城市/条件重算的方向卡和图表、完整原子技术词表、固定研究判断与真实期次归档。固定研究文案和实时图表有各自口径，部署时按包内结果保留。

首屏由Worker读取`catalog.json.gz`和`technology-index.json.gz`；全文详情按需读取分片，完整corpus和期次归档供下载/二次分析。静态服务需要正确返回`.mjs`的JavaScript MIME和JSON，数据请求不能被SPA兜底替换为HTML。gzip作为下载文件时保留压缩字节，服务若透明解压需正确设置Content-Encoding；具体见INTEGRATION.md。

部署前运行`python tools/verify_data.py`，核对包内验收与截图。上线后从实际路由检查城市筛选、技术钻取、完整JD、CSV导出、手机布局及资源请求，并在目标对话报告实际访问地址和上线结果。当地已有旧版入口时，按目标项目的发布与回滚流程更新；本包的历史基线仍须保留。

采集与后续月份更新见MAINTENANCE.md和maintenance/PACKAGE_COMMANDS.md。当前只有一期真实基线，跨期趋势等待真实新一期采集后由工具生成。网站源码需要提交/推送时，遵循目标项目已有GitHub分支与发布约定。
