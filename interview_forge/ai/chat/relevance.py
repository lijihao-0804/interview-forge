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

from interview_forge.ai.chat.page_context import PageContext


POLICY_VERSION = "chat-relevance-v3"
_RESET = re.compile(r"^(?:换个(?:话题|问题)|另一个问题|新的问题|不谈(?:这个|之前)|先不聊|重新开始|new topic\b|unrelated question\b)", re.I)
_PAST = r"(?:之前|此前|先前|以前|前面|刚才|上次|上回)"
# A time or ordering word inside a technical question need not refer to chat.
_RECALL = re.compile(
    rf"前文|(?:回顾|回查|回忆|还记得|比较|对照)(?:一下)?(?:我们?|你|咱们)?{_PAST}|"
    rf"{_PAST}(?:我们?|你|咱们)?(?:曾经?|已经|给我|所)?(?:说|讲|聊|讨论|提[到过的]|问过|回答|写过|约定|建议|学过|做过)|"
    rf"{_PAST}(?:的|那[个条道段种份])(?:答案|回答|话题|问题|消息|对话|要求|约定|计划|做法|提示|例子|代码)|"
    rf"(?:^|[，,。！？])\s*{_PAST}(?=的|那|[，,。！？]|$)|"
    r"\b(?:earlier|previous|prior|last)\s+(?:messages?|answers?|repl(?:y|ies)|chats?|discussions?|conversations?|"
    r"questions?|examples?|agreements?|topics?|suggestions?|time)\b|"
    r"\b(?:earlier|previously|last time)\s*,?\s*(?:we|you|I)\b|\b(?:we|you|I)\s+(?:earlier|previously)\b|"
    r"\b(?:we|you|I)\s+(?:(?:had|have|already|previously)\s+)?(?:say|said|ask(?:ed)?|"
    r"discuss(?:ed)?|mention(?:ed)?|suggest(?:ed)?|recommend(?:ed)?|agree(?:d)?|wrote|learn(?:ed|t)?)"
    r"\b[^.?!\n]{0,48}\b(?:before|earlier|previously)\b",
    re.I,
)
_EARLIEST_RECORD = re.compile(
    r"(?:最早|最初|最先)的?(?:(?:那|第)?一[条句则段]|那[条句则段]|约定|消息|原话|留言)|"
    r"(?:第一[条句则段]|一开始)(?:的)?(?:[^。！？\n]{0,12})(?:记录|消息|约定|原话|留言)|"
    r"\b(?:first|earliest|oldest|original|initial)\s+(?:(?:matching|recorded|chat)\s+)?"
    r"(?:message|record|agreement|note|statement|entry|quote)\b", re.I,
)
_ONLY_EARLIEST = re.compile(
    r"(?:只(?:要|看|查|读|找|引用|给)|仅(?:需|要|查|引用)?)[^。！？]{0,10}(?:最早|最初|最先)的?"
    r"(?:那?[一1]?[条句则段]|(?=$|[\s，。！？、；：,.;:!?]))|"
    r"\bonly\s+(?:the\s+)?(?:oldest|earliest|first)\s+(?:one|entry|match)\b", re.I,
)
_OMIT_LATER = re.compile(r"(?:较晚|后期|后来|最新|后续)[^。！？]{0,12}(?:略过|跳过|省略|忽略|不用|不必)|"
                         r"(?:略过|跳过|省略|忽略|不要|不用|不必)[^。！？]{0,12}(?:较晚|后期|后来|最新|后续)")
_LATER_COMPARISON = re.compile(
    r"也(?:请|要|想)?(?:查|看|列|给|说|比较|对照|引用|讲).{0,9}(?:后来|后期|较晚|最新|最近|后续)|"
    r"(?:与|和|及|以及|到|对比|比较|对照|再(?:看看?|查|说说?)|分别).{0,8}(?:后来|后期|较晚|最新|最近|后续|第二)|"
    r"\b(?:and|to|with)\s+(?:the\s+)?(?:newest|latest|later|second)\b", re.I,
)
_HISTORY_SUBJECT = re.compile(
    r"之前|聊天|对话|会话|历史|回顾|回查|留言|曾经|学习要求|约定|原话|"
    r"我(?:们|的|当时|说|提|写|发|最初|最早)|你(?:当时|说|写|发)|"
    r"\b(?:my|our|we|chat|history|conversation)\b", re.I,
)


