"""Built-in assistant tools are registered here as the catalog grows."""
from __future__ import annotations

from interview_forge.ai.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    from interview_forge.ai.tools.builtins.learning import GetLearningContextArgs, get_learning_context
    from interview_forge.ai.tools.builtins.problem import GetProblemArgs, get_problem
    from interview_forge.ai.tools.builtins.progress import GetProblemProgressArgs, get_problem_progress
    from interview_forge.ai.tools.builtins.review import GetReviewQueueArgs, get_review_queue
    from interview_forge.ai.tools.builtins.weather import GetWeatherArgs, get_weather
    from interview_forge.ai.tools.builtins.actions import (
        MarkProblemArgs, PinProblemForTomorrowArgs, SetDailyGoalArgs, SyncLeetCodeArgs,
        mark_problem, mark_problem_confirmation, pin_problem_for_tomorrow,
        pin_problem_for_tomorrow_confirmation, set_daily_goal, set_daily_goal_confirmation,
        sync_leetcode, sync_leetcode_confirmation,
    )
    from interview_forge.ai.tools.contracts import ToolKind, ToolSpec

    registry.register(ToolSpec(
        name="get_problem",
        display_name="查询题目",
        description="查询本地题库中的题目元数据、站内链接和力扣链接，不返回完整题解。",
        args_model=GetProblemArgs,
        handler=get_problem,
        timeout_seconds=2.0,
        max_result_tokens=700,
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
        description="查询指定题目的轮次、提交和下次复习日期等精简学习进度。",
        args_model=GetProblemProgressArgs,
        handler=get_problem_progress,
        timeout_seconds=4.0,
        max_result_tokens=700,
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
