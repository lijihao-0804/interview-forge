# LangChain 框架面试题

## 你了解过哪些 AI Agent 开发框架？

👔面试官：你了解过哪些 AI Agent 开发框架？

🙋‍♂️我：了解过 LangChain、LangGraph、LlamaIndex、CrewAI、AutoGen……反正都是封装大模型和工具调用的，用哪个都差不多。

👔面试官：只会报名字不算了解。它们解决的问题、抽象层次和适用场景都不同，怎么会差不多？

🙋‍♂️我：那 LangChain 生态最大，所有项目都使用 LangChain，复杂流程多写几个 Chain 就行。

👔面试官：复杂的有状态流程还只想到 Chain？LangGraph 为什么会出现？LlamaIndex 又为什么长期强调数据和上下文增强？

🙋‍♂️我：那我多背几个框架名称和 GitHub Star，面试时全部说一遍，应该就显得了解得比较全面。

👔面试官：框架名称说得多，不等于理解得深。你应该围绕项目难点说明为什么选，而不是拿热度和名词数量代替技术判断。

发现没有，这道题看似在考你知道多少框架，其实面试官更想听到的是：你是否真正理解主流框架的定位，能不能根据业务问题完成技术选型。

### 💡 简要回答

我重点了解过 LangChain、LangGraph 和 LlamaIndex。

LangChain 提供模型、Prompt、工具、Agent 和中间件等通用抽象，集成范围比较广，适合快速构建工具调用、RAG、SQL 查询等 AI 应用。

LangGraph 更偏底层的状态与流程编排。面对循环、分支、并行、断点恢复和人工审批等复杂流程时，可以使用图结构显式控制 Agent 的执行路径。现在 LangChain 的 Agent 也运行在 LangGraph 之上，因此二者更多是上下层关系，而不是互相替代的竞争关系。

LlamaIndex 的优势集中在数据接入、文档解析、索引和检索，适合企业知识库、文档问答和复杂 RAG 等数据密集型应用。

除此之外，我也了解 OpenAI Agents SDK 和 CrewAI。前者适合以 OpenAI 模型为主的轻量 Agent，后者擅长使用角色和任务表达多 Agent 协作。不过在通用 Python Agent 开发岗位中，我会优先掌握 LangChain、LangGraph 和 LlamaIndex，再根据公司的技术栈补充其他框架。

### 📝 详细解析

#### Agent 框架解决了什么？

假设不用任何框架，自己实现一个能查询资料、调用接口并记住上下文的 Agent，需要做多少事情？

你需要接入模型、定义工具协议、实现 Agent 循环，并把工具结果重新交给模型。此外，还要处理状态、重试、超时、流式输出、人工确认和运行追踪。完成一次演示并不难，真正困难的是系统执行十几步后能否恢复，以及出错时能否快速定位问题。

Agent 框架会把这些重复工程抽象成可复用组件。不过，不同框架选择的重点并不相同：LangChain 偏通用组件和快速集成，LangGraph 偏状态与流程控制，LlamaIndex 偏数据与检索。

![](../images/6f954d117d4d58b60c33cf33.png)

所以，回答这道题时不要只比较谁更强，而要说清楚在什么业务约束下，哪个框架更合适。

#### 为什么重点看 LangChain？

LangChain 的定位已经不只是早期的「把多个 Prompt 串成 Chain」。它提供模型、消息、Prompt、工具、结构化输出、中间件和 Agent 等通用抽象，并集成了大量模型供应商、向量数据库和外部工具。

它最大的价值是集成范围广、开发速度快。例如，我们需要切换不同模型，接入搜索、数据库或 MCP 工具，快速实现 RAG Agent、SQL Agent 或客服助手时，LangChain 可以减少大量协议适配和样板代码。

不过，LangChain 的高层抽象更适合常见 Agent 模式。当业务出现复杂循环、精细分支、长时间暂停和断点恢复时，就需要进一步使用 LangGraph 控制执行流程。

#### LangGraph 和 LangChain 是什么关系？

LangGraph 使用 `State + Node + Edge` 表达 Agent 工作流：State 保存共享状态，Node 负责执行模型或工具，Edge 决定下一步运行哪个节点。

它重点解决的是循环、条件分支、并行执行、持久化、暂停恢复和人工介入等问题。

例如，一个报销 Agent 必须先读取单据，再进行合规检查；金额超过限制时暂停并等待主管审批；审批通过后才能调用付款工具。这类流程使用图结构表达，会比把所有逻辑塞进一个 Agent 循环更加清晰。

现在 LangChain 的 Agent 高层接口运行在 LangGraph 之上。可以把 LangChain 理解为常用组件和预制路线，把 LangGraph 理解为支撑这些路线的道路系统：简单 Agent 优先使用 LangChain；需要精细控制时，再下沉到 LangGraph。

![](../images/d972efc665bd21024c7349af.png)

因此，面试时不要把 LangChain 和 LangGraph 简单说成两个互相替代的框架。二者既有职责差异，也经常组合使用。

#### LlamaIndex 强在哪里？

很多人把 LlamaIndex 简单理解成「另一个 LangChain」，这会忽略它最有辨识度的能力。

LlamaIndex 更强调在私有数据之上构建 AI 应用。它长期积累了数据连接、文档解析、切分、索引、检索、重排、Query Engine 和结构化数据访问等能力，也可以把 RAG Pipeline 封装为 Agent 使用的工具。

当需求是让 Agent 查询企业知识库时，真正困难的往往不是实现工具调用循环。资料进入系统时，PDF 表格要正确解析，多种数据源要统一接入，文档还要切分并建立索引。

用户开始提问后，系统又要过滤和重排召回结果，并确保不同用户只能看到自己有权访问的数据。可以发现，问题是沿着整条数据链路逐步出现的，而不是多注册一个搜索工具就能解决。

这些问题正是 LlamaIndex 更擅长的方向。因此，它尤其适合企业知识库、文档 Agent、研究助手和复杂 RAG 系统。

![](../images/9ef4e04e7a9c8c3d91ed4031.png)

LlamaIndex 也提供 Agent、Memory、多 Agent Pattern 和 Workflow，所以它并不只是 RAG 工具。不过从选型角度看，LangChain 的入口更偏通用 Agent 组装，LlamaIndex 的优势更集中在数据密集型应用。

#### 三个框架怎么配合？

LangChain、LangGraph 和 LlamaIndex 并不一定三选一。一个企业知识库 Agent 可以先用 LlamaIndex 处理文档、建立索引并提供检索结果，再把这项检索能力包装成 Tool，交给 LangChain Agent 决定何时调用。

如果外围还存在查询改写、答案校验、人工审核和失败恢复，就让 LangGraph 负责这些步骤如何衔接。这样三者分别解决数据、Agent 组装和流程控制问题，而不是在同一层重复造轮子。

![](../images/dadc72d10a8b4e62fa231d0e.png)

是否需要同时引入三者，取决于项目复杂度。如果只是简单工具调用，不必为了技术栈完整而引入 LlamaIndex；如果只是普通知识库问答，也不一定需要复杂的 LangGraph 工作流。

#### 其他框架要了解吗？

除了上面三个框架，还可以简单了解 OpenAI Agents SDK 和 CrewAI，但不必在通用 Python Agent 面试中平均分配准备时间。

**OpenAI Agents SDK** 围绕 Agent、Runner、Tools、Handoffs、Guardrails、Sessions 和 Tracing 提供一套相对轻量的开发方式。它适合以 OpenAI 模型和接口为主，希望快速实现客服分流、语音助手或工具 Agent 的团队。

**CrewAI** 使用角色、目标、任务和团队表达多 Agent 协作，并通过 Flow 管理状态、条件和事件。它适合研究报告、内容生产和多角色审核等容易映射为团队分工的场景，但角色越多也意味着更高的调用成本和协作不确定性。

![](../images/ff09302f7f4cea28461a0377.png)

AutoGen、Semantic Kernel 和 Microsoft Agent Framework 更偏微软生态或存量项目。对于通用 Python Agent 岗位，可以知道它们的定位，不需要在这道题中详细展开。Dify 则更接近低代码 AI 应用开发平台，也不宜和 Python Agent 框架放在同一层面重点比较。

#### 到底该怎么选？

选框架前，先别急着比较功能数量，而要把问题从外到内收窄。

最外层先判断任务是否真的需要 Agent。如果步骤固定、规则明确，普通函数或工作流通常更便宜、更稳定。把本来能写成 `if/else` 的流程交给模型自由决定，只会平白增加不确定性。

确认需要 Agent 后，再找项目真正困难的那一层。模型和工具接入最费力，LangChain 更自然；难点集中在私有数据、文档解析和检索质量，LlamaIndex 更贴近问题；业务路径包含复杂分支、循环和状态恢复，才轮到 LangGraph 发挥优势。

这时还不能马上结束选型，因为 Demo 能跑和系统能上线是两回事。流程越长，越要继续追问：中断后能否恢复，敏感动作是否需要审批，重复执行会不会产生副作用，不同用户的数据能否隔离，出错后是否留有完整轨迹。真正决定框架是否合适的，往往正是这些原型阶段看不见的生产约束。

| 框架 | 核心定位 | 更适合的场景 | 掌握程度 |
| --- | --- | --- | --- |
| LangChain | 通用模型、工具和 Agent 抽象 | 工具型 Agent、RAG Agent、SQL Agent | 重点掌握 |
| LangGraph | 有状态的图式流程编排 | 循环分支、暂停恢复、人工审批 | 重点掌握 |
| LlamaIndex | 数据接入、索引和检索 | 企业知识库、文档 Agent、复杂 RAG | 重点掌握 |
| OpenAI Agents SDK | OpenAI 技术栈下的轻量 Agent SDK | 客服分流、语音助手、工具 Agent | 了解并按需深入 |
| CrewAI | 角色化多 Agent 协作 | 研究、内容生产、多角色审核 | 了解并按需深入 |

### 🎯 面试总结

面试时，不需要一口气罗列十几个框架。框架说得越多，面试官越可能继续追问，而没有实际使用经验的框架很容易暴露出只是听过名字。

更稳妥的回答方式是围绕 LangChain、LangGraph 和 LlamaIndex 展开：LangChain 偏通用组件与快速集成，LangGraph 偏有状态流程编排，LlamaIndex 偏数据接入与检索。然后再补充自己对 OpenAI Agents SDK、CrewAI 等框架有所了解。

最后，一定要把框架特点落到真实场景：简单 Agent 为什么选择 LangChain，复杂审批流程为什么使用 LangGraph，企业知识库为什么考虑 LlamaIndex。能讲清楚「什么场景为什么选」，比单纯记住框架名称更有说服力。

### 📚 参考资料

本文框架定位核对时间为 2026 年 8 月 2 日，优先参考官方文档，并结合 AI 应用开发岗位的招聘要求：

