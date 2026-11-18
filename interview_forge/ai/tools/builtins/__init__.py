"""Built-in assistant tools are registered here as the catalog grows."""
from __future__ import annotations

from interview_forge.ai.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    from interview_forge.ai.tools.builtins.actions import (
        MarkProblemArgs,
        PinProblemForTomorrowArgs,
        SetDailyGoalArgs,
        SyncLeetCodeArgs,
        mark_problem,
        mark_problem_confirmation,
        pin_problem_for_tomorrow,
        pin_problem_for_tomorrow_confirmation,
        set_daily_goal,
        set_daily_goal_confirmation,
        sync_leetcode,
        sync_leetcode_confirmation,
    )
    from interview_forge.ai.tools.builtins.history import (
        HISTORY_RESULT_TOKENS,
        RecallChatHistoryArgs,
        recall_chat_history,
    )
    from interview_forge.ai.tools.builtins.learning import (
        GetLearningContextArgs,
        get_learning_context,
    )
    from interview_forge.ai.tools.builtins.library import (
        SearchLibraryArgs,
        search_library,
    )
    from interview_forge.ai.tools.builtins.problem import (
        GetAcmExamplesArgs, GetProblemArgs, get_acm_examples, get_problem,
    )
    from interview_forge.ai.tools.builtins.progress import (
        GetProblemProgressArgs,
        get_problem_progress,
    )
    from interview_forge.ai.tools.builtins.review import (
        GetReviewQueueArgs,
        get_review_queue,
    )
    from interview_forge.ai.tools.builtins.weather import GetWeatherArgs, get_weather
    from interview_forge.ai.tools.builtins.observations import RecallLearningObservationArgs, recall_learning_observation
    from interview_forge.ai.tools.contracts import ToolKind, ToolSpec

    registry.register(ToolSpec(
        name="get_acm_examples",
        display_name="查询公开判题样例",
        description="按力扣题号查本站 ACM 输入输出契约、比较规则和公开样例。statement 源于力扣题面，supplemental 为本站用例。截断字段为节选；按 next_index 翻页。",
        args_model=GetAcmExamplesArgs,
        handler=get_acm_examples,
        timeout_seconds=2.0,
        max_result_tokens=780,
        observation_receipt_tokens=80,
    ))
    registry.register(ToolSpec(
        name="get_problem",
        display_name="查询题目",
        description="按题号或准确题名读取站内题目的方法、不变量、复杂度和链接。可据此逐步提示、检查代码思路；模糊关键词返回候选题目。",
        args_model=GetProblemArgs,
        handler=get_problem,
        timeout_seconds=2.0,
        max_result_tokens=700,
    ))
    registry.register(ToolSpec(
        name="search_library",
        display_name="站内书架",
        description="按 query 搜索本站章节，多个概念用空格分隔。用户指刚才书架列表中的第几项时，按 previous_source 序号读取该章当前的索引片段。",
        args_model=SearchLibraryArgs,
        handler=search_library,
        timeout_seconds=4.0,
        max_result_tokens=2400,
    ))
    registry.register(ToolSpec(
        name="recall_chat_history",
        display_name="会话历史",
        description="回读本会话历史原文。知道来源 ID 可直接读。已知连续原词用 literal；只记得意思、用词不同或可能跨语言时用 mode=semantic，按主题找来源片段。查最初约定可设 oldest_first。",
        args_model=RecallChatHistoryArgs,
        handler=recall_chat_history,
        timeout_seconds=30.0,
        max_result_tokens=HISTORY_RESULT_TOKENS,
        cache_within_turn=False,
    ))
    registry.register(ToolSpec(
        name="get_learning_context",
        display_name="读取学习记录",
        description="读取当前用户指定任务的精简学习上下文。",
        args_model=GetLearningContextArgs,
        handler=get_learning_context,
        timeout_seconds=6.0,
        max_result_tokens=1500,
    ))
    registry.register(ToolSpec(
        name="get_problem_progress",
        display_name="查询题目进度",
        description="查询本题轮次、力扣提交、复习日期和站内 ACM 记录。native_acm.status 表示是否曾通过，latest_verdict 是最近判定。",
        args_model=GetProblemProgressArgs,
        handler=get_problem_progress,
        timeout_seconds=4.0,
        max_result_tokens=780,
        observation_receipt_tokens=80,
    ))
    registry.register(ToolSpec(
        name="recall_learning_observation",
        display_name="回读历史学习记录",
        description="回读本会话先前轮次的原始题目进度或公开样例。按 problem_id 和 source_tool 取最近的旧记录，或按 observation_id 精确回读。excerpt 为当时数据 JSON，按 next_offset 和 observation_id 翻页。不要用实时进度代替历史记录。",
        args_model=RecallLearningObservationArgs,
        handler=recall_learning_observation,
        timeout_seconds=4.0,
        max_result_tokens=1800,
        cache_within_turn=False,
    ))
    registry.register(ToolSpec(
        name="get_review_queue",
        display_name="查询复习队列",
        description="查询当前用户到期和逾期的题目复习队列。",
        args_model=GetReviewQueueArgs,
        handler=get_review_queue,
        timeout_seconds=5.0,
        max_result_tokens=1200,
    ))
    registry.register(ToolSpec(
        name="get_weather",
        display_name="查询天气",
        description="查询当前用户天气设置或用户明确指定的城市天气。",
        args_model=GetWeatherArgs,
        handler=get_weather,
        timeout_seconds=8.0,
        max_result_tokens=700,
    ))
    registry.register(ToolSpec(
        name="sync_leetcode",
        display_name="同步 LeetCode",
        description="请求启动当前用户的 LeetCode 学习记录同步；必须等待用户确认，不会自行执行。",
        args_model=SyncLeetCodeArgs,
        handler=sync_leetcode,
        kind=ToolKind.ACTION,
        requires_confirmation=True,
        timeout_seconds=5.0,
        max_result_tokens=300,
        confirmation_builder=sync_leetcode_confirmation,
    ))
    registry.register(ToolSpec(
        name="mark_problem",
        display_name="标记题目",
        description="更新指定题目的掌握、复习中或薄弱标记；必须等待用户确认。",
        args_model=MarkProblemArgs,
        handler=mark_problem,
        kind=ToolKind.ACTION,
        requires_confirmation=True,
        timeout_seconds=4.0,
        max_result_tokens=400,
        confirmation_builder=mark_problem_confirmation,
    ))
    registry.register(ToolSpec(
        name="pin_problem_for_tomorrow",
        display_name="安排明日题目",
        description="把指定题目加入明日学习计划；必须等待用户确认。",
        args_model=PinProblemForTomorrowArgs,
        handler=pin_problem_for_tomorrow,
        kind=ToolKind.ACTION,
        requires_confirmation=True,
        timeout_seconds=4.0,
        max_result_tokens=400,
        confirmation_builder=pin_problem_for_tomorrow_confirmation,
    ))
    registry.register(ToolSpec(
        name="set_daily_goal",
        display_name="设置每日目标",
        description="设置每日学习目标轮数（1 到 50）；必须等待用户确认。",
        args_model=SetDailyGoalArgs,
        handler=set_daily_goal,
        kind=ToolKind.ACTION,
        requires_confirmation=True,
        timeout_seconds=4.0,
        max_result_tokens=300,
        confirmation_builder=set_daily_goal_confirmation,
    ))
    return registry


__all__ = ["register_builtin_tools"]
