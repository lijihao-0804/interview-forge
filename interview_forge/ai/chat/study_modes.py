"""Per-turn teaching preferences and explicitly attached practice evidence."""
from interview_forge.ai.chat.context_blocks import ContextBlock


_GUIDANCE = {
    "hint": "只给一个简短启发性问题就停下，等用户追问再给算法步骤或代码。",
    "review": "学习复盘：结合相关记录梳理已掌握内容、困惑和下一步练习；资料不足时说明。",
    "code": "代码走查：围绕问题检查可用代码、输入与运行结果，指出具体原因和验证方法。",
}


def validate_study_mode(value: object) -> str:
    if not isinstance(value, str) or (value != "auto" and value not in _GUIDANCE):
        raise ValueError("不支持的学习模式")
    return value


def validate_practice_snapshot(value: object, mode: str) -> str | None:
    if value is None:
        return None
    if mode != "code" or not isinstance(value, str) or len(value) > 8_000:
        raise ValueError("练习快照仅适用于代码走查，最多 8000 个字符")
    return value.strip() or None


def study_blocks(mode: str, snapshot: str | None) -> list[ContextBlock]:
    if mode == "auto":
        return []
    guidance = "本轮要求优先，只用相关资料。" + _GUIDANCE[mode]
    blocks = [ContextBlock("study_mode", guidance, 95, 160, trusted=True, alternatives=())]
    if snapshot:
        # Editor text comes first and judge output last. Keep both ends when
        # the detailed view exceeds its token allocation.
        alternatives = tuple(
            snapshot[:edge] + "\n…练习快照已截短…\n" + snapshot[-edge:]
            for edge in (500, 160, 60) if len(snapshot) > edge * 2
        )
        blocks.append(ContextBlock("practice_snapshot", snapshot, 92, 1_400, alternatives=alternatives))
    return blocks