def requests_first_history_match(query: str) -> bool:
    """Only a request for one historical source makes a later version out of scope."""
    single = (_EARLIEST_RECORD.search(query) or _ONLY_EARLIEST.search(query)
              or (_OMIT_LATER.search(query) and any(word in query for word in ("最早", "最初", "最先"))))
    return bool(single and _HISTORY_SUBJECT.search(query) and not _LATER_COMPARISON.search(query))


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
_PAGE = re.compile(
    r"这(?:个|道|一)?(?:题|页|章|段)|(?:当前|(?<!基)本)(?:页|题|章)|选中|划选|"
    r"页面(?:上|里|中|标题|内容|题号)|\b(?:(?:this|current) (?:page|problem|chapter)|selected text)\b", re.I,
)
_NUMBERED_PROBLEM = re.compile(
    r"第\s*(\d{1,9})\s*(?:道)?题|"
    r"(?:题号|题目|题|力扣|(?<![a-z0-9_])(?:leetcode|lc|problem|exercise))\s*[#＃:：]?\s*(\d{1,9})(?![\d.])|"
    r"(?<![\d.])(\d{1,9})\s*号题|(?<![\d.])(?P<shorthand>\d{1,9})\s*题", re.I,
)
_PROBLEM_COUNT = re.compile(
    r"(?:[了共剩够满这那前后]|做完|刷完|总计|合计|只有|完成|累计|至少|至多|最多|最少|超过|仅有|"
    r"(?:每[日天周月]|一[天周月]|[只仅])(?:要|只|至少)?(?:[做刷写练]|复习|重做|回顾))\s*$",
)
_GREETING = re.compile(r"^(?:你好|您好|嗨|哈喽|早上好|晚上好|在吗|谢谢|hello|hi|hey)[!！。.，,？?\s]*$", re.I)
_ACKNOWLEDGEMENT = re.compile(r"^(?:嗯|好|好的|好吧|是的|可以|开始吧)[。！？?\s]*$")
_IMPLICIT_PAGE = re.compile(r"^(?:它(?:呢|怎么做|怎么理解)?|继续|接着(?:讲|说)?)[。！？?\s]*$")
_STUDY_PAGE_START = re.compile(
    r"(?:我?(?:有点)?(?:卡住了?|没思路)[，,。\s]*)?"
    r"(?:(?:请)?(?:给我?|来)(?:一个|一点|个|点)?(?:起步|入门|第一步的?)?(?:提示|思路|线索)|"
    r"第一步(?:呢|怎么做|是什么)?|(?:我(?:应该|该|可以)?)?从哪(?:里|儿)?(?:入手|下手|开始)|"
    r"怎么(?:入手|起步|开始))"
)


def _study_page_start(query: str) -> bool:
    return bool(_STUDY_PAGE_START.fullmatch(query.strip().rstrip("。！？!?")))


def referenced_problem_ids(query: str) -> tuple[int, ...]:
    """Read problem labels and the site's '146题' shorthand, excluding exercise counts."""
    number = re.fullmatch(r"\s*[#＃]?\s*(\d{1,9})\s*[?？]?\s*", query)
    if number:
        value = int(number[1])
        return (value,) if value > 0 else ()
    ids = []
    for match in _NUMBERED_PROBLEM.finditer(query):
        if match["shorthand"] and _PROBLEM_COUNT.search(query, max(0, match.start() - 32), match.start()):
            continue
        value = int(next(group for group in match.groups() if group is not None))
        if value > 0:
            ids.append(value)
    return tuple(ids)


def topic_terms(text: str) -> set[str]:
    """Use word anchors and Chinese bigrams, excluding generic question words."""
    text = _FILLER.sub(" ", str(text).casefold())
    terms = set(re.findall(r"[a-z][a-z0-9_+#.-]*|\d+", text))
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(span[index:index + 2] for index in range(len(span) - 1))
    return terms


def topics_overlap(left: str, right: str, *, ignore_numbers: bool = False) -> bool:
    a, b = topic_terms(left), topic_terms(right)
    shared = a & b
    if ignore_numbers:
        shared = {term for term in shared if not term.isdecimal()}
    # One exact technical word/number is useful; one common Chinese bigram
    # alone is too weak unless it constitutes most of the shorter subject.
    return any(re.fullmatch(r"[a-z0-9_+#.-]+", term) for term in shared) or (
        bool(shared) and (len(shared) >= 2 or len(shared) / max(1, min(len(a), len(b))) >= .5)
    )


def _dependent(text: str) -> bool:
    return bool(_REFERENCE.search(text) or _RECALL.search(text) or _PAGE.search(text))


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


def page_identity(path: str | None, problem_id: int | None = None) -> str | None:
    if path == "/books/ai-exam/acm-playground.html" and type(problem_id) is int and problem_id > 0:
        return f"{path}#problem-{problem_id}"
    return path


