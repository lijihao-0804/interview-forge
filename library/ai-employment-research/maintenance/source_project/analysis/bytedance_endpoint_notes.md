# 字节招聘列表接口核验

核验日期：2026-11-17。目标仅限确认官方公开招聘页实际使用的职位列表接口、方法和匿名读取条件；没有尝试登录、获取或重建签名、伪装浏览器身份、处理验证码或遍历其他端点。

## 从官方页面脚本确认的接口

- 招聘门户：[jobs.bytedance.com](https://jobs.bytedance.com/)
- 页面加载的官方前端脚本：[2816.fe85e779.js](https://lf-package-cn.feishucdn.com/obj/atsx-throne/hire-fe-prod/portal/mainland/static/js/2816.fe85e779.js)
- 脚本中的位置列表配置为 `getPositionList -> /search/job/posts`；同一模块的请求调用使用 `v_` 封装。网络封装模块将 `v_` 映射为 `method: "post"`，因此实际列表请求是：

  ```text
  POST https://jobs.bytedance.com/api/v1/search/job/posts
  ```

- 页面响应归一化代码读取 `data.job_post_list` 和 `data.count`。请求体由前端表单参数转换，包含关键字、分页偏移/大小、招聘类别、地点、招聘项目等筛选字段。
- 详情页配置为 `GET /api/v1/job/posts/{职位ID}`，过滤配置为 `GET /api/v1/config/job/filters/{筛选ID}`。本次只为解释列表到详情的关系记录这些脚本中出现的路径，没有请求其他端点。

## 为什么不能按匿名普通HTTP批量读取

官方脚本的请求拦截器会为列表和详情路径追加 `_signature`，签名依赖请求URL和POST正文；POST还由页面补入 `portal_entrance`。同一运行时会设置 `website-path`、`Portal-Channel`、`Portal-Platform` 等头，并使用 `x-csrf-token`。脚本的CSRF逻辑从站点Cookie或页面请求的令牌取得该值。Axios客户端也配置 `withCredentials: true`。

这说明脚本中虽有职位列表API，但直接请求接口与页面实际请求并不相同。本次用普通HTTP做了小规模连通性核验：

| 请求 | 结果 |
|---|---|
| `POST /api/v1/search/job/posts`，仅带普通关键字/分页JSON和常规Origin/Referer | HTTP 405，空响应体，未取得记录 |
| 同路径普通 `GET`，带关键字/分页查询参数 | HTTP 200，但返回标题为“字节跳动猎头平台”的HTML外壳，不是招聘JSON |

响应细节保存在 [bytedance_collection_audit.json](../evidence/bytedance_collection_audit.json)，采集逻辑在 [collect_bytedance.py](collect_bytedance.py)，职位结果文件为 [bytedance_bulk.json](../evidence/bytedance_bulk.json)。

## 结论与停止条件

已从官方公开前端代码确认真实列表地址和POST方法；接口请求依赖页面运行时提供的签名和CSRF上下文。裸请求未返回招聘数据。按照本任务边界，不重建这些运行时参数，也不启动动态页面来提取请求身份信息，因此字节批量正文真实获取量为0条，职位数和全量规模保持未知。到此停止字节批量尝试；这不改变其他企业数据的采集结果。
