# 长对话历史回查对照实验

同一个合成会话包含 1,280 条原始消息。八个主测问题覆盖通勤、算法、复习、旅行、网页交互、小数精度、图书保管和发布检查。提问用当事人可能记得的意思描述原话。对每个目标，语料还包含一条用问题措辞描述他人经历的干扰项，以及一条含相近场景、不同细节的记录。目标消息全部在上下文构建器直接加载的最近 256 条以外。

另外五题分别检查原词保留、只找最早记录、两条均合理时的澄清、会话内没有答案以及历史留言中的指令。在同账号的其他会话中植入了一条缺失题的仿真答案。各题使用不同聊天会话，避免上题回答补充下题的上下文。

原版的第一组测量完成后，另封存五题。在任何候选版输出产生前，为这组题保存了独立的语料、问题、原句位置和判分依据。四题检查说话人归属、引述中的第一人称、长消息靠后的原话和多分句引用，一题保留相同措辞作为正对照。该组单独计算，以便作为未用于调整实现的预留验证。

## 固定材料和评分

运行两种实现前已保存问题、消息、金标准、直接检索查询和顺序。冻结文件的 SHA-256 为 `9d1a34350fd857f262f795a68d4747184d906008801c140e7c5c07c32e72361b`。`freeze.py` 仅用标准库生成 `fixtures.json` 和 `lock.json`，发现既有文件与预期不同即退出。仓库的 UTF-8 JSON 使用 LF 行尾。

五题预留文件的 SHA-256 为 `4f7e2455f399e59fc4908ac5242e5b6a45c9ae3c994506a6517af78c1447e781`。`holdout.py` 使用第一份材料的生成逻辑重建该语料和清单。

主指标要求最终可见回答同时含完整原句，包括原标点，以及明确标注的正确消息编号。另计召回所有目标证据、逐字引用、正确编号、链接能否打开原片段。多解题另核查明确承认多解并列出两份证据，缺失题检查是否明确没有证据且没有给出消息编号。保留逐题原答案便于复核。原句中独有的物品、颜色和方案均未出现在主测问题里。

固定的关键词探针会先各用三个短词，对应的不设轮数上限版本允许每个短词翻完历史。后一项用于检查整份历史里能否查到目标，不能当作旧 Agent 的实际成绩。语义探针仅使用预先固定的一次短查询。主评测让两个版本的正常 Agent 自主选择工具、搜索词和翻页，提示里没有工具名或查询方式。两版使用各自发布时的系统提示与工具说明，因此测得的是整套产品变更的差异。

两个版本对每题各调用一次在线模型。发布时段、供应商负载和缓存可能影响用时及账单。八个主测领域为人工选取，百分比只描述这组题。配对结果含增益、退化、持平、双侧精确符号检验和逐一剔除每个领域后的差值。金额只在有真实单价、计费单位和缓存分项的情况下计算。

第一份会话的 1,280 条消息含 293 段不同的全文，第二份含 303 段。其余为打散后重复出现的非目标问答。候选实现可以复用相同文本的向量，因此冷索引用时只代表这种重复率和文本长度。不同主题的新作文档或大量长代码块需要单独压测。

## 本地复现

在仓库根目录使用该版本项目依赖的 Python。只跑 `freeze.py` 和 `score.py` 无需额外依赖。命令中的 `python` 可替换为项目解释器路径。

```console
python scripts/benchmarks/semantic_history/freeze.py
python scripts/benchmarks/semantic_history/holdout.py
python scripts/benchmarks/semantic_history/replay.py literal --case k01
python scripts/benchmarks/semantic_history/replay.py semantic --case p03
python scripts/benchmarks/semantic_history/replay.py agent --case p03
python scripts/benchmarks/semantic_history/replay.py semantic --suite holdout --case h03
python scripts/benchmarks/semantic_history/score.py --baseline path/to/baseline.json --candidate path/to/candidate.json --out path/to/paired.json
```

`replay.py` 为每题创建临时 SQLite 数据库，结束后删除。省略 `--case` 可跑完 13 题。可用 `--repo` 指定统一使用项目正常 Python 依赖的另一份代码检出，以比较基线提交 `4ce3e62ecb567bc456ae59e06588ca8a2a96698d` 与候选版本。基线支持 `literal` 和 `agent`。候选的 `semantic` 使用项目已配置的本地编码器。`agent` 使用该检出配置的实际聊天模型，会产生供应商用量，输出会明确标出使用的模型。复现场景运行在本地服务层。发布实测通过登录后的公网 HTTPS SSE 路由，包含网络时间、入站和持久化。