def _historical_page(row: Mapping[str, Any]) -> tuple[str | None, bool]:
    try:
        metadata = json.loads(str(row["metadata_json"])) if "metadata_json" in row.keys() else {}
        page = metadata.get("page_context")
        if isinstance(page, dict):
            mode = metadata.get("study_mode", "auto")
            # Browser metadata is stored even when it was irrelevant to the
            # turn. An unrelated question on a problem page never starts that
            # problem's episode. Older path-only entries retain their boundary.
            if page.get("title") and not page_is_relevant(str(row["content"]), PageContext.from_payload(page), mode):
                return None, False
            selected = (mode in ("hint", "review", "code")
                        and page.get("page_type") in ("problem", "library/chapter"))
            return page_identity(page.get("path"), page.get("problem_id")), selected
    except (ValueError, TypeError, AttributeError):
        pass
    return None, False


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
    if requests_first_history_match(query):
        # A recent suffix (including its rolling summary) cannot establish the first
        # occurrence. Let the scoped history tool find the matching original instead.
        return HistorySelection((), "recall", "first_history_match")
    # Explicit cross-episode references may need more than the latest topic.
    if _RECALL.search(query):
        return HistorySelection(tuple(rows), "recall", "explicit_history_reference")
    episodes: list[list[Any]] = []
    anchors: list[str] = []
    last_page = None
    previous_row = None
    for row in rows:
        content = str(row["content"])
        if str(row["role"]) == "user":
            row_page, selected_study_page = _historical_page(row)
            page_start = selected_study_page and _study_page_start(content)
            page_changed = row_page and row_page != last_page and (
                _PAGE.search(content) or _IMPLICIT_PAGE.fullmatch(content.strip()) or page_start
            ) and not _RECALL.search(content)
            row_time = _message_time(row)
            stale_ack = previous_row is not None and row_time is not None and _stale_acknowledgement(
                [previous_row], content, as_of=row_time,
            )
            starts_topic = stale_ack or page_changed or _GREETING.fullmatch(content.strip()) or _RESET.search(content.strip()) or (
                not page_start and _standalone(content) and anchors and not topics_overlap(content, anchors[-1])
            )
            if not episodes or starts_topic:
                episodes.append([])
                anchors.append(content)
            elif _standalone(content):
                anchors[-1] += "\n" + content
            # Short follow-ups can continue an established page topic even
            # when this turn had no independent reason to attach the page.
            if row_page or starts_topic:
                last_page = row_page
        if episodes:
            episodes[-1].append(row)
        previous_row = row

    if not episodes:
        return HistorySelection((), "independent", "no_user_anchor")
    if current_page_path and last_page != current_page_path and (
        _PAGE.search(query) or _IMPLICIT_PAGE.fullmatch(query.strip()) or _study_page_start(query)
    ):
        return HistorySelection((), "independent", "new_page_reference")
    if current_page_path and _study_page_start(query):
        return HistorySelection(tuple(episodes[-1]), "followup", "latest_topic_reference")
    if not _dependent(query) and not _standalone(query):
        return HistorySelection(tuple(rows), "ambiguous", "insufficient_topic_signal")
    if _dependent(query):
        return HistorySelection(tuple(episodes[-1]), "followup", "latest_topic_reference")
    for episode, anchor in reversed(list(zip(episodes, anchors))):
        if topics_overlap(query, anchor):
            return HistorySelection(tuple(episode), "related", "matching_user_topic")
    return HistorySelection((), "independent", "new_standalone_question")


def page_is_relevant(query: str, page: Any, study_mode: str = "auto") -> bool:
    if page is None:
        return False
    if _PAGE.search(query):
        return True
    if getattr(page, "page_type", None) in {"problem", "library/chapter"}:
        if _IMPLICIT_PAGE.fullmatch(query.strip()) or (study_mode != "auto" and _study_page_start(query)):
            return True
    subject = " ".join(str(getattr(page, key, "") or "") for key in ("title", "heading"))
    if topics_overlap(query, subject, ignore_numbers=True):
        return True
    return getattr(page, "problem_id", None) in referenced_problem_ids(query)


def action_context_is_relevant(query: str, selection: HistorySelection, *, pending: bool = False) -> bool:
    if _ACTION.search(query):
        return True
    if pending and _ACKNOWLEDGEMENT.fullmatch(query.strip()) and selection.reason != "stale_acknowledgement":
        return True
    return selection.mode in {"followup", "recall"} and any(
        _ACTION.search(str(row["content"])) for row in selection.rows
    )
