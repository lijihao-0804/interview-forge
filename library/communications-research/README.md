# 通信工程就业数据包

本目录为独立静态前端和分析数据。不要覆盖已封存v4主看板；建议部署到 /research/communications/。

本地预览：在本目录运行 E:\python\python.exe -m http.server 8765，然后访问 http://127.0.0.1:8765/。需HTTP服务，不能双击HTML加载数据。

入口 index.html；报告 reports/通信工程专业就业报告.html；完整文本 data/corpus.ndjson.gz；轻量目录 data/catalog.json.gz，浏览器不支持解压时回退明文；详情 data/details/*.json 按需加载。全部路径相对，支持嵌套路由。需正确提供 .mjs 为JavaScript、JSON为application/json，不要对普通gzip文件重复套Content-Encoding。

后续分析使用 data/analysis.json、reports/技能分职业统计.csv、专业候选岗位.csv。字典970项，零提及项也留在技能聚合CSV；city_tags与degree_words可多值重复，不能相加作总量。

不要将原始网页HTML直接嵌入站点；前端详情以文本展示。原始采集文件另见 archives/ 和 source_archives.zip。详情包含source_job_id、来源时间、文本哈希与专业证据。请保留审阅和专业分层，不把相邻专业、社招参考与应届直接候选混合宣称可投。
