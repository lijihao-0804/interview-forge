"""Local, inspectable topic selection; storage is never pruned by this policy.

Only user turns establish topics. Assistant prose cannot make an unrelated
topic relevant. Ambiguous references keep their context rather than guessing
an antecedent. No provider call or embedding service is needed.
"""
from __future__ import annotations

import re
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping, Sequence
from typing import Any


POLICY_VERSION = "chat-relevance-v1"
_RESET = re.compile(r"^(?:换个(?:话题|问题)|另一个问题|新的问题|不谈(?:这个|之前)|先不聊|重新开始|new topic\b|unrelated question\b)", re.I)
_RECALL = re.compile(r"之前|先前|前面|刚才|上次|前文|earlier|previous|before", re.I)
_REFERENCE = re.compile(
    r"这个|那个|这些|那些|这样|那样|这题|本题|这章|本章|这段|上述|上面|下面|它|他们|它们|你说|你提到|你的(?:回答|建议)|"
    r"第[一二三四五六七八九十0-9]+(?:个|种|步)|继续|接着|再(?:说|讲|解释|举|详细)|"
    r"详细(?:点|一些|一点)|具体点|展开(?:说|讲)?|"
    r"举(?:个|一个)?例|给(?:个|一个)?例|^.{0,10}呢[？?]?$|^(?:复杂度|边界条件|给我代码|能优化吗)[？?]?$|"
    r"^(?:没(?:有)?(?:看懂|明白|理解)|不懂|不知道|好的|好吧|嗯|好|是的|可以|开始吧|确认|取消|重试)[。！？?！]*$|"
    r"^(?:那|那么|然后|还有|为什么[？?]?$|怎么做[？?]?$)|"
    r"\b(?:it|its|they|them|that|this|those|these|continue|elaborate|what about)\b", re.I,
)
_FILLER = re.compile(
    r"我想(?:知道|了解|学习)|请问|请你|帮我|给我|能不能|可以|一下|详细|解释|介绍|讲解|讲讲|说说|什么是|是什么|有哪些|"
    r"有什么|为什么|如何|怎么|怎样|区别|原理|机制|过程|问题|当前|关于|以及|一个|一下子|"
    r"实现|方式|代码|示例|优缺点|的|了|吗|\b(?:can|could|you|tell|me)\b|"
    r"\b(?:please|explain|describe|what|is|are|how|does|do|the|a|an|of|to|and|in|for|about)\b",
    re.I,
)
_ACTION = re.compile(
    r"待确认|等待确认|确认(?:操作|同步|执行)|取消(?:操作|同步|请求)|标记(?:题目|为)|"
    r"(?:每日|每天|今日|学习)目标|目标(?:改|设|调)|明日计划|明天(?:学|复习)|"
    r"学习进度|同步.{0,8}(?:完成|成功|失败|进度|状态|结果)|(?:力扣|leetcode).{0,8}同步|"
    r"同步.{0,8}(?:力扣|leetcode|记录|数据)|(?:操作|任务|执行).{0,4}(?:状态|结果|进度)|"
    r"好了吗|完成了吗|成功了吗|^(?:请|帮我|重新|开始)?同步(?:一下)?[。！？?]*$|"
    r"^(?:确认|取消|重试)[。！？?]*$|"
    r"\b(?:confirm|cancel)\b", re.I,
)
_PAGE = re.compile(r"这(?:个|道|一)?(?:题|页|章|段)|当前(?:页|题|章)|选中|划选|页面|本题|本章|\b(?:this page|this problem|selected text)\b", re.I)
_GREETING = re.compile(r"^(?:你好|您好|嗨|哈喽|早上好|晚上好|在吗|谢谢|hello|hi|hey)[!！。.，,？?\s]*$", re.I)
_ACKNOWLEDGEMENT = re.compile(r"^(?:嗯|好|好的|好吧|是的|可以|开始吧)[。！？?\s]*$")
_IMPLICIT_PAGE = re.compile(r"^(?:它(?:呢|怎么做|怎么理解)?|继续|接着(?:讲|说)?)[。！？?\s]*$")


def topic_terms(text: str) -> set[str]:
    """Use word anchors and Chinese bigrams, excluding generic question words."""
    text = _FILLER.sub(" ", str(text).casefold())
    terms = set(re.findall(r"[a-z][a-z0-9_+#.-]*|\d+", text))
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(span[index:index + 2] for index in range(len(span) - 1))
    return terms


def topics_overlap(left: str, right: str) -> bool:
    a, b = topic_terms(left), topic_terms(right)
    shared = a & b
    # One exact technical word/number is useful; one common Chinese bigram
    # alone is too weak unless it constitutes most of the shorter subject.
    return any(re.fullmatch(r"[a-z0-9_+#.-]+", term) for term in shared) or (
        bool(shared) and (len(shared) >= 2 or len(shared) / max(1, min(len(a), len(b))) >= .5)
    )


def _dependent(text: str) -> bool:
    return bool(_REFERENCE.search(text) or _RECALL.search(text))