- [LangChain 官方概览](https://docs.langchain.com/oss/python/langchain/overview)
- [LangGraph 官方概览](https://docs.langchain.com/oss/python/langgraph/overview)
- [LlamaIndex Framework 官方文档](https://developers.llamaindex.ai/python/framework/)
- [OpenAI Agents SDK 官方文档](https://openai.github.io/openai-agents-python/agents/)
- [CrewAI 官方介绍](https://docs.crewai.com/en/introduction)
- [AutoGen 官方仓库与维护状态说明](https://github.com/microsoft/autogen)
- [大模型应用开发工程师招聘要求示例](https://www.nowcoder.com/jobs/detail/434226)
- [重庆市渝中区急需紧缺人才需求目录](https://www.cqyz.gov.cn/bm_229/qrlsbj/zwxx_97154/dt/202604/P020260429566664462212.pdf)

---

## 使用 LangChain 构建 Agent 的核心步骤是什么？

👔面试官：如果让你用 LangChain 构建一个完整的 AI Agent，你会怎么做？

🙋‍♂️我：选择一个大模型，写好 Prompt，再接几个工具就完成了。

👔面试官：那只是能运行的 Demo。任务边界、工具权限、状态恢复、结构化输出和测试监控怎么办？

🙋‍♂️我：可以使用 `AgentExecutor`，网上很多示例都是这么写的。

👔面试官：那是旧版常见路径。LangChain v1 新项目应该从 `create_agent` 开始，并理解它底层的 LangGraph 运行时。

🙋‍♂️我：那把模型和工具传给 `create_agent`，本地能回答一次问题，应该就可以上线了。

👔面试官：能跑通不等于完整。状态怎么恢复，危险工具怎么审批，调用轨迹怎么测试，线上错误又怎么定位？

这道题考察的不是几行初始化代码，而是你能否把 Agent 从需求定义一直做到可测试、可观测和可上线。

### 💡 简要回答

我通常分七步构建 LangChain Agent。

第一，明确任务边界，包括 Agent 能做什么、不能做什么、何时结束，以及什么结果算成功。

第二，选择支持所需工具调用和结构化输出能力的模型，并把数据库、搜索和业务 API 封装为职责单一、Schema 清晰的 Tools。

第三，使用 `system_prompt` 约束角色、工具使用规则和失败策略；如果结果还要交给程序处理，则使用 `response_format` 定义结构化输出。

第四，通过 `create_agent` 组装模型、工具、提示词和输出格式。它底层使用 LangGraph，在模型判断、工具执行和工具结果回传之间循环。

第五，补充状态与安全能力。使用 Checkpointer 按 `thread_id` 保存当前线程状态，使用 Store 管理跨线程信息，通过 Middleware 添加重试、摘要、权限控制和人工审批。

第六，根据场景选择同步、异步或流式调用，并设置超时、并发和取消策略。

第七，先单测 Tool，再测试 Agent 的工具选择与调用轨迹，最后通过 Trace 观察模型调用、工具参数、耗时、Token 和异常。

### 📝 详细解析

#### 什么才算完整 Agent？

模型成功调用一次天气工具，只能说明 Demo 跑通了。真正进入业务后，我们先要知道它能做什么、不能做什么；模型选中工具后，还要检查参数是否正确，失败或重复调用会不会带来副作用。

流程跑得更久时，新的问题又会出现：会话中断后能否恢复，最终结果能否稳定进入业务系统，线上出错后能不能复现？因此，完整 Agent 不是一次模型调用，而是一条从任务设计、能力接入、运行控制走到测试监控的工程链路。

![](../images/dcb3014c9ed4b06b98f1b728.png)

#### 第一步：明确任务边界

构建 Agent 的第一步不是选择模型，而是定义任务。

例如订单客服 Agent 可以查询订单和解释物流状态，但不能自行退款；订单不存在、身份验证失败或用户要求高风险操作时，必须转人工。最终输出需要包含答复、订单状态和是否转人工。

怎么把边界说清楚？先定义 Agent 的目标和允许执行的动作，再划出禁止动作与权限边界。接下来还要约定什么算成功、什么算失败、什么时候停止，以及哪些情况必须转人工。

这些答案会继续决定后面的工具、Prompt 和测试用例。边界一旦模糊，模型就只能猜测什么行为算正确，后面再精细的工程配置也补不回来。

#### 第二步：选择模型与 Tools

模型需要支持项目所需的工具调用、结构化输出和上下文长度。模型负责判断和规划，真正访问数据库、搜索资料、发送消息的动作应该由 Tool 执行。

Tool 为什么要尽量小而清楚？因为模型主要依靠名称、描述和参数 Schema 来判断能不能调用。一个工具同时负责查询、退款和通知，模型就更容易选错动作；参数没有类型与范围约束，运行时也很难拦住错误输入。

所以，Tool 应先做到职责单一、名称清楚、输入输出容易理解。到了执行阶段，服务端还要重新检查身份与权限；只要工具会修改外部状态，就必须补上幂等和审计。前一层帮助模型「选对」，后一层保证系统「做得安全」。

```python
from langchain.tools import tool


# 装饰器会把函数名、docstring 和类型注解转换成工具说明
@tool
def lookup_order(order_id: str) -> dict[str, str]:
    """根据订单号查询订单状态，只读，不修改订单。"""
    # 真实项目应在这里调用经过身份校验的订单服务
    return {"order_id": order_id, "status": "已发货"}
```

工具描述中的「只读」很重要。模型会根据名称、描述和 Schema 选择工具，业务服务则负责真正的权限控制。Prompt 中写「禁止退款」，不能替代退款接口本身的身份校验。

![](../images/b611deef5bd4b17d03aac849.png)

#### 第三步：约束行为与输出

`system_prompt` 应说明角色、目标、信息边界、工具规则和失败策略。例如：回答订单状态前必须查询工具，不能猜测数据库中不存在的信息，高风险请求必须转人工。

如果输出只供人阅读，自然语言即可；如果结果还要进入前端、工单或后续工作流，应该定义结构化输出：

```python
from pydantic import BaseModel, Field


class SupportReply(BaseModel):
    # response_format 会按这三个字段校验 Agent 的最终结果
    answer: str = Field(description="给用户的简洁答复")
    order_status: str | None = Field(default=None, description="订单状态")
    needs_human: bool = Field(description="是否需要转人工")
```

结构化输出可以约束字段和类型，但不能保证业务事实正确。事实仍必须来自可信工具，权限仍必须由业务服务控制。

#### 第四步：组装 Agent

LangChain v1 推荐使用 `create_agent`：

```python
from langchain.agents import create_agent


# 将模型、工具、行为约束和输出 Schema 组装成 Agent
agent = create_agent(
    model="openai:gpt-5.4-mini",
    tools=[lookup_order],
    system_prompt=(
        "你是订单客服。回答订单状态前必须调用查询工具；"
        "不得猜测，无法处理时设置转人工。"
    ),
    response_format=SupportReply,
)

# messages 是 Agent State 的默认输入字段
result = agent.invoke({
    "messages": [{"role": "user", "content": "订单 A100 到哪了？"}]
})

# 结构化结果已经通过 SupportReply 的字段校验
reply: SupportReply = result["structured_response"]
```

底层执行流程是：

```text
用户消息 -> 模型判断
模型判断 -> 工具调用 -> ToolMessage -> 模型继续判断
模型判断 -> 最终结果（没有工具调用）
```

模型没有工具调用时，Agent 输出最终结果；模型请求工具时，LangGraph 运行时执行工具并把结果写回消息状态，再让模型继续判断。

![](../images/18e9c47df5e5f480c98e5872.png)

旧资料中的 `create_tool_calling_agent` 和 `AgentExecutor` 仍可能出现在存量项目中，但 LangChain v1 新项目应优先使用 `create_agent`。

#### 第五步：补齐状态与安全

Agent 能跑通之后，还要处理状态、故障和高风险动作。

短期状态通常保存在 Agent State 中。配置 Checkpointer 并稳定传入 `thread_id` 后，同一线程可以续接之前的消息和执行状态，流程中断后也有机会恢复。

跨线程的用户偏好或长期事实则放入 Store，通过 namespace 和 key 隔离不同租户与用户。Checkpointer 和 Store 的作用不同，不能因为二者都能落盘就混为一谈。

接下来，重试、摘要、权限和审批应该写在哪里？它们往往会同时影响多个模型或工具调用，如果散落在每个节点中，规则很快就会重复。Middleware 就是用来承接这类横切逻辑的。

例如，模型或只读工具临时失败时，可以在调用周围做有上限的重试；上下文过长时，可以在模型调用前压缩历史；用户权限变化时，可以动态隐藏工具。遇到敏感动作，Middleware 还能在工具执行前暂停等待审批，并在模型输出后补充格式或安全检查。

![](../images/cad31da6c986d668474f4062.png)

付款、发邮件、删除数据等工具必须具备幂等、最小权限和审计能力。自动重试不能导致重复扣款或重复发信。

#### 第六步：选择调用方式

调用方式需要与产品形态匹配：

| 调用方式 | 适用场景 |
| --- | --- |
| `invoke` | 短任务、后台任务、等待最终结果 |
| 异步调用 | 并发 I/O、异步 Web 服务 |
| `stream` | 长任务，需要展示 Token、步骤或工具进度 |

流式输出改善的是等待体验，并不会自动缩短工具执行时间。超时、取消、并发限制和缓存仍要单独设计。

#### 第七步：测试与监控

Agent 输出具有概率性，所以测试不能只比较最终文本。

第一层测试 Tool。检查正常输入、非法参数、权限错误、超时和幂等性。Tool 是相对确定的业务代码，应该优先做到稳定。

第二层测试 Agent 轨迹。检查是否选择正确工具、参数是否正确、是否发生越权调用，以及结构化输出是否符合 Schema。

第三层做端到端评测和线上监控。把典型问题、边界案例和历史故障整理成数据集，对比模型、Prompt 和 Tool 版本；上线后通过 Trace 观察模型调用、工具调用、延迟、Token、失败率和人工转接率。

![](../images/671c431ae1a30f968871fd3d.png)

#### 上线前检查什么？

上线前可以快速检查：

1. 任务和停止条件是否明确。
2. Tool 是否职责单一，并在服务端校验权限。
3. 有副作用的操作是否具备幂等和审批。
4. Checkpointer 与 Store 是否使用持久化实现并做好用户隔离。
5. 是否设置超时、重试上限、并发和成本预算。
6. 是否覆盖工具、轨迹和端到端评测。
7. 是否能够追踪一次失败运行的完整调用链。

### 🎯 面试总结

用 LangChain 构建完整 Agent，可以沿着「边界、能力、约束、组装、状态、交互、验证」回答。

先明确 Agent 的目标、权限和停止条件；再选择模型，把外部能力封装成 Schema 清晰、职责单一的 Tools；通过 `system_prompt` 约束行为，通过 `response_format` 固定业务输出；随后使用 `create_agent` 组装，底层由 LangGraph 管理模型与工具之间的循环。

工程上还要配置 Checkpointer 和 Store，使用 Middleware 加入重试、摘要、权限控制和人工审批，并根据产品需要选择同步、异步或流式调用。最后既要测试最终结果，也要测试工具轨迹，并通过 Trace 持续观察线上行为。

能把这七步讲清楚，说明你构建的不是一个只能演示的 Agent，而是一个有边界、有状态、可测试、可观测的业务系统。

### 📚 参考资料

- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain 官方文档：Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [LangChain 官方文档：Structured Output](https://docs.langchain.com/oss/python/langchain/structured-output)
- [LangChain 官方文档：Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [LangChain 官方文档：Short-term Memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangChain 官方文档：Long-term Memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [LangChain 官方文档：Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [LangChain 官方文档：Agent Evals](https://docs.langchain.com/oss/python/langchain/test/evals)
- [LangSmith 官方文档：Observability](https://docs.langchain.com/oss/python/langchain/observability)
- [LangChain 官方文档：v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)

---

## 请你谈谈对 LangChain 中核心概念「Chain」的理解，以及它的核心作用与设计理念。

👔面试官：你怎么理解 LangChain 里的 Chain？

🙋‍♂️我：Chain 就是把 Prompt 和大模型连起来，先拼提示词，再让模型回答。

👔面试官：这只能算最简单的一条链。检索器、输出解析器、自定义函数能不能进 Chain？一个步骤的输出又怎么交给下一个步骤？

🙋‍♂️我：那就都塞进 `LLMChain`，复杂一点再套一个 `SequentialChain`，LangChain 主要就是靠这些 Chain 类来编排。

👔面试官：你这个答案停在旧版本了。LangChain v1 已经把这些旧式 Chain 移到 `langchain-classic`，新代码还应该这么写吗？

🙋‍♂️我：应该改用 LCEL，用 `|` 把步骤连起来。不过 `|` 可能只是让代码短一点，本质上还是按顺序调几个函数吧。

👔面试官：又漏了一层。LCEL 组合出来的是 Runnable，整条链会获得统一的同步、异步、批处理、流式调用和配置能力。那 Chain、Runnable、LCEL 三者到底是什么关系？

这道题真正考的不是会不会写一个 `|`，而是能不能讲清楚 LangChain 为什么要把一堆零散组件变成一条可组合、可执行、可观测的数据流水线。

### 💡 简要回答

我理解的 Chain，不是某一个固定的类，而是一种应用编排思路：把 Prompt、模型、检索器、输出解析器和自定义逻辑等步骤，按照明确的数据流连接起来，让上一步的输出成为下一步的输入，最终形成一个可以整体执行的流程。

在现在的 LangChain 里，Chain 最重要的技术基础是 `Runnable`。每个步骤都尽量遵守统一的输入输出和执行接口，再通过 LCEL 的 `|` 做串行组合，或者通过字典、`RunnableParallel` 做并行组合。

组合后的整条 Chain 本身仍然是 Runnable，所以可以继续嵌套，也能统一使用 `invoke`、`ainvoke`、`batch` 和 `stream` 等能力。

它的核心设计理念是「组合优于堆积封装」。开发者只关注每一步做什么、数据怎么流动，框架负责把执行方式、配置、重试、回退和追踪等通用能力接到整条流程上。

需要注意版本边界。`LLMChain`、`SequentialChain` 属于旧式 Chain API，LangChain v1 已把这类能力移入 `langchain-classic`，适合维护旧项目，不应再作为新项目的首选写法。

确定性的线性或分支流程可以用 Runnable 和 LCEL，Agent 让模型在运行时动态决定下一步；带循环、持久状态和人工审批的复杂工作流，则更适合用 LangGraph。

### 📝 详细解析

#### 为什么需要 Chain？

假设我们要做一个最简单的商品评价分类功能。完整过程不是只调用一次模型，而是要先清洗用户输入，再把变量填进 Prompt，调用模型，最后把模型返回的消息解析成业务需要的字符串。

如果全部手写，代码里很快就会出现一堆胶水逻辑：这个函数返回字符串，下一个函数却要消息对象；同步调用写一套，异步调用再写一套；想加流式输出、批处理、重试和链路追踪，又得分别改造每一步。

步骤只有三个时还能忍，等流程变成「问题改写 -> 检索 -> 文档整理 -> Prompt -> 模型 -> 结构化解析」，维护起来就像拿很多根散落的电线临时接出一台机器。每加一个零件，都要重新确认接口能不能接上。

Chain 解决的就是这个问题。它先让每个零件暴露相对统一的插口，再把它们按照数据流接成一台完整机器。调用方不用逐个驱动内部步骤，只需要给整条链输入，再从整条链拿输出。

![](../images/11c53681d8d267f8cdf87b77.png)

所以，从业务视角看，Chain 是「把多个处理步骤串成一个完整任务」；从软件设计视角看，它是在做数据流编排和组件组合。

#### Chain 只能线性执行吗？

很多林友看到 Chain 这个单词，会自然地把它理解成从左到右的一根直线。这个直觉只对了一半。

最简单的 Chain 确实是线性的，例如：

![](../images/bce58aa5d960b291eec6b043.png)

```text
用户输入 -> Prompt 模板 -> Chat Model -> 输出解析器 -> 字符串答案
```

但真实应用还可能出现并行分支。比如用户问题一边送去知识库检索，一边原样保留下来，等检索结束后再把「问题」和「上下文」汇合到 Prompt。它也可能根据分类结果走不同分支。

因此，更准确的理解是：Chain 描述了一张事先确定好的数据流图。节点负责处理数据，连接关系决定数据往哪里走。即使某个节点内部调用了生成结果不完全确定的 LLM，流程拓扑本身仍然是开发者提前写好的。

这也解释了 Chain 和 Agent 最容易混淆的地方。Chain 通常由开发者决定「下一步调用谁」，Agent 则让模型根据当前状态动态决定「下一步做什么工具、是否继续循环」。一个偏确定性编排，一个偏运行时决策。

#### Runnable 解决了什么？

理解了 Chain 是数据流，接下来就有一个关键问题：Prompt、模型、检索器和解析器明明不是同一种东西，为什么能接在一起？

答案就是 Runnable。

不要急着背定义，可以把 Runnable 想成 LangChain 给不同组件定的一份「电器插头标准」。组件内部怎么工作可以不同，但只要遵守这份标准，就能被统一调用，也能继续和其他组件组合。

按照当前 `langchain-core` 的官方参考，Runnable 是一个可以调用、批处理、流式处理、转换和组合的工作单元。处理单个输入时使用 `invoke` 或 `ainvoke`，输入变成一批时，接口自然对应为 `batch` 或 `abatch`。

如果产品需要边生成边展示，可以使用 `stream` 或 `astream`，但前提是内部组件真正支持流式处理。执行方式统一以后，`with_config`、`with_retry` 和 `with_fallbacks` 才能继续在同一抽象上附加配置、重试和降级能力。

这里最巧妙的地方是「组合后的结果仍然是 Runnable」。两个组件接成一条小链后，这条小链又可以作为一个普通步骤接到更大的链里。就像乐高积木，两个小块拼成一辆小车，小车还可以继续成为整座城市的一部分。

![](../images/c6e3ec77486460bc379e6d92.png)

Runnable 还暴露输入、输出和配置的 schema，并允许通过 `config` 携带标签、元数据等信息。这些能力让框架更容易检查数据契约，也方便 LangSmith 之类的追踪系统识别整条调用链里的父子运行关系。

不过别把 Runnable 理解成魔法。前一个步骤输出什么类型，后一个步骤就必须能够接住什么类型。`ChatPromptTemplate` 通常接收字典，Chat Model 接收格式化后的 Prompt Value 或消息，`StrOutputParser` 接收模型消息并输出字符串。类型接不上，链照样会在运行时报错。

#### LCEL 不只是语法糖

LCEL 全称是 LangChain Expression Language。它最显眼的写法，是用 `|` 把 Runnable 接起来。

为什么用一个符号值得单独起名字？因为这不是普通的 Python 管道，也不只是一颗语法糖。`prompt | model | parser` 声明的是三个 Runnable 的组合关系，LangChain 会据此构造一个 `RunnableSequence`。在这个序列里，前一步的输出会作为后一步的输入。

![](../images/f1ca9fa71673b0ccec78d180.png)

下面用当前推荐方式写一条可以直接理解的链：

```python
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Prompt 本身就是 Runnable，输入是包含 product 和 review 的字典
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是商品评价分类助手，只回答 positive、neutral 或 negative。",
        ),
        ("human", "商品：{product}\n评价：{review}"),
    ]
)

# 使用 LangChain v1 提供的统一模型初始化入口
# 运行前需要安装对应 Provider 包并配置 OPENAI_API_KEY
model = init_chat_model("openai:gpt-5.5", temperature=0)

# LCEL 会把三个步骤组合为 RunnableSequence
# 数据依次经过 Prompt -> 模型 -> 字符串解析器
chain = prompt | model | StrOutputParser()

# 整条 chain 仍然是 Runnable，可以通过统一接口执行
result = chain.invoke(
    {
        "product": "机械键盘",
        "review": "手感不错，但空格键声音有点大。",
    }
)
print(result)
```

这段代码里，`chain` 不是执行结果，而是一份已经组装好的「可执行流程」。只有调用 `invoke` 时，数据才真正从左向右流动。

如果要异步调用，不用重写内部流程，只需要改成 `await chain.ainvoke(...)`。批量处理可以调用 `chain.batch([...])`，流式输出可以遍历 `chain.stream(...)`。这种统一执行方式，才是 LCEL 比手写函数嵌套更有价值的地方。

不过，流式能力有一个容易被说得太满的细节。

`RunnableSequence` 会尽量保留各组件的流式能力，但如果中间某个组件不支持流式转换，输出就要等它完成后才能继续流出。例如普通 `RunnableLambda` 默认不实现流式转换，把它放错位置就可能推迟首个输出块。

#### 如何并行与汇合？

真实的 RAG 链为什么也能用 LCEL 表达？关键是 Runnable 不只支持串行，还支持并行。

比如同一篇文章，我们既想让模型生成摘要，又想让模型给出标题。两个任务互不依赖，没必要先后等待。可以使用 `RunnableParallel` 把同一个输入同时送到两条子链：

![](../images/69e4fc50a401ee8c43e2c7d0.png)

```python
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableParallel

model = init_chat_model("openai:gpt-5.5", temperature=0)
parser = StrOutputParser()

# 两个分支接收相同的输入字典，但分别执行不同任务
summary_chain = (
    ChatPromptTemplate.from_template("用两句话总结这篇文章：\n{article}")
    | model
    | parser
)
title_chain = (
    ChatPromptTemplate.from_template("为这篇文章起一个简洁标题：\n{article}")
    | model
    | parser
)

# 并行运行两个子链，最后把结果汇合成一个字典
chain = RunnableParallel(
    summary=summary_chain,
    title=title_chain,
)

result = chain.invoke({"article": "这里放待处理的文章正文"})
print(result["title"])
print(result["summary"])
```

`RunnableSequence` 解决「先做 A，再做 B」，`RunnableParallel` 解决「把相同输入同时交给 A 和 B」。二者组合起来，就能表达不少固定流程。

在 LCEL 里，字典也可以在组合上下文中被自动转换为 `RunnableParallel`。不过面试讲原理时，建议先说清楚显式类名，再补充字典简写。这样面试官能确认你知道背后真正生成了什么，而不是只记住了一个看起来很酷的写法。

#### 为什么统一协议能不断扩展？

如果面试官继续问「为什么 LangChain 要这么设计」，只说方便串起来还不够。真正值得理解的是，一套统一协议如何让小流程逐渐长成大流程。

![](../images/5d88edd0ec4c410dd84e2032.png)

起点是可组合。每个步骤只处理自己的输入和输出，小链可以继续组成大链。开发者能够替换某个模型、解析器或检索器，而不必推翻整条业务流程，这就降低了组件之间的耦合。

但组件只是能接在一起还不够。如果每种组件都有完全不同的调用方式，组合只能停留在表面。Runnable 继续把单次、异步、批量和流式等执行方式收拢到统一接口上，组合后的流程才有机会继承这些能力。当然，最终效果仍取决于内部组件是否真正支持对应模式。

接口统一后，LCEL 才能进一步把代码写成声明式数据流。开发者主要表达「数据先去哪，再去哪」，不用把线程调度、回调传递和中间结果搬运混在业务逻辑里，读代码时也能直接看出流程结构。

有了清楚的流程结构，重试、回退、标签、元数据和追踪这类横切能力就能复用，不需要每个业务函数各写一遍。它们可以附着在某个 Runnable，也可以作用于整条链。生产环境排查问题时，我们看到的不再只是最终报错，而是这次运行究竟经过了哪些子步骤。

#### 为什么弃用旧式 Chain？

这一段是现在面试最容易踩的版本坑。

早期 LangChain 提供了大量面向具体场景的类。`LLMChain` 常用于封装 Prompt 加模型，`SequentialChain` 用于把多条旧式 Chain 顺序连接。它们在老项目和老教程里非常常见，所以很多人会误以为这就是今天的标准答案。

![](../images/74a0af34567dcf998038d162.png)

但框架后来遇到了一个问题：专用 Chain 类越来越多，每个类的输入字段、返回结构和扩展方式不完全一致。开发者既要记住大量类名，又很难把它们自由拼装。

Runnable 和 LCEL 的方向，是把重心从「为每个场景造一个专用类」转向「提供少量统一原语，让开发者自己组合」。`LLMChain(prompt=prompt, llm=model)` 能做的事情，现在通常直接写成 `prompt | model | parser`，数据流更清楚，组合能力也更一致。

截至 2026 年 7 月，LangChain v1 迁移指南已经把旧式 chains 明确移到 `langchain-classic`，其中包括 `LLMChain`、`ConversationChain` 和 `SequentialChain` 等旧 API。

它们不是突然不能运行了。维护旧系统时仍可以安装兼容包，但新项目不应该因为看到旧教程，就继续把这些旧式 Chain 当成首选。

因此，看到老代码里的 `LLMChain` 和 `SequentialChain`，我们要能读懂它们过去解决了什么问题；真正写新代码时，则优先使用 Runnable 与 LCEL 表达固定数据流。

如果下一步由模型动态决定，就从 LangChain v1 的 `create_agent` 开始。等流程的核心难点变成循环、持久状态、暂停恢复或人工审批，再进一步使用 LangGraph。这个选择顺序比背一组新旧类名更重要。

#### 三种编排方式怎么选？

Chain 好用，是不是所有流程都应该塞进一条超长 LCEL？当然不是。

如果步骤和数据流在编码时就能确定，比如文本清洗、检索增强问答、分类后解析，Runnable 和 LCEL 通常很合适。它们结构直接，调用方式统一，也容易追踪。

如果下一步取决于模型的动态判断，例如模型要自己选择搜索、计算器还是数据库工具，并可能重复多轮，问题就从「固定数据流」变成了「Agent 循环」。在 LangChain v1 中，官方推荐用 `create_agent` 构建标准 Agent，这套 Agent 架构运行在 LangGraph 之上。

如果我们还要精确控制循环、分支、状态持久化、失败恢复和人工介入，那就进一步使用 LangGraph 的底层图编排能力。LangGraph 并不是为了取代每一条简单 Chain，而是处理 Chain 难以清楚表达的长时、有状态工作流。

可以用一个判断方法：开发前就知道下一步去哪里，优先考虑 Chain；运行时要由模型决定下一步，考虑 Agent；流程需要显式状态图和恢复能力，考虑 LangGraph。

#### 哪些理解容易走偏？

最容易出现的偏差，是把 Chain 缩小成「一次 LLM 调用」或某个具体的 `LLMChain` 类。一次模型调用只能算流程中的一个节点，旧类也只是早期实现。今天谈 Chain，重点应该放在如何用 Runnable 组织完整数据流，再补充旧 API 的迁移状态。

理解了这一点，就不会把 `|` 当成自动修好一切的魔法。LCEL 负责组合，却不会猜测业务语义。上一步输出与下一步输入不匹配时，仍要用 `RunnableLambda`、`RunnablePassthrough`、`itemgetter` 或显式转换函数整理数据。

同样，统一接口只代表调用方式一致，不代表内部组件天然拥有相同能力。某一步不支持流式转换，整条链的首个输出就可能被推迟；模型没有服务端批处理能力，调用 `batch` 也不会凭空获得最优性能。

最后再回到控制权。Chain 的连接关系通常由代码预先确定，Agent 的动作路径则可能由模型在运行中选择。二者可以组合，但不能因为都调用了模型，就把固定数据流和动态决策循环混为一谈。

### 🎯 面试总结

回到开头的问题，面试官问 Chain，不是想听一句「把 Prompt 和模型串起来」，也不是想让我们背 `LLMChain` 的构造参数。

一个完整的回答，应该先说 Chain 是确定性的数据流编排，把多个步骤组合成一个可以整体调用的流程。再往下落到现代实现，说明 Runnable 是统一执行与组合接口，LCEL 是声明组合关系的表达方式，`|` 通常生成 `RunnableSequence`，并行分支可以用 `RunnableParallel`。

接着点出它的设计价值：组件可以替换，小链可以继续嵌套，整条流程能共享同步、异步、批处理、流式、重试、回退和追踪等能力，同时也要承认类型适配与真实流式能力仍取决于具体组件。

最后一定补上版本意识。`LLMChain`、`SequentialChain` 已是 legacy chains，LangChain v1 将它们移入 `langchain-classic`。新项目写固定流程优先使用 Runnable 与 LCEL，动态工具决策使用 `create_agent`，复杂有状态编排再使用 LangGraph。

能把「Chain 是什么」「Runnable 怎么支撑它」「LCEL 为什么有价值」「旧 API 现在在哪里」这四层讲清楚，这道题就不只是会用框架，而是真正理解了它的设计。

### 📚 参考资料

- [LangChain v1 官方概览](https://docs.langchain.com/oss/python/langchain/overview)：核对 v1 当前定位、`create_agent` 与 LangGraph 的关系。
- [LangChain v1 官方迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)：核对主包命名空间收缩，以及 legacy chains 移入 `langchain-classic` 的现状。
- [Runnable 官方 API 参考](https://reference.langchain.com/python/langchain-core/runnables/base/Runnable)：核对统一执行接口、schema、配置与组合能力。
- [RunnableSequence 官方 API 参考](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableSequence)：核对 `|`、串行执行、批处理及流式传播条件。
- [LangChain Core Runnables 官方参考](https://reference.langchain.com/python/langchain-core/runnables)：核对 `RunnableParallel`、`RunnableLambda` 等现行组合原语。

---

## Deep Research 的实现逻辑和适用场景是什么？

👔面试官：你了解 LangChain 生态里的 Deep Research 吗？

🙋‍♂️我：就是多搜索几次，再让模型生成一篇更长的报告。

👔面试官：搜索次数多不等于研究深入。研究范围如何确定？子课题如何拆分？资料冲突怎么办？什么时候停止？

🙋‍♂️我：可以让十个 Agent 每人写一章，最后拼起来，Agent 越多速度越快。

👔面试官：并行写章节容易重复和口径不一致。更合理的方式是并行收集独立子课题的证据，再由一个写作阶段统一综合。

🙋‍♂️我：那只要搜索结果里带了很多链接，最终报告应该就算可靠了。

👔面试官：链接多不代表证据可靠。来源是否独立、引用是否支持结论、冲突资料如何复核，这些才决定研究质量。

这道题真正考的是：你能否讲清研究型 Agent 如何动态规划、控制上下文、核验证据，以及多 Agent 会带来哪些成本和风险。

### 💡 简要回答

Deep Research 不是 LangChain 核心包里的一个固定开关，而是一类面向开放问题的研究型 Agent 架构。LangChain 团队提供了 `open_deep_research` 参考实现，也提供了更通用的 Deep Agents SDK；前者是具体研究应用，后者是通用 Agent 开发框架，不能混为一谈。

它的核心流程是：先澄清用户目标并生成 Research Brief，再由 Supervisor 把问题拆成相对独立的子课题。多个 Researcher 在隔离上下文中并行检索，并对来源进行筛选和压缩。

Supervisor 会检查证据是否覆盖研究目标，发现空白就继续补搜，最后再由统一的写作阶段综合证据并生成带引用的报告。

这种架构的价值不只是并行加速。子 Agent 可以隔离不同主题的上下文，避免大量搜索结果互相干扰；Supervisor 可以根据中间证据动态调整方向；统一写作则能减少章节重复和口径冲突。

它适合竞品分析、技术调研、文献综述和供应商尽调等开放式、多来源、可拆分任务，不适合一次搜索就能回答的简单事实，也不适合子任务高度依赖的强耦合工作。

生产环境必须限制并发、迭代、Token 和搜索预算，并对网页提示词注入、来源可信度和高风险结论进行人工复核。

### 📝 详细解析

#### Deep Research 是什么？

普通问答通常可以通过一次检索得到答案，而研究任务往往一开始就没有固定路径。例如，比较三家云厂商的 Agent 托管能力，需要分别查产品定位、价格、限制和区域差异，还要处理产品改名、资料过期和来源矛盾。

Deep Research 的关键不是「搜索很多次」，而是让系统围绕研究目标动态决定：下一步搜索什么、哪些问题可以并行、证据是否充分，以及何时停止。

理解了研究任务需要动态调整，生态里的几个名字就不难区分了。LangChain 提供模型、工具和 Agent 等高层积木，LangGraph 负责有状态流程如何编排和运行。

在这套基础之上，`open_deep_research` 展示了一套具体研究流程，而 Deep Agents 把规划、子 Agent 和上下文管理提炼成更通用的能力。

回答面试题时说明这层区别即可，不需要背诵每个托管产品和仓库实现。

#### 核心流程是什么？

一套典型的 Deep Research 流程可以拆成六步：

```text
澄清问题并确定范围
-> 生成 Research Brief
-> Supervisor 拆分子课题
-> Researcher 并行检索与核验
-> 压缩证据并检查研究缺口
-> 统一生成最终报告
```

第一步是范围澄清。用户只说「研究某家公司」时，系统需要确认是在关注投资价值、技术路线还是就业风险，否则后续搜索很容易跑偏。

第二步是形成 Research Brief。它把用户目标、研究维度、时间范围、来源要求和最终交付形式整理成稳定的成功标准。

第三步由 Supervisor 拆分子课题。只有相对独立的问题才适合并行，例如分别研究三家公司的定价；如果后一个问题依赖前一个结论，则应该串行执行。

第四步由 Researcher 多轮使用搜索、企业检索或 MCP 工具。每个研究员只处理一个主题，并保留来源信息。

第五步不是把所有网页原文塞回 Supervisor，而是压缩成带出处的关键证据。Supervisor 再检查 Brief 是否被覆盖，发现缺口或冲突时继续补搜。

最后由一个写作阶段统一组织论证、处理重复内容，并将事实、推断和不确定性分开表达。

![](../images/b96a7c407a06c161907556f1.png)

#### 为什么需要子 Agent？

如果一个 Agent 同时研究多个主题，搜索结果会不断占用同一个上下文。A 公司的价格、B 公司的安全文档和 C 公司的失败请求混在一起，模型反而更难关注当前证据。

所以，拆出子 Agent 首先是在隔离上下文。每个 Researcher 只处理一个子课题，最终只返回压缩后的结论和来源，主 Agent 不必背着全部搜索过程继续思考。

课题隔离以后，并行才成为自然结果。相互独立的研究任务可以同时执行，整体等待时间会下降；彼此依赖的任务却仍要按顺序完成。Agent 数量越多，模型调用、搜索费用、限流和协调成本也越高，因此不能为了并行而并行，关键仍是子课题能否独立推进。

![](../images/a0251d42f7b3035b3e294149.png)

为什么不让子 Agent 分别写报告章节？因为各章节可能重复背景、使用不同口径，甚至得出相互冲突的结论。并行搜证据、统一写报告，更容易保持全文一致性。

#### 如何保证研究质量？

研究报告很长、链接很多，并不代表质量高。判断质量时，可以沿着「来源 -> 证据 -> 结论」反向追查。

先看来源是否值得信。官方文档、论文、监管文件和一手资料通常更接近原始事实，多篇转载却可能都来自同一篇文章，不能因为链接数量多就当成交叉验证。

来源可靠以后，还要确认它真的支持当前结论。报告应把事实、推断和不确定性分开；遇到冲突时，继续追查发布时间、统计口径和原始出处，而不是挑一个最符合预期的答案。

如果结论仍不稳，就回到研究过程检查原因。搜索词是否漏掉关键限定，子课题是否重复，停止条件是否过早，工具失败后有没有换用有效来源，这些过程问题最终都会反映到证据质量上。

![](../images/b39e4780517a7b7d102f37f0.png)

评测时既要看最终答案，也要看研究轨迹、来源覆盖率、引用正确性、耗时和成本。通用 Benchmark 可以用于版本比较，但不能代替企业自己的业务数据集。

#### 如何控制成本和安全？

Deep Research 的成本同时受到「宽度」和「深度」影响。宽度是并行研究单元数量，深度是每个研究员和 Supervisor 最多迭代多少轮。

怎么控制这两个维度？先限制同时运行的研究单元，避免宽度无限扩大；再限制每个 Researcher 的工具调用次数和 Supervisor 的补搜轮数，避免深度失控。

单个分支有上限还不够，整项任务还要设置总 Token、搜索费用和超时预算。最后再补上失败重试、缓存、限流和取消策略，系统才知道什么时候继续、什么时候降级、什么时候停止。

网页和外部文档都是不可信输入，可能包含诱导 Agent 泄露密钥或执行危险操作的提示词注入。因此研究工具应优先只读，内部数据遵循最小权限，密钥不要暴露给搜索或沙箱环境，高风险操作必须人工审批并保留 Trace。

![](../images/ed55933712879682d0d018e1.png)

对于金融、医疗、法律和安全决策，Deep Research 只能辅助资料整理，不能因为报告带有引用就取消专家复核。

#### 哪些场景适合？

什么任务值得动用 Deep Research？先看问题是否开放到需要多轮搜索和动态调整方向。如果一次权威检索就能回答，复杂研究流程只会增加成本。

接着看任务能否拆出相对独立的子课题，否则并行 Researcher 会频繁等待和交换状态。最后还要看报告价值能不能覆盖多轮模型与搜索成本，三项都成立时才值得使用。

典型场景包括竞品分析、技术路线调研、文献综述、供应商尽调、政策影响研究，以及企业内部资料与公开信息的联合分析。

如果只是查询一个容易核验的实时事实，一次权威搜索更快、更便宜；如果多个子任务必须严格共享中间状态，强行并行只会增加冲突；如果数据源本身不可靠或没有访问权限，研究 Agent 也无法凭空得到正确答案。

### 🎯 面试总结

回答 Deep Research 时，先说明它是一类研究型 Agent 架构，而不是 LangChain 核心包中的一个开关。官方参考实现与通用 Deep Agents 框架定位不同，但它们都可以借助 LangChain 和 LangGraph 的模型、工具、状态与编排能力。

核心流程是「明确范围、生成 Brief、拆分子课题、并行检索、压缩核验、统一写作」。Supervisor 负责规划和补缺，Researcher 负责隔离上下文中的多轮搜证，最终由一个写作阶段综合报告。

最后要主动说明边界：它适合开放、多来源、可拆分且报告价值较高的任务；上线时必须控制并发、迭代、Token、搜索费用和提示词注入风险，并保留来源追溯与人工复核。

### 📚 参考资料

- [LangChain 官方博客：Open Deep Research](https://www.langchain.com/blog/open-deep-research)
- [LangChain 官方仓库：Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [LangChain 官方博客：Deep Agents](https://www.langchain.com/blog/deep-agents)
- [Deep Agents 官方文档：Overview](https://docs.langchain.com/oss/python/deepagents/overview)
- [Deep Agents 官方文档：Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- [Deep Agents 官方文档：Context Engineering](https://docs.langchain.com/oss/python/deepagents/context-engineering)
- [LangSmith 官方文档：Evaluation Approaches](https://docs.langchain.com/langsmith/evaluation-approaches)

---

## 请你谈谈 LangChain4j 这类 Java 生态的 LangChain 衍生框架，主要帮开发者解决了哪些核心问题？它的核心适用场景是什么？

👔面试官：LangChain4j 是什么？它主要解决了什么问题？

🙋‍♂️我：它就是 LangChain 官方做的 Java 版本，把 Python API 翻译成 Java，让 Java 程序员也能用 Chain。

👔面试官：这个定位就错了。LangChain4j 的 API、内部实现和发布节奏都独立于 Python LangChain，官方还特意强调它不是 Java 移植版。那它为什么仍然有价值？

🙋‍♂️我：因为它把 OpenAI 接口封装了一层，少写一点 HTTP 请求代码，换模型也只要改个地址。

👔面试官：只看到模型调用太浅了。`ChatModel`、`EmbeddingModel`、`EmbeddingStore` 是统一抽象，高层还有 AI Services、Tools、Chat Memory、RAG 和结构化输出。它到底怎样接住 Java 业务代码？

🙋‍♂️我：用注解定义一个接口，框架就会把所有事情自动做好，所以接入 LangChain4j 以后，模型切换、安全、记忆和生产监控都不用关心了。

👔面试官：框架减少的是重复胶水代码，不会消灭供应商差异，也不会替你承担权限、数据隔离、评测和运维责任。Guardrails 和部分可观测能力目前还是实验性功能，这些边界不说清楚，怎么做生产选型？

这道题真正考的不是你记住了多少类名，而是能不能说清「为什么 Java 项目需要这一层抽象，以及这一层抽象不能替你做什么」。

### 💡 简要回答

我会先纠正一个常见误区：LangChain4j 虽然名字受 LangChain 启发，但它不是 LangChain 官方的 Java 移植版，而是一套独立开发、按照 Java 习惯设计的开源 LLM 应用框架。

它主要解决三类问题。第一类是供应商 API 不统一，框架通过 `ChatModel`、`EmbeddingModel`、`EmbeddingStore` 等接口，把常见模型和向量库接到相对一致的 Java API 上。

第二类是 LLM 应用胶水代码太多。AI Services 可以像 Spring Data JPA 一样声明 Java 接口，再把 Prompt、输出解析、Tools、Chat Memory 和 RAG 组装起来。

第三类是 Java 工程接入成本。官方生态能融入 Spring Boot、Quarkus、Helidon 和 Micronaut，复用依赖注入、配置、测试和监控体系。

它最适合已有 Java 技术栈，要做企业知识库问答、智能客服、文档抽取、内容生成，或者让模型调用现有 Java 服务的团队。特别是业务已经沉淀在 Spring Boot 或 Quarkus 中时，不必为了增加 AI 能力再单独维护一套 Python 服务。

不过我不会说用了它就能无成本切换所有模型。不同厂商在工具调用、JSON Schema、多模态和流式能力上仍然有差异，Chat Memory 也不等于完整聊天记录，复杂长事务仍需业务系统或专门编排层兜底。

选型时还要看模块成熟度。官方目前仍有带 beta 后缀的模块，Guardrails 和 AI Service Observability 也标注为实验性。

### 📝 详细解析

#### 它是 LangChain 的 Java 版吗？

看到「LangChain4j」这个名字，很多林友会自然地把它理解成「LangChain for Java」。可如果我们真按这个思路回答，第一句话就可能踩雷。

官方的定位很明确：LangChain4j 是从 Java 习惯出发设计的 JVM 开源库，重视类型安全、POJO、注解、接口和依赖注入。

它的 API、内部实现和发布周期都独立于 Python LangChain。因此，更准确的说法是「它吸收了 LLM 应用生态中的通用模式」，而不是「逐项复刻 LangChain」。

![](../images/b6cc711e96da9493b6c24c92.png)

这个区别为什么重要？因为它解释了 LangChain4j 最有辨识度的能力为什么叫 AI Services。Java 开发者熟悉的是接口、类型和服务层，而不是在业务代码里到处拼消息数组和 JSON。LangChain4j 选择顺着 Java 的思维方式，把一次 AI 能力包装成一个可调用的服务接口。

可以把这两层理解成「自己组零件」和「直接调用装修好的服务台」。需要精细控制时，我们可以在低层直接操作模型、消息、Embedding 和存储；更关心业务接口时，则在高层使用 AI Services，把这些零件组合起来。

截至 2026 年 7 月 31 日，官方文档也按这个思路组织框架。低层的代表抽象包括 `ChatModel`、`EmbeddingModel` 和 `ChatMemory`，高层的主入口则是 AI Services。

官方文档中的旧式 Chains 已明确标为 legacy。新项目不应因为框架名字里有 Chain，就把 `ConversationalChain` 当成主入口。

#### 统一接口能抹平所有差异吗？

假设公司今天试 OpenAI，明天因为数据合规改用云厂商模型，后天又要接本地 Ollama。若直接调用每一家 SDK，认证方式、请求对象、消息格式、流式回调和异常类型都不同，业务层很快会长满适配代码。

LangChain4j 先给这些能力找共同语言。聊天模型通常实现 `ChatModel` 或 `StreamingChatModel`，文本向量化使用 `EmbeddingModel`，向量数据的写入和搜索面向 `EmbeddingStore`。具体厂商能力放进独立集成模块，业务代码尽量依赖核心接口。

![](../images/9675f36040b3eea3b87b7348.png)

这样做最大的收益不是「一行代码切换任意模型」，而是把变化关在适配层里。单元测试可以替换模型实现，试验不同向量库时也不用推翻上层 RAG 流程。

但为什么不能吹成完全无锁定？因为抽象只能覆盖交集。某个模型是否支持工具调用、原生 JSON Schema、图片输入、思考内容或特殊采样参数，仍要查官方能力矩阵。切换供应商后，Prompt 效果、Token 计算、限流、异常处理和评测基线也要重新验证。

#### AI Services 解决什么问题？

如果只做一次模型调用，手写几行 SDK 代码并不难。真正麻烦的是业务开始要求多轮对话、工具调用、知识检索和稳定字段以后，开发者要不断处理 Prompt 拼装、消息转换、模型循环和输出反序列化。

AI Services 正是为了收拢这些胶水代码。开发者声明一个 Java 接口，LangChain4j 在运行时提供代理实现。它很像 Spring Data JPA 或 Retrofit：我们描述「服务要暴露什么方法」，框架负责把方法参数变成消息，再把模型响应转换成方法返回值。

![](../images/40fa89e39375ee26e7377ea6.png)

下面这个例子把当前主线中的几个关键能力放到了一起。为了让代码聚焦结构，模型、向量库和持久化存储的具体 Bean 由项目配置提供。

```java
record SupportReply(
        @Description("给用户展示的中文答复") String answer,
        @Description("查到的订单状态，未查询时返回空字符串") String orderStatus,
        @Description("是否需要转人工") boolean needsHuman) {
}

interface SupportAssistant {

    @SystemMessage("""
            你是订单客服。涉及订单状态时必须调用查询工具，
            不得猜测系统中不存在的信息；高风险请求必须建议转人工。
            """)
    SupportReply chat(@MemoryId String conversationId,
                      @UserMessage String question);
}

final class OrderTools {

    private final OrderService orderService;

    OrderTools(OrderService orderService) {
        // 复用现有 Java 领域服务，不把数据库连接直接暴露给模型
        this.orderService = orderService;
    }

    @Tool("根据订单号查询订单状态，只读，不执行退款或修改")
    String findOrder(@P("订单号") String orderId) {
        // 真正的鉴权、租户隔离和审计仍应由业务服务完成
        return orderService.findStatus(orderId);
    }
}

// 向量库中的文档应已在离线流程完成切分、向量化和写入
ContentRetriever retriever = EmbeddingStoreContentRetriever.builder()
        .embeddingStore(embeddingStore)
        .embeddingModel(embeddingModel)
        .maxResults(5)
        .minScore(0.75)
        .build();

SupportAssistant assistant = AiServices.builder(SupportAssistant.class)
        .chatModel(chatModel)
        .tools(new OrderTools(orderService))
        .contentRetriever(retriever)
        .chatMemoryProvider(memoryId -> MessageWindowChatMemory.builder()
                .id(memoryId)
                .maxMessages(20)
                // 生产环境可接自定义 ChatMemoryStore 持久化当前记忆窗口
                .chatMemoryStore(chatMemoryStore)
                .build())
        .build();

SupportReply reply = assistant.chat("conversation-1001", "订单 A1024 到哪了？");
```

这段代码是怎么跑起来的？入口只有一句 `assistant.chat()`，背后却串起了一条完整链路。

AI Service 代理先把方法参数组织成消息，Retriever 再补充知识库内容。模型如果判断需要查询订单，就调用 `OrderTools`；工具结果返回后，模型继续生成答案。`MemoryProvider` 用会话 ID 隔离上下文，最后框架把模型输出转换成 `SupportReply`。

这里有一个时效性细节值得单独提醒。AI Service 返回 `record` 或 POJO 时，LangChain4j 可以自动生成 Schema 并解析响应。

如果想使用模型供应商原生的 JSON Schema 约束，还要确认对应 `ChatModel` 支持并显式启用相关能力。模型不支持时，框架可能退回到 Prompt 格式指令，这种方式的可靠性更弱。

即使反序列化成功，也只说明数据形状能对上，不代表金额、权限和订单状态一定符合业务规则。确定性的业务校验仍然不能交给模型。

依赖版本也不要在多处手填。官方推荐通过 `langchain4j-bom` 管理模块版本，再从官方 Release Notes 选择经过验证的版本。这样可以避免核心包、模型集成和 Spring Starter 版本互相错位。

#### Tools 如何连接业务动作？

Tools 最容易被误解成「把数据库权限交给模型」。其实模型只负责生成工具名和参数，请求执行某个动作，真正运行 Java 方法的是应用程序。

LangChain4j 可以通过 `@Tool` 暴露对象方法，也支持在运行时提供工具。框架会把工具说明和参数 Schema 发给模型，再执行模型选择的 Java 方法，并把结果作为工具消息交回模型。

一次 AI Service 调用中可能发生多轮「模型 -> 工具 -> 模型」，直到拿到最终结果。理解了这条循环，就能明白模型负责提出调用请求，Java 应用才负责真正执行。

![](../images/21e68a16ac49c44420abecf6.png)

这层自动循环确实省代码，但安全边界不能省。查订单要做用户与租户校验，退款要有幂等和额度控制，发消息要有审批与审计，工具异常也不应把堆栈、路径或敏感信息原样回传给模型。工具描述约束的是模型行为，服务端权限约束的才是真实能力。

#### Chat Memory 等于聊天档案吗？

多轮客服如果每次都把历史消息手工拼回请求，既麻烦又容易超过上下文窗口。LangChain4j 提供 `ChatMemory` 抽象，常用实现包括按消息数淘汰的 `MessageWindowChatMemory`，以及按 Token 窗口淘汰的 `TokenWindowChatMemory`。

这里必须分清 memory 和 history。Chat Memory 保存的是下一次要喂给模型的上下文，可以发生淘汰、压缩或注入；完整聊天记录则是产品实际展示和审计所需的事实记录。官方文档明确说明 LangChain4j 当前提供的是 memory，不替应用保存完整 history。

![](../images/a5eb73640e323e81f8cc0a78.png)

默认实现把消息放在内存中。需要持久化时，可以实现 `ChatMemoryStore` 接到数据库。

多用户场景则用 `@MemoryId` 和 `ChatMemoryProvider` 隔离会话，不能让所有用户共享同一个窗口。同一个 `MemoryId` 也不应被并发调用，否则可能破坏 Chat Memory，所以分布式并发控制仍是应用的责任。

如果业务说的「长期记忆」是用户偏好、历史事实或企业知识，通常应该把它结构化存入业务数据库，或者做成可检索知识再通过 RAG 注入，而不是无限增大消息窗口。

#### RAG 不只是连接向量库

企业项目常见的需求不是让模型闲聊，而是让它回答内部制度、产品手册和客户资料。LangChain4j 对此提供从文档加载、解析、切分、Embedding、向量存储，到在线检索和注入的一组组件。

简单知识库可以把一个检索器直接交给 AI Service，让它先找资料，再把结果交给模型。

当项目需要查询改写、多路检索、融合、重排和上下文注入时，再使用 `RetrievalAugmentor` 把这些阶段组合起来。底层来源也不只限于向量库，还可以是全文搜索、Web 搜索、知识图谱或业务数据库。

![](../images/d3b7a35d3791c581a0737ebe.png)

为什么这种封装对 Java 团队有用？因为数据加载、检索策略和模型调用可以继续留在同一套工程、配置和测试体系中。但框架只提供积木，文档质量、切分策略、召回率、权限过滤、引用溯源和离线评测仍决定最终效果。

#### Java 生态如何集成？

LangChain4j 的另一个核心价值，在于它不强迫 Java 团队另起炉灶。选哪种集成，先看团队原来用什么服务框架，而不是先背一遍支持列表。

已有 Spring Boot 服务时，最自然的做法是继续沿用它的配置、依赖注入和监控体系。Starter 可以自动创建常用 Bean，也能用 `@AiService` 声明 AI Service。接入或升级时，再根据项目的 Spring Boot 大版本选择对应依赖。

已有 Quarkus 服务时，则优先使用 Quarkus LangChain4j。它复用 LangChain4j 的核心抽象，再接入 Quarkus 的 CDI、构建期装配、原生镜像和开发工具，不是一套互不相干的新框架。

Helidon 和 Micronaut 也有对应集成，但普通面试回答不必展开版本和注解清单。除非岗位的技术栈明确使用它们，否则说清楚「优先沿用团队现有的依赖注入、配置和监控体系」就够了。

#### 可观测性与 Guardrails 的边界

一次客服回答错了，我们应该先看什么？不能只盯着最终文本，因为一次调用可能已经经过 RAG 检索、模型判断和工具执行。

排查时可以顺着调用链往下看：先检查送给模型的消息，再确认 Retriever 找回了什么，接着看 Tool 的参数与结果，最后确认输入输出校验是否拦住了异常内容。`ChatModelListener` 等监听入口，就是为了采集这些阶段的请求、响应、耗时和错误。

如果使用高层 AI Services，还可以把一次服务调用中的模型、工具和 Guardrail 事件串起来。Spring Boot 或 Quarkus 集成能继续把这些事件接入团队已有的指标与追踪系统，但这属于工程接入方式，不是面试时需要背诵的功能目录。

![](../images/08eff9d747dfb67c38474d9c.png)

Guardrails 用于在模型调用前后校验输入和输出，例如检测越界问题、Prompt Injection、格式错误或违反业务规则的回答。可是截至本文调研时间，官方仍把 Guardrails 和 AI Service Observability 标为实验性，而且它们只适用于 AI Services，不能直接套在低层 `ChatModel` 上。

还有一个更关键的边界：Guardrail 不是安全系统的替代品。Prompt Injection 检测可能漏报，输出校验也不能替代业务权限。认证、授权、数据隔离、资金风控和审计必须继续放在确定性的业务层。

#### 什么时候适合 LangChain4j？

如果团队已有大量 Java 服务，希望把 AI 能力嵌入现有系统，LangChain4j 很合适。典型场景包括企业知识库问答、带会话上下文的智能客服、从合同和简历中抽取结构化字段、批量摘要与分类、让模型查询订单或创建工单，以及需要在多个模型或向量库之间评估选型的项目。

它尤其适合「AI 是业务系统的一部分」的团队。领域服务、数据库访问、权限和审计已经写在 Java 中，直接把这些能力注册为受控 Tools，通常比新增一个 Python 微服务再跨语言调用更简单。

反过来，如果需求只是调用一家模型做一次文本生成，厂商官方 SDK 可能更轻，不必为了抽象而抽象。

如果项目深度依赖某家模型刚发布的专属能力，直接 SDK 往往更早暴露完整参数。如果要做跨小时运行、可暂停恢复、强事务补偿的复杂流程，也不能只依赖模型工具循环，还要结合工作流引擎、消息系统或图编排方案。

同类 Java 方案应该怎么选？关键还是看团队原有技术栈，而不是比较谁的组件名称更多。

如果团队以 Spring 为中心，希望统一遵循 Spring 的编程模型，可以重点比较 Spring AI。已经采用 Microsoft AI 技术栈的团队，可以评估 Semantic Kernel。Quarkus 项目则优先看 Quarkus LangChain4j，因为它与 Quarkus 的开发和部署体验结合得更深。

| 现状或目标 | 更值得优先评估的方案 |
| --- | --- |
| 已有普通 Java 项目，需要丰富的模型、Tools、Memory 和 RAG 组件 | LangChain4j |
| Spring Boot 是统一技术底座，希望沿用 Spring 官方抽象 | Spring AI，也可对比 LangChain4j Spring Boot Starter |
| Quarkus、原生镜像和 Dev Services 是核心诉求 | Quarkus LangChain4j |
| 深度绑定单一供应商最新专属能力 | 厂商官方 Java SDK |
| 长时间、可恢复、强确定性的业务流程 | 工作流引擎或图编排层，再组合 LLM 框架 |

选型时我会做一个小型真实 PoC，而不是只比功能清单。用同一批问题验证回答质量、工具参数准确率、结构化输出成功率、延迟、Token 成本、监控完整度和故障恢复，再决定框架。因为「支持某项功能」和「满足自己的生产要求」，中间还隔着业务数据与工程验证。

### 🎯 面试总结

回到开头的面试，第一句话要先把定位说准：LangChain4j 不是 Python LangChain 的官方 Java 移植，而是一套独立、遵循 Java 习惯的 JVM LLM 应用框架。

接着回答它解决什么问题。它用统一接口隔离常见模型和向量库差异，用 AI Services 把 Prompt、Tools、Chat Memory、RAG 和结构化输出组合成类型化 Java 服务，再通过 Spring Boot、Quarkus、Helidon、Micronaut 等集成降低工程接入成本。

然后给出场景。已有 Java 系统要做知识问答、智能客服、文档抽取、内容处理，或者让模型受控调用现有 Java 业务能力时，它很合适。

只调用一次单一模型时，官方 SDK 可能更轻；强依赖 Spring 编程模型时要对比 Spring AI；复杂的长事务和可靠工作流还需要专门编排与业务兜底。

最后主动说出边界会很加分：统一 API 不等于厂商能力完全一致，Chat Memory 不等于完整历史，Guardrails 不等于权限系统，实验性或 beta 模块上线前必须锁版本、做回归评测和可观测验证。能答到这一层，面试官才会相信你不是只跑过 Demo，而是真的做过 Java AI 工程选型。

### 📚 参考资料

本文依据截至 2026 年 7 月 31 日可见的官方资料整理，版本与实验性标记应在实际接入前再次核对：

- [LangChain4j 官方定位与架构](https://docs.langchain4j.dev/intro/)
- [LangChain4j 官方仓库](https://github.com/langchain4j/langchain4j)
- [AI Services 官方教程](https://docs.langchain4j.dev/tutorials/ai-services/)
- [Tools 官方教程](https://docs.langchain4j.dev/tutorials/tools/)
- [Chat Memory 官方教程](https://docs.langchain4j.dev/tutorials/chat-memory/)
- [RAG 官方教程](https://docs.langchain4j.dev/tutorials/rag/)
- [Structured Outputs 官方教程](https://docs.langchain4j.dev/tutorials/structured-outputs/)
- [Spring Boot 集成](https://docs.langchain4j.dev/tutorials/spring-boot-integration/)
- [Quarkus 集成](https://docs.langchain4j.dev/integrations/frameworks/quarkus/)
- [Helidon 集成](https://docs.langchain4j.dev/tutorials/helidon-integration/)
- [Observability 官方教程](https://docs.langchain4j.dev/tutorials/observability/)
- [Guardrails 官方教程](https://docs.langchain4j.dev/tutorials/guardrails/)
- [Spring AI 官方 API 概览](https://docs.spring.io/spring-ai/reference/api/index.html)
- [Semantic Kernel 官方概览](https://learn.microsoft.com/semantic-kernel/overview/?view=semantic-kernel-java)

---

## LangChain 的底层架构与实现原理是什么？

👔面试官：你了解 LangChain 吗？说说它的底层架构。

🙋‍♂️我：LangChain 就是把 Prompt、模型和解析器串成一条 Chain。

👔面试官：这只能解释早期最表面的用法。不同模型如何统一？工具结果怎样回到模型？Agent 的状态和循环又由谁管理？

🙋‍♂️我：底层应该就是一个 `while` 循环，模型要调用工具就执行，不调用就退出。

👔面试官：表面行为相似，但生产级 Agent 还需要状态、路由、持久化、中断恢复和人工介入。现在 `create_agent` 底层运行在 LangGraph 上，不能只理解成普通循环。

🙋‍♂️我：那我记住 `create_agent` 底层是 LangGraph，应该就算理解架构了。

👔面试官：还不够。Message、Tool、State、Context、Store 和 Middleware 分别负责什么，它们又怎样协作，才是架构题真正要讲清的内容。

这道题真正考察的是：你能否从一次 Agent 请求出发，讲清楚 LangChain 各层如何协作。

### 💡 简要回答

当前 LangChain v1 更像一套面向 Agent 的分层开发框架，而不只是将 Prompt 串起来的 Chain 工具。

底层的 `langchain-core` 定义 Message、Model、Tool 和 Runnable 等标准协议；不同模型厂商的独立集成包负责把自己的请求与响应适配到这些协议，因此应用层可以使用相对统一的方式切换模型和工具。

在执行层，Runnable 统一了组件的同步、异步、批处理和流式调用方式。对于步骤固定的流程，可以使用 LCEL 组合 Prompt、Model 和 Parser；对于需要模型自主选择工具的任务，则使用 `create_agent` 创建 Agent。

`create_agent` 会把模型节点和工具节点编译成 LangGraph 状态图。模型读取消息后生成 `AIMessage`；如果其中包含 `tool_calls`，运行时执行对应工具，并把结果包装成带相同调用 ID 的 `ToolMessage` 写回状态；模型再次读取工具结果并继续判断，直到生成最终回答。

在这套架构中，State 保存会变化的消息与业务状态，Runtime 提供可信上下文和长期 Store，Middleware 负责在模型或工具调用前后加入权限、重试、摘要与人工审批，LangGraph 则负责路由、检查点、暂停恢复和长时间运行。

一句话概括：LangChain 用标准协议统一组件，用 `create_agent` 提供高层 Agent 入口，再由 LangGraph 承担有状态的执行运行时。

### 📝 详细解析

#### LangChain 解决了什么？

直接调用一家模型厂商的 SDK 并不困难。真正的问题出现在应用逐渐复杂之后：不同厂商的消息格式、工具调用结构和流式响应各不相同，业务还需要接入 Prompt、工具、状态、重试和追踪。一旦更换模型，大量厂商专属字段可能已经散落在业务代码中。

LangChain 的核心思路是在这些差异之上定义稳定接口。厂商集成负责适配，应用只依赖公共协议，从而让模型、工具和运行时能够相对独立地演进。

#### 架构分成几层？

理解 LangChain v1，可以抓住下面四层：

| 层次 | 主要职责 | 典型对象 |
| --- | --- | --- |
| 核心协议层 | 统一组件的数据结构与调用接口 | Message、Runnable、Model、Tool |
| 集成适配层 | 屏蔽模型、向量库和外部服务差异 | `langchain-openai` 等独立集成包 |
| Agent 开发层 | 提供高层 Agent 组装与扩展能力 | `create_agent`、Middleware、Structured Output |
| 编排运行层 | 管理状态、循环、路由、持久化和恢复 | LangGraph Runtime |

可观测性贯穿各层，通过运行事件和 Trace 记录模型调用、工具调用、耗时和异常。

![](../images/4a73aaaabdb770dd7c690584.png)

这张图表达的是职责边界，不是严格的单向调用顺序。例如模型和编译后的 Agent 都遵循 Runnable 调用方式，但它们承担的架构角色不同。

#### 核心协议如何统一？

`langchain-core` 中最值得理解的不是类名数量，而是一条数据如何从用户走到模型，再进入业务系统。

这条链路先需要统一「传什么」。`HumanMessage` 表示用户输入，`AIMessage` 表示模型输出，`ToolMessage` 表示工具执行结果。不同厂商原本各有一套消息格式，适配成 Message 后，上层就不用跟着每家 SDK 反复改动。

只有消息还不能完成业务动作，于是 Tool 接住下一棒。模型看到的是工具名称、描述和参数 Schema，它只能提出「想调用哪个工具、参数是什么」。真正执行 Python 函数或外部服务的仍是应用程序，权限校验和副作用也必须留在这里。

当消息、模型和工具都要进入同一条流程时，又需要统一「怎么执行」。Runnable 提供 `invoke`、异步调用、批处理和流式输出等调用语义。对于步骤已经确定的流程，我们就能继续通过 LCEL 组合组件：

```python
# 三个组件都遵循 Runnable 协议，可以使用管道符顺序组合
chain = prompt | model | output_parser

# 组合后的整体仍然通过统一的 invoke 接口执行
result = chain.invoke({"question": "什么是 Agent？"})
```

这样看，Message 统一数据表达，Tool 划清模型与业务动作的边界，Runnable 再统一执行方式。三者连起来以后，LangChain 才不只是替换模型 SDK 的薄封装。

上面的 LCEL 流程每一步由开发者确定。Agent 则不同，它允许模型根据上下文决定是否调用工具以及下一步做什么。

#### Agent loop 如何运行？

Agent 的核心不是一次模型调用，而是模型和工具之间可能重复多轮的执行循环：

```text
HumanMessage -> Model -> AIMessage(tool_calls)
AIMessage(tool_calls) -> 最终回答（没有工具调用）
AIMessage(tool_calls) -> Tool Runtime（有工具调用）
Tool Runtime -> ToolMessage(tool_call_id) -> Model 再次判断
```

其中 `tool_call_id` 很重要。模型一轮可能请求多个工具，工具结果必须通过调用 ID 与原请求对应，模型才能知道每条结果属于哪次调用。

![](../images/28627103bab64c13877adf67.png)

`create_agent` 会根据模型、工具、系统提示词和中间件创建这套循环。它返回的不是普通函数，而是编译后的 LangGraph 图，因此能够在每一步保存状态、输出进度并决定下一条执行边。

#### 数据应该放在哪里？

Agent 中的数据不应该全部塞进消息或 Prompt。当前运行时会区分下面几类数据：

| 数据 | 作用 | 示例 |
| --- | --- | --- |
| State | 执行中不断变化的数据 | 消息、当前步骤、工具结果 |
| Context | 一次调用期间不变的可信依赖 | 用户 ID、租户、权限 |
| Store | 跨线程保存的数据 | 用户偏好、长期事实 |

![](../images/114386cbd17c3fc8139066a7.png)

这样划分的好处是，可信用户身份不需要让模型生成，数据库连接也不会被写入对话上下文。工具可以通过 Runtime 读取这些数据，同时只把真正需要模型填写的参数暴露在工具 Schema 中。

#### Middleware 做什么？

真实应用通常需要处理动态提示词、模型切换、工具筛选、重试、对话摘要、敏感信息和人工审批。如果把这些逻辑全部塞进 Prompt 或 Tool，代码会很快纠缠在一起。

Middleware 提供模型和工具调用前后的扩展点。请求进入模型前，可以根据用户身份生成系统提示词，或者在历史消息过长时先做摘要；模型决定调用工具后，可以先检查权限，敏感动作还可以暂停等待审批。

真正执行工具时，如果遇到临时网络故障，可以在这一层做有上限的重试。结果返回后，再补上格式或安全校验。这样，一次请求从进入模型到离开 Agent 的各个阶段都有清楚的扩展位置。

![](../images/4444448c64643abf484730b6.png)

Middleware 并不是另一套运行时。它会运行在 `create_agent` 编译出的 LangGraph 内部，对执行行为进行组合式扩展。

#### LangGraph 是什么角色？

如果只用 `while` 循环实现 Agent，进程退出后中间状态容易丢失，也很难在敏感工具前暂停几小时再继续。

LangGraph 将流程建模为 `State + Node + Edge`：State 保存状态，Node 执行模型或工具，Edge 决定下一步。检查点可以保存每一步状态，因此能够支持中断恢复、人工介入、故障恢复和长时间运行。

LangChain 与 LangGraph 不是简单的二选一关系。LangChain 提供高层组件和标准 Agent 架构，LangGraph 提供底层执行能力。简单 Agent 直接使用 `create_agent`，只有流程需要复杂分支、并行、审批或精细状态控制时，才需要直接编写 LangGraph。

#### 旧版 Chain 还能用吗？

早期教程常见的 `LLMChain`、`ConversationChain` 和部分旧式 Agent 执行器已经进入 `langchain-classic`。它们可以用于维护存量项目，但不再代表 LangChain v1 的主架构。

新项目可以按下面的边界选择：

| 场景 | 更合适的方式 |
| --- | --- |
| 固定的 Prompt、Model、Parser 流程 | Runnable + LCEL |
| 标准模型与工具循环 | `create_agent` |
| 复杂分支、并行、暂停恢复和人工审批 | 直接使用 LangGraph |
| 维护旧式 Chain 项目 | `langchain-classic` 后渐进迁移 |

### 🎯 面试总结

回答 LangChain 底层架构时，可以从一次请求的执行过程展开。

首先，`langchain-core` 使用 Message、Model、Tool 和 Runnable 等标准协议隔离厂商差异。用户消息进入 Agent State 后，模型生成 `AIMessage`；如果其中包含工具调用，LangGraph 会路由到工具节点，工具结果以带相同调用 ID 的 `ToolMessage` 写回状态，模型再继续判断，直到产生最终回答。

其次，要讲清数据和控制的职责：State 保存可变状态，Context 提供可信依赖，Store 保存跨线程数据，Middleware 负责权限、重试、摘要和人工审批，LangGraph 负责状态推进、路由、检查点与恢复。

最后补充版本边界：LangChain v1 的主线是「标准协议 + `create_agent` + LangGraph Runtime」；Runnable 与 LCEL 仍适合确定性流程，旧式 Chain 主要用于维护存量项目。

### 📚 参考资料

- [LangChain 官方文档：Overview](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain 官方文档：Messages](https://docs.langchain.com/oss/python/langchain/messages)
- [LangChain 官方文档：Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [LangChain 官方文档：Runtime](https://docs.langchain.com/oss/python/langchain/runtime)
- [LangChain 官方文档：Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [LangChain API Reference：Runnable](https://reference.langchain.com/python/langchain-core/runnables/base/Runnable)
- [LangGraph 官方文档：Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangChain 官方文档：v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)

---

## 请你详细说说 LangChain 和 LangGraph 的核心区别是什么？

👔面试官：你说说 LangChain 和 LangGraph 有什么区别？

🙋‍♂️我：LangChain 只能把步骤线性串起来，LangGraph 才能做分支和循环。

👔面试官：这句话早就不准确了。LCEL 有分支和并行能力，LangChain v1 的 `create_agent` 本身也是带条件和循环的图。你把「能不能分支」当成两者边界，说明你还停留在旧版教程里。

🙋‍♂️我：那 LangChain 负责开发，LangGraph 负责部署。需要持久化、流式输出和人工审批时，再把项目迁移到 LangGraph。

👔面试官：也不对。现在 LangChain Agent 就运行在 LangGraph 上，能直接使用检查点、流式输出和人工审批中间件，并不是用了 LangChain 就没有这些能力。

🙋‍♂️我：明白了，它们其实是一套东西，只是 LangGraph 换了一种图写法，选哪个都差不多。

👔面试官：又走到另一个极端了。底层运行时可以相同，但抽象层级、控制权和开发成本完全不同。标准工具调用 Agent 和跨多个业务阶段的长流程，当然不能用同一个粒度去设计。

这道题真正想考的，不是你能不能背出两个项目的功能列表，而是能不能说清「高层 Agent 框架」与「低层编排运行时」之间的关系。

### 💡 简要回答

我不会把 LangChain 和 LangGraph 理解成两个互相替代的竞品。按照当前官方定位，LangChain v1 是高层 Agent 开发框架，负责提供模型、工具、结构化输出和 middleware 等常用能力。

LangGraph 则是低层的 Agent 编排框架与运行时，让开发者直接设计状态、节点、路由、并行、中断和恢复。

两者最关键的关系是，LangChain v1 的 `create_agent` 构建在 LangGraph 之上，返回一个编译后的图。也就是说，LangChain Agent 不是脱离 LangGraph 运行的另一套引擎，它已经继承了 LangGraph 的状态、持久化、流式输出、durable execution 和 human-in-the-loop 等运行能力。

真正的区别不在于「有没有图」或「能不能分支」，而在于开发者控制哪一层。若需求是常见的「模型判断 -> 调用工具 -> 返回模型」循环，我会优先用 LangChain，再借助 middleware 做提示词、重试、护栏和审批等定制。

若业务需要显式控制多个阶段，让确定性步骤与 Agent 步骤混排，或者要处理复杂并行、长期暂停和多 Agent 协作，我会直接用 LangGraph。`create_agent` 生成的 Agent 仍然可以作为图中的节点或子图复用。

所以一句话概括：LangChain 帮我快速得到一个好用的 Agent，LangGraph 帮我精确控制整个 Agent 系统怎么运行。

### 📝 详细解析

#### 两者处于同一层吗？

很多林友第一次看到这两个名字，会自然地问「哪个功能更多」。可这个问题就像在比较一台咖啡机和它内部的控制系统，能列出差异，却很容易忽略两者是上下层关系。

先用一句人话理解：LangChain 给我们一套装好的 Agent，LangGraph 让我们自己设计整条业务路线。

截至 2026 年 7 月，官方也是按上下层来定位它们。LangChain 是高层 Agent 框架，提供模型、工具和常见的 Agent 循环；LangGraph 是更低层的编排框架与运行时，负责有状态流程如何执行、暂停和恢复。

LangGraph 可以使用 LangChain 的模型和工具组件，但并不强制依赖 LangChain，也可以直接接其他模型 SDK 或普通 Python 函数。

更关键的是，LangChain v1 的 `create_agent` 会构建一个基于 LangGraph 的图运行时。Agent 在模型节点和工具节点之间循环，直到模型给出最终答案或命中停止条件。因此正确的层次关系是：

`LangChain 高层 Agent API -> 编译后的 LangGraph -> 检查点、流式事件、中断与执行运行时`

![](../images/6740c8f108e30dfdef19662e.png)

这也解释了为什么两者既有重叠能力，又不能说「选哪个都一样」。用 LangChain 时，框架已经替你搭好了常见 Agent 的拓扑，你主要配置零件和生命周期钩子；用 LangGraph 时，节点怎么拆、状态怎么更新、下一步去哪，都由你来决定。

#### 核心差异：抽象层级

先把容易混淆的能力放进一张表里看，边界就清楚多了：

![](../images/f36e85955706fc51e16f4418.png)

| 对比维度 | LangChain v1 | LangGraph |
| --- | --- | --- |
| 官方定位 | 高层 Agent 开发框架 | 低层 Agent 编排框架与运行时 |
| 主要入口 | `create_agent`、模型、工具、middleware、结构化输出 | `StateGraph`、State、Node、Edge、`Command`、`Send`、Subgraph |
| 默认提供什么 | 预构建的模型与工具调用循环，以及常用扩展点 | 构建任意有状态工作流的编排原语，不替你规定 Prompt 或 Agent 架构 |
| 控制流 | 标准 Agent loop 已搭好，可通过 middleware 定制行为 | 开发者显式定义顺序、条件路由、循环、并行、动态分发和子图 |
| 状态 | 以 `AgentState` 和 `messages` 为默认核心，可扩展自定义字段 | 可设计完整 State Schema、输入输出 Schema、内部通道与 reducer |
| 持久化与记忆 | 通过底层 LangGraph 的 checkpointer 和 store 使用 | 直接在图编译和运行层控制 checkpointer、store、thread 与状态历史 |
| durable execution | 可以继承底层运行能力，标准 Agent 也能暂停和恢复 | 是核心定位之一，更适合显式设计长流程的恢复边界和副作用 |
| 人工介入 | 常用 `HumanInTheLoopMiddleware` 审批工具调用，也能组合自定义逻辑 | 可在任意节点内用 `interrupt()` 暂停，用 `Command(resume=...)` 恢复 |
| 流式输出 | 直接从 Agent 输出消息 token、步骤更新和自定义进度 | 除消息和状态外，还可观察 checkpoint、task、debug 等更底层事件 |
| 扩展方式 | middleware 钩住 Agent、模型和工具生命周期 | 节点、边、路由函数、`Command`、`Send`、子图和 Runtime |
| 部署与调试 | 可接 LangSmith tracing、Studio 和 Deployment | 使用同一套 LangSmith 能力，并能更直接查看节点路径和状态变化 |
| 更适合 | 标准工具调用 Agent、客服助手、数据查询助手、快速原型 | 长流程、多阶段审批、确定性与 Agent 混排、复杂并行、多 Agent 系统 |

注意表中的「持久化」「流式输出」「人工介入」都出现在两列，这不是写重复了，而是在强调一个很重要的事实：这些能力由 LangGraph 运行时提供，也能从 LangChain Agent 的高层接口中使用。两者差别主要是封装层级和控制粒度，不是简单的有或没有。

#### LangChain 只能线性执行吗？

为什么「LangChain 只能线性，LangGraph 才能分支」是错的？因为它混淆了三个不同概念。

先看传统 Chain。它并不等于只能顺序执行，LCEL 除了 `RunnableSequence`，也能通过并行和分支 Runnable 表达并发与条件选择。固定的 Prompt、模型、解析器流水线确实常写成线性形式，但那是用法选择，不是框架能力上限。

再看 LangChain v1 的 `create_agent`，它本身就不是一条直线。模型可能直接结束，也可能请求工具；工具执行后又会回到模型继续决策，这已经形成「条件路由 + 循环」。

多个工具调用还可能被并行执行。因此，拿一条早期 `prompt | model | parser` 管道去代表当前 LangChain Agent，并不公平。

真正拉开差异的，是 LangGraph 把业务拓扑变成一等公民。

比如先做权限校验，再让三个研究节点并行检索，之后汇总，金额高时转人工，失败时走补偿节点，最后等待次日任务继续。这时开发者需要明确看到每个节点、状态字段和路由条件，图编排的价值才真正体现出来。

所以更准确的边界应该是：LangChain 能表达分支和循环，但它的高层 Agent API 主要围绕通用模型与工具循环组织；LangGraph 则允许开发者直接拥有整个工作流的拓扑控制权。

#### Middleware 与图编排有何不同？

看到 middleware 能在模型和工具前后执行代码，有些林友又会问：既然 middleware 什么都能插，为什么还要 LangGraph？

关键要看我们是在「改造同一台机器」，还是「重新规划整条生产线」。

![](../images/6432c74b6f7e8909fc60e7d0.png)

LangChain middleware 很适合改造标准 Agent loop。例如，在模型调用前动态生成提示词、裁剪消息、选择模型和工具，在模型调用后做安全检查，或者给工具调用增加重试和人工审批。

这些逻辑都围绕 Agent、Model、Tool 的生命周期展开，不需要重新设计整张图。

LangGraph 节点和边处理的是更一般的流程结构。它可以让分类节点进入完全不同的子流程，让多个节点并行后再汇合，也可以把数据库写入、人工表单、规则引擎和一个完整 Agent 放在同一张图中。这里的每一步不一定是模型或工具调用，甚至可以完全不使用 LLM。

当前官方文档特别说明，middleware 不是独立运行时，它会运行在 `create_agent` 返回的编译图内部。这个完整 Agent 还可以作为节点或子图放进更大的 `StateGraph`，middleware 会跟着它一起工作。这正是两层组合，而不是二选一。

```python
from typing import Literal

from langchain.agents import AgentState, create_agent
from langgraph.graph import END, START, StateGraph


class WorkflowState(AgentState):
    # route 是外层业务流程状态，不属于标准 Agent loop 的固定字段
    route: Literal["research", "reject"]


def classify_request(state: WorkflowState) -> dict:
    # 这里用确定性规则演示路由，实际项目也可以调用分类模型
    text = str(state["messages"][-1].content)
    route = "reject" if "删除生产数据" in text else "research"
    return {"route": route}


def choose_route(state: WorkflowState) -> Literal["research_agent", "reject"]:
    # 条件边根据外层业务状态选择下一节点
    return "research_agent" if state["route"] == "research" else "reject"


def reject_request(state: WorkflowState) -> dict:
    # 确定性的拒绝节点不需要调用模型
    return {"messages": [{"role": "assistant", "content": "该操作不在允许范围内。"}]}


# research_model 和 search_tool 由项目按实际模型、搜索服务实现
# create_agent 返回编译后的 LangGraph，可直接嵌入外层图成为子图
research_agent = create_agent(
    model=research_model,
    tools=[search_tool],
)

builder = StateGraph(WorkflowState)
builder.add_node("classify", classify_request)
builder.add_node("research_agent", research_agent)
builder.add_node("reject", reject_request)
builder.add_edge(START, "classify")
builder.add_conditional_edges("classify", choose_route)
builder.add_edge("research_agent", END)
builder.add_edge("reject", END)

# 外层 LangGraph 管业务拓扑，内层 LangChain Agent 管模型与工具循环
workflow = builder.compile()
```

这段代码不是在把 LangChain「迁移」成 LangGraph，而是在正确分工。内部研究 Agent 继续享受高层抽象，外部业务流程则获得显式路由。真实项目还需要补上模型、工具、检查点和异常处理，这里只保留能说明层次关系的部分。

#### State：默认状态与自由建模

Agent 为什么需要状态？因为模型调用、工具结果、人工意见和中间产物不可能只靠函数局部变量一直传下去。两者都有状态，但使用姿势不同。

LangChain 为常见 Agent 准备了 `AgentState`，默认核心是 `messages`。用户消息、模型的工具调用、工具结果和最终回复都追加到这份状态中。业务还可以用 `TypedDict` 扩展额外字段，官方更推荐让相关 middleware 声明自己需要的状态，这样能力和数据不会散落在各处。

LangGraph 则让状态设计本身成为工作流架构的一部分。开发者可以定义整体 State，也可以区分输入、输出和内部 Schema。节点只返回局部更新，reducer 决定并行或多次更新如何合并。

为什么需要 reducer？假如多个研究节点同时写入 `evidence`，我们希望追加结果，而不是让后写入的结果覆盖前一份证据。因此，合并语义必须在 State 中提前定义。

![](../images/1417ebd2b6810686b4fefd35.png)

这不是说 LangChain 没有 State，因为它的 Agent State 就运行在 LangGraph 上。区别在于，用 LangChain 时通常接受一套为标准 Agent loop 设计好的状态骨架；直接使用 LangGraph 时，你要为整个业务工作流设计数据通道和更新规则，也因此拥有更大的自由度和责任。

#### 谁提供持久化与记忆？

这一部分是面试里最容易说错的地方。有人会回答「LangChain 管记忆，LangGraph 管持久化」，也有人会说「只有 LangGraph 才能断点恢复」。两种说法都把上下层拆散了。

当前 LangGraph 的持久化分成两套机制。Checkpointer 按 `thread_id` 保存图状态快照，适合线程内短期记忆、人工介入、时间旅行和故障恢复；Store 保存图状态之外、跨线程可读取的业务数据，适合用户偏好、事实和共享知识等长期记忆。

![](../images/95d7a5ce5c034803ccd56bfd.png)

LangChain 的 `create_agent` 会把 `checkpointer` 和 `store` 交给底层图，因此 LangChain Agent 同样可以获得短期记忆、长期记忆和恢复能力。使用 Agent Server 时，持久化基础设施还可以由服务端处理。

真正的差异在控制粒度：LangChain 给标准 Agent 暴露便利入口，LangGraph 让开发者在任意节点和子图层面设计状态保存与恢复边界。

durable execution 也不只是「把数据存进数据库」。一个长流程中途失败后，如果从头重跑发邮件、扣款等副作用，状态虽然保存了，业务仍可能出事故。

可靠恢复要求把非确定性操作和副作用放进可记录的任务边界，并保证可能重试的操作幂等。直接设计 LangGraph 时，这些边界会更显式；LangChain 标准 Agent 虽然能借用同一运行时，复杂业务副作用仍需要开发者认真建模。

#### 人工介入有什么区别？

如果需求是「模型想发送邮件时先让人确认」，LangChain 的 `HumanInTheLoopMiddleware` 已经非常合适。它可以在工具真正执行前暂停，然后接受批准、修改、拒绝或人工直接回复。

底层状态仍由 LangGraph 持久化，恢复时继续使用相同的 `thread_id`。

但如果人工节点不只是审批工具呢？比如理赔流程要展示中间材料，让审核员补充字段；营销流程要等一周后再继续；多位审核人要分别填写意见，随后根据票数路由。

这时，LangGraph 的 `interrupt()` 可以放在节点内部的任意业务位置，恢复时再把外部输入送回流程，更适合自定义人机协作。

因此，不能说 LangChain 没有 human-in-the-loop。准确说法是，LangChain 提供了围绕 Agent 工具调用的高层审批体验，LangGraph 提供了更通用的中断与恢复原语。前者用起来省事，后者表达范围更广。

#### 流式输出能看到多深？

用户界面逐字显示模型回答，只是流式输出最表面的一层。Agent 真正执行时，用户还想看到「正在搜索」「工具已返回」「等待审批」等进度，开发者则可能需要观察哪个节点更新了哪些状态、哪个任务失败、何时写入检查点。

LangChain Agent 可以直接使用 `stream` 或 `stream_events`，输出模型消息、Agent 步骤和工具发出的自定义进度。因为 `create_agent` 返回编译图，它遵循 LangGraph 的流式接口。

LangGraph 在更低层暴露 `values`、`updates`、`messages`、`custom`、`checkpoints`、`tasks` 和 `debug` 等事件类型，还能处理子图命名空间。换句话说，两者都能流式输出，LangChain 优先给常见 Agent 体验，LangGraph 允许观察完整执行引擎。

#### 部署与调试如何分工？

有些回答会把 LangSmith 当成 LangGraph 专属控制台，这也不准确。LangSmith 承担 tracing、evaluation、Studio 和 Deployment 等平台能力，可以观察 LangChain Agent，也可以观察直接编写的 LangGraph，甚至支持其他框架接入 tracing。

由于 `create_agent` 本身就是图，LangChain Agent 也可以在 Studio 中查看节点、线程、状态和执行轨迹。

直接使用 LangGraph 时，业务步骤被拆成更明确的节点，往往更容易看到复杂路由走了哪条路径，并使用 checkpoint 做状态回放和时间旅行调试。但这种可见性来自图的建模粒度，不代表 LangChain 无法部署或调试。

![](../images/fe375984df55bca4e94b8aec.png)

生产部署同样如此。LangChain Agent 和 LangGraph 工作流都能部署到 LangSmith 的 Agent Server 体系，也可以根据团队基础设施自行托管。是否使用托管平台，是部署选择；是否使用 LangChain 高层 Agent API，是开发抽象选择，别把这两个问题混成一个。

#### 什么时候下沉 LangGraph？

如果需求可以自然表达成「给模型一组工具，让它循环调用，直到完成任务」，优先从 LangChain `create_agent` 开始通常更省事。客服问答、数据库查询助手和内部知识助手，大量工作都属于这个范围。

提示词动态化、模型切换、工具筛选、摘要、重试、护栏和敏感工具审批，可以先用 middleware 解决。

如果需求的主角已经不是一个 Agent loop，而是一条业务流程，就应该考虑 LangGraph。典型信号包括：确定性规则与模型决策交替出现，多条路径要并行再汇合，任务要跨小时或跨天暂停恢复，需要多个 Agent 协作，或者必须精确控制失败补偿和人工节点。

还有一种常见做法不是选边站，而是渐进式组合。先用 LangChain 做出单个可用 Agent，等业务拓扑变复杂时，再把这个 Agent 作为 LangGraph 的节点或子图。官方当前也推荐「从高层开始，需要时下沉到细粒度控制」的路线。

这里再破除最后一个误区：不要因为 LangGraph 更底层，就默认它更高级、更适合所有项目。控制权越大，需要自己设计和测试的状态、路由、恢复与副作用就越多。一个标准 Agent 用几十个节点重新搭一遍，未必更可靠，反而可能增加维护成本。

### 🎯 面试总结

回答这道题时，先把关系定准：LangChain v1 是高层 Agent 框架，LangGraph 是低层编排框架与运行时，`create_agent` 构建在 LangGraph 上。因此它们不是彼此隔离的两套引擎，也不是简单的替代关系。

接着讲核心边界：LangChain 默认提供常见模型与工具循环，用模型、工具、结构化输出和 middleware 帮开发者快速完成 Agent；LangGraph 不替开发者规定 Agent 架构，而是把 State、Node、Edge、分支、循环、并行、子图、中断和恢复交出来，让开发者显式控制整个流程。

最后主动纠正常见误区。不能说 LangChain 只能线性，也不能说持久化、流式输出、记忆和人工审批只有 LangGraph 才有。LangChain Agent 通过底层 LangGraph 同样能使用这些能力，真正不同的是控制粒度和使用成本。

如果面试官追问选型，我会回答：标准工具调用 Agent 优先用 LangChain；复杂、长时间运行、状态丰富、需要精确路由的业务工作流用 LangGraph；很多真实项目最合适的方案，是用 LangChain 构建 Agent，再把它作为 LangGraph 的节点或子图。

### 📚 参考资料

- [LangChain 官方文档：Overview](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain 官方概念：Frameworks, runtimes, and harnesses](https://docs.langchain.com/oss/python/concepts/products)
- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain 官方文档：Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview)
- [LangChain 官方文档：Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangChain 官方文档：Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [LangChain Core 官方参考：Runnables](https://reference.langchain.com/python/langchain-core/runnables)
- [LangGraph 官方文档：Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph 官方文档：Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph 官方文档：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph 官方发布说明：What's new in LangGraph v1](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- [LangSmith 官方文档：Studio](https://docs.langchain.com/langsmith/studio)
- [LangChain 官方文档：Deployment](https://docs.langchain.com/oss/python/langchain/deploy)

---

## LangChain 和 LlamaIndex 有什么区别？

👔面试官：LangChain 和 LlamaIndex 的核心区别是什么？

🙋‍♂️我：LangChain 用来写 Chain，LlamaIndex 用来做 RAG。

👔面试官：这是过时的二分。现在两者都能做 Agent、Tools、RAG 和 Workflow，应该怎么比较？

🙋‍♂️我：既然功能差不多，那就选热度更高的。

👔面试官：功能有交集，不代表设计重心相同。项目最难的是工具集成，还是数据解析和检索，才是选型关键。

🙋‍♂️我：那项目选了 LangChain，就不能再使用 LlamaIndex，否则技术栈会冲突。

👔面试官：框架不是只能二选一。LlamaIndex 的检索能力可以包装成 Tool，再交给 LangChain Agent 或 LangGraph 调度，关键是边界是否清楚。

这道题考察的不是框架标签，而是你能否根据业务的主要风险判断应该优先使用哪套抽象。

### 💡 简要回答

LangChain 和 LlamaIndex 现在都能构建 Agent、调用工具和实现 RAG，但它们的默认入口与优势重心不同。

LangChain 更偏通用 Agent 组装。它统一模型、消息、工具、结构化输出和中间件等接口，适合快速连接不同模型供应商、业务 API 和外部工具。当前 LangChain Agent 底层运行在 LangGraph 之上，需要复杂状态、暂停恢复和人工审批时，可以进一步使用 LangGraph 编排。

LlamaIndex 更偏数据与上下文增强。它在数据接入、文档解析、切分、索引、检索、重排和 Query Engine 等环节积累更深，适合企业知识库、复杂文档问答和数据密集型 Agent。它也提供 Agent 和 Workflow，因此不能简单说它只能做 RAG。

选型时应看项目的主要难点：如果难点是模型与工具集成，优先评估 LangChain；如果难点是私有数据处理和检索质量，优先评估 LlamaIndex；如果两边都复杂，可以让 LlamaIndex 负责数据层，把检索能力封装成 Tool，再由 LangChain Agent 或 LangGraph 调度。

### 📝 详细解析

#### 为什么容易混淆？

两个框架都支持模型调用、Tools、RAG、Agent 和 Workflow，所以按照功能清单比较，很容易得出「它们差不多」的结论。

真正应该比较的是设计重心：LangChain 更关心如何统一模型与工具，并快速组装通用 Agent；LlamaIndex 更关心如何把私有数据加工成高质量上下文，再交给模型或 Agent 使用。

![](../images/12c6146fc2e1ef7e16e29703.png)

#### 核心区别是什么？

| 维度 | LangChain | LlamaIndex |
| --- | --- | --- |
| 设计重心 | 通用 Agent 组装和工具集成 | 数据接入与上下文增强 |
| 主要优势 | 模型、Tools、中间件和第三方集成 | 文档处理、索引、检索和重排 |
| 常见场景 | 工具型 Agent、SQL Agent、业务助手 | 企业知识库、文档 Agent、复杂 RAG |
| 复杂流程 | 通过 LangGraph 管理状态、恢复和人工介入 | 使用 Workflows，或与 LangGraph 组合 |

这张表比较的是优势重心，不是能力边界。LangChain 也有完整的 RAG 组件，LlamaIndex 也能创建 Agent；区别在于哪一套抽象更贴近项目的主要问题。

#### LangChain 强在哪里？

如果项目需要接入多个模型、搜索、数据库、浏览器、MCP Server 和公司内部 API，最大的工程成本往往是不同接口之间的适配。

LangChain 通过相对统一的 Model、Message、Tool 和 Structured Output 接口屏蔽差异，再用 `create_agent` 组装模型与工具。Middleware 可以统一加入权限、重试、摘要、动态模型选择和人工审批。

因此，项目如果要快速构建工具型 Agent，同时连接多个模型与外部服务，LangChain 会更顺手。这里的主要难点是让模型选对工具、填对参数，并把权限、重试和审批统一接入调用过程。

等流程复杂到需要精细控制分支、并行和恢复时，团队还可以继续下沉到 LangGraph，不必推翻已经定义好的模型与工具。

LangGraph 是 LangChain Agent 的底层运行时。简单的模型与工具循环使用 `create_agent` 即可；出现复杂分支、并行、暂停恢复和人工审批时，可以显式编写状态图。

![](../images/2b51b60d5af0de5bb0c5c705.png)

#### LlamaIndex 强在哪里？

真实 RAG 项目的困难通常不止是把文档放进向量数据库。数据刚进来时，就要处理 PDF 表格、跨页内容、切分方式和元数据；同一制度存在多个版本时，还要判断哪一份仍然有效。

到了查询阶段，系统又要决定走向量检索、关键词检索还是结构化数据库。多路结果回来后，还得过滤、重排并处理冲突。也就是说，难点沿着「数据进入 -> 建立索引 -> 发起检索 -> 组织上下文」一路传递，而不是某一个向量库能单独解决。

LlamaIndex 将数据处理链路拆得更细，可以概括为：

```text
数据接入 -> 解析与切分 -> 索引 -> 检索与重排 -> Query Engine -> Agent
```

它的价值不在于记住每个组件名字，而在于它把「如何得到高质量上下文」作为核心工程问题。企业文档、多数据源路由和复杂检索是它更自然的应用入口。

![](../images/c237be44bbddef50b8a4bcb9.png)

LlamaIndex 也提供 Agent 和事件驱动 Workflow，可以让模型调用普通工具或数据查询能力。因此，准确的说法是「LlamaIndex 以数据为优势重心」，而不是「LlamaIndex 只能做 RAG」。

#### 应该如何选型？

可以直接问：这个项目最怕哪件事做不好？

| 项目主要风险 | 优先评估 | 原因 |
| --- | --- | --- |
| 模型和业务工具太多，集成复杂 | LangChain | 通用组件和工具接口更自然 |
| 文档解析、切分和检索质量差 | LlamaIndex | 数据与上下文链路抽象更细 |
| 流程需要暂停恢复和人工审批 | LangGraph，可搭配 LangChain | 状态与执行控制是核心能力 |
| 同时需要复杂检索和复杂流程 | LlamaIndex + LangChain/LangGraph | 数据层与编排层分别选择合适组件 |

![](../images/e5996ee46465710ff408c707.png)

如果只是简单知识库或单工具 Agent，没有必要为了架构完整同时引入两套框架。组合会增加依赖、追踪和调试成本，只有当两边确实解决独立难题时才值得。

#### 两者如何组合？

最常见的组合边界是 Tool。

LlamaIndex 负责加载数据、构建索引和实现 Query Engine；对外暴露一个「查询企业知识库」的函数，再包装成 LangChain Tool。LangChain Agent 判断什么时候调用，外层如果还有审批、重试和恢复，则交给 LangGraph。

```python
# LlamaIndex Query Engine 被包装成 LangChain 可以调用的 Tool
@tool
def search_company_knowledge(question: str) -> str:
    """查询企业知识库。"""
    return str(query_engine.query(question))


# LangChain Agent 负责判断何时查询知识库，何时调用订单工具
agent = create_agent(
    model=chat_model,
    tools=[search_company_knowledge, lookup_order],
)
```

这段代码表达的重点是职责边界：LlamaIndex 管理数据与检索，LangChain 管理模型和工具选择。生产环境还需要补充租户权限、引用来源、超时和可观测性。

![](../images/dac295b0f9bfdf7aa9ab8850.png)

#### 常见误区

最容易出现的误区，是被框架名字或早期教程限制住。LangChain 并不只会把 Prompt 串成 Chain，当前主线已经转向 Agent，固定流程则继续由 Runnable 和 LCEL 承担。

同样，LlamaIndex 也不只是一个 RAG 工具，更不是向量数据库。它能够连接向量库，也提供 Agent 和 Workflow，但真正有辨识度的仍是对数据处理、索引、检索与上下文组织的抽象。

既然两边能力有重叠，也就不能简单推导出「必须二选一」或「最好全部引入」。项目可以通过 Tool 或服务接口组合两套框架，可只有数据层和 Agent 编排层确实各自存在独立难题时，这种组合才有收益。否则，多一套依赖和追踪链路只会增加调试成本。

### 🎯 面试总结

回答这道题时，不要再使用「LangChain 做 Chain，LlamaIndex 做 RAG」的过时标签。两者都能做 Agent、工具调用和 RAG，真正的区别是设计重心。

LangChain 更偏通用 Agent 组装和广泛工具集成，复杂执行流程可以下沉到 LangGraph；LlamaIndex 更偏数据接入、解析、索引、检索和上下文增强，适合企业知识库与复杂 RAG。

最后把选型落到业务：工具与模型集成是主要难点，优先考虑 LangChain；数据处理和检索质量是主要难点，优先考虑 LlamaIndex；两边都复杂时，让 LlamaIndex 管数据层，让 LangChain 或 LangGraph 管 Agent 和运行层。

### 📚 参考资料

- [LangChain 官方概览](https://docs.langchain.com/oss/python/langchain/overview)
- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain 官方文档：Retrieval](https://docs.langchain.com/oss/python/langchain/retrieval)
- [LangGraph 官方概览](https://docs.langchain.com/oss/python/langgraph/overview)
- [LlamaIndex Framework 官方概览](https://developers.llamaindex.ai/python/framework/)
- [LlamaIndex 官方文档：High-Level Concepts](https://developers.llamaindex.ai/python/framework/getting_started/concepts/)
- [LlamaIndex 官方文档：Building an Agent](https://developers.llamaindex.ai/python/framework/understanding/agent/)
- [LlamaIndex 官方文档：Workflows](https://developers.llamaindex.ai/python/llamaagents/workflows/)

---

## LangGraph 相比于 LangChain 有哪些核心优势？更适配哪些 Agent 场景？

👔面试官：LangGraph 相比 LangChain 有什么优势？

🙋‍♂️我：LangChain 只能写线性 Chain，LangGraph 才支持分支、循环和 Agent。

👔面试官：这还是早期教程里的印象。LangChain v1 的 `create_agent` 本身就是基于 LangGraph 构建的图运行时，标准 Agent loop 本来就有循环和条件路由。

🙋‍♂️我：那 LangGraph 的优势就是多了一张流程图，复杂项目用它看起来更高级。

👔面试官：图不是装饰。State、节点边界、并行汇合、检查点、中断与恢复都要进入执行语义，只画一张图解决不了可靠性问题。

🙋‍♂️我：懂了，只要项目要持久化、流式输出或记忆，就必须抛弃 LangChain，全部改成 LangGraph。

👔面试官：又把上下层说成二选一了。LangChain Agent 已经继承这些底层能力。真正需要下沉到 LangGraph 的时机，是标准 Agent loop 不足以表达业务流程，而不是看到某个功能名就重写项目。

这道题要回答好的关键，是把「功能有没有」换成「开发者需要把控制精确到哪一层」。

### 💡 简要回答

我会先纠正一个前提：LangGraph 和 LangChain 不是互斥的两套 Agent 框架。LangChain v1 提供模型、工具、中间件和预构建 Agent loop，`create_agent` 本身就运行在 LangGraph 上；LangGraph 是更低层的编排框架与运行时，让开发者直接控制 State、节点、边、路由、并行、子图、中断和恢复。

因此，LangGraph 的核心优势不是「LangChain 没有这些能力」，而是把复杂 Agent 的运行过程变成显式、可持久化、可观察、可恢复的业务状态机。

我们既可以用 `StateGraph` 声明拓扑和共享状态，也可以用 Functional API 在普通 Python 控制流上增加检查点与恢复能力。

当任务会持续很久、必须人工审批、要从故障点继续，或者需要并行研究与多 Agent 协作时，LangGraph 的优势最明显。

Checkpointer 保存线程内状态快照，Store 保存跨线程长期记忆；`interrupt()` 可以暂停任意业务节点；时间旅行可以从旧 checkpoint 重放或分叉；节点级容错则让失败路径也能被建模。

如果需求只是常见的「模型选择工具 -> 调用工具 -> 返回模型」循环，我会优先使用 LangChain `create_agent`，再用 middleware 完成提示词、重试、护栏和审批等定制。

只有当业务拓扑、恢复边界或多角色协作成为主要复杂度时，我才直接使用 LangGraph，也常把 LangChain Agent 作为图中的节点或子图复用。

### 📝 详细解析

#### 两者为什么不对立？

很多林友听到「相比」两个字，就会下意识列一张功能表：LangChain 有模型和工具，LangGraph 有状态、循环和持久化。这个答法看似清楚，实际会制造一个错误前提，好像用了 LangChain 就没有 LangGraph 的运行能力。

打个比方，LangChain 像一辆已经装好方向盘、刹车和导航的汽车，日常驾驶直接用就行；LangGraph 更像开放底盘、动力分配和道路控制系统。当业务真的需要多路调度、途中停车、事故恢复和路线回放时，底层控制才会成为核心价值。

对应到开发中，LangChain 帮我们快速获得一个常见形态的 Agent；LangGraph 让我们继续向下控制完整业务流程，例如任务在哪暂停、失败后从哪恢复、过程如何持续反馈给用户。

截至 2026 年 7 月，官方也把 LangChain 定位为高层 Agent 框架，把 LangGraph 定位为低层编排框架与运行时。LangChain v1 的 `create_agent` 会构建一个基于 LangGraph 的图运行时，所以两者不是互斥关系。

![](../images/f615ed6bcc6f2885c783bd64.png)

因此，后面提到的持久化、流式输出和人工介入，并不是在说 LangChain Agent 无法获得这些能力。真正的优势是，直接使用 LangGraph 时，我们能决定这些能力放在哪个节点、围绕哪些状态生效、失败后从哪里恢复，以及不同子流程如何组合。

#### 为什么要把流程与状态摊开？

为什么标准工具调用 Agent 一复杂，就容易让人失去控制？因为模型通常既在理解问题，又在决定下一步做什么。

流程只有两三个工具时问题不大。可一旦加入权限校验、并行取证、质量评估、人工审批和失败补偿，把所有规则塞进 Prompt，就等于把业务流程交给一个概率模型临场发挥。

LangGraph 的核心价值，是让确定性规则与模型决策各自待在合适的位置。需要模型判断的步骤交给 Agent，需要严格执行的权限、金额阈值、审批顺序和结束条件写成节点与边。这样模型仍然有自主性，但自主性被放在明确的护栏里。

拿采购流程来说，State 就像一张不断补充的申请单，Node 是预算检查、合规检查等办事窗口，Edge 则规定材料下一步送到哪里。这就是 `StateGraph` 最核心的三个角色。

如果预算和合规检查同时往申请单里写结果，谁也不能覆盖谁，这时要由 Reducer 规定如何合并更新。

基础流程理解以后，再看两个高级原语就容易了。一个节点既要改状态又要改道时，可以返回 `Command`；运行时才知道要派出多少个研究任务时，可以用 `Send` 动态分发。先理解它们解决的问题，比一次背下所有类名更重要。

这比「多了一张流程图」多在哪里？答案是图结构会直接决定执行。哪些节点能并行，哪些节点必须等前置任务完成，哪份状态会被保存，恢复后从哪里继续，都不再只是文档上的约定。

![](../images/32ff483edf1e090110bc04b6.png)

这种显式状态还有一个工程上的好处：我们可以把输入、输出和内部状态分开。外部请求只提交用户问题，内部节点维护证据、风险分、重试次数和审批意见，最后只返回对外结果。复杂流程的中间变量不必全部塞进消息历史，也不必让每个节点看到所有数据。

不过，自由度也意味着责任。State 字段怎么设计，并行写入如何合并，节点边界切多细，都要由开发者决定。LangGraph 不会因为用了图就自动让流程合理，错误的 State 设计照样会造成状态膨胀、并发覆盖和难以维护。

#### 两种编排 API 怎么选？

提到 LangGraph，很多人只知道 `StateGraph`。当前官方还提供 Functional API，两者共享同一套运行时能力，但编程方式不同。

如果流程有复杂分支、并行汇合、多 Agent 路由，或者团队需要直观看清每条路径，Graph API 更合适。开发者声明 State、Node 和 Edge，业务拓扑非常明确，Studio 里也更容易沿着节点观察状态变化。

如果团队已经有一大段普通 Python 流程，只是希望增加检查点、任务恢复和人工暂停，Functional API 往往更省改造成本。`@entrypoint` 表示工作流入口，`@task` 把有副作用或非确定性的操作变成可记录任务，流程仍然可以写普通的 `if`、`for` 和函数调用。

两者也不是二选一。外层多 Agent 调度可以使用 `StateGraph`，某个数据处理节点内部再调用 Functional API 工作流。面试时能说出这一层，说明你理解的不是某套固定模板，而是如何按复杂度选择表达方式。

| 需求特征 | 更自然的入口 | 原因 |
| --- | --- | --- |
| 分支和循环很多，需要看清完整拓扑 | Graph API | 节点、边和共享 State 显式，便于可视化与评审 |
| 多路并行后汇合，或多 Agent 交接 | Graph API | 并发关系、Reducer 和子图边界更容易建模 |
| 已有过程式代码，希望少改代码 | Functional API | 保留普通 Python 控制流，用装饰器增加运行时能力 |
| 线性流程加少量条件和人工确认 | Functional API | 局部变量与函数作用域更自然，样板代码更少 |
| 不同子流程复杂度差异很大 | 混合使用 | 外层图负责调度，内部函数工作流负责局部步骤 |

#### 流程跨小时后如何继续？

一个 Agent 运行几十秒，进程挂了可以让用户重试。可如果它要运行几小时，期间已经查了数据库、调用了外部服务，还在等审批，重新从第一步开始就不只是浪费 token，还可能重复发邮件、重复创建订单。

LangGraph 的 persistence 会在图执行过程中保存 checkpoint，并按 `thread_id` 组织线程状态。这样一个运行可以暂停，甚至服务重启后再从已保存状态恢复。官方把 durable execution 作为核心能力，重点不只是「落盘」，而是把任务结果、状态快照和恢复位置纳入运行时。

这里要说清两个很容易混淆的概念。

Checkpointer 保存某个线程的图状态快照，支撑会话连续性、中断恢复和故障恢复。Store 保存图状态之外的应用数据，适合跨线程使用的用户偏好、事实与共享知识。

前者回答「这次任务走到哪里」，后者回答「以后其他任务还要记住什么」。真实项目经常同时使用，而不是二选一。

![](../images/4a393bc0e4305829d4e3e007.png)

但 durable execution 不是数据库开关。恢复时，节点里的代码可能重新执行；从旧 checkpoint 重放时，后续模型调用和 API 请求也会再次发生。

因此，外部副作用必须有幂等保护，例如使用业务幂等键、upsert、发送记录或先查后写。复杂节点还应该把非确定性操作和副作用划分成更清楚的恢复边界。

换句话说，LangGraph 能提供可靠执行的基础设施，却不能替业务自动发明幂等语义。面试时如果只说「加 Checkpointer 就绝对不会重复执行」，反而暴露了对恢复机制理解不够。

#### 人工怎样进入任意一步？

Agent 真正进入生产系统后，完全自治往往不是终点。退款、付款、删库、发送正式邮件、发布内容等动作，需要人看一眼；有些流程还要等人工补充材料、修改状态，甚至等待几天后再继续。

LangGraph 的 `interrupt()` 可以放在节点内部任意位置。当代码触发中断时，运行时保存状态，并把一个可序列化的中断载荷交给外部系统。流程可以一直等待，之后使用相同 `thread_id` 和 `Command(resume=...)` 恢复，外部输入就成为 `interrupt()` 的返回值。

这比只支持「确认或取消」更灵活。审核员可以批准、拒绝，也可以修改金额、补充证据或给出反馈，后续路由再根据这份输入决定去哪。多级审批也可以拆成多个节点，让每个角色只看到自己需要的信息。

LangChain v1 已经有 `HumanInTheLoopMiddleware`，如果需求只是对若干敏感 Tool Call 做批准、编辑或拒绝，它通常更省事。LangGraph 的优势出现在审批对象不是一个标准工具调用，或者暂停点要嵌进更长的业务工作流时。

还有一个必须主动说的坑：节点恢复时会从节点开头重新执行，而不是从 `interrupt()` 那一行继续跑。因此，放在中断之前的副作用也要幂等，`interrupt()` 的调用顺序不要随意改变，中断载荷应保持可序列化。

![](../images/a8a36dbf9cbefeb80393a230.png)

#### 失败后为什么不必整段重跑？

传统脚本失败后，开发者常见的选择只有两个：整段重跑，或者手工改数据库再祈祷流程能继续。LangGraph 通过 checkpoint、节点边界和错误策略，把失败处理变成工作流的一部分。

当前官方文档把节点失败处理拆成可组合的三层：Retry Policy 负责按异常类型和退避策略重试，Timeout 限制单次尝试时间，Error Handler 在重试耗尽后接管错误。处理函数还可以返回 `Command`，一边更新错误状态，一边把流程送往降级、补偿或人工处理节点。

并行节点失败时又会怎样？LangGraph 会保存同一步中已经成功完成节点的结果。恢复时，成功分支不必全部重跑，只重试失败部分。

这对并行抓取多个数据源特别有价值，否则一个慢接口失败，就会让其他已经成功的请求也重新付费。

时间旅行处理的是另一个问题。通过状态历史找到旧 checkpoint 后，可以从旧位置重新执行，也可以先修改旧状态，再分出另一条轨迹。

它适合复现 Agent 为什么走错路、尝试不同人工决策，或者修正错误的中间状态。

![](../images/ef7a8178b6edf3548a88d87d.png)

这里也要避免夸大。Time travel 不是把程序时光倒流后原样播放录像。checkpoint 之前的节点会跳过，之后的节点会重新执行，因此模型输出、网络响应和外部副作用可能不同。它提供的是「可定位、可重放、可分叉」的调试基础，不是自动撤销现实世界已经发生的操作。

#### 复杂任务如何并行又汇合？

深度研究类任务为什么适合图？因为它往往不是一个 Agent 从头想到尾，而是先拆主题，再并行搜索多个来源，随后交叉验证、合并证据、发现空白后继续补搜，最后统一写报告。

Graph API 支持把一个任务拆成多条并行分支，再把结果汇合回来。如果任务数量在运行时才能确定，可以使用 `Send` 动态创建分支。

并行节点更新同一个 State 字段时，需要通过 Reducer 明确合并方式，不能指望最后写入者碰巧正确。

子图则解决模块化问题。一个完整 LangChain `create_agent` 返回的本来就是图，可以作为外层 `StateGraph` 的节点或子图。不同团队也可以分别维护研究、合规、财务等子图，只要约定好输入输出状态，父图不必知道内部细节。

子图的记忆范围需要显式选择。

一次性子任务可以让每次调用都从新状态开始。确实需要连续记忆的子 Agent，才让子图在同一线程的多次调用间积累状态。完全无状态的调用虽然更简单，但也不能依赖中断与可靠恢复能力。

![](../images/5154acd742099d62098d9e15.png)

不过，多 Agent 不等于效果必然更好。角色越多，提示词、上下文交接、错误定位和 Token 成本越高。

很多交接场景使用单 Agent 加 middleware 会更简单。只有角色需要不同工具、不同状态结构、独立生命周期，或者确实需要并行和跨团队维护时，子图才值得引入。

#### 运行中怎样持续看见进度？

复杂 Agent 常常不是慢在最后回答，而是慢在搜索、文件处理、子 Agent 调用和人工等待。如果前端只显示一个转圈图标，用户不知道系统卡住了还是仍在工作。

LangGraph 的 streaming 不只有模型 Token。它还能输出每步 State 更新、模型消息、自定义进度、checkpoint 和任务状态。

产品界面可以展示「正在查询政策库」「已完成 3/5 个来源」「等待财务审批」，开发者则能观察哪个节点更新了什么、哪个任务失败。这样，底层事件才真正变成用户能理解的进度。

LangChain Agent 因为运行在 LangGraph 上，也能使用相同的底层流式能力。直接使用 LangGraph 的优势，仍然是节点和业务阶段由我们定义，所以流式事件可以与产品进度条、审计日志和告警规则精确对应。

这种可观察性与 LangSmith tracing、Studio 配合后更有价值。开发者可以查看实际走过的节点路径、状态变更和耗时，复杂流程不再只剩一长串难以还原的模型日志。

#### 状态如何走向生产部署？

长时间运行的 Agent 不能只靠进程内列表保存状态，也不能把用户偏好和当前任务进度混进一个向量库。LangGraph 将线程内状态与跨线程长期资料分开后，系统边界会清楚很多。

短期记忆跟随 State 和 Checkpointer，由 `thread_id` 隔离，适合当前会话消息、已完成步骤和审批上下文。

长期记忆进入 Store，按 namespace 与 key 组织，用来召回用户偏好和历史事实。生产环境还要使用数据库后端，并补齐租户隔离、保留期限、删除更正与敏感信息治理。

部署也要讲清边界。开源 LangGraph 是编排框架和运行时，不等于购买某个托管服务。

团队可以自行托管并接自己的 Checkpointer、Store 和队列，也可以使用托管的 Agent Server。后者把图、持久化数据库与任务队列组合起来，更适合后台运行、流式交互和有状态长任务。

![](../images/dd6151d9402cd2d70c1d1cb1.png)

这套部署能力也是为什么 LangGraph 适合长任务，但不要说成「用了 LangGraph 就自动高可用」。自托管时，数据库、任务队列、Worker 扩缩容、重试策略、监控和数据保留都仍然是团队责任。即使使用托管平台，也需要做容量评估、幂等设计和故障演练。

#### 完整流程示例

假设我们要做一个采购 Agent。申请提交后，要并行做预算检查和合规检查，两个结果齐了才能进入人工审批，审批通过才调用采购系统，拒绝则结束。这个流程里，模型可以帮助理解材料，但顺序与权限不能交给模型自由发挥。

下面用简化代码表达核心结构。示例重点是图的控制语义，不包含真实模型、数据库和鉴权实现。

```python
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class PurchaseState(TypedDict, total=False):
    # request_id 也可作为外部采购接口的幂等键
    request_id: str
    amount: float
    budget_ok: bool
    compliance_ok: bool
    approved: bool
    result: str


def normalize_request(state: PurchaseState) -> dict:
    # 真实项目应在这里完成字段校验和权限检查
    return {"amount": round(state["amount"], 2)}


def check_budget(state: PurchaseState) -> dict:
    # 该节点可以替换为预算系统查询，并配置重试与超时
    return {"budget_ok": state["amount"] <= 100_000}


def check_compliance(state: PurchaseState) -> dict:
    # 与预算检查写入不同字段，因此两个节点可以安全并行
    return {"compliance_ok": True}


def human_review(state: PurchaseState) -> dict:
    # 暂停流程，将两项检查结果交给审核系统
    review = interrupt(
        {
            "request_id": state["request_id"],
            "budget_ok": state["budget_ok"],
            "compliance_ok": state["compliance_ok"],
        }
    )
    return {"approved": bool(review["approved"])}


def route_after_review(state: PurchaseState) -> Literal["execute", "reject"]:
    # 审批结果决定后续确定性路径
    return "execute" if state["approved"] else "reject"


def execute_purchase(state: PurchaseState) -> dict:
    # 真实调用必须携带 request_id，防止恢复或重试造成重复采购
    return {"result": f"采购申请 {state['request_id']} 已执行"}


def reject_purchase(state: PurchaseState) -> dict:
    # 拒绝路径不触发外部采购副作用
    return {"result": "采购申请未通过"}


builder = StateGraph(PurchaseState)
builder.add_node("normalize", normalize_request)
builder.add_node("budget", check_budget)
builder.add_node("compliance", check_compliance)
builder.add_node("human_review", human_review)
builder.add_node("execute", execute_purchase)
builder.add_node("reject", reject_purchase)

builder.add_edge(START, "normalize")

# 从同一节点扇出，预算和合规检查进入并行分支
builder.add_edge("normalize", "budget")
builder.add_edge("normalize", "compliance")

# 使用多起点边做 fan-in，两项检查都完成后才进入人工审批
builder.add_edge(["budget", "compliance"], "human_review")
builder.add_conditional_edges("human_review", route_after_review)
builder.add_edge("execute", END)
builder.add_edge("reject", END)

# 内存检查点仅用于示例，生产环境应替换为数据库后端
graph = builder.compile(checkpointer=InMemorySaver())

# thread_id 是暂停、恢复和状态历史的定位依据
config = {"configurable": {"thread_id": "purchase-2026-001"}}
graph.invoke(
    {"request_id": "PO-001", "amount": 58_000},
    config=config,
)

# 审核员稍后提交结果，图从同一线程的中断点恢复
final_state = graph.invoke(
    Command(resume={"approved": True}),
    config=config,
)
print(final_state["result"])
```

这段代码体现了四件事：业务拓扑是显式的，两项检查能并行且有明确汇合点，人工审批可以跨时间暂停，执行动作有业务幂等键。真正上线时，还要给外部查询增加 Retry Policy 与 Timeout，给执行失败设计补偿或人工接管路径，并把 InMemorySaver 换成持久化实现。

如果用 LangChain，也不是不能实现这个系统。更自然的组合通常是：用 `create_agent` 做「材料理解」或「异常解释」节点，外层采购流程仍由 `StateGraph` 控制。这样高层 Agent 抽象和低层业务编排各司其职。

#### 哪些场景适合 LangGraph？

理解了前面的能力，场景判断就不用死记。我们只要先问一句：这个系统最难的是「让模型会用工具」，还是「让整个任务可靠地走完一条复杂路线」？

如果难点只是让模型从几个工具中做选择，标准 Agent 往往已经足够。可一旦业务顺序不能交给模型自由发挥，问题就变了。理赔、退款、采购、合同审核和生产变更都有明确阶段、权限与审批点，模型只能参与理解和判断，真正的路线必须由确定性规则控制。LangGraph 的价值，就是把模型能力嵌进业务流程，而不是让 Prompt 充当流程引擎。

路线明确以后，再看它是否会跨时间运行。深度研究、报表生成、代码迁移和跨系统工单可能持续数十分钟到数天，中间还要等待人或外部事件。这类任务需要 checkpoint、interrupt 和 durable execution 保住进度，否则每次等待或故障都可能让流程从头再来。

任务继续变复杂时，单条路线还会长出并行分支。Planner 临时拆出多个研究主题，各分支分别搜索、抽取与验证，再用 Reducer 汇总证据；多个 Agent 也可能因为拥有不同工具、状态或团队边界而组成子图。此时 `Send`、fan-out、fan-in 和 subgraph 不是为了炫技，而是在表达真实存在的并发与协作关系。

最后再看团队是否需要干预中间状态。复杂 RAG 会在证据不足时改写查询并重新检索，模型走错路线时也需要查看 checkpoint、修改状态后重放。只看最终答案已经无法解释问题时，显式节点、状态历史和分叉能力才会真正转化为调试价值。

#### 哪些场景不必用 LangGraph？

LangGraph 更底层，不等于更适合所有项目。一个只需要查天气、查订单、总结文档的标准工具调用 Agent，使用 `create_agent` 往往更快、更短，也更符合团队认知。

动态提示词、模型切换、工具过滤、消息摘要、重试、护栏和敏感工具审批，优先看看 LangChain middleware 能不能解决。

如果流程只有固定的 Prompt、模型和解析器，也不一定需要 Agent，更不用为了「图」而引入 LangGraph。普通函数、LCEL 或一个队列任务可能就够了。

下面这张选型表比「简单用 LangChain，复杂用 LangGraph」更有操作性：

| 判断问题 | 优先 LangChain `create_agent` | 考虑直接使用 LangGraph |
| --- | --- | --- |
| 主流程是什么 | 常见模型与工具循环 | 多阶段业务工作流 |
| 路由由谁决定 | 大部分由模型按工具描述决定 | 模型决策与确定性规则混合 |
| 状态复杂度 | 消息为主，少量自定义字段 | 多类业务状态、Reducer、内部通道 |
| 运行时长 | 单次交互或短任务 | 跨小时、跨天、等待外部事件 |
| 人工介入 | 审批敏感工具调用 | 任意阶段补充、修改、审批和改道 |
| 并行结构 | 少量并行工具调用 | 动态 fan-out、fan-in、map-reduce |
| 角色数量 | 单 Agent 或简单子 Agent | 多 Agent、子图、明确 handoff |
| 故障处理 | 通用重试与错误包装 | 节点级恢复、补偿、历史分叉 |
| 团队成本 | 希望快速交付，少写编排代码 | 愿意维护图、状态和恢复语义 |

最稳妥的选型路径通常是渐进式的。先用 LangChain 搭出一个能工作的 Agent，当 middleware 已经开始承担业务路由、状态字段越来越多、任务必须跨时间恢复时，再把外围流程下沉到 LangGraph。已有 Agent 不必推倒重来，可以直接成为图里的节点或子图。

最后再提醒一个常见误区：图越复杂，不代表系统越智能。节点过细会增加 checkpoint、序列化和维护成本，节点过粗又会降低恢复粒度。真正成熟的设计，是根据副作用、重试、人工介入和可观测性来划分边界，而不是追求节点数量。

### 🎯 面试总结

回答这道题时，我会先把关系说准：LangChain v1 的 Agent 本身构建在 LangGraph 上，所以两者不是互斥框架。LangGraph 的优势不是凭空多出持久化、流式输出和人工介入，而是让开发者从高层 Agent loop 下沉，显式控制整个有状态业务流程。

接着我会抓住三条主线。第一是控制，State、节点、边和确定性规则都能进入执行拓扑。第二是可靠，checkpoint、interrupt 和节点级容错让长任务可以暂停与恢复。

第三是工程化，流式事件、短期与长期记忆以及部署服务，可以支撑有状态、长时间运行的生产系统。

场景上，LangGraph 更适合高风险审批、跨小时或跨天任务、并行深度研究、多 Agent 协作、自纠错 RAG 和需要精确调试的复杂工作流。它尤其适合把确定性步骤与 LLM 驱动步骤混在一张图里，让模型负责需要判断的部分，让业务规则负责不能出错的部分。

最后给出边界：标准工具调用 Agent 优先用 LangChain `create_agent`，简单审批优先用 middleware。只有当业务拓扑、状态作用域、恢复边界或多角色协作成为主要复杂度时，才直接使用 LangGraph。

真实项目常见的成熟方案不是二选一，而是让 LangChain Agent 成为 LangGraph 中可复用的节点或子图。

### 📚 参考资料

- [LangGraph 官方文档：Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangGraph 官方文档：Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph 官方文档：Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)
- [LangGraph 官方文档：Graph API 与 Functional API 选型](https://docs.langchain.com/oss/python/langgraph/choosing-apis)
- [LangGraph 官方文档：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph 官方文档：Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph 官方文档：Time Travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)
- [LangGraph 官方文档：Fault Tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
- [LangGraph 官方文档：Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
- [LangGraph 官方文档：Streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
- [LangGraph 官方文档：Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangSmith 官方文档：Agent Server](https://docs.langchain.com/langsmith/agent-server)

---

## LangChain 如何实现短期记忆和长期记忆？

👔面试官：LangChain 中的短期记忆和长期记忆怎么实现？

🙋‍♂️我：短期记忆就是把最近几轮对话放进 Prompt，长期记忆就是把全部聊天记录存进向量数据库。

👔面试官：全部聊天记录都值得长期保存吗？当前线程状态由谁管理？用户换一个会话后，又如何读取以前的偏好？

🙋‍♂️我：可以使用 `ConversationBufferMemory` 和 `ConversationSummaryMemory`。

👔面试官：这些是旧版 Chain 时代的常见抽象。LangChain v1 新项目应该讲清 Checkpointer、Store、`thread_id` 和 namespace 的作用。

🙋‍♂️我：Checkpointer 和 Store 都能把数据保存下来，项目里选择其中一个应该就够了。

👔面试官：它们的作用域完全不同。Checkpointer 保存当前线程的状态，Store 才负责跨线程数据，混用后不是换会话失忆，就是发生用户数据串读。

这道题的重点不是背 Memory 类名，而是理解信息应该存在哪个作用域、如何召回，以及怎样避免串用户、上下文膨胀和错误记忆。

### 💡 简要回答

在 LangChain v1 中，可以用一句话区分两类记忆：

```text
短期记忆 = State + thread_id + Checkpointer
长期记忆 = namespace/key + Store
```

短期记忆属于当前会话线程。Agent State 保存消息、当前步骤和中间结果；Checkpointer 按 `thread_id` 保存状态快照。使用同一个 `thread_id` 再次调用时，可以恢复前面的对话和执行状态。

长期记忆不应该绑定某个线程，而是保存到 Store。Store 使用 namespace 和 key 组织数据，namespace 通常包含租户、用户和记忆类型。即使用户新建了线程，只要使用相同的可信用户身份和 namespace，仍然可以读取以前保存的偏好或经验。

工具可以通过 `ToolRuntime` 读取当前 State、可信 Context 和长期 Store。用户 ID、租户和权限应由应用运行时注入，不能让模型自己填写。

长对话还需要控制上下文：裁剪只减少本次模型输入，删除会真正移除持久状态，摘要则用更短文本保留主要语义。生产环境要使用数据库型 Checkpointer 和 Store，并做好租户隔离、写入幂等、记忆更正、过期删除、敏感信息保护和检索评测。

### 📝 详细解析

#### 应该记住什么？

假设用户正在规划杭州旅行。当前对话中提到的日期、预算和下一步计划，只服务于这次任务，属于短期状态。

一周后用户新建会话，Agent 仍然知道他不吃辣、喜欢住地铁附近，这些跨会话仍然有效的信息才属于长期记忆。

因此，记忆设计的第一步不是选数据库，而是确定作用域。当前线程运行到了哪里，由 State 和 Checkpointer 管理；未来其他线程仍可能使用的用户偏好与事实，才由 Store 管理。

![](../images/9c865bb1ac33c765b7c4be67.png)

#### 短期记忆如何实现？

LangChain v1 的 `create_agent` 底层运行在 LangGraph 上。Agent State 默认包含 `messages`，也可以扩展订单号、当前步骤和工具调用次数等业务字段。

只有 State 还不够。请求可能由不同服务实例处理，进程也可能重启，因此需要 Checkpointer 持久化执行状态。调用 Agent 时传入稳定的 `thread_id`，同一编号就可以恢复同一线程：

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


# Checkpointer 按 thread_id 保存线程内的 Agent State
agent = create_agent(
    model="openai:gpt-5.4-mini",
    tools=[],
    checkpointer=InMemorySaver(),
)

# 两次调用复用同一个 thread_id，表示它们属于同一会话线程
config = {"configurable": {"thread_id": "chat-1001"}}

# 第一轮把用户姓名写入当前线程的 messages 状态
agent.invoke(
    {"messages": [{"role": "user", "content": "我叫小林"}]},
    config=config,
)

# 第二轮会先恢复同一线程之前保存的状态
result = agent.invoke(
    {"messages": [{"role": "user", "content": "我叫什么？"}]},
    config=config,
)
```

`InMemorySaver` 只适合本地演示。生产环境要换成持久化实现，否则进程退出后状态会丢失。

Checkpoint 保存的不只是聊天字符串，而是图执行过程中的 State 快照。因此它还可以支撑暂停恢复、人工审批和故障恢复。

#### 消息太多怎么办？

Checkpointer 能保存历史，不代表每次都应该把全部历史交给模型。消息越多，Token、延迟和干扰越大。

常用策略有三种：

| 策略 | 作用 | 主要风险 |
| --- | --- | --- |
| 裁剪 | 只选择部分消息进入本次模型上下文 | 持久状态仍会继续增长 |
| 删除 | 从 State 中永久移除旧消息 | 信息不可恢复 |
| 摘要 | 把早期历史压缩成简短语义摘要 | 可能遗漏细节或逐轮失真 |

客服 Agent 可能需要保护当前工单和用户承诺，代码 Agent 可能需要保护最新报错和修改记录。因此不能只按固定消息条数处理，而应该结合 Token 预算、消息角色和业务重要性制定策略。

![](../images/49856e1483d59b067b4dade7.png)

#### 长期记忆如何实现？

新 `thread_id` 默认不会继承旧线程的 State，这是正确的线程隔离。如果某条信息需要跨线程使用，就应提炼后写入 Store。

Store 中的数据通常使用下面的结构定位：

```text
namespace = (tenant_id, user_id, memory_type)
key       = 某条记忆的稳定标识
value     = JSON 数据
```

已知 key 时使用精确读取；需要从多条记忆中按语义查找时，可以配置向量索引后进行搜索。向量检索只是召回方式，不代表所有聊天记录都应该成为长期记忆。

长期记忆常见内容可以简单分为：

| 类型 | 示例 |
| --- | --- |
| 用户事实与偏好 | 不吃辣、偏好中文、常用 Java |
| 历史经验 | 上次如何成功处理支付超时 |
| 工作规则 | 退款前必须核验订单归属 |

这些分类用于帮助设计数据结构，不是要求把每段原始对话都永久保存。写入前仍要做去重、脱敏、冲突处理和质量判断。

#### 如何跨线程读取？

工具可以通过 `ToolRuntime` 访问这些信息，但不能把三个入口混成一个数据袋。当前线程的短期状态来自 `runtime.state`，可信用户身份和权限来自 `runtime.context`，只有跨线程长期数据才从 `runtime.store` 读取。

```python
from dataclasses import dataclass

from langchain.tools import ToolRuntime, tool


@dataclass
class UserContext:
    # 用户身份由可信应用注入，不暴露给模型填写
    user_id: str


@tool
def remember_preference(
    preference: str,
    runtime: ToolRuntime[UserContext],
) -> str:
    """保存当前用户明确要求记住的偏好。"""
    # namespace 将不同用户的长期记忆隔离开
    namespace = (runtime.context.user_id, "preferences")
    # key 为 main，本例只维护一条当前偏好记录
    runtime.store.put(namespace, "main", {"text": preference})
    return "偏好已保存"
```

模型只负责生成 `preference`，`user_id` 由已认证的应用通过 Context 注入。这样可以防止模型填错身份或被提示注入诱导访问其他用户的数据。

两个不同 `thread_id` 的会话，只要可信 `user_id` 相同，就可以访问同一个长期记忆 namespace；另一位用户则应被 namespace 和服务端权限隔离。

![](../images/8f3936c21aedd32ecd6cd299.png)

#### 什么时候写入长期记忆？

长期记忆不是越多越好。把每句闲聊都存进去，会产生噪声、冲突和隐私风险。

用户明确说「请记住」时，可以在主链路中实时写入，使信息立即生效。普通对话中推断出的偏好和经验，更适合在会话结束后由后台任务提炼、去重和脱敏，再写入 Store。

无论实时还是后台写入，都应保存来源、时间和置信度，并支持更新、纠错和删除。订单金额、账户余额和库存等实时事实仍应查询权威业务系统，不能使用长期记忆代替真实数据库。

#### 生产环境要注意什么？

把记忆从 Demo 带到生产，第一关不是换一套更大的模型，而是确认数据能否可靠保存。开发时的内存实现会随着进程退出而丢失，线上需要数据库型 Checkpointer 和 Store，并把表结构与迁移一起纳入部署流程。

数据保存下来后，紧接着要解决「这是谁的记忆」。`thread_id`、`tenant_id` 和 `user_id` 必须来自可信身份体系，不能相信模型生成的身份，也不能让客户端随意指定另一个用户的 namespace。否则记得越多，越容易造成跨用户数据泄露。

隔离做好以后，还要承认记忆会过时、会冲突，也会被用户纠正。系统要能够去重、更新和过期淘汰，同时支持用户查看、更正、导出和删除。敏感信息则默认不记，确实需要保存的数据要加密并限制访问，日志与 Trace 也不能成为隐私的另一个泄漏口。

最后才是判断这套记忆到底有没有用。评测不能只看「成功写入多少条」，而要沿着整条链路检查：这条信息是否值得写入，相关问题能否召回，无关问题会不会误召回，注入模型后是否真正改善答案。只有写入、召回和使用三步都有效，记忆才不是一个不断膨胀的数据库。

![](../images/81b544930908ca630de94476.png)

#### 旧 Memory 还能用吗？

旧教程常见的 `ConversationBufferMemory`、`ConversationSummaryMemory` 等属于 Chain 时代的抽象，目前主要位于 `langchain-classic`，适合维护存量项目。

LangChain v1 新项目更推荐使用：

```text
AgentState + Checkpointer -> 管理线程内状态
Store + namespace/key -> 管理跨线程长期记忆
Middleware 或图节点 -> 管理裁剪、摘要和写入策略
```

这套方式把状态作用域、持久化和记忆治理拆得更清楚，也更适合有工具调用、暂停恢复和多用户隔离要求的 Agent。

### 🎯 面试总结

回答这道题时，首先说清楚两条主线：短期记忆是线程级 State，由 Checkpointer 按 `thread_id` 保存；长期记忆是跨线程数据，由 Store 按 namespace 和 key 管理。

接着说明 `ToolRuntime` 的边界：模型只生成任务参数，可信用户身份通过 Context 注入，工具再访问当前 State 和长期 Store。这样即使用户更换线程，也能读取自己的长期偏好，同时避免跨用户数据泄露。

最后补充长上下文治理和生产要求：消息需要裁剪、删除或摘要；线上使用持久化后端，并做好租户隔离、幂等写入、冲突更正、过期删除、隐私保护和召回评测。旧式 `Conversation*Memory` 可以维护存量项目，但不再是 v1 新项目的主路径。

### 📚 参考资料

- [LangChain 官方文档：Memory 概览](https://docs.langchain.com/oss/python/concepts/memory)
- [LangChain 官方文档：Short-term Memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)
- [LangChain 官方文档：Long-term Memory](https://docs.langchain.com/oss/python/langchain/long-term-memory)
- [LangGraph 官方文档：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph 官方文档：Memory](https://docs.langchain.com/oss/python/langgraph/add-memory)
- [LangChain 官方文档：Tools 与 ToolRuntime](https://docs.langchain.com/oss/python/langchain/tools)
- [langchain-classic 官方 API Reference](https://reference.langchain.com/python/langchain-classic)

---

## 在 LangChain 中，如何为 Agent 注册工具？

👔面试官：在 LangChain 中，怎么给 Agent 注册工具？

🙋‍♂️我：给函数加一个 `@tool`，然后放进 Agent 就行。

👔面试官：已有的普通函数能不能直接传？复杂参数怎么校验？什么情况下需要 `StructuredTool` 或 `BaseTool`？

🙋‍♂️我：那就全部继承 `BaseTool`，这样最规范。

👔面试官：为了查询一次天气也写一个类，只会增加样板代码。用户身份和权限又应该怎么传给工具？

🙋‍♂️我：让模型生成一个 `user_id` 参数。

👔面试官：可信身份不能由模型填写，否则既可能填错，也可能被提示注入利用。

这道题并不是让你背诵所有 Tool 类，而是考察你是否理解工具协议，能否根据输入复杂度和工程要求选择合适的实现方式。

### 💡 简要回答

LangChain 中注册 Tool 的本质，是同时向模型提供一份工具说明，并向运行时提供一个真正可执行的函数。工具说明主要包含名称、用途和参数 Schema，模型根据它选择工具并生成参数，LangChain 再执行对应函数。

最常用的实现方式有四种：

1. 简单的已有函数，可以带上类型注解和 docstring 后直接放入 `tools`。
2. 大多数业务工具使用 `@tool`，便于自定义名称、描述和参数 Schema。
3. 需要在运行时组装同步函数、异步函数和 Schema 时，可以使用 `StructuredTool`。
4. 工具需要封装客户端、维护资源或定制执行过程时，再继承 `BaseTool`。

在 LangChain v1 中，通常通过 `create_agent(model=..., tools=[...])` 完成注册。城市、关键词、订单号等任务参数可以让模型填写；用户 ID、租户、权限和存储对象等可信参数，应通过 `ToolRuntime` 从运行时注入，不能暴露给模型。

生产环境还要关注参数校验、权限检查、超时、重试、幂等和错误分类。只有网络超时等临时故障适合自动重试，参数错误和业务拒绝应该返回清楚的信息，程序 Bug 则不应该被统一吞掉。

### 📝 详细解析

#### Tool 注册了什么？

模型看不到 Python 函数的源码，那它凭什么知道该调用谁？注册工具时，LangChain 会先把函数转换成一份模型能够理解的说明。

模型首先看到 `name` 和 `description`，借此判断工具叫什么、应该在什么情况下使用。决定调用后，它再按照 `args_schema` 生成满足类型和约束的参数。真正拿着这些参数做事的，则是应用侧的函数或协程，也就是 executor。

模型先生成包含工具名和参数的调用请求，运行时执行函数，再把结果作为 `ToolMessage` 返回给模型。模型拿到结果后，决定继续调用工具还是生成最终回答。

![](../images/fdeb9d8759dcf8db51062d9d.png)

所以，工具描述和 Schema 不是普通注释，而是模型与业务代码之间的调用合同。描述过于模糊，模型可能选错工具；参数缺少约束，模型可能生成无法执行的数据。

#### 常用方式怎么选？

日常开发中，没有必要为了显得专业而直接继承最底层的类。选择方式时，可以先问这个工具到底还是不是一个普通函数。

如果已有函数的名称、类型注解和 docstring 已经能把用途说清楚，直接放入 `tools` 就够了。可一旦我们希望明确修改工具名称、补充参数描述，或者用 Pydantic 限制枚举和范围，普通函数提供的信息就不够，这时 `@tool` 会成为大多数业务工具的自然选择。

再往上走，问题可能不是 Schema 不清楚，而是原函数不能修改，或者工具要在运行时动态组装同步与异步实现。`StructuredTool` 解决的正是这个组装问题。只有当工具需要长期持有客户端、维护资源并定制完整执行过程时，它才从「一个函数」变成「一个组件」，这时再考虑继承 `BaseTool` 才划算。

所以，这四种方式不是互相竞争的功能清单，而是一条随复杂度上升的路径：先让函数说清楚，再补充工具契约，接着处理动态组装，最后才管理组件生命周期。

模型厂商提供的 Web Search、代码执行器等服务端工具，有时会使用厂商约定的字典配置。这类工具属于特定 Provider 能力，使用时应单独查看对应集成文档，不需要把它当作通用 Python Tool 的主要定义方式。

#### 为什么优先使用 @tool ？

`@tool` 能从函数签名和 docstring 自动推导 Schema，也允许通过 Pydantic 显式描述复杂参数，是大多数业务工具的首选。

```python
from typing import Literal

from langchain.agents import create_agent
from langchain.tools import tool
from pydantic import BaseModel, Field


class OrderQuery(BaseModel):
    # Field 描述和类型约束都会进入模型看到的工具 Schema
    order_id: str = Field(description="要查询的订单号")
    detail: Literal["summary", "full"] = Field(
        default="summary",
        description="返回摘要还是完整信息",
    )


# args_schema 显式指定工具参数的校验模型
@tool(args_schema=OrderQuery)
def query_order(order_id: str, detail: str = "summary") -> str:
    """查询订单状态。用户询问某个订单时调用。"""
    return f"订单 {order_id} 的状态为已发货，返回模式：{detail}"


# 注册时把 Tool 放进 create_agent 的 tools 列表
agent = create_agent(
    model="openai:gpt-5.4-mini",
    tools=[query_order],
)
```

这个例子中，模型只需要决定 `order_id` 和 `detail`。Pydantic 的字段描述和枚举限制会进入工具 Schema，既帮助模型正确填写参数，也能在执行前拦截非法输入。

![](../images/ecba709f44bab10d2ec3f2d3.png)

如果只是已有的简单函数，也可以不加装饰器，直接传给 `tools`。不过函数必须有清楚的名称、类型注解和 docstring，否则自动生成的工具说明很难指导模型正确调用。

#### 何时使用高级定义？

`StructuredTool.from_function` 更适合「原函数不能修改，但需要改变它对模型的呈现方式」的场景。例如，同一个业务函数需要注册成不同名称，或者要把同步函数和异步协程组合成一个工具对象。

什么时候才需要 `BaseTool`？当工具不再只是一个函数，而是要长期持有数据库或第三方客户端，并同时管理同步、异步、tags、metadata 和回调时，它已经变成了一个有生命周期的组件。此时使用 `BaseTool`，才值得承担更多样板代码。

选择原则可以概括为：函数能够说清楚就用普通函数，需要明确 Schema 就用 `@tool`，需要运行时组装再用 `StructuredTool`，出现组件生命周期后才考虑 `BaseTool`。

![](../images/01b5d313d4dad373b6f10b05.png)

#### 可信参数如何注入？

假设「查询我的账户余额」工具需要用户 ID。如果把 `user_id` 放进模型可见的 Schema，模型可能填错用户，也可能被恶意提示诱导查询其他账户。

因此，需要区分两类参数：

| 参数类型 | 示例 | 参数来源 |
| --- | --- | --- |
| 任务参数 | 城市、关键词、订单号 | 模型根据用户问题生成 |
| 可信参数 | 用户 ID、租户、权限、当前状态 | 应用运行时注入 |

LangChain v1 使用 `ToolRuntime` 把这些可信信息送进工具，但不同信息仍有不同作用域。用户身份、租户和依赖属于本次调用上下文，从 `runtime.context` 读取；当前会话消息和短期状态放在 `runtime.state`；跨会话仍要保留的长期数据，才进入 `runtime.store`。

```python
from dataclasses import dataclass

from langchain.tools import ToolRuntime, tool


@dataclass
class UserContext:
    # 这些字段由应用运行时提供，不让模型生成
    user_id: str
    role: str


@tool
def get_balance(
    account_type: str,
    runtime: ToolRuntime[UserContext],
) -> str:
    """查询当前登录用户的账户余额。"""
    # 先使用可信 Context 做权限检查
    if runtime.context.role not in {"user", "finance_admin"}:
        return "当前用户无权查询余额"

    # 用户 ID 来自 Runtime，而不是模型参数
    user_id = runtime.context.user_id
    return f"用户 {user_id} 的 {account_type} 账户余额为 100 元"
```

模型能够看到并填写 `account_type`，却看不到 `runtime`。可信用户身份由应用传入，而不是由模型生成。这是工具权限控制的重要边界。

![](../images/6f4344c6180970c8d50a480b.png)

#### 异步工具怎么处理？

搜索、数据库和远程 API 通常属于 I/O 密集型操作。如果底层客户端支持异步，工具也应使用原生 `async def`，并通过 Agent 的 `ainvoke` 或异步流式接口调用。

不要只把函数声明成 `async def`，内部却继续调用阻塞式 HTTP 客户端；这种写法不会自动提高并发能力。工具是否异步，应该和底层客户端以及整条 Agent 调用链保持一致。

#### 错误应该怎么处理？

工具调用失败时，先别急着统一重试，因为不同失败意味着完全不同的下一步。

如果日期格式错误或缺少必填字段，问题出在模型生成的参数，应先让 Schema 拦截，再把可修正的信息交给模型重新填写。库存不足、没有权限或订单不存在则不是参数格式问题，而是一次正常的业务结果。工具应该把原因说清楚，让 Agent 决定换条路径或直接告知用户。

网络超时、限流和服务暂不可用才属于可以尝试恢复的临时故障。这类错误可以做有上限的重试，但必须同时设置退避和总超时，否则 Agent 只会在一个坏掉的服务前反复等待。

程序 Bug、数据损坏和权限配置错误不应该被统一转换成「调用失败」后继续执行，否则系统会掩盖真正的问题。对于付款、发邮件、创建订单等有副作用的工具，还必须设计幂等键和人工审批，避免重试造成重复执行。

#### 注册后还要检查什么？

一个能被 Agent 调用的函数，并不等于一个可以安全上线的工具。检查时可以沿着一次真实调用往下走，而不是背一张清单。

模型准备调用之前，先看名称和描述是否会与其他工具混淆，Schema 有没有限制枚举、范围和必填字段。这一步决定模型能不能选对工具、填对参数。

请求进入执行阶段后，再确认用户身份和权限来自可信 Runtime，而不是模型参数。远程调用还要有超时、重试上限和并发限制；只要动作会改变外部状态，就继续补上幂等、审批与审计，防止一次恢复或重试变成重复扣款、重复发信。

调用结束也不是安全边界的终点。日志与 Trace 需要帮助排查错误，但不能记录密钥、完整身份凭证或不必要的敏感数据。这样从模型选择、业务执行到事后追踪，工具契约才算真正闭环。

工具数量也不是越多越好。一次性向模型暴露大量相似工具，会增加选择错误和参数混淆的概率。更合理的做法是根据用户权限和当前任务动态缩小工具集合。

### 🎯 面试总结

回答这道题时，不要把重点放在背诵所有 Tool 类名上。先说明 Tool 是「模型可见的调用合同 + 运行时可执行函数」，再讲清楚四种常用定义方式的选择边界。

实际项目中，普通函数和 `@tool` 能覆盖大多数需求；`StructuredTool` 用于运行时组装，`BaseTool` 用于复杂组件。可信身份和权限通过 `ToolRuntime` 注入，不能交给模型生成。

最后补充 Schema 校验、异步 I/O、错误分类、幂等和权限治理，就能体现你不仅会注册工具，也理解工具如何安全、稳定地运行在生产环境中。

### 📚 参考资料

- [LangChain 官方文档：Tools](https://docs.langchain.com/oss/python/langchain/tools)
- [LangChain 官方文档：Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain API：StructuredTool](https://reference.langchain.com/python/langchain-core/tools/structured/StructuredTool)
- [LangChain API：BaseTool](https://reference.langchain.com/python/langchain-core/tools/base/BaseTool)
- [LangChain 官方文档：Middleware](https://docs.langchain.com/oss/python/langchain/middleware)

---

## LangChain 大版本升级有哪些核心变化？

👔面试官：你说说 LangChain 大版本升级都改了什么？

🙋‍♂️我：主要是支持的模型和向量数据库越来越多，功能变得更丰富。

👔面试官：这些只是表面。为什么要拆分 `langchain-core` 和模型集成包？为什么又引入 Runnable、LangGraph 和 middleware？

🙋‍♂️我：因为旧 API 不好用，所以新版本把旧 Chain 全部删掉了。

👔面试官：旧能力主要被移到 `langchain-classic`，并不是全部删除。真正值得关注的是框架职责发生了什么变化。

🙋‍♂️我：那升级时只更新 `langchain` 主包，再把旧导入改掉就可以了。

👔面试官：还要检查 LangGraph、社区包和模型集成包的兼容关系，并回归测试工具调用、流式输出和持久化，不能把跨版本迁移理解成换几个 import。

这道题不是让你背每个小版本增加了哪些 API，而是要回答：LangChain 为什么从一个包罗万象的 LLM 工具箱，逐渐演进成「稳定核心协议、独立模型集成、高层 Agent API、LangGraph 运行时」的分层架构。

### 💡 简要回答

LangChain 的版本演进可以抓住四条主线。

第一是拆分核心与集成。稳定的消息、模型、Tool 和 Runnable 协议放进 `langchain-core`，第三方模型与向量库则迁到 `langchain-community` 或独立集成包，避免厂商 SDK 的变化频繁影响核心框架。

第二是使用 Runnable 和 LCEL 统一组件调用。Prompt、Model、Parser 等组件拥有一致的 `invoke`、`batch`、`stream` 和异步接口，确定性流程可以通过组合而不是不断继承新的 Chain 类实现。

第三是将 Agent 运行时转向 LangGraph。传统 Agent 执行器适合简单循环，却难以处理复杂状态、分支、暂停恢复和人工审批。LangGraph 将执行过程显式表示为状态图，成为 LangChain Agent 的底层运行基础。

第四是 LangChain v1 进一步聚焦 Agent。`create_agent` 成为高层入口，middleware 负责动态提示词、工具控制、摘要、重试和人工介入等横切能力，旧 Chain 等接口进入 `langchain-classic`。

这些变化的共同方向不是「增加更多类」，而是稳定核心抽象、解耦第三方集成、统一组合协议，并把复杂 Agent 交给可持久化、可恢复的图运行时。

### 📝 详细解析

#### 为什么要不断调整架构？

LangChain 早期把模型、向量库、工具、Retriever 和大量预制 Chain 都放在相近的包结构中，快速验证想法很方便。可项目一大，第三方 SDK 的一次更新就可能牵动整个依赖树。

依赖问题只是第一层。继续往上看，不同 Chain 的调用和组合方式并不统一，开发者需要记住越来越多专用 API；再遇到复杂 Agent，执行循环又藏在执行器内部，很难插入分支、审批和恢复逻辑。功能越加越多，核心职责反而越来越模糊。

因此，大版本演进的重点并不是单纯增加功能，而是重新划分边界：哪些协议需要保持稳定，哪些集成应该独立更新，哪些流程应该由更底层的运行时管理。

![](../images/9a75b9d543950e1f6700c1a1.png)

#### 核心与集成为何拆开？

模型厂商、向量数据库和外部工具的 SDK 变化很快，而消息、Runnable、Tool 等核心协议应该尽量稳定。把它们全部放在同一个包中，会让两种不同的迭代节奏互相影响。

拆分后，主要职责可以这样理解：

| 包 | 核心职责 |
| --- | --- |
| `langchain-core` | 消息、模型、Tool、Runnable 等基础协议 |
| `langchain` | 面向应用开发的高层 Agent 能力 |
| `langchain-community` | 大量社区维护的第三方集成 |
| `langchain-openai` 等独立包 | 跟随特定厂商 SDK 独立迭代 |

这种设计让项目只安装真正需要的集成，也降低了某个模型 SDK 升级对整个框架的影响。面试时不需要背出所有包名，重点应放在「稳定内核，释放边缘」这一架构思想。

![](../images/0654ed6829693eb3e121fe38.png)

#### Runnable 改变了什么？

早期 LangChain 为不同流程提供了大量 Chain 类，调用方式和扩展方式并不完全一致。Runnable 协议与 LCEL 将 Prompt、Model、Parser、Retriever 等组件统一为可组合单元。

```python
# Prompt、Model 和 Parser 统一遵循 Runnable 协议
chain = prompt | model | output_parser

# 组合后的整体仍然使用统一的 invoke 接口
result = chain.invoke({"question": "什么是 Agent？"})
```

这段代码的重要之处不是管道符，而是组合后的整体仍然遵循 Runnable 协议，因此可以使用统一的同步、异步、批处理、流式和追踪接口。

它代表 LangChain 从「大量预制类」转向「少量标准协议 + 组合」。对于步骤固定的确定性流程，Runnable 和 LCEL 往往比 Agent 更容易测试和控制。

#### 为什么转向 LangGraph？

传统 Agent 执行器通常在内部运行「模型判断、调用工具、再次判断」的循环。简单 Agent 使用方便，但一旦加入规划、反思、并行分支、人工审批或故障恢复，隐藏的循环就会变得难以修改。

LangGraph 的解决思路，是把隐藏循环摊开成 `State + Node + Edge`。State 保存消息和业务进度，Node 执行模型、工具或普通业务逻辑，Edge 决定结果接下来流向哪里。

这样，循环和分支不再隐藏在执行器内部，检查点还能保存运行状态，为暂停恢复、人工介入和长时间执行提供基础。

![](../images/68eb3f5d4c3eb9215964d6ce.png)

LangGraph 并不是把 LangChain 完全替换掉。LangChain 提供模型、Tool、middleware 和 `create_agent` 等高层开发体验，LangGraph 提供底层状态与执行能力。简单 Agent 使用 LangChain 即可，复杂流程再下沉到 LangGraph。

#### LangChain v1 聚焦了什么？

LangChain v1 将主线进一步收敛到 Agent 开发。要理解这次收敛，可以先从开发者最常接触的入口看起。

新项目通常从 `create_agent` 开始。开发者提供模型、工具和系统提示词，底层由 LangGraph 运行 Agent loop，因此这套高层入口能够继续使用持久化、流式输出和人工介入等运行能力。换句话说，易用性留在 LangChain，复杂执行能力则由 LangGraph 承接。

Agent 跑起来后，总会出现动态提示词、模型选择、工具筛选、对话摘要、重试和人工审批等需求。如果每增加一项能力都重写循环，高层入口很快又会失去意义。因此 v1 把 middleware 作为主要扩展方式，让这些横切逻辑插入关键执行阶段，而不是复制整套 Agent loop。

高层入口和扩展机制明确以后，主命名空间也能顺势精简。旧 Chain、Retriever、Indexing 和 Hub 等能力主要迁到 `langchain-classic`，存量项目仍可渐进迁移，新的 `langchain` 包则把注意力留给 Agent 主线。

![](../images/cccb78061c441140138e8220.png)

因此，不能把 v1 简单理解成「旧 API 全部删除」。更准确的说法是：新项目使用聚焦后的 Agent API，旧项目通过 `langchain-classic` 保持运行，再根据需要逐步迁移。

#### Pydantic 2 值得重点背吗？

Python v0.3 将内部数据模型迁移到 Pydantic 2，并停止使用 Pydantic 1 兼容层。这属于重要的迁移背景，因为工具 Schema、结构化输出和配置对象都依赖 Pydantic。

不过，面试时不需要展开 Pydantic 的全部版本差异。只要说明它统一了数据模型与校验基线，旧项目升级时需要检查导入路径和模型定义即可。相比之下，拆包、Runnable、LangGraph 和 v1 Agent 架构更能体现 LangChain 的长期演进方向。

#### 升级时要注意什么？

跨大版本升级不能只执行一次依赖更新。动手前先锁定当前依赖和可复现环境，再阅读目标版本的迁移指南，否则一旦多个包同时变化，很难判断问题从哪里开始。

接下来要顺着新的分层检查兼容关系。`langchain`、LangGraph 和模型集成包各自有更新节奏，确认版本组合以后，才能逐步替换废弃导入路径和内部 API。这里适合小步修改、小步运行，不要等所有代码改完才第一次启动。

代码能够启动，只说明导入问题解决了。工具调用、结构化输出、流式响应和持久化仍要分别回归，因为这些边界最容易受到协议和运行时变化影响。付款、发消息等有副作用的路径还要先在隔离环境验证幂等，再做小流量发布，避免一次升级把重复执行带进真实业务。

不同包的更新节奏并不完全一致。主包的稳定承诺不能自动覆盖社区集成、合作伙伴包和实验性 API，因此生产项目应该固定依赖版本，并尽量建立在公开稳定接口之上。

#### 演进方向是什么？

把几次架构变化连起来，主线其实很清楚。首先用 `langchain-core` 稳定基础协议，再把模型和数据库集成拆出去独立更新，解决核心与外部 SDK 节奏不一致的问题。

核心边界稳定以后，Runnable 与 LCEL 统一了确定性流程的组合方式。最后，复杂状态和执行流程下沉到 LangGraph，高层再通过 `create_agent` 和 middleware 提供更容易使用的 Agent 入口。

这套方向让 LangChain 从「封装大量 LLM 功能」，转向「提供清晰分层的 Agent 工程体系」。代价是旧项目升级需要处理依赖和导入路径，收益则是核心接口更稳定、复杂流程更可控，也更适合生产环境。

### 🎯 面试总结

面试时，不需要背诵每个小版本增加了哪些 API，也不建议报当前最新补丁版本。围绕四个架构节点回答即可：

- 拆分核心与第三方集成。
- 使用 Runnable 和 LCEL 统一组件协议。
- 使用 LangGraph 承担复杂 Agent 运行时。
- v1 通过 `create_agent`、middleware 和 `langchain-classic` 重新聚焦 Agent。

最后再说出自己的判断：LangChain 的演进方向是稳定核心、解耦集成、组合确定性流程、图化 Agent 运行时。这样既能回答「升级了什么」，也能解释「为什么要升级」。

### 📚 参考资料

- [LangChain 官方：v0.1 发布说明](https://www.langchain.com/blog/langchain-v0-1-0)
- [LangChain 官方：v0.2 稳定性升级说明](https://www.langchain.com/blog/langchain-v02-leap-to-stability)
- [LangChain 官方：v0.3 发布说明](https://www.langchain.com/blog/announcing-langchain-v0-3)
- [LangChain 官方：LangChain 与 LangGraph 1.0 发布说明](https://www.langchain.com/blog/langchain-langgraph-1dot0)
- [LangChain Python 官方文档：v1 新能力](https://docs.langchain.com/oss/python/releases/langchain-v1)
- [LangChain Python 官方文档：v1 迁移指南](https://docs.langchain.com/oss/python/migrate/langchain-v1)
- [LangChain Python 官方文档：版本策略](https://docs.langchain.com/oss/python/release-policy)

---
