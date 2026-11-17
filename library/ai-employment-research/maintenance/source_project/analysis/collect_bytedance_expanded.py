"""Collect ByteDance's publicly visible China R&D, Product, Operations, and AI job postings.

All listing responses are obtained by opening the official careers website in
Microsoft Edge and using its visible category, keyword-search, and pagination
controls. The collector does not call the API directly, inspect request
headers/bodies, reuse signatures, log in, or handle verification challenges.

Run from this project with:
    E:\python\python.exe analysis\collect_bytedance_expanded.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page, Response, TimeoutError as PlaywrightTimeoutError, sync_playwright

from collect_tencent import AI, APP, INFRA, POST, SKILLS

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
ARCHIVE = ROOT / "archives" / "bytedance"
PAGE_ARCHIVE = ARCHIVE / "search_responses"
OUTPUT = EVIDENCE / "bytedance_expanded_jobs.json"
AUDIT_OUTPUT = EVIDENCE / "bytedance_expanded_audit.json"
CHECKPOINT_OUTPUT = ARCHIVE / "collection_checkpoint.json"
POSITION_URL = "https://jobs.bytedance.com/experienced/position"
HOME_URL = "https://jobs.bytedance.com/"
POSTS_PATH = "/api/v1/search/job/posts"
PAGE_SIZE_HINT = 10
PAGE_PAUSE_SECONDS = 0.35
RESPONSE_TIMEOUT_MS = 30_000
DISPLAY_COUNT_CEILING = 10_000

# Blank-keyword pagination covers the full R&D, Product, and Operations
# top-level categories. A separate R&D large-model query keeps the previously
# verified count in scope and makes the AI subset independently reproducible.
SEARCH_PLAN: list[dict[str, str]] = [
    {"query": "", "category_scope": "研发"},
    {"query": "", "category_scope": "产品"},
    {"query": "", "category_scope": "运营"},
    {"query": "大模型", "category_scope": "研发", "expected_count_hint": "1554"},
]

PREFERRED_RE = re.compile(r"优先|加分|更佳|优先考虑|prefer(?:red)?|bonus|a plus", re.I)
REQUIRED_RE = re.compile(
    r"必须|必需|须(?:要|具备|掌握|熟悉)?|需(?:要|具备|掌握|熟悉)|要求|至少|具备|熟悉|掌握|精通|熟练|本科及以上|硕士及以上|\d+\s*年(?:以上|及以上)|有.{0,16}经验",
    re.I,
)
NUMBERED_ITEM_RE = re.compile(r"(?m)^\s*(\d{1,3})\s*[、.．)）]\s*")
TECH_ARTIFACT_RE = re.compile(
    r"系统|平台|框架|引擎|架构|算法|模型|评测|指标|数据集|工具链|代码|服务|吞吐|延迟|性能|部署|编译器|算子|训练|推理|GPU|CUDA|PyTorch|TensorRT|vLLM|SGLang|Triton|RLHF|SFT|RAG|Agent",
    re.I,
)
EXPLICIT_OUTPUT_RE = re.compile(
    r"构建|设计|开发|实现|交付|沉淀|上线|落地|优化|验证|评估|建立|主导|负责|研发|量化|监控|解决",
    re.I,
)
YEAR_RE = re.compile(r"\b\d+\s*年(?:以上|及以上|经验)?")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text(item) for item in value if text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def category_matches_scope(raw: dict[str, Any], category_scope: str) -> bool:
    category = raw.get("job_category") if isinstance(raw.get("job_category"), dict) else {}
    names: set[str] = set()
    node: Any = category
    while isinstance(node, dict):
        name = text(node.get("name"))
        if name:
            names.add(name)
        node = node.get("parent")
    return category_scope == "全部类别" or category_scope in names


def response_data_matches(
    data: dict[str, Any],
    category_scope: str,
    query: str,
    previous_ids: set[str] | None = None,
    expected_count: int | None = None,
) -> bool:
    rows = data.get("job_post_list")
    if not isinstance(rows, list):
        return False
    try:
        count = int(data.get("count"))
    except (TypeError, ValueError):
        return False
    if expected_count is not None and count != expected_count:
        return False
    if rows and category_scope != "全部类别":
        if any(not isinstance(row, dict) or not category_matches_scope(row, category_scope) for row in rows):
            return False
    if query and rows:
        query_folded = query.casefold()
        matches = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_text = "\n".join(text(row.get(key)) for key in ("title", "sub_title", "description", "requirement"))
            if query_folded in row_text.casefold():
                matches += 1
        # Search may match a title/summary field not returned in the list,
        # but a stale unfiltered page must not be accepted as a query result.
        if matches < max(1, math.ceil(len(rows) * 0.5)):
            return False
    if previous_ids is not None and rows:
        ids = {
            text(row.get("id") or row.get("job_id") or row.get("position_id") or row.get("code"))
            for row in rows if isinstance(row, dict)
        }
        if ids and ids.issubset(previous_ids):
            return False
    return True


def exact_search_response(
    page: Page,
    action: Callable[[], Any],
    category_scope: str,
    query: str,
    previous_ids: set[str] | None = None,
    expected_count: int | None = None,
) -> tuple[Response, bytes, dict[str, Any]]:
    """Capture a successful normal response whose rows match the visible UI action."""
    accepted: dict[str, Any] = {}

    def predicate(response: Response) -> bool:
        if POSTS_PATH not in response.url or response.request.method != "POST" or response.status != 200:
            return False
        try:
            body = response.body()
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("code") != 0:
                return False
            data = payload.get("data")
            if not isinstance(data, dict) or not response_data_matches(
                data, category_scope, query, previous_ids, expected_count
            ):
                return False
            accepted.update({"body": body, "data": data})
            return True
        except Exception:
            return False

    with page.expect_response(predicate, timeout=RESPONSE_TIMEOUT_MS) as response_info:
        action()
    response = response_info.value
    body = accepted.get("body") or response.body()
    data = accepted.get("data")
    if data is None:
        payload = json.loads(body.decode("utf-8"))
        data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Official page response has no data object")
    return response, body, data


def open_position_list(page: Page, first: bool) -> None:
    if first:
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.get_by_role("button", name="稍后再说").click(timeout=4_000)
        except PlaywrightTimeoutError:
            pass
        page.get_by_role("link", name="所有职位").click(timeout=25_000)
    else:
        # This URL was observed as the destination of the official "所有职位"
        # link; navigating to it is ordinary page navigation, not an API call.
        page.goto(POSITION_URL, wait_until="domcontentloaded", timeout=60_000)
    page.get_by_role("textbox", name="搜索职位").wait_for(timeout=30_000)
    page.get_by_role("treeitem").filter(has_text="研发").first.wait_for(timeout=20_000)
    # Let the unfiltered landing list finish before applying a category. Its
    # response can otherwise arrive after the click and look like the result.
    page.wait_for_timeout(1_200)


def visible_challenge(page: Page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return False
    return any(term in body for term in ("安全验证", "滑动验证", "请完成验证", "验证码验证"))


def apply_category_filter(
    page: Page, category_scope: str, query: str = ""
) -> tuple[Response, bytes, dict[str, Any]] | None:
    if category_scope == "全部类别":
        return None
    tree = page.get_by_role("treeitem").filter(has_text=category_scope).first
    return exact_search_response(
        page,
        lambda: tree.locator(".atsx-tree-checkbox").click(timeout=20_000),
        category_scope,
        "",
    )


def split_numbered_items(value: str) -> tuple[str, list[dict[str, Any]]]:
    raw = value or ""
    matches = list(NUMBERED_ITEM_RE.finditer(raw))
    if not matches:
        return "", ([{"number": None, "text": raw.strip()}] if raw.strip() else [])
    prefix = raw[: matches[0].start()].strip()
    items: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        clause = raw[match.end() : end].strip()
        if clause:
            items.append({"number": int(match.group(1)), "text": clause})
    return prefix, items


def requirement_clauses(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for item in items:
        segments = [part.strip() for part in re.split(r"[；;]\s*", item["text"]) if part.strip()]
        for segment in segments:
            has_preferred = bool(PREFERRED_RE.search(segment))
            has_required = bool(REQUIRED_RE.search(segment))
            if has_preferred and has_required:
                level = "mixed_or_ambiguous"
            elif has_preferred:
                level = "preferred_explicit"
            elif has_required:
                level = "required_explicit_or_requirement_section"
            else:
                level = "priority_unspecified"
            clauses.append({"item_number": item.get("number"), "text": segment, "level": level})
    return clauses


def get_country(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    info = raw.get("job_post_info")
    if not isinstance(info, dict):
        return None, None
    addresses = info.get("address_list")
    if isinstance(addresses, list) and addresses:
        first = addresses[0] if isinstance(addresses[0], dict) else {}
        country = first.get("country")
        if isinstance(country, dict) and country.get("name"):
            return text(country.get("name")), "job_post_info.address_list[0].country.name"
    address = text(info.get("address"))
    if address:
        if "中国大陆" in address:
            return "中国大陆", "job_post_info.address"
        return None, "job_post_info.address (country not structured)"
    return None, None


def publish_time_iso(value: Any) -> str | None:
    try:
        milliseconds = int(value)
        return dt.datetime.fromtimestamp(
            milliseconds / 1000, tz=dt.timezone(dt.timedelta(hours=8))
        ).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def canonical_record(
    raw: dict[str, Any],
    source_occurrences: list[dict[str, Any]],
    versions: list[dict[str, Any]],
) -> dict[str, Any]:
    post_id = text(raw.get("id") or raw.get("job_id") or raw.get("position_id") or raw.get("code"))
    title = text(raw.get("title") or raw.get("name"))
    description = text(raw.get("description"))
    requirement = text(raw.get("requirement"))
    description_prefix, responsibility_items = split_numbered_items(description)
    _, requirement_items = split_numbered_items(requirement)
    req_clauses = requirement_clauses(requirement_items)
    combined = "\n".join((title, description, requirement))
    responsibility_hits = [name for name, pattern in SKILLS.items() if re.search(pattern, description, re.I)]
    requirement_hits = [name for name, pattern in SKILLS.items() if re.search(pattern, requirement, re.I)]
    is_ai = bool(AI.search(combined))
    is_infra = bool(INFRA.search(combined))
    full_text_hash = hashlib.sha256((description + "\n" + requirement).encode("utf-8")).hexdigest()
    raw_hash = hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    category = raw.get("job_category") if isinstance(raw.get("job_category"), dict) else {}
    parent = category.get("parent") if isinstance(category.get("parent"), dict) else {}
    category_name = text(category.get("name"))
    parent_name = text(parent.get("name"))
    category_path = (
        f"{parent_name} - {category_name}"
        if parent_name and category_name and parent_name != category_name
        else category_name or parent_name
    )
    city_info = raw.get("city_info") if isinstance(raw.get("city_info"), dict) else {}
    city = text(city_info.get("name")) or None
    country, country_source = get_country(raw)
    if not description and not requirement:
        detail_status = "list_only"
    elif description and requirement:
        detail_status = "full"
    else:
        detail_status = "partial"
    in_research_category = any(item.get("category_filter") == "研发" for item in source_occurrences)
    if is_infra:
        primary_direction = "AI Infra"
    elif POST.search(combined):
        primary_direction = "后训练"
    elif APP.search(combined):
        primary_direction = "AI应用/Agent"
    elif is_ai:
        primary_direction = "其他AI技术"
    elif in_research_category:
        primary_direction = "其他技术"
    else:
        primary_direction = "其他/非AI"
    direction_tags: list[str] = []
    if is_ai:
        direction_tags.append("AI/机器学习")
    if is_infra:
        direction_tags.append("AI Infra")
    if POST.search(combined):
        direction_tags.append("后训练")
    if APP.search(combined):
        direction_tags.append("AI应用/Agent")
    preferred_items = [clause["text"] for clause in req_clauses if clause["level"] == "preferred_explicit"]
    required_items = [clause["text"] for clause in req_clauses if clause["level"] == "required_explicit_or_requirement_section"]
    ambiguous_items = [clause["text"] for clause in req_clauses if clause["level"] == "mixed_or_ambiguous"]
    unspecified_items = [clause["text"] for clause in req_clauses if clause["level"] == "priority_unspecified"]
    duties = [item["text"] for item in responsibility_items]
    overview = f"岗位聚焦“{title}”。"
    if description_prefix:
        overview += f"团队/业务背景：{description_prefix}。"
    if duties:
        overview += "核心职责：" + "；".join(duties) + "。"
    elif description:
        overview += "职责原文：" + description
    if required_items:
        overview += "明确要求：" + "；".join(required_items) + "。"
    if preferred_items:
        overview += "明确加分项：" + "；".join(preferred_items) + "。"
    if ambiguous_items:
        overview += "同时含要求与加分措辞、需结合原文判断：" + "；".join(ambiguous_items) + "。"
    if unspecified_items:
        overview += "要求栏中未明示优先级：" + "；".join(unspecified_items) + "。"
    if not requirement:
        overview += "官网列表响应未返回任职要求正文。"

    skill_set = sorted(set(responsibility_hits + requirement_hits))
    verifiable_requirement_signals = []
    if re.search(r"本科|硕士|博士|学士|学历", requirement):
        verifiable_requirement_signals.append("学历条件")
    if YEAR_RE.search(requirement):
        verifiable_requirement_signals.append("年限条件")
    if skill_set:
        verifiable_requirement_signals.append("可核对技能/技术名词")
    explicit_outputs = sorted(
        {
            term
            for term in ("系统", "平台", "框架", "引擎", "架构", "算法", "模型", "评测", "指标", "数据集", "工具链", "服务", "部署", "编译器", "算子")
            if term in description
        }
    )
    actionable = bool(EXPLICIT_OUTPUT_RE.search(description))
    quality_score = (
        min(len(responsibility_items), 4)
        + min(len(skill_set), 3)
        + min(len(verifiable_requirement_signals), 2)
        + (1 if preferred_items else 0)
        + (1 if actionable and explicit_outputs else 0)
    )
    quality_reasons = []
    if len(responsibility_items) >= 3:
        quality_reasons.append(f"职责拆分为{len(responsibility_items)}条，便于核对交付边界")
    if explicit_outputs:
        quality_reasons.append("职责点名了可核验产物/技术对象：" + "、".join(explicit_outputs[:6]))
    if skill_set:
        quality_reasons.append("技能/技术词可核对：" + "、".join(skill_set[:8]))
    if required_items and preferred_items:
        quality_reasons.append("要求栏同时能区分明确要求与加分项")
    elif preferred_items:
        quality_reasons.append("原文明确标注加分项")

    return {
        "company": "字节跳动",
        "source_job_id": post_id,
        "source_post_code": text(raw.get("code")) or None,
        "title": title,
        "subtitle": text(raw.get("sub_title")) or None,
        "source_url": f"https://jobs.bytedance.com/experienced/position/{post_id}/detail" if post_id else POSITION_URL,
        "source_list_url": POSITION_URL,
        "source": "字节跳动公开招聘官网职位列表页正常响应",
        "collection_method": "Microsoft Edge公开页面；职位类别/关键词/分页均经可见官网UI操作",
        "collected_at": source_occurrences[0]["captured_at"] if source_occurrences else now_iso(),
        "source_occurrences": source_occurrences,
        "detail_status": detail_status,
        "description": description,
        "requirement": requirement,
        "responsibility_context": description_prefix,
        "responsibility_items": responsibility_items,
        "requirement_items": requirement_items,
        "requirement_clauses_with_level": req_clauses,
        "requirements_explicitly_required": required_items,
        "requirements_explicitly_preferred": preferred_items,
        "requirements_mixed_or_ambiguous": ambiguous_items,
        "requirements_priority_unspecified": unspecified_items,
        "requirement_level_policy": "只把明确出现必须/要求/需具备等词的条目标为required；明确出现优先/加分等词的条目标为preferred；混合或未明示层级的条目保留为独立状态，不从文本外推。",
        "summary_zh": overview,
        "experience_mentions": sorted(set(re.findall(r"\d+\s*年(?:以上|及以上|经验)?", requirement))),
        "education_mentions": [term for term in ("本科", "硕士", "博士") if term in requirement],
        "skills_in_requirement": requirement_hits,
        "skills_in_responsibility": responsibility_hits,
        "skills_matched": skill_set,
        "ai_broad_flag": is_ai,
        "infra_flag": is_infra,
        "ai_relevant_flag": bool(is_ai or is_infra),
        "primary_direction": primary_direction,
        "direction_tags": direction_tags,
        "job_category": category_name or None,
        "job_category_path": category_path or category_name or None,
        "city": city,
        "country": country,
        "country_source": country_source,
        "recruit_type": text((raw.get("recruit_type") or {}).get("name")) if isinstance(raw.get("recruit_type"), dict) else None,
        "publish_time_raw": raw.get("publish_time"),
        "publish_time": publish_time_iso(raw.get("publish_time")),
        "experience_raw": text(raw.get("experience") or raw.get("require_work_years") or (raw.get("job_post_info") or {}).get("experience")) or None,
        "status_raw": raw.get("status") or raw.get("IsValid"),
        "text_sha256": full_text_hash,
        "raw_record_sha256": raw_hash,
        "source_text_versions": versions,
        "jd_quality_review": {
            "heuristic_score": quality_score,
            "signals": {
                "responsibility_item_count": len(responsibility_items),
                "explicit_output_terms": explicit_outputs,
                "verifiable_requirement_signals": verifiable_requirement_signals,
                "explicit_preferred_item_count": len(preferred_items),
                "actionable_verb_present": actionable,
            },
            "reasons": quality_reasons,
        },
    }


def safe_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug[:32] or "query"


def archive_response(
    body: bytes,
    query_index: int,
    query: str,
    category_scope: str,
    page_number: int,
) -> dict[str, Any]:
    scope = {"研发": "rd", "产品": "product", "运营": "operations", "全部类别": "all"}.get(
        category_scope, safe_slug(category_scope) or "all"
    )
    name = f"q{query_index:02d}_{scope}_{safe_slug(query)}_page_{page_number:04d}.json"
    target = PAGE_ARCHIVE / name
    target.write_bytes(body)
    return {
        "query_index": query_index,
        "query": query,
        "category_scope": category_scope,
        "page_number": page_number,
        "source_url": POSITION_URL,
        "http_status": 200,
        "page_state": "official UI list response accepted after category/query validation",
        "path": str(target.relative_to(ROOT)).replace("\\", "/"),
        "response_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "archived_at": now_iso(),
    }


def archive_file_path(query_index: int, query: str, category_scope: str, page_number: int) -> Path:
    scope = {"研发": "rd", "产品": "product", "运营": "operations", "全部类别": "all"}.get(
        category_scope, safe_slug(category_scope) or "all"
    )
    return PAGE_ARCHIVE / f"q{query_index:02d}_{scope}_{safe_slug(query)}_page_{page_number:04d}.json"


def load_valid_archived_page(
    query_index: int,
    query: str,
    category_scope: str,
    page_number: int,
    expected_count: int,
) -> tuple[dict[str, Any], bytes, dict[str, Any]] | None:
    path = archive_file_path(query_index, query, category_scope, page_number)
    if not path.exists():
        return None
    body = path.read_bytes()
    try:
        payload = json.loads(body.decode("utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or payload.get("code") != 0:
            return None
        if not response_data_matches(data, category_scope, query, expected_count=expected_count):
            return None
        rows = data.get("job_post_list")
        if not isinstance(rows, list) or not rows:
            return None
        archived = {
            "query_index": query_index,
            "query": query,
            "category_scope": category_scope,
            "page_number": page_number,
            "source_url": POSITION_URL,
            "http_status": 200,
            "page_state": "previous official UI response; category and displayed total revalidated from archive",
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "response_bytes": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "archived_at": dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat(timespec="seconds"),
            "reused_existing_official_response": True,
        }
        return data, body, archived
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def write_checkpoint(query_audit: dict[str, Any], archive_manifest: list[dict[str, Any]]) -> None:
    CHECKPOINT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    last_archive = query_audit["archive_paths"][-1] if query_audit.get("archive_paths") else None
    checkpoint = {
        "updated_at": now_iso(),
        "current_query": query_audit.get("query"),
        "current_category_filter": query_audit.get("category_filter"),
        "current_page_number": query_audit.get("page_numbers_captured", [])[-1] if query_audit.get("page_numbers_captured") else None,
        "reported_count": query_audit.get("reported_count_initial"),
        "expected_pages": query_audit.get("pages_expected_from_displayed_count"),
        "pages_captured_in_current_query": query_audit.get("pages_captured"),
        "last_response_archive": last_archive,
        "archive_pages_in_current_run": len(archive_manifest),
    }
    temporary = CHECKPOINT_OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(CHECKPOINT_OUTPUT)


def current_page_number(page: Page) -> int | None:
    try:
        raw = page.locator("li.atsx-pagination-item-active").get_attribute("title", timeout=2_000)
        return int(raw) if raw and raw.isdigit() else None
    except Exception:
        return None


def collect_query(
    page: Page,
    plan: dict[str, str],
    query_index: int,
    first_navigation: bool,
    all_raw: dict[str, dict[str, Any]],
    occurrences: dict[str, list[dict[str, Any]]],
    versions: dict[str, dict[str, dict[str, Any]]],
    archive_manifest: list[dict[str, Any]],
    response_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    query = plan["query"]
    category_scope = plan["category_scope"]
    query_audit: dict[str, Any] = {
        "query_index": query_index,
        "query": query,
        "category_filter": category_scope,
        "started_at": now_iso(),
        "reported_count_initial": None,
        "reported_counts_seen": [],
        "page_size_observed": None,
        "pages_expected_from_displayed_count": None,
        "pages_captured": 0,
        "rows_received": 0,
        "unique_ids_seen_in_query": 0,
        "unique_ai_relevant_ids_seen_in_query": 0,
        "count_at_display_ceiling": False,
        "pagination_complete_for_displayed_count": False,
        "page_numbers_captured": [],
        "reused_valid_archived_pages": 0,
        "pages_fetched_in_current_run": 0,
        "archive_paths": [],
        "errors": [],
    }
    ai_ids_for_query: set[str] = set()
    try:
        open_position_list(page, first=first_navigation)
        if visible_challenge(page):
            query_audit["errors"].append("页面出现验证界面；按边界停止，不处理验证码")
            query_audit["stopped_for_verification"] = True
            query_audit["unique_ai_relevant_ids_seen_in_query"] = len(ai_ids_for_query)
            query_audit["finished_at"] = now_iso()
            return query_audit

        filter_response = apply_category_filter(page, category_scope)
        if query == "" and filter_response is not None:
            response, body, data = filter_response
        else:
            search = page.get_by_role("textbox", name="搜索职位")
            response, body, data = exact_search_response(
                page,
                lambda: (search.fill(query), search.press("Enter")),
                category_scope,
                query,
                expected_count=(int(plan["expected_count_hint"]) if plan.get("expected_count_hint") else None),
            )
        first_page = data.get("job_post_list")
        if not isinstance(first_page, list):
            raise ValueError("Official list response did not contain job_post_list")
        total = data.get("count")
        try:
            total_int = int(total) if total is not None else None
        except (TypeError, ValueError):
            total_int = None
        query_audit["reported_count_initial"] = total_int
        query_audit["reported_counts_seen"].append(total_int)
        if not response_data_matches(data, category_scope, query):
            raise ValueError("Captured first-page response does not match selected category/search")
        page_size = len(first_page) or PAGE_SIZE_HINT
        query_audit["page_size_observed"] = page_size
        expected_pages = math.ceil(total_int / page_size) if total_int and page_size else 0
        query_audit["pages_expected_from_displayed_count"] = expected_pages
        query_audit["count_at_display_ceiling"] = bool(total_int is not None and total_int >= DISPLAY_COUNT_CEILING)
        query_audit["page_size_control_visible_in_pagination"] = bool(
            page.locator(".atsx-pagination select, .atsx-pagination [role=combobox]").count()
        )

        def ingest(
            page_no: int,
            payload_data: dict[str, Any],
            raw_body: bytes,
            existing_archive: dict[str, Any] | None = None,
        ) -> None:
            archived = existing_archive or archive_response(raw_body, query_index, query, category_scope, page_no)
            archived["http_status"] = 200
            archived["page_state"] = (
                "previous official UI response; category and displayed total revalidated from archive"
                if existing_archive
                else ("visible first-page response matched selected category/query" if page_no == 1 else "visible next-page action completed; active page number confirmed")
            )
            archive_manifest.append(archived)
            query_audit["archive_paths"].append(archived["path"])
            query_audit["pages_captured"] += 1
            query_audit["page_numbers_captured"].append(page_no)
            if existing_archive:
                query_audit["reused_valid_archived_pages"] += 1
            else:
                query_audit["pages_fetched_in_current_run"] += 1
            rows = payload_data.get("job_post_list")
            if not isinstance(rows, list):
                query_audit["errors"].append(f"第{page_no}页无job_post_list数组")
                return
            query_audit["rows_received"] += len(rows)
            reported = payload_data.get("count")
            try:
                reported_value = int(reported) if reported is not None else None
            except (TypeError, ValueError):
                reported_value = None
            if reported_value not in query_audit["reported_counts_seen"]:
                query_audit["reported_counts_seen"].append(reported_value)
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                job_id = text(raw.get("id") or raw.get("job_id") or raw.get("position_id") or raw.get("code"))
                if not job_id:
                    query_audit.setdefault("rows_without_id", 0)
                    query_audit["rows_without_id"] += 1
                    continue
                captured_at = (
                    archived.get("archived_at")
                    if existing_archive and archived.get("archived_at")
                    else now_iso()
                )
                text_hash = hashlib.sha256(
                    (text(raw.get("description")) + "\n" + text(raw.get("requirement"))).encode("utf-8")
                ).hexdigest()
                occurrence = {
                    "query": query,
                    "category_filter": category_scope,
                    "page_number": page_no,
                    "http_status": archived["http_status"],
                    "page_state": archived["page_state"],
                    "captured_at": captured_at,
                    "archive_path": archived["path"],
                    "archive_response_sha256": archived["body_sha256"],
                    "text_sha256": text_hash,
                }
                occurrences.setdefault(job_id, []).append(occurrence)
                if job_id not in all_raw:
                    all_raw[job_id] = raw
                    versions.setdefault(job_id, {})[text_hash] = {
                        "description": text(raw.get("description")),
                        "requirement": text(raw.get("requirement")),
                        "first_seen": occurrence,
                    }
                else:
                    if text_hash not in versions.setdefault(job_id, {}):
                        versions[job_id][text_hash] = {
                            "description": text(raw.get("description")),
                            "requirement": text(raw.get("requirement")),
                            "first_seen": occurrence,
                        }
                all_text = "\n".join((text(raw.get("title")), text(raw.get("description")), text(raw.get("requirement"))))
                if AI.search(all_text) or INFRA.search(all_text):
                    ai_ids_for_query.add(job_id)
            write_checkpoint(query_audit, archive_manifest)

        ingest(1, data, body)
        if visible_challenge(page):
            query_audit["errors"].append("页面出现验证界面；按边界停止，不处理验证码")
            query_audit["stopped_for_verification"] = True
            query_audit["unique_ai_relevant_ids_seen_in_query"] = len(ai_ids_for_query)
            query_audit["finished_at"] = now_iso()
            return query_audit

        # The visible list exposes no per-page-size selector; the response
        # page size is measured from page 1 and pagination is followed normally.
        target_pages = expected_pages if expected_pages > 0 else 1
        cached_pages: dict[int, tuple[dict[str, Any], bytes, dict[str, Any]]] = {}
        if target_pages > 1 and total_int is not None:
            for cached_no in range(2, target_pages + 1):
                cached = load_valid_archived_page(
                    query_index, query, category_scope, cached_no, total_int
                )
                if cached is None:
                    cached_pages.clear()
                    break
                cached_pages[cached_no] = cached
        can_reuse_all_cached_pages = len(cached_pages) == max(0, target_pages - 1)
        query_audit["cached_pages_reused_as_a_complete_tail"] = can_reuse_all_cached_pages
        previous_page_ids = {
            text(row.get("id") or row.get("job_id") or row.get("position_id") or row.get("code"))
            for row in first_page if isinstance(row, dict)
        }
        for page_no in range(2, target_pages + 1):
            if can_reuse_all_cached_pages:
                cached_data, cached_body, cached_archive = cached_pages[page_no]
                ingest(page_no, cached_data, cached_body, cached_archive)
                if page_no % 25 == 0:
                    emit({"event": "query_progress", "query": query, "category_filter": category_scope, "pages_captured": page_no, "pages_expected": target_pages, "reused_existing_archives": True})
                continue
            next_button = page.locator("li.atsx-pagination-next")
            if next_button.count() == 0:
                query_audit["errors"].append(f"到第{page_no}页前未找到可见下一页控件")
                break
            klass = text(next_button.first.get_attribute("class"))
            if "disabled" in klass:
                query_audit["errors"].append(f"第{page_no - 1}页的下一页控件已禁用")
                break
            try:
                next_response, next_body, next_data = exact_search_response(
                    page,
                    lambda: next_button.first.click(timeout=20_000),
                    category_scope,
                    query,
                    previous_ids=previous_page_ids,
                    expected_count=total_int,
                )
            except PlaywrightTimeoutError as exc:
                failure = {
                    "query": query,
                    "category_filter": category_scope,
                    "page_number": page_no,
                    "error": "未在可见下一页操作后收到正常200职位列表响应；未重试",
                    "detail": str(exc).splitlines()[0][:200],
                    "captured_at": now_iso(),
                }
                response_failures.append(failure)
                query_audit["errors"].append(failure["error"])
                if visible_challenge(page):
                    query_audit["stopped_for_verification"] = True
                break
            try:
                page.wait_for_function(
                    "expected => { const e = document.querySelector('li.atsx-pagination-item-active'); return !!e && e.title === String(expected); }",
                    arg=page_no,
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:
                actual_page = current_page_number(page)
                query_audit["errors"].append(
                    f"官网列表响应虽匹配查询，但活动页码未确认第{page_no}页（显示{actual_page}）；停止此条件"
                )
                break
            actual_page = current_page_number(page)
            if actual_page is not None and actual_page != page_no:
                query_audit["errors"].append(f"期望第{page_no}页，但页面当前页码显示{actual_page}；停止此条件")
                break
            ingest(page_no, next_data, next_body)
            previous_page_ids = {
                text(row.get("id") or row.get("job_id") or row.get("position_id") or row.get("code"))
                for row in (next_data.get("job_post_list") or []) if isinstance(row, dict)
            }
            if next_response.status != 200:
                query_audit["errors"].append(f"第{page_no}页HTTP状态{next_response.status}")
                break
            if page_no % 25 == 0:
                emit({"event": "query_progress", "query": query, "category_filter": category_scope, "pages_captured": page_no, "pages_expected": target_pages})
            if page_no < target_pages:
                time.sleep(PAGE_PAUSE_SECONDS)

        query_audit["pagination_complete_for_displayed_count"] = (
            (
                query_audit["pages_captured"] == target_pages
                and not query_audit["errors"]
                and (expected_pages > 0 or (total_int == 0 and not first_page))
            )
        )
        query_audit["unique_ids_seen_in_query"] = len(
            {job_id for job_id, where in occurrences.items() if any(o["query"] == query and o["category_filter"] == category_scope for o in where)}
        )
        query_audit["unique_ai_relevant_ids_seen_in_query"] = len(ai_ids_for_query)
        query_audit["finished_at"] = now_iso()
        return query_audit
    except PlaywrightTimeoutError as exc:
        query_audit["errors"].append("页面或职位列表响应超时；未重试：" + str(exc).splitlines()[0][:200])
        query_audit["finished_at"] = now_iso()
        query_audit["stopped_for_verification"] = visible_challenge(page)
        query_audit["unique_ai_relevant_ids_seen_in_query"] = len(ai_ids_for_query)
        return query_audit
    except Exception as exc:
        query_audit["errors"].append(f"{type(exc).__name__}: {str(exc)[:240]}")
        query_audit["finished_at"] = now_iso()
        query_audit["stopped_for_verification"] = visible_challenge(page)
        query_audit["unique_ai_relevant_ids_seen_in_query"] = len(ai_ids_for_query)
        return query_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="run the isolated Edge browser headless")
    parser.add_argument("--queries", nargs="*", help="optional exact query terms to run; default is the full collection plan")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PAGE_ARCHIVE.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    all_raw: dict[str, dict[str, Any]] = {}
    occurrences: dict[str, list[dict[str, Any]]] = {}
    versions: dict[str, dict[str, dict[str, Any]]] = {}
    archive_manifest: list[dict[str, Any]] = []
    response_failures: list[dict[str, Any]] = []
    query_audits: list[dict[str, Any]] = []
    if args.queries:
        selected = set(args.queries)
        plan = [item for item in SEARCH_PLAN if item["query"] in selected]
        missing = sorted(selected - {item["query"] for item in plan})
        if missing:
            print("Unknown query terms: " + ", ".join(missing), file=sys.stderr)
            return 2
    else:
        plan = SEARCH_PLAN

    audit: dict[str, Any] = {
        "schema_version": 1,
        "started_at": started_at,
        "employer": "字节跳动",
        "source_site": "https://jobs.bytedance.com/",
        "source_list_url": POSITION_URL,
        "access_method": "在Microsoft Edge中打开官网公开职位页，通过可见研发类别、关键词搜索和分页控件取得正常职位列表响应；不直接调用API、不读取请求头/请求体、不提取/重建签名、不登录、不处理验证码。",
        "scope": "中国招聘门户中，研发、产品、运营三个官网顶级类别的空关键词分页；研发类别按官网显示数量完整分页，并另采研发类“大模型”关键词搜索。按官方职位ID跨条件去重，并分别标记AI/Infra相关性。",
        "category_filter": "研发、产品、运营树节点均由官网UI选择；全类别补充项不应用类别过滤",
        "query_plan": plan,
        "page_size_control_check": "页面UI未显示每页条数选择器；抓取响应每页条数记录在各查询审计中；本次不改写或直接提交分页参数。",
        "reported_count_ceiling": DISPLAY_COUNT_CEILING,
        "count_ceiling_note": "官网列表在查询达到10000时只显示10000；该值记为显示上限，不当作准确总体职位数。",
        "dedupe_key": "官方列表响应中的id（source_job_id）",
        "requirement_level_policy": "明确必须/要求/需具备等标记才分类为required；明确优先/加分等标记才分类为preferred；混合和未标注层级单列，不把推断写成原文事实。",
        "query_audits": query_audits,
        "archive_manifest": archive_manifest,
        "response_failures": response_failures,
        "limitations": [],
    }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=bool(args.headless))
            page = browser.new_page(locale="zh-CN", viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(20_000)
            first_navigation = True
            stopped_for_verification = False
            try:
                for query_index, item in enumerate(plan, start=1):
                    result = collect_query(
                        page,
                        item,
                        query_index,
                        first_navigation,
                        all_raw,
                        occurrences,
                        versions,
                        archive_manifest,
                        response_failures,
                    )
                    first_navigation = False
                    query_audits.append(result)
                    emit({
                        "event": "query_complete",
                        "query": item["query"],
                        "category_filter": item["category_scope"],
                        "reported_count": result.get("reported_count_initial"),
                        "pages_captured": result.get("pages_captured"),
                        "pages_expected": result.get("pages_expected_from_displayed_count"),
                        "errors": result.get("errors", []),
                    })
                    if result.get("stopped_for_verification"):
                        stopped_for_verification = True
                        break
            finally:
                browser.close()
    except Exception as exc:
        audit["fatal_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    all_records = []
    for job_id, raw in all_raw.items():
        occurrence_list = occurrences.get(job_id, [])
        version_map = versions.get(job_id, {})
        version_values = list(version_map.values())
        record = canonical_record(raw, occurrence_list, version_values if len(version_values) > 1 else [])
        all_records.append(record)
    all_records.sort(key=lambda record: (record["primary_direction"], record["title"], record["source_job_id"]))
    OUTPUT.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")

    full = sum(record["detail_status"] == "full" for record in all_records)
    audit.update({
        "finished_at": now_iso(),
        "unique_listing_ids_before_ai_relevance_filter": len(all_raw),
        "unique_ai_relevant_postings": sum(record["ai_relevant_flag"] for record in all_records),
        "unique_non_ai_technical_postings": sum(record["primary_direction"] == "其他技术" for record in all_records),
        "detail_status_counts": {
            "full_from_list_response": full,
            "partial": sum(record["detail_status"] == "partial" for record in all_records),
            "list_only": sum(record["detail_status"] == "list_only" for record in all_records),
        },
        "skill_hits_in_requirements": {},
        "skill_hits_in_responsibilities": {},
        "skill_dictionary": {
            name: (pattern.pattern if hasattr(pattern, "pattern") else str(pattern))
            for name, pattern in SKILLS.items()
        },
        "classification_patterns": {
            "ai": AI.pattern,
            "infra": INFRA.pattern,
            "posttraining": POST.pattern,
            "application_agent": APP.pattern,
        },
        "direction_counts": {},
        "country_counts": {},
        "archive_directory": str(ARCHIVE.relative_to(ROOT)).replace("\\", "/"),
        "archive_response_files": len(archive_manifest),
        "archive_response_bytes": sum(item["response_bytes"] for item in archive_manifest),
        "output_file": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "stopped_for_verification": bool(locals().get("stopped_for_verification", False)),
    })
    for record in all_records:
        for skill in record["skills_in_requirement"]:
            audit["skill_hits_in_requirements"][skill] = audit["skill_hits_in_requirements"].get(skill, 0) + 1
        for skill in record["skills_in_responsibility"]:
            audit["skill_hits_in_responsibilities"][skill] = audit["skill_hits_in_responsibilities"].get(skill, 0) + 1
        audit["direction_counts"][record["primary_direction"]] = audit["direction_counts"].get(record["primary_direction"], 0) + 1
        country = record["country"] or "列表响应未提供国家字段"
        audit["country_counts"][country] = audit["country_counts"].get(country, 0) + 1
    audit["country_mainland_china_count"] = sum(
        count for country, count in audit["country_counts"].items() if country in {"中国大陆", "中国"}
    )
    audit["country_unstructured_or_unknown_count"] = audit["country_counts"].get("列表响应未提供国家字段", 0)
    quality_pool = [record for record in all_records if record["ai_relevant_flag"]] or all_records
    audit["high_clarity_candidates_scope"] = "AI/Infra相关职位优先；若无则退回全采集范围"
    quality_candidates = sorted(
        quality_pool,
        key=lambda record: (
            record["jd_quality_review"]["heuristic_score"],
            len(record["responsibility_items"]),
            len(record["skills_matched"]),
            record["source_job_id"],
        ),
        reverse=True,
    )[:5]
    audit["high_clarity_candidates"] = [
        {
            "source_job_id": record["source_job_id"],
            "source_post_code": record["source_post_code"],
            "title": record["title"],
            "source_url": record["source_url"],
            "heuristic_score": record["jd_quality_review"]["heuristic_score"],
            "reasons": record["jd_quality_review"]["reasons"],
            "duty_item_count": len(record["responsibility_items"]),
            "skills_in_requirement": record["skills_in_requirement"],
            "explicit_required_count": len(record["requirements_explicitly_required"]),
            "explicit_preferred_count": len(record["requirements_explicitly_preferred"]),
        }
        for record in quality_candidates
    ]
    if not all_records:
        audit["limitations"].append("本次未生成AI相关具体职位记录；请检查query_audits和response_failures。")
    if any(item.get("count_at_display_ceiling") for item in query_audits):
        audit["limitations"].append("至少一个搜索条件达到官网10000条显示上限；对应分页已按页面展示范围采集，但不据此声称总体职位总数精确。")
    if any(not item.get("pagination_complete_for_displayed_count") for item in query_audits):
        audit["limitations"].append("至少一个搜索条件没有完整到达官网显示的末页；逐条件的实际页数与错误已记录。")
    if stopped_for_verification:
        audit["limitations"].append("官网出现验证界面后停止；没有处理验证码或绕过验证。")
    AUDIT_OUTPUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    emit({
        "event": "collection_saved",
        "unique_postings": len(all_records),
        "full_details_from_list_response": full,
        "archive_pages": len(archive_manifest),
        "jobs_file": str(OUTPUT),
        "audit_file": str(AUDIT_OUTPUT),
        "stopped_for_verification": audit["stopped_for_verification"],
    })
    return 1 if audit.get("fatal_error") or any(item.get("errors") for item in query_audits) else 0


if __name__ == "__main__":
    raise SystemExit(main())