def _standalone(text: str) -> bool:
    if _dependent(text):
        return False
    # Tiny acknowledgements and underspecified questions need the last turn.
    terms = topic_terms(text)
    return bool(terms) and (
        len(terms) >= 2 or bool(re.search(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]{2}", _FILLER.sub(" ", text)))
    )


@dataclass(frozen=True)
class HistorySelection:
    rows: tuple[Any, ...]
    mode: str
    reason: str


def _page_path(row: Mapping[str, Any]) -> str | None:
    try:
        metadata = json.loads(str(row["metadata_json"])) if "metadata_json" in row.keys() else {}
        page = metadata.get("page_context")
        return page.get("path") if isinstance(page, dict) else None
    except (ValueError, TypeError, AttributeError):
        return None


def _message_time(row: Mapping[str, Any]) -> datetime | None:
    try:
        raw = str(row["created_at"])
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _stale_acknowledgement(
    rows: Sequence[Mapping[str, Any]], query: str, *, as_of: datetime | None = None,
) -> bool:
    if not rows or not _ACKNOWLEDGEMENT.fullmatch(query.strip()):
        return False
    last = _message_time(rows[-1])
    return last is not None and (as_of or datetime.now(timezone.utc)) - last >= timedelta(hours=24)


def select_history(
    rows: Sequence[Mapping[str, Any]], query: str, *, current_page_path: str | None = None,
) -> HistorySelection:
    """Select a coherent topic episode, preserving each user/assistant pair."""
    if not rows:
        return HistorySelection((), "independent", "empty_history")
    if _GREETING.fullmatch(query.strip()):
        return HistorySelection((), "independent", "standalone_greeting")
    if _RESET.search(query.strip()):
        return HistorySelection((), "independent", "explicit_topic_reset")
    if _stale_acknowledgement(rows, query):
        return HistorySelection((), "independent", "stale_acknowledgement")
    # Explicit cross-episode references may need more than the latest topic.
    if _RECALL.search(query):
        return HistorySelection(tuple(rows), "recall", "explicit_history_reference")
    if current_page_path and (_PAGE.search(query) or _IMPLICIT_PAGE.fullmatch(query.strip())):
        previous_page = None
        for row in reversed(rows):
            if str(row["role"]) != "user":
                continue
            previous_page = _page_path(row)
            break
        if previous_page != current_page_path:
            return HistorySelection((), "independent", "new_page_reference")

    episodes: list[list[Any]] = []
    anchors: list[str] = []
    last_page = None
    previous_row = None
    for row in rows:
        content = str(row["content"])
        if str(row["role"]) == "user":
            row_page = _page_path(row)
            page_changed = row_page and row_page != last_page and (
                _PAGE.search(content) or _IMPLICIT_PAGE.fullmatch(content.strip())
            ) and not _RECALL.search(content)
            row_time = _message_time(row)
            stale_ack = previous_row is not None and row_time is not None and _stale_acknowledgement(
                [previous_row], content, as_of=row_time,
            )
            starts_topic = stale_ack or page_changed or _GREETING.fullmatch(content.strip()) or _RESET.search(content.strip()) or (
                _standalone(content) and anchors and not topics_overlap(content, anchors[-1])
            )
            if not episodes or starts_topic:
                episodes.append([])
                anchors.append(content)
            elif _standalone(content):
                anchors[-1] += "\n" + content
            last_page = row_page
        if episodes:
            episodes[-1].append(row)
        previous_row = row

    if not episodes:
        return HistorySelection((), "independent", "no_user_anchor")
    if not _dependent(query) and not _standalone(query):
        return HistorySelection(tuple(rows), "ambiguous", "insufficient_topic_signal")
    if _dependent(query):
        return HistorySelection(tuple(episodes[-1]), "followup", "latest_topic_reference")
    for episode, anchor in reversed(list(zip(episodes, anchors))):
        if topics_overlap(query, anchor):
            return HistorySelection(tuple(episode), "related", "matching_user_topic")
    return HistorySelection((), "independent", "new_standalone_question")


def page_is_relevant(query: str, page: Any) -> bool:
    if page is None:
        return False
    if _PAGE.search(query):
        return True
    if getattr(page, "page_type", None) in {"problem", "library/chapter"} and _IMPLICIT_PAGE.fullmatch(query.strip()):
        return True
    subject = " ".join(str(getattr(page, key, "") or "") for key in ("title", "heading"))
    if topics_overlap(query, subject):
        return True
    problem_id = getattr(page, "problem_id", None)
    return problem_id is not None and bool(re.search(rf"(?<!\d){problem_id}(?!\d)", query))


def action_context_is_relevant(query: str, selection: HistorySelection, *, pending: bool = False) -> bool:
    if _ACTION.search(query):
        return True
    if pending and _ACKNOWLEDGEMENT.fullmatch(query.strip()) and selection.reason != "stale_acknowledgement":
        return True
    return selection.mode in {"followup", "recall"} and any(
        _ACTION.search(str(row["content"])) for row in selection.rows
    )
