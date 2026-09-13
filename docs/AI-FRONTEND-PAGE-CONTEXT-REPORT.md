# InterviewForge AI Frontend + Page Context 验收报告

## 1. Final SHA

本报告在提交前生成，最终 SHA 以 Git commit 为准。

## 2. Frontend Bugs Fixed

- Tool 状态名称统一优先使用服务端 `display_name`；`tool.start` 会为当前行保存标签，`tool.done` / `tool.error` 不再退化为“工具信息”。
- Stop Generation 取消后会重新读取当前会话，移除未持久化的临时用户消息和 assistant 气泡。
- provider error、SSE error、网络失败结束后会重新加载当前会话，避免前端显示与数据库历史不一致。
- 完整 AI 页面和嵌入式抽屉复用同一份 `assets/ai-assistant.js`，没有复制第二套 Chat、SSE、Tool 或 Action 实现。

## 3. Global AI Launcher

通过 FastAPI 静态 HTML 注入与现有构建器统一接入：

- 中控台、Hot 100 专题页、Hot 100 题解页、学习书架首页、模块页、章节页、学习记录、力扣连接、指南及其他登录后学习页面都会加载统一 AI Launcher。
- 书架和阅读页由 `scripts/build/build_library.py` / `scripts/build/build_html_site.py` 生成共享资源引用；书架构建器同步产出 `library/assets/` 下的 AI 公共资源。
- AI 助手完整页面、登录、注册和管理后台明确排除 Launcher；AI 助手页本身保留完整两栏界面。
- 未登录时 Launcher 通过 `/api/me` 静默隐藏。
- 点击 `✦ AI` 打开右侧同源 iframe 抽屉；可关闭并留在原页面，也可在新标签页打开完整 AI 页面。

## 4. Page Context Contract

新增 `interview_forge/ai/chat/page_context.py`，允许字段为：

| 字段 | 限制 |
| --- | --- |
| `path` | 必填，最多 512 字符 |
| `title` | 必填，最多 200 字符 |
| `page_type` | `problem`、`library/chapter`、`cockpit`、`history`、`leetcode`、`guide`、`other` |
| `problem_id` | 正整数 |
| `content_id` | 最多 200 字符 |
| `heading` | 最多 300 字符 |
| `selected_text` | 最多 2000 字符 |

未知字段以及 cookie、token、user_id、db_path、任意 metadata 等字段会被拒绝。所有字段由服务器重新规范化，超长文本裁剪。旧请求 `{\"message\": \"...\"}` 完全保持兼容。

## 5. Context Pipeline

```text
浏览器 location/title/当前 heading/选中文本
        ↓
assets/ai-page-context.js
        ↓  page_context（有界 JSON）
POST /api/chat/sessions/{id}/stream
        ↓
PageContext.from_payload()
        ↓
PageContextProvider → ContextBlock(key=current_page, priority=85)
        ↓
ContextBuilder → LLM
```

当前页上下文仅保存到本轮 user message 的 `metadata_json.page_context`，不保存完整网页正文，不将历史每轮 page context 重新注入。题解页能提供题号，章节页能提供 bounded `content_id`。

## 6. Embedded / Full UI

- `/pages/ai-assistant.html`：完整页面，保留会话列表、记忆入口和完整聊天布局。
- `/pages/ai-assistant.html?embedded=1`：同一页面进入抽屉模式，隐藏页面级标题、返回链接和会话侧栏，复用同一 Chat 实现。
- 父页面与 iframe 仅通过同源 `postMessage` 交换当前 page context；只接受 `event.origin === location.origin`。
- 抽屉打开、滚动、文本选择变化和发送前都会刷新当前页面上下文。

## 7. Tests

- Page Context normalization：正常题解上下文、长度裁剪、未知字段/敏感字段拒绝、ContextBlock 生成。
- Chat stream：旧请求兼容、新 page context 进入 ContextBuilder、规范化 metadata 持久化、未知字段 400。
- Current page / Tool UI：当前题号上下文、M7 Tool display name、stop/error reload、Action UI、heartbeat 解析兼容。
- Launcher integration：静态 HTML 注入、登录/管理员/完整 AI 页面排除、生成书架页不重复注入。
- 定向 AI 测试：`42 passed, 8 subtests passed`。
- `python -m compileall -q interview_forge tests scripts/build`：通过。
- Node `--check`：三个 AI 前端脚本通过。
- `python tools/build_hot100.py`：通过，重建 100 个题解页、135 个阅读页、37 个书架模块 / 736 个章节。
- `python tools/check_hot100.py`：通过，`broken_links=0, errors=0, warnings=0`。
- 全量 pytest：258 passed、25 个子断言通过；另有 1 个既有 Admin V2 文案契约失败，本轮按要求未修改 Admin V2。

## 8. Changed Files

- `interview_forge/ai/chat/page_context.py`
- `interview_forge/ai/chat/service.py`
- `interview_forge/ai/chat/tool_orchestrator.py`
- `interview_forge/api/routers/chat.py`
- `interview_forge/api/routers/static.py`
- `assets/ai-page-context.js`
- `assets/ai-launcher.js`
- `assets/ai-launcher.css`
- `assets/ai-assistant.js`
- `assets/ai-assistant.css`
- `pages/ai-assistant.html`
- `scripts/build/build_library.py`
- `scripts/build/build_html_site.py`
- 生成后的学习页面及 `library/assets/` AI 公共资源
- Page Context、Launcher、前端同步相关测试

本轮未部署 VPS，未开发新的 Tool、Memory 或 RAG，也未改变 M1–M7 后端架构。
