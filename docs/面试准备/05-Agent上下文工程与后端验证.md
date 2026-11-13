# Agent 怎样在预算内记住用户的要求

2026-11-14。本次对照基线为 `b14e31be`。本文的测量来自临时 SQLite 数据库、脚本化模型和本地浏览器，可用文末命令复现。

## 三个可以现场演示的需求

1. 学员在一大段背景中说“必须先让我自己回答，再给提示”。隔了很多轮再问最初的约定时，助手可以按摘要里的消息 ID 找回原话，也可以从最早的消息开始查关键词。追问刚才的长答案时，两端的问答也有来源。
2. 助手先查资料 A，再查 B，最后重新用 A。即使上下文很挤，也能再取 A 的全文，回答下方的资料链接随最后一次真正送给模型的证据变化。
3. 同一会话从两个浏览器标签页同时提问，后到的一次在扣额前收到 409。学员可以展开回答下的“上下文使用情况”，查看历史条数、每次输入估算和旧工具结果压缩情况。

## 调研如何改变设计

| 实现或实验 | 借鉴到项目中的取舍 |
| --- | --- |
| OpenHands 把压缩后的视图和事件历史分开，保护边界事件。 | SQLite 保留原消息，按完整问答保留最近历史。被挤出的长问答使用带消息 ID 的摘录，原文可以再次读取。[OpenHands condenser](https://github.com/OpenHands/software-agent-sdk/blob/e454a869d539de6d643a62bfe0dedf381cd99348/openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py#L311-L355) |
| LangMem 单独预算摘要和最近消息，处理模型工具调用与结果的配对。 | 工具参数、调用 ID、操作确认及错误都有协议含义。省掉旧结果正文时保留原位置与调用关系。[LangMem 实现](https://github.com/langchain-ai/langmem/blob/8620b986af5b0c7593e6b7fbece2998690d22d15/src/langmem/short_term/summarization.py#L164-L214) |
| Mastra 在记忆回查中限制资源和线程；Deep Agents 对大结果生成预览和可寻址的来源。 | 由服务端会话确定允许读取的原记录。数据库里的消息以 ID 定位，工具的完整结果复用单轮只读缓存。两种来源有不同生命周期。[Mastra 回查工具](https://github.com/mastra-ai/mastra/blob/a86a47c7ef92aa3a48b6663336235a43b7535aaa/packages/memory/src/tools/om-tools.ts#L188-L199) · [Deep Agents 结果处理](https://github.com/langchain-ai/deepagents/blob/c4f08a3de015003a9f16ebf560e5fef439000f11/libs/deepagents/deepagents/middleware/_message_eviction.py#L241-L280) |
| Aider 对实际生成的内容重复计量；LlamaIndex 预留提示和生成空间。 | 学情分析把完整消息、结构化 schema、输出和显式思考预算一起计算。首次和修复请求都放得下，才调用模型。[Aider 实现](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py#L675-L701) · [LlamaIndex 实现](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/indices/prompt_helper.py#L168-L261) |
| JetBrains 比较了隐藏旧观察和调用模型做摘要，在软件工程任务中测试两者的成本与效果。 | 这里优先隐藏可恢复的只读结果，用确定性规则摘出约束，压缩本身无需增加一次模型调用。论文的任务与本站面试练习不同，本站数字单独测量。[原始研究](https://arxiv.org/abs/2508.21433) |

## 一轮请求经过哪些边界

| 入口 | 保留和压缩的单位 | 容量不足时的行为 |
| --- | --- | --- |
| 聊天、页面选区与学情问答 | 当前问题全文、按话题选出的完整问答、历史摘录和来源 ID。每次准备最多物化 256 条历史原文。页面选区保留首尾，学习事实、记忆、操作状态都有完整的精简版本。 | 长回答改用摘录与 ID；显式跨历史回顾可以使用较早的摘要。独立新话题跳过无关上下文。即使去掉可选内容还超限，就拒绝该次模型请求。 |
| 每次工具调用、最终作答与工具回退 | 每次按实际消息和工具定义计量。可用输入预算使用量超过 90% 或累计结果过大时，先隐藏较早的纯成功只读批次中的结果。 | 保护最近一次有效读取、写操作状态、确认结果和错误。新批次本身超工具硬限额时返回明确的错误。最终回答只列该次模型请求可见的书架来源。 |
| 学情分析、修复与规则分析 | 固定用户要求、资料覆盖和数据质量。案例和支持它的事实一起选择，首次、修复和流式路径共用本次可见引用集合。 | 即使某引用真实存在于数据库，模型也只能引用本次请求送入的依据。窗口无法容纳必要约束和案例时，后台在模型调用和扣额前转用规则分析。 |
| 长期记忆抽取、更新与注入 | 对完整原文判断敏感信息、临时要求、否定和例外；明确遗忘才允许删除。涉及条件的短偏好保留用户措辞，注入聊天时按完整记录取舍。 | 抽取模型窗口不足或无法忠实表示时跳过该次抽取。已确定的简单偏好可以由规则处理。本轮聊天仍可继续。 |

聊天、学情和记忆都会为显式配置的思考 token 预留空间。供应商没有公布窗口时，使用各自的本地预算。健身图片识别等视觉业务有独立的模型白名单、图片输入和降级路径，文本压缩器只处理上述文本请求。不同模型的 tokenizer 和供应商协议开销会有差异，聊天明细将本地估算与供应商实际返回的输入用量分开。

### 流式请求和配额如何保持一致

生产采用单主机多 worker。启用 `IF_SHARED_RUNTIME=1` 时，相同账号数据库和会话 ID 竞争同一个操作系统文件锁。取得锁后才扣额度，因此不同账号和同一账号的不同会话可以同时生成。扣额线程运行中收到取消时，路由等待数据库给出确定结果，再按回执中的上海业务日退款和释放锁。

在本次上下文工程的验收版本中，服务端以用户消息写入 SQLite 后产生的 `message.start` 作为计费分界。仅发出 HTTP 响应头时断开，会退回本次扣量。后续发布引入了客户端请求标识。当前网页重试已完成的消息可取回原答案；无已提交结果或副作用的中断可按原业务日退额，再用同一标识重试。两版的验收记录应按各自发布版本解读。[当前聊天请求恢复机制](../AI-CHAT-REQUEST-RECOVERY.md) · [Chat 路由](../../interview_forge/api/routers/chat.py) · [Stripe 幂等请求](https://docs.stripe.com/api/idempotent_requests)

### 如何检查一次真实回答

在 AI 助手发起问题，展开回答下的“上下文使用情况”。后台从当前登录账号的数据库中按会话和轮次查询，返回准备阶段的选入条数、压缩或省略的类型，以及每次模型调用的估算与可用的供应商用量。账号间隔离与返回字段采用白名单。API 地址为 `GET /api/chat/sessions/{session_id}/turns/{turn_id}/context`。无历史追踪数据的旧回答会显示记录不可用。[诊断实现](../../interview_forge/ai/chat/diagnostics.py)

## 可复现的对照

同一脚本先生成 4 条消息，检查压在长段中间的约束；再追加 512 条消息，检查读取规模和完整提示。页面选区使用固定的长字符串。两版使用各自的真实构建器和同一组问题。

| 观测项 | 基线 | 改造后 |
| --- | ---: | ---: |
| 摘要包含“必须先让我自己回答，再给提示” | 否 | 是 |
| 摘要可用原消息 ID 定位 | 否 | 是 |
| 长选区末尾“不能提前公布答案”可见 | 否 | 是 |
| 每次准备读入的历史消息正文 | 516 | 256 |
| 保留在数据库的消息 | 516 | 516 |
| 516 条样本的准备阶段输入估算 | 2,375 | 2,923 |

读取的历史正文减少了 50.4%。这条样本的提示增加了 548 个估算 token，包含早期要求、来源和回查说明。另一条超过 1,300 条消息的测试让唯一约定出现在会话开头，按最早优先搜索一次即命中。默认按最近搜索，两种方向都只搜索本账号、本会话和当前消息之前的原文。仅凭这些样本不能推算线上账单或回答正确率。[历史回查测试](../../tests/test_ai_chat_recall.py)

工具压力实验把模型窗口设为 780、输出预留设为 50，按 A、B、A 三次查询，每份正文 800 个 ASCII 字符。回归用例中四次请求的原始／准入估算依次为 110／110、476／476、843／540、1,217／610。最后一次重新获得完整 A，处理器实际执行 A 和 B 各一次。加入前置 system 消息重测，最终请求为 1,229／621。LangChain Core 转换后，工具调用和结果的 ID 配对，最终轮与回退均只有一条位于首位的 system。该协议检查使用本地模型替身。[缓存恢复与来源测试](../../tests/test_ai_agent_runtime_governance.py) · [Anthropic 适配器](https://github.com/langchain-ai/langchain/blob/langchain-anthropic%3D%3D0.3.22/libs/partners/anthropic/langchain_anthropic/chat_models.py#L273-L295)

在当前仓库运行以下命令。比较旧版时把第二条的路径指向已检出 `b14e31be` 的仓库。脚本在临时目录中构建数据库。

```powershell
python scripts/check/ai_context_eval.py
python scripts/check/ai_context_eval.py --source-root ../interview-forge-baseline
python -m pytest tests/test_chat_context_compaction.py tests/test_ai_chat_recall.py tests/test_chat_quota_admission.py
python -m pytest tests/test_ai_agent_runtime_governance.py tests/test_ai_request_budget.py tests/test_ai_coach.py tests/test_ai_memory.py
```

面试演示可以从“刚刚那段答案很长，下一轮还找得到哪一句”开始，然后展示该轮的上下文用量、消息 ID、工具回查和数据库原文。断开连接与跨午夜退款可以运行回归测试演示，无需使用个人账号额度。

## 验收记录

- Windows 全仓 Python 回归共 1,509 项通过，另有 233 个子测试通过。1 项仅适用 Linux 的四 worker Uvicorn 集成测试跳过。显式思考预算接入聊天后，模型请求、工具、学情与记忆的 114 项专项测试及 18 个子测试再次通过。
- 10 个前端 JavaScript 测试脚本通过。本地 Chrome 以临时登录账号发起聊天，经历工具查询和两次模型请求。在 1,280 与 390 像素宽度下，流式完成后和页面刷新后均可展开明细，页面无横向溢出，浏览器无 JavaScript 错误。在手机宽度下另用固定诊断响应验证节省量与超限提示。
- 模型替身记录实际送入的消息，用于验证引文、约束和错误路径。这里没有使用真实供应商调用或生产账号，统计结果适用于给定输入和项目估算器。
