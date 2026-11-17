"""Collect public JD.com and Alibaba job-search results without login.

The official APIs return complete duty/qualification fields. To respect the
request not to reproduce whole job descriptions, this script stores metadata,
field lengths/hashes, short excerpts and coded requirements; source pages remain
the place to read the original JD.

Run from the workspace with:
  E:\\python\\python.exe analysis/collect_public_jobs.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_tencent import SKILLS, AI, INFRA, POST, APP  # shared coding dictionary

ACCESS_DATE = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()
PAGE_SIZE = 50
REQUEST_PAUSE = 0.18

JD_BASE = "https://zhaopin.jd.com"
JD_SEARCH_TERMS = [
    "Agent", "大模型", "智能体", "AI", "AIGC", "LLM", "AI Agent",
    "大模型应用", "推理", "后训练", "强化学习", "MCP", "RAG",
]

ALI_BASE = "https://talent.alibaba.com"
ALI_SEARCH_TERMS = [
    "Agent", "大模型", "智能体", "AI应用", "AI应用开发", "AI应用研发",
    "RAG", "LLM", "MCP", "AIGC", "推理", "后训练", "强化学习",
]

def dump(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json_or_text(response: requests.Response) -> Any:
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text.strip()


def extract_experience(text: str) -> str:
    patterns = [
        r"\d+\s*(?:年以上|年及以上|年工作经验|年相关经验|年经验)",
        r"\d+\s*[-至~—]\s*\d+\s*年(?:以上)?",
        r"(?:经验不限|不限经验|无经验要求|应届毕业生|应届生|校招|实习生)",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = re.sub(r"\s+", "", match.group(0))
            if value not in found:
                found.append(value)
    return "；".join(found[:4]) if found else "未明示"


def infer_seniority(title: str, text: str, campus: bool = False) -> str:
    if campus or re.search(r"校招|应届|毕业生|实习", title + " " + text):
        return "校招/应届"
    if re.search(r"首席|资深专家|高级专家|架构师|总监", title):
        return "资深/专家（按职称词推断）"
    if re.search(r"高级|资深", title):
        return "高级（按职称词推断）"
    if re.search(r"专家", title):
        return "专家（按职称词推断）"
    return "未明示"


def short_quote(text: str, limit: int = 16) -> str:
    """Return one contiguous original excerpt of 15-16 Han characters if possible."""
    cleaned = re.sub(r"^[\s\d.、:：()（）]+", "", text or "")
    for line in re.split(r"[\r\n。；;！？!?]", cleaned):
        match = re.search(rf"[\u4e00-\u9fff]{{15,{limit}}}", line)
        if match:
            return match.group(0)
    return ""


def directions(title: str, duty: str) -> tuple[list[str], str]:
    text = title + " " + duty
    tags: list[str] = []
    if AI.search(text):
        if INFRA.search(text):
            tags.append("AI Infra")
        if POST.search(text):
            tags.append("后训练")
        if APP.search(text):
            tags.append("AI应用/Agent")
        if not tags:
            tags.append("其他AI技术")
    if len(tags) > 1:
        primary = next((x for x in ["AI应用/Agent", "AI Infra", "后训练"] if x in tags), tags[0])
    else:
        primary = tags[0] if tags else "关键词检索命中，需人工复核"
    return tags, primary


def title_direction(title: str) -> str:
    """Higher-precision candidate label based only on employer-supplied title."""
    if INFRA.search(title or ""):
        return "AI Infra候选"
    if POST.search(title or ""):
        return "后训练候选"
    if APP.search(title or ""):
        return "AI应用/Agent候选"
    if AI.search(title or ""):
        return "其他AI技术候选"
    return "未命中AI标题规则"


def topic_tags(text: str) -> list[str]:
    """Non-exhaustive, paraphrased topic labels; never quotes source prose."""
    checks = [
        ("Agent/智能体研发与编排", r"agent|智能体|多智能体"),
        ("模型应用/RAG/知识检索", r"rag|检索增强|知识库|向量检索|知识问答"),
        ("工具调用/协议接入", r"tool.?call|function.?call|工具调用|mcp|api接入"),
        ("推理服务/性能优化", r"推理|inference|低延迟|吞吐|性能优化"),
        ("后训练/对齐/微调", r"后训练|post.?train|sft|微调|强化学习|rlhf|grpo|dpo|对齐"),
        ("模型训练/数据/评测", r"训练|数据集|数据构建|合成数据|benchmark|评测|评估"),
        ("AI产品/业务场景交付", r"应用|产品|业务场景|运营|客户|工作流"),
        ("工程平台/服务稳定性", r"平台|infra|部署|服务化|稳定性|可观测|安全"),
    ]
    return [label for label, pattern in checks if re.search(pattern, text or "", re.I)]


def skill_hits(text: str) -> list[str]:
    return [name for name, pattern in SKILLS.items() if re.search(pattern, text or "", re.I)]


def make_record(company: str, title: str, duty: str, requirement: str, *,
                ident: str, category: Any, location: Any, posting_date: str,
                url: str, department: str = "", experience_field: str = "",
                campus: bool = False, raw_query: list[str] | None = None,
                availability: str = "官网本次公开列表返回；未确认剩余HC") -> dict[str, Any]:
    combined = (duty or "") + "\n" + (requirement or "")
    tags, primary = directions(title, duty or "")
    category_value = category if isinstance(category, (str, list)) else (category or "未知")
    return {
        "id": f"{company}-{ident}",
        "company": company,
        "title": title or "未知",
        "category": category_value,
        "seniority": infer_seniority(title or "", requirement or "", campus),
        "location": location or "未知",
        "experience": experience_field or extract_experience(requirement or ""),
        "degree": [degree for degree in ["本科", "硕士", "博士"] if degree in (requirement or "")],
        "salary": "未知（公开接口未提供）",
        "url": url,
        "source_type": "雇主官方公开招聘API；完整职责/要求字段已读取，原文不批量复刻",
        "access_date": ACCESS_DATE,
        "posted_date": posting_date or "未知",
        "availability": availability,
        "short_quote": short_quote(duty or requirement or ""),
        "skills_in_responsibility": skill_hits(duty or ""),
        "skills_in_requirement": skill_hits(requirement or ""),
        "education_mentions": [degree for degree in ["本科", "硕士", "博士"] if degree in (requirement or "")],
        "detail_status": "full" if duty and requirement else "partial",
        "responsibility_chars": len(duty or ""),
        "requirement_chars": len(requirement or ""),
        "text_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "direction_tags": tags,
        "primary_direction": primary,
        "title_direction": title_direction(title or ""),
        "responsibility_summary": topic_tags(duty or ""),
        "requirements_summary": topic_tags(requirement or ""),
        "field_availability": {
            "responsibility": bool(duty), "requirements": bool(requirement),
            "location": bool(location), "posting_date": bool(posting_date),
            "salary": False, "experience": bool(experience_field or extract_experience(requirement or "") != "未明示"),
        },
        "department": department or "未知",
        "matched_queries": sorted(set(raw_query or [])),
    }


def jd_request(session: requests.Session, endpoint: str, payload: dict[str, Any]) -> Any:
    response = session.post(
        JD_BASE + endpoint,
        data=payload,
        headers={
            "Origin": JD_BASE,
            "Referer": JD_BASE + "/web/job/job_info_list/3",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=35,
    )
    return get_json_or_text(response)


def collect_jd() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
    by_id: dict[str, dict[str, Any]] = {}
    query_audit: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    raw_rows = 0
    for term in JD_SEARCH_TERMS:
        base = {"workCityJson": "[]", "jobTypeJson": "[]", "jobSearch": term, "depTypeJson": "[]"}
        try:
            before_ids = set(by_id)
            reported = int(jd_request(session, "/web/job/job_count", base))
            fetched = 0
            pages = math.ceil(reported / PAGE_SIZE)
            for page in range(1, pages + 1):
                time.sleep(REQUEST_PAUSE)
                response = jd_request(session, "/web/job/job_list", {**base, "pageIndex": page, "pageSize": PAGE_SIZE})
                rows = json.loads(response) if isinstance(response, str) else response
                raw_rows += len(rows)
                fetched += len(rows)
                for row in rows:
                    requirement_id = str(row.get("requirementId") or row.get("id") or "")
                    if not requirement_id:
                        continue
                    record = make_record(
                        "京东", row.get("positionNameOpen") or row.get("positionName") or "未知",
                        row.get("workContent") or "", row.get("qualification") or "",
                        ident=requirement_id, category=row.get("jobType") or "未知",
                        location=row.get("workCity") or "未知",
                        posting_date=row.get("formatPublishTime") or "未知",
                        url=f"{JD_BASE}/web/job-info-detail?requementId={requirement_id}",
                        department=row.get("positionDeptName") or "",
                        raw_query=[term],
                    )
                    record["requirement_number"] = row.get("reqNumber") or "未知"
                    record["position_id"] = row.get("positionId") or "未知"
                    record["department"] = row.get("positionDeptName") or "未知"
                    record["category_raw"] = row.get("jobType") or "未知"
                    record["category_code"] = row.get("jobTypeCode") or "未知"
                    record["position_name_raw"] = row.get("positionName") or "未知"
                    record["position_name_open_raw"] = row.get("positionNameOpen") or "未知"
                    record["position_level_raw"] = row.get("positionLevel") or "未知"
                    record["availability"] = "JD官网公开职位列表本次返回；页面未提供剩余HC确认"
                    if requirement_id in by_id:
                        record["matched_queries"] = sorted(set(by_id[requirement_id]["matched_queries"] + [term]))
                    by_id[requirement_id] = record
            query_audit.append({"query": term, "reported_total": reported, "pages_requested": pages,
                                "rows_fetched": fetched,
                                "new_unique_ids": len(set(by_id) - before_ids),
                                "overlap_rows": fetched - len(set(by_id) - before_ids)})
        except Exception as exc:
            errors.append({"company": "京东", "query": term, "error": str(exc)})
            query_audit.append({"query": term, "error": str(exc)})
    records = sorted(by_id.values(), key=lambda x: (x.get("posted_date", ""), x["id"]), reverse=True)
    audit = {
        "employer": "京东",
        "access_date": ACCESS_DATE,
        "source_scope": "zhaopin.jd.com public job_count/job_list endpoints; targeted queries; no login",
        "queries": query_audit,
        "raw_query_rows": raw_rows,
        "unique_positions": len(records),
        "detail_full": sum(x["detail_status"] == "full" for x in records),
        "detail_partial": sum(x["detail_status"] != "full" for x in records),
        "errors": errors,
        "skill_dictionary": SKILLS,
        "limitation": "Keyword search is a targeted non-probability snapshot. The endpoint exposes full detail fields but the dataset retains only hashes, character counts, short excerpts and coded summaries; unknown salary/experience/degree is not inferred as absent. API return does not confirm remaining headcount.",
    }
    return records, audit


def alibaba_request(session: requests.Session, csrf: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        ALI_BASE + "/position/search",
        params={"_csrf": csrf},
        json=payload,
        headers={
            "Origin": ALI_BASE,
            "Referer": ALI_BASE + "/off-campus/position-list?lang=zh",
            "X-XSRF-TOKEN": csrf,
        },
        timeout=45,
    )
    data = response.json()
    response.raise_for_status()
    if not data.get("success"):
        raise RuntimeError(f"Alibaba API error {data.get('errorCode')}: {data.get('errorMsg')}")
    return data.get("content") or {}


def collect_alibaba() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
    landing = session.get(ALI_BASE + "/off-campus/position-list?lang=zh", timeout=35)
    landing.raise_for_status()
    csrf = session.cookies.get("XSRF-TOKEN")
    if not csrf:
        raw = landing.headers.get("Set-Cookie", "")
        match = re.search(r"XSRF-TOKEN=([^;,]+)", raw)
        csrf = match.group(1) if match else ""
    if not csrf:
        raise RuntimeError("Could not obtain anonymous XSRF token from the public landing page")
    by_id: dict[str, dict[str, Any]] = {}
    query_audit: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    raw_rows = 0
    for term in ALI_SEARCH_TERMS:
        fetched = 0
        pages = 0
        try:
            before_ids = set(by_id)
            payload = {"batchId": "", "corpCode": "", "pageIndex": 1, "pageSize": PAGE_SIZE,
                       "key": term, "categoryType": "off-campus", "channel": "group_official_site", "language": "zh"}
            first = alibaba_request(session, csrf, payload)
            total = int(first.get("totalCount") or 0)
            page_total = math.ceil(total / PAGE_SIZE)
            page_payloads = [first]
            for page in range(2, page_total + 1):
                time.sleep(REQUEST_PAUSE)
                next_payload = {**payload, "pageIndex": page}
                page_payloads.append(alibaba_request(session, csrf, next_payload))
            pages = len(page_payloads)
            for page_data in page_payloads:
                rows = page_data.get("datas") or []
                raw_rows += len(rows)
                fetched += len(rows)
                for row in rows:
                    pid = str(row.get("id") or "")
                    if not pid:
                        continue
                    duty = row.get("description") or ""
                    requirement = row.get("requirement") or ""
                    record = make_record(
                        "阿里巴巴", row.get("name") or "未知", duty, requirement,
                        ident=pid, category=row.get("categories") or "未知",
                        location=row.get("workLocations") or "未知",
                        posting_date=(dt.datetime.fromtimestamp(row["publishTime"] / 1000, dt.timezone(dt.timedelta(hours=8))).date().isoformat()
                                      if row.get("publishTime") else "未知"),
                        url=ALI_BASE + f"/off-campus/position-detail?positionId={pid}",
                        campus=False, raw_query=[term],
                        availability="阿里巴巴官网‘全部开放职位’API本次返回；未确认剩余HC",
                    )
                    record["position_id"] = pid
                    record["category_raw"] = row.get("categories") or []
                    record["work_locations_raw"] = row.get("workLocations") or []
                    record["publish_timestamp_ms"] = row.get("publishTime")
                    record["updated_timestamp_ms"] = row.get("modifyTime")
                    record["graduation_time"] = row.get("graduationTime")
                    record["tags_raw"] = row.get("tags") or []
                    record["source_position_url"] = row.get("positionUrl") or record["url"]
                    record["experience_field"] = record["experience"]
                    record["degree"] = record["education_mentions"]
                    if pid in by_id:
                        record["matched_queries"] = sorted(set(by_id[pid]["matched_queries"] + [term]))
                    by_id[pid] = record
            query_audit.append({"query": term, "reported_total": total,
                                "pages_requested": pages, "rows_fetched": fetched,
                                "new_unique_ids": len(set(by_id) - before_ids),
                                "overlap_rows": fetched - len(set(by_id) - before_ids)})
        except Exception as exc:
            errors.append({"company": "阿里巴巴", "query": term, "error": str(exc)})
            query_audit.append({"query": term, "error": str(exc)})
    records = sorted(by_id.values(), key=lambda x: (x.get("posted_date", ""), x["id"]), reverse=True)
    audit = {
        "employer": "阿里巴巴",
        "access_date": ACCESS_DATE,
        "source_scope": "talent.alibaba.com anonymous public position/search endpoint, off-campus channel; targeted queries; no login",
        "queries": query_audit,
        "raw_query_rows": raw_rows,
        "unique_positions": len(records),
        "detail_full": sum(x["detail_status"] == "full" for x in records),
        "detail_partial": sum(x["detail_status"] != "full" for x in records),
        "errors": errors,
        "skill_dictionary": SKILLS,
        "limitation": "Keyword search is a targeted non-probability snapshot, limited to the official off-campus/all-open-jobs channel. Full description and requirement fields were read from the API; only hashes, character counts, one short excerpt and coded summaries are retained. Unknown salary/experience/degree is not inferred as absent. API return does not confirm remaining headcount.",
    }
    return records, audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jd, jd_audit = collect_jd()
    ali, ali_audit = collect_alibaba()
    dump("jd_bulk.json", jd)
    dump("alibaba_bulk.json", ali)
    audit = {
        "access_date": ACCESS_DATE,
        "method": "Public employer job-search APIs, anonymous sessions, no login; targeted keyword unions deduplicated by stable requirement/position IDs.",
        "companies": {"京东": jd_audit, "阿里巴巴": ali_audit},
        "caution": "The two employers use different keyword search and scope; counts must not be pooled as market-share denominators. Records are snapshots and availability means returned by public list at access time, not guaranteed remaining HC.",
    }
    dump("public_bulk_audit.json", audit)
    print(json.dumps({
        "jd_unique": len(jd), "jd_full": jd_audit["detail_full"], "jd_errors": len(jd_audit["errors"]),
        "alibaba_unique": len(ali), "alibaba_full": ali_audit["detail_full"], "alibaba_errors": len(ali_audit["errors"]),
        "audit_path": str(OUT / "public_bulk_audit.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
