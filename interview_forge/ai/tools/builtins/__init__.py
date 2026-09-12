"""Built-in assistant tools are registered here as the catalog grows."""
from __future__ import annotations

from interview_forge.ai.tools.registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    from interview_forge.ai.tools.builtins.learning import GetLearningContextArgs, get_learning_context
    from interview_forge.ai.tools.builtins.problem import GetProblemArgs, get_problem
    from interview_forge.ai.tools.builtins.weather import GetWeatherArgs, get_weather
    from interview_forge.ai.tools.builtins.actions import SyncLeetCodeArgs, sync_leetcode, sync_leetcode_confirmation
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
    return registry


__all__ = ["register_builtin_tools"]
