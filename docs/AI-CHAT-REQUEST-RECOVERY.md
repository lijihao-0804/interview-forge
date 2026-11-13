# 聊天请求的重试与恢复

## 页面行为

用户点“发送”时，聊天页为本轮分配随机的 `client_request_id`，连同原消息、当时的页面上下文一起保存，再发起流式请求。待恢复的原始请求体保存在当前标签页的 `sessionStorage` 中，按登录账号和会话隔离。刷新完整页面或重新打开同一标签页里的助手抽屉，都可以找回这条记录。成功、主动停止并得到确认、或明确选择“编辑为新消息”后清除。若浏览器禁止会话存储，当前页面仍可重试，刷新后需通过会话历史查看已保存的结果。

页面收到完整的 `message.done` 帧才结束流式展示。中途断网、缺少结束帧或刷新后，页面用原标识查询状态。浏览器不会根据相同文本推断两次发送属于同一轮。

| 查询结果 | 用户看到的行为 |
| --- | --- |
| `in_progress` | 显示原请求仍在处理，按 1、2、4、8 秒的间隔查询，此后每 8 秒查询一次。切换会话会停止当前页面的查询。 |
| `completed` | 从服务器重读会话消息和待确认操作，替换本地预览。原回答保留已存储的时间、资料链接和上下文详情入口。 |
| `retryable` 或带 `chat_request_not_found` 的 404 | 显示原文与“重试原消息”。点击后发送同一个请求体和标识，包括原页面上下文。“编辑为新消息”会恢复编辑，下一次发送分配新标识。 |
| `interrupted` | 展示服务器已保存的会话与待确认操作，并按状态提示查看操作或长期记忆。这一轮已经产生持久化效果，页面结束本轮恢复。 |
| 状态接口或历史读取暂时失败 | 保留原请求并显示“检查状态”。点击或恢复联网时只读取状态和历史。 |

“停止生成”会中止浏览器连接，并在未完成的请求上先保存停止意图。若服务器已提交，页面仍显示已保存的回答。若原请求可重新执行，页面结束这次发送。刷新页面也遵守该停止意图。之后主动发送是新一轮，即使问题文字完全相同。

## 服务端约定

旧客户端可继续使用 `POST /api/chat/sessions/{session_id}/stream`。需要恢复的客户端应提供 `client_request_id`。它允许 1 至 128 位 ASCII 字母、数字及 `._:-`。服务器在用户库和会话内匹配标识，并核对规范化的消息和页面上下文。同一标识与不同内容组合会返回 409 `idempotency_conflict`。

`GET /api/chat/sessions/{session_id}/requests/{client_request_id}` 提供上述状态及可用的原 `message_id`。重复提交已完成的请求时，服务器可以从落库数据重放开始帧、原确认事件、回答正文以及终帧中的引用与用量。活动会话返回 409 `chat_in_progress`。已保存操作或记忆的中断轮返回 409 `chat_request_interrupted`。

恢复单位是一个已标识的请求。浏览器不续接丢失的 token 位置，服务器也无需重放每个流式分片。已完成轮通过历史或回放取回。若某次尝试既未提交回答也未保存操作或记忆，服务器可在取得会话锁后清理孤立用户消息，并按原扣费日期退回这次带标识请求的站内额度，允许同键重新尝试。供应商可能已处理过上一次输入，站内恢复无法撤销其已经发生的推理或计费。关闭标签页或清除浏览器存储后，可以按账号查看已提交的历史，但新标签页没有旧标签页的待恢复请求体。

## 无人重试时的对账

服务启动后，一个 worker 会检查已有账号库，此后每五分钟扫描一次仍处于预扣或生成中的请求。对账和生成竞争同一个会话锁，仍在生成的请求会被跳过。对于没有已提交结果或副作用的遗留请求，退款和状态更新在同一事务内完成，退款归还当初扣额的业务日。已经提交的答案及其额度保留。扫描只报告汇总数量。[对账入口](../interview_forge/ai/chat/recovery.py)

在网站目录执行 `python -m interview_forge.ai.chat.recovery` 可预览预计调整的数量。加入 `--apply` 会立即执行。独立进程应使用与服务相同的账号数据库和 `IF_RUNTIME_DIR`，以便识别正在生成的请求。生产服务当前使用单主机多 worker。

## DeepSeek 官方示例的参考范围

DeepSeek 于 2026 年 11 月 13 日更新的 `deepseek-ai/chat-demo` 是浏览器直连 API 的静态客户端，使用 IndexedDB 存储会话。以下对应源码固定在 v0.1.1 的提交 `5d5dd75`。[官方仓库](https://github.com/deepseek-ai/chat-demo) · [版本提交](https://github.com/deepseek-ai/chat-demo/commit/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c)

- 其 SSE 解码器保留跨分片的 UTF-8 和换行状态，支持多行 `data`，丢弃缺少空行分隔的末尾事件。消息层把缺少 `message_stop` 的 EOF 标为中断。本站采用同样的帧边界原则，并用服务端记录判断原请求结果。[SSE 解码器](https://github.com/deepseek-ai/chat-demo/blob/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c/src/services/api/sse.ts#L27-L55) · [消息流](https://github.com/deepseek-ai/chat-demo/blob/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c/src/services/api/client.ts#L159-L188)
- 示例按会话维护生成状态，重开时会将未结束的本地回复标为停止。它只在特定附件失效且尚未收到内容时进行有限退避重试。本站存在账号配额、记忆与确认操作，刷新后先查服务端状态，再决定是否显示原请求的重试入口。[重新载入](https://github.com/deepseek-ai/chat-demo/blob/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c/src/services/chat/store.ts#L272-L289) · [停止与重试](https://github.com/deepseek-ai/chat-demo/blob/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c/src/services/chat/store.ts#L1036-L1072)
- 示例从当前分支中选取有可用回复的问题与回答组成历史，并在快照变化时写入提醒。本站由服务器组装历史。浏览器只固定本轮提交的原页面上下文，使重试不受后来滚动、选区或切页影响。[历史轮次与上下文](https://github.com/deepseek-ai/chat-demo/blob/5d5dd754ebc1948e977ddb880a9eb5aa25f37b4c/src/services/chat/reply.ts#L286-L328)
