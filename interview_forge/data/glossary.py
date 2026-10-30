"""术语词典（服务端权威数据源）。

设计原则：
  · 词典由开发/服务端维护，用户不能自行添加（避免污染与不可控内容）
  · 每条术语：term(主词) / abbr(英文缩写或全称) / aliases(文中可能出现的写法)
    / definition(一句话解释) / detail(补充说明，可为空) / category(分类)
  · 前端只负责「匹配 + 展示」，不做任何内容判断

构建时由 scripts/build/build_library.py 导出为 assets/glossary.json，
章节页与书目页统一下载同一份词典，保证口径一致。
"""

from __future__ import annotations

GLOSSARY: list[dict[str, str]] = [
    # ---------------- Agent / 大模型基础 ----------------
    {
        "term": "LLM",
        "abbr": "Large Language Model",
        "aliases": ["LLM", "大语言模型", "大模型"],
        "definition": "大规模预训练的语言模型，能理解并生成自然语言，是 Agent 的「大脑」。",
        "detail": "通过海量语料自监督预训练得到，具备通用语言能力；本身不会主动行动，需要外部工具或流程驱动。",
        "category": "大模型基础",
    },
    {
        "term": "Agent",
        "abbr": "智能体",
        "aliases": ["Agent", "智能体"],
        "definition": "能感知环境、自主决策并调用工具完成目标的 AI 系统。",
        "detail": "典型结构：目标 → 规划 → 调用工具 → 观察结果 → 循环，直到任务完成或触发终止条件。",
        "category": "Agent 基础",
    },
    {
        "term": "RAG",
        "abbr": "Retrieval-Augmented Generation",
        "aliases": ["RAG", "检索增强生成"],
        "definition": "先检索相关资料、再让模型基于资料作答的技术，用于缓解模型幻觉与知识过时。",
        "detail": "流程：文档切分 → 向量化入库 → 查询召回 → 重排 → 拼进 Prompt 生成。",
        "category": "检索增强",
    },
    {
        "term": "MCP",
        "abbr": "Model Context Protocol",
        "aliases": ["MCP"],
        "definition": "一套让模型/Agent 标准化接入外部工具与数据源的协议。",
        "detail": "把「工具提供方」与「Agent 宿主」解耦，工具一次实现、多个宿主复用，类似 AI 领域的 USB-C。",
        "category": "工具与协议",
    },
    {
        "term": "ReAct",
        "abbr": "Reasoning + Acting",
        "aliases": ["ReAct"],
        "definition": "让模型交替进行「推理」与「行动」的 Agent 范式，边想边做。",
        "detail": "循环：Thought（想）→ Action（调工具）→ Observation（看结果），直到得出答案。",
        "category": "Agent 范式",
    },
    {
        "term": "CoT",
        "abbr": "Chain of Thought",
        "aliases": ["CoT", "思维链"],
        "definition": "让模型分步推理、展示中间思考过程，从而提升复杂问题正确率的提示技术。",
        "detail": "常见变体：Zero-shot CoT（加「让我们一步步思考」）、Few-shot CoT（给示例推理过程）。",
        "category": "提示技术",
    },
    {
        "term": "Prompt Engineering",
        "abbr": "提示工程",
        "aliases": ["Prompt Engineering", "提示工程"],
        "definition": "通过设计输入提示词来引导模型产出预期结果的方法论。",
        "detail": "常用手段：角色设定、示例（Few-shot）、输出格式约束、分步引导、自我检查。",
        "category": "提示技术",
    },
    {
        "term": "Function Calling",
        "abbr": "工具调用",
        "aliases": ["Function Calling", "函数调用", "工具调用"],
        "definition": "模型按约定格式输出「要调用哪个函数、传什么参数」，由外部执行后再把结果喂回模型。",
        "detail": "是 Agent 与外部世界交互的基础机制；模型本身不执行函数，只负责产生结构化调用意图。",
        "category": "工具与协议",
    },
    {
        "term": "Hallucination",
        "abbr": "幻觉",
        "aliases": ["Hallucination", "幻觉"],
        "definition": "模型生成了看似合理但与事实不符的内容。",
        "detail": "成因包括训练数据噪声、知识缺口、过度追求流畅；缓解手段有 RAG、工具校验、要求引用来源。",
        "category": "大模型基础",
    },
    {
        "term": "Context Window",
        "abbr": "上下文窗口",
        "aliases": ["Context Window", "上下文窗口", "上下文长度"],
        "definition": "模型单次能「看到」的最大 token 数，包括输入与输出。",
        "detail": "窗口越大可放资料越多，但存在「Lost in the Middle」：中间位置的信息更容易被忽略。",
        "category": "大模型基础",
    },
    {
        "term": "Token",
        "abbr": "",
        "aliases": ["Token", "token"],
        "definition": "模型处理文本的最小单位，约等于 1 个英文词或半个中文词。",
        "detail": "计费、上下文长度、生成速度都以 token 计量；中文通常 1 个字 ≈ 1~2 token。",
        "category": "大模型基础",
    },
    {
        "term": "Embedding",
        "abbr": "向量嵌入",
        "aliases": ["Embedding", "向量嵌入", "嵌入向量"],
        "definition": "把文本转成一串数字向量，语义相近的文本向量距离也相近。",
        "detail": "是语义检索、聚类、去重的基础；常见维度 768 / 1024 / 1536。",
        "category": "检索增强",
    },
    {
        "term": "Vector DB",
        "abbr": "向量数据库",
        "aliases": ["Vector DB", "向量数据库"],
        "definition": "专门存储向量并支持「相似度检索」的数据库，如 Milvus、Qdrant、pgvector。",
        "detail": "核心能力是近邻搜索（ANN），用近似算法在亿级向量中快速找到最相似的 K 条。",
        "category": "检索增强",
    },
    {
        "term": "Rerank",
        "abbr": "重排",
        "aliases": ["Rerank", "重排", "重排序"],
        "definition": "在初步召回后，用更精细的模型对候选结果重新打分排序。",
        "detail": "典型两阶段检索：向量召回（快而粗）→ Cross-Encoder 重排（慢而准），兼顾效率与质量。",
        "category": "检索增强",
    },
    {
        "term": "Chunking",
        "abbr": "分块",
        "aliases": ["Chunking", "分块", "文档切分"],
        "definition": "把长文档切成适合检索的小片段。",
        "detail": "策略有固定长度、按标题/段落、语义切分；块太大噪声多，太小上下文不足，需要 overlap 衔接。",
        "category": "检索增强",
    },
    {
        "term": "Fine-tuning",
        "abbr": "微调",
        "aliases": ["Fine-tuning", "微调", "SFT"],
        "definition": "在预训练模型基础上，用特定领域数据继续训练，使其更贴合任务。",
        "detail": "适合固定风格/格式或垂直领域；知识更新优先用 RAG，行为对齐优先用微调。",
        "category": "模型训练",
    },
    {
        "term": "LoRA",
        "abbr": "Low-Rank Adaptation",
        "aliases": ["LoRA"],
        "definition": "一种低成本微调方法：冻结原模型，只训练少量低秩旁路参数。",
        "detail": "显存占用与训练成本大幅降低，可产出小体积「适配器」，按需加载切换。",
        "category": "模型训练",
    },
    {
        "term": "RLHF",
        "abbr": "Reinforcement Learning from Human Feedback",
        "aliases": ["RLHF", "人类反馈强化学习"],
        "definition": "用人类偏好数据训练奖励模型，再用强化学习优化模型输出。",
        "detail": "ChatGPT 对齐的关键步骤；后续演进有 DPO 等更轻量的偏好优化方法。",
        "category": "模型训练",
    },
    {
        "term": "MoE",
        "abbr": "Mixture of Experts",
        "aliases": ["MoE", "混合专家"],
        "definition": "模型由多个「专家」子网络组成，每次只激活其中一部分，兼顾容量与算力。",
        "detail": "稀疏激活让总参数量很大但单次计算量可控，是当前大模型扩容的主流结构之一。",
        "category": "大模型基础",
    },
    {
        "term": "Quantization",
        "abbr": "量化",
        "aliases": ["Quantization", "量化"],
        "definition": "把模型权重从高精度（如 FP16）压缩到低精度（如 INT8/INT4），降低显存与加速推理。",
        "detail": "常见 GPTQ、AWQ、GGUF；代价是精度轻微下降，需评估任务敏感度。",
        "category": "推理优化",
    },
    {
        "term": "KV Cache",
        "abbr": "",
        "aliases": ["KV Cache", "KV 缓存"],
        "definition": "推理时缓存已计算的注意力键值，避免重复计算，显著加速逐 token 生成。",
        "detail": "长上下文下 KV Cache 占用显存很大，衍生出 PagedAttention、GQA 等优化。",
        "category": "推理优化",
    },
    {
        "term": "Transformer",
        "abbr": "",
        "aliases": ["Transformer"],
        "definition": "基于自注意力机制的主流神经网络架构，是几乎所有大语言模型的基础。",
        "detail": "核心是 Self-Attention：让每个 token 动态关注序列中其他位置，天然适合并行训练。",
        "category": "大模型基础",
    },
    {
        "term": "Semantic Search",
        "abbr": "语义检索",
        "aliases": ["Semantic Search", "语义检索", "语义搜索"],
        "definition": "按「意思」而非字面关键词检索，能召回同义但不同措辞的内容。",
        "detail": "常与关键词检索（BM25）做混合检索（Hybrid Search），互补召回效果更好。",
        "category": "检索增强",
    },
    {
        "term": "System Prompt",
        "abbr": "系统提示词",
        "aliases": ["System Prompt", "系统提示词"],
        "definition": "在对话开始前设定的全局指令，规定模型角色、边界与行为准则。",
        "detail": "优先级高于用户输入；写好 System Prompt 是控制 Agent 行为最直接的手段。",
        "category": "提示技术",
    },
    {
        "term": "Few-shot",
        "abbr": "",
        "aliases": ["Few-shot", "小样本"],
        "definition": "在提示中给出几个示例，让模型照着示例的格式与思路完成任务。",
        "detail": "对应 Zero-shot（不给示例）；示例质量比数量更关键，错误示例会带偏模型。",
        "category": "提示技术",
    },
    {
        "term": "Workflow",
        "abbr": "工作流",
        "aliases": ["Workflow", "工作流"],
        "definition": "按预先编排好的固定步骤执行任务的流程，路径确定、可控性强。",
        "detail": "与 Agent 的区别：Workflow 步骤写死，Agent 自主决策；复杂稳定场景优先 Workflow。",
        "category": "Agent 基础",
    },
    {
        "term": "Plan-and-Execute",
        "abbr": "",
        "aliases": ["Plan-and-Execute", "先规划后执行"],
        "definition": "Agent 范式：先制定完整计划，再逐步执行，必要时回头修订计划。",
        "detail": "相比 ReAct 的逐步试探，更适合步骤多、需要全局统筹的复杂任务。",
        "category": "Agent 范式",
    },
    {
        "term": "Reflection",
        "abbr": "反思",
        "aliases": ["Reflection", "反思机制"],
        "definition": "让 Agent 审视自己的输出并改进的机制，类似「做完检查一遍」。",
        "detail": "典型做法：生成 → 自评/找错 → 修正重试，可显著提升复杂任务成功率。",
        "category": "Agent 范式",
    },
    {
        "term": "Sandbox",
        "abbr": "沙箱",
        "aliases": ["Sandbox", "沙箱"],
        "definition": "隔离的运行环境，让代码执行等高风险操作不影响主机系统。",
        "detail": "Agent 执行用户或模型生成的代码时必须隔离；常见方案容器、gVisor、Firecracker。",
        "category": "工程实践",
    },
    {
        "term": "Observability",
        "abbr": "可观测性",
        "aliases": ["Observability", "可观测性", "Trace", "链路追踪"],
        "definition": "通过日志、指标、链路追踪了解系统内部运行状况的能力。",
        "detail": "Agent 场景靠 Trace 还原「想了什么、调了什么工具、拿到什么结果」，是排障核心。",
        "category": "工程实践",
    },
]


def glossary_map() -> dict[str, dict[str, str]]:
    """构建「任一写法 → 词条」的索引，供前端匹配使用。"""
    index: dict[str, dict[str, str]] = {}
    for entry in GLOSSARY:
        keys = {entry["term"], *entry.get("aliases", [])}
        for key in keys:
            if key:
                index[key] = {
                    "term": entry["term"],
                    "abbr": entry.get("abbr", ""),
                    "definition": entry["definition"],
                    "detail": entry.get("detail", ""),
                    "category": entry.get("category", ""),
                }
    return index
