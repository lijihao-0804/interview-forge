# 网站执行者接入说明

## 推荐交付方式

把整个文件夹放到网站静态目录，例如 `/research/jobs/`，访问 `/research/jobs/index.html`。所有JS、Worker、数据和全文分片均通过相对路径加载。不要只复制HTML；`assets/` 与 `data/` 必须保持同级。

如果原网站已经有导航、登录和布局，可先以独立静态路由或iframe集成，避免CSS相互覆盖。本包不操作原网站账号、学习进度、服务Worker或鉴权状态。需要原生组件化时，可复用下述数据与纯统计模块，再接入原站组件。

Vite/React/Next等项目可把文件夹完整放到 `public/research/jobs/`。无需安装本包的依赖。若迁为组件，使用原站的路由和数据缓存，不要直接把整个 `app.mjs` 当作React组件引入；它是独立页面控制器。

## 静态服务要求

- `.mjs` 返回JavaScript MIME，JSON返回 `application/json`，避免SPA兜底把数据请求改写为HTML。
- Worker脚本和入口建议同源。不要把本包脚本放在跨域CDN而不处理Worker策略。
- HTTPS用于线上；复制链接可能需要安全上下文，失败时界面提供手动复制。
- 对JSON/JS/CSS开启HTTP gzip或Brotli压缩，详情分片使用缓存；版本更新时按manifest版本/哈希更新缓存。`corpus.ndjson.gz` 是下载用gzip文件，不应再误加 `Content-Encoding: gzip` 导致下载内容被服务端透明解包后仍叫.gz。
- 本包同时提供约3.37MB的`catalog.json.gz`，Worker优先通过浏览器原生DecompressionStream读取；缺少支持或请求失败时回退约44MB的普通JSON，因此建议同时保留两个文件。直接修改目录后应重新生成gzip镜像，并同步清单哈希。
- 先检查 `/research/jobs/data/catalog.json` 和任一 `detail_shard` 返回的是JSON，再检查页面。
- URL查询串只保存公开筛选条件。收藏、对照与技能清单在localStorage，不上传个人资料。

## 数据读取

```js
const base = new URL('/research/jobs/data/', location.origin);
const catalog = await fetch(new URL('catalog.json', base)).then(r => r.json());
const job = catalog.jobs[0];
const shard = await fetch(new URL(job.detail_shard, base)).then(r => r.json());
const full = shard[job.id];
console.log(full.description, full.requirements); // 原文
```

`requirements_analysis` 是技能统计用段落；原始完整资格字段仍在 `requirements`。不要用摘要代替原文，不要把缺失文本写成空要求/不限要求。不要直接把上游provenance字符串当网站链接。

## 复用筛选与统计

`assets/engine.mjs` 是无DOM、无框架依赖的模块：

```js
import {prepareJobs, filterJobs, aggregate, csvText} from './assets/engine.mjs';
const jobs = prepareJobs(catalog.jobs);
const selected = filterJobs(jobs, {
  directions: ['AI Infra'],
  skills: ['C++', 'CUDA/Triton'], skillMode: 'all',
  geography: 'mainland', hasRequirements: 'yes'
});
const stats = aggregate(selected);
```

筛选协议是 `DEFAULT_FILTERS` 的字段；数组维度内任一匹配，不同维度同时满足，技能/学历词另设all/any。空格分隔搜索词默认全部匹配，排除词命中任一就剔除。搜索覆盖标题、摘要、公司、城市、代码和技能标签，**不是全文检索**。

`aggregate()`返回记录/正文/独立要求分母、公司与职能/城市、技能、四方向交叉统计和共现组合。默认Lift最小共现20条；公司均权仅纳入方向内要求≥5条的公司。筛选集合改变后Lift和分母也会改变，不应跨集合直接比高低。

`worker.mjs` 消息：`INIT`→`READY`；`QUERY {filters,page,favoriteIds,requestId}`→`RESULT`；`PAGE`→`PAGE_RESULT`；`LOOKUP {ids}`；`EXPORT`→CSV。`requestId`用于忽略过期响应。单页24条，全文按需加载，目录与全文分离。

## 进一步做高级筛选或分析

完整语料见 `data/corpus.ndjson.gz`，可直接Python逐行读取，见 `tools/analyze_example.py`。需要全JD检索/多人并发接口时，可运行 `tools/build_sqlite.py` 构建可选SQLite与FTS5索引，再接入原项目后端。前端当前不假装能在所有JD正文上全文搜索。

后端可增加：正文FTS、经验表达人工复核、按公司/团队范围标准化、真正的发布时间序列及职位关闭事件。当前单日截面无法推导同比或HC转化，不能从标题规则直接推最低学历或必须精通。

高级分析的可重算脚本和文档随包提供。`editorial.json`是有来源数字与边界的固定研究结论，不应在用户切换条件时伪装成实时生成结论。更新数据后要同步重新计算并审读这些文案。

```sh
python tools/recompute_analysis.py --output-dir reports/recomputed
python tools/analyze_example.py --direction "AI Infra"
python tools/verify_data.py
```

第一个命令默认直接读取本包的gzip语料，不依赖原项目；重新生成JSON和Markdown供复核，不覆盖当前已审读的结论文案。目录扩展的后训练线索可用 `posttrainingSignal: 'duty' | 'requirement' | 'either' | 'candidate'` 选择。前三种是文本命中；candidate还并入严格标题组，不能解释成已确认的后训练主责。

## 上线前检查

检查子目录资源与Worker无404、技能AND/OR结果、筛选CSV全量行数、长数字ID文本保护、全文分片、元数据缺口、手机横向溢出、明暗模式和键盘操作。已有验收记录位于 `reports/`。本包不含任何自动发布/上传动作；挂站由目标项目执行者按其发布流程完成。
