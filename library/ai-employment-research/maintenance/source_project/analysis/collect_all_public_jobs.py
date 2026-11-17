"""Fetch full anonymous official position lists from JD and Alibaba.

No login or verification bypass is used. Duties and requirements are processed
in memory; outputs retain official URLs, field availability, hashes, one short
excerpt, and coded topic/skill mentions rather than whole JD bodies.

Run: E:\\python\\python.exe analysis/collect_all_public_jobs.py
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

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_tencent import SKILLS  # use the shared, current skill dictionary

TZ = dt.timezone(dt.timedelta(hours=8))
PAGE_SIZE = 100
PAUSE = 0.12
JD_BASE = "https://zhaopin.jd.com"
ALI_BASE = "https://talent.alibaba.com"


def now_iso() -> str:
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def han_quote(text: str, minimum: int = 15, maximum: int = 16) -> str:
    """Pick one contiguous excerpt with 15-16 Han characters when possible."""
    if not text:
        return ""
    # Prefer an excerpt within one sentence and avoid taking more than 35 total
    # source characters. It remains verbatim; only the excerpt is retained.
    for sentence in re.split(r"[\r\n。；;！？!?]", text):
        sentence = sentence.strip()
        for start in range(len(sentence)):
            han = 0
            stop = min(len(sentence), start + 35)
            for end in range(start, stop):
                if "\u4e00" <= sentence[end] <= "\u9fff":
                    han += 1
                if han == minimum:
                    return sentence[start:end + 1]
                if han > maximum:
                    break
    return ""


def extract_experience(text: str, raw: Any = None) -> str:
    if raw not in (None, "", "未知"):
        return str(raw)
    patterns = [
        r"\d+\s*(?:年以上|年及以上|年工作经验|年相关经验|年经验)",
        r"\d+\s*[-至~—]\s*\d+\s*年(?:以上)?",
        r"(?:经验不限|不限经验|无经验要求|应届毕业生|应届生|校招|实习生)",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", re.I):
            phrase = re.sub(r"\s+", "", match.group(0))
            if phrase not in found:
                found.append(phrase)
    return "；".join(found[:4]) if found else "未明示"


def skill_hits(text: str) -> list[str]:
    return [key for key, pattern in SKILLS.items() if re.search(pattern, text or "", re.I)]


def topic_tags(text: str) -> list[str]:
    # Paraphrased labels only; no long copied strings from the employer's JD.
    checks = [
        ("Agent/智能体", r"agent|智能体|多智能体"),
        ("RAG/知识检索", r"rag|检索增强|知识库|向量检索|知识问答"),
        ("工具/协议集成", r"tool.?call|function.?call|工具调用|mcp|api接入"),
        ("推理/服务性能", r"推理|inference|低延迟|吞吐|性能优化"),
        ("后训练/对齐/微调", r"后训练|post.?train|sft|微调|强化学习|rlhf|grpo|dpo|对齐"),
        ("训练/数据/评测", r"训练|数据集|数据构建|合成数据|benchmark|评测|评估"),
        ("产品/业务交付", r"应用|产品|业务场景|运营|客户|工作流"),
        ("工程平台/稳定性", r"平台|infra|部署|服务化|稳定性|可观测|安全"),
    ]
    return [label for label, pattern in checks if re.search(pattern, text or "", re.I)]


def degree_mentions(requirement: str) -> list[str]:
    return [level for level in ["本科", "硕士", "博士"] if level in (requirement or "")]


def to_date(value: Any) -> str:
    if value in (None, "", 0):
        return "未知"
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, TZ).date().isoformat()
    text = str(value).strip()
    return text[:10] if text else "未知"


def unique_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value != "" else []


def build_record(*, company: str, ident: str, title: str, duty: str,
                 requirement: str, category: Any, locations: Any,
                 posting_date: Any, url: str, raw: dict[str, Any],
                 manual_quote_ids: set[tuple[str, str]]) -> dict[str, Any]:
    full_text = (duty or "") + "\n" + (requirement or "")
    source_fields = {str(k): v for k, v in raw.items() if k in {
        "id", "positionId", "requirementId", "positionCode", "reqNumber",
        "positionName", "positionNameOpen", "positionDeptName", "positionDeptCodeFullpath",
        "positionSubsequence", "positionType", "positionLevel", "positionLevelCode", "lvlName",
        "lvlCode", "jobType", "jobTypeCode", "categories", "workLocations", "workCity",
        "workCityCode", "regionEnNameMap", "interviewLocations", "country", "countryName",
        "countryCode", "graduationTime", "publishTime", "formatPublishTime", "modifyTime",
        "status", "salary", "experience", "requireWorkYears", "tags"
    }}
    city_values = unique_text_list(locations)
    country = raw.get("countryName") or raw.get("country") or raw.get("countryCode") or "未明示"
    raw_experience = raw.get("RequireWorkYearsName") or raw.get("requireWorkYears") or raw.get("experience") or raw.get("lvlName")
    quote = "" if (company, ident) in manual_quote_ids else han_quote(duty or requirement)
    return {
        "id": f"{company}-{ident}",
        "company": company,
        "position_id": str(raw.get("positionId") or raw.get("id") or ident),
        "requirement_id": str(raw.get("requirementId") or "未知"),
        "title": title or "未知",
        "position_name_raw": raw.get("positionName") or "未知",
        "position_name_open_raw": raw.get("positionNameOpen") or "未知",
        "category": category if category not in (None, "") else "未知",
        "category_raw": category if category not in (None, "") else "未知",
        "department_raw": raw.get("positionDeptName") or raw.get("positionDeptCodeFullpath") or "未知",
        "country": str(country),
        "city": city_values,
        "city_raw": raw.get("workCity") or raw.get("workLocations") or "未知",
        "location_country_note": "国家/地区仅按API原字段记录；未明示时不从城市名推断",
        "seniority_raw": raw.get("positionLevel") or raw.get("lvlName") or "未明示",
        "experience": extract_experience(requirement, raw_experience),
        "experience_raw": str(raw_experience) if raw_experience not in (None, "") else "未提供独立年限字段",
        "degree": degree_mentions(requirement),
        "education_mentions": degree_mentions(requirement),
        "salary": str(raw.get("salary")) if raw.get("salary") not in (None, "") else "未知（API未返回）",
        "url": url,
        "source_type": "雇主官方匿名公开职位API；详情字段在内存读取，原文未批量保存",
        "access_date": dt.datetime.now(TZ).date().isoformat(),
        "posted_date": to_date(posting_date),
        "availability": "官网公开职位列表API本次返回；不代表剩余HC或HR确认",
        "short_quote": quote,
        "skills_in_responsibility": skill_hits(duty),
        "skills_in_requirement": skill_hits(requirement),
        "responsibility_summary": topic_tags(duty),
        "requirements_summary": topic_tags(requirement),
        "detail_status": "full" if duty and requirement else "partial",
        "field_availability": {
            "responsibility": bool(duty), "requirements": bool(requirement),
            "category": category not in (None, ""), "city": bool(city_values),
            "country": country != "未明示", "experience": raw_experience not in (None, "") or extract_experience(requirement) != "未明示",
            "education_mentions": bool(degree_mentions(requirement)),
            "salary": raw.get("salary") not in (None, ""), "posted_date": posting_date not in (None, "", 0),
        },
        "responsibility_chars": len(duty or ""),
        "requirement_chars": len(requirement or ""),
        "text_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
        "source_fields_raw": source_fields,
    }


def read_manual_quote_ids() -> set[tuple[str, str]]:
    path = OUT / "application_jds.json"
    ids: set[tuple[str, str]] = set()
    if not path.exists():
        return ids
    try:
        manual = json.loads(path.read_text(encoding="utf-8"))
        for row in manual:
            company = row.get("company")
            url = row.get("url") or row.get("official_url") or ""
            if company == "京东":
                match = re.search(r"requementId=(\d+)", url)
                if match:
                    ids.add((company, match.group(1)))
            elif company == "阿里巴巴":
                match = re.search(r"position(?:Id|/)(\d+)", url)
                if match:
                    ids.add((company, match.group(1)))
    except Exception:
        pass
    return ids


def jd_post(session: requests.Session, endpoint: str, payload: dict[str, Any]) -> Any:
    response = session.post(
        JD_BASE + endpoint, data=payload, timeout=40,
        headers={"Origin": JD_BASE, "Referer": JD_BASE + "/web/job/job_info_list/3",
                 "X-Requested-With": "XMLHttpRequest"},
    )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text.strip()


def collect_jd(manual_quote_ids: set[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
    query = {"workCityJson": "[]", "jobTypeJson": "[]", "jobSearch": "", "depTypeJson": "[]"}
    reported = int(jd_post(session, "/web/job/job_count", query))
    first = jd_post(session, "/web/job/job_list", {**query, "pageIndex": 1, "pageSize": PAGE_SIZE})
    rows = first if isinstance(first, list) else json.loads(first)
    effective_size = len(rows) if 0 < len(rows) < PAGE_SIZE and reported > len(rows) else PAGE_SIZE
    pages = math.ceil(reported / effective_size) if effective_size else 0
    page_log = [{"page": 1, "rows": len(rows)}]
    raw_rows = list(rows)
    errors: list[dict[str, Any]] = []
    for page in range(2, pages + 1):
        time.sleep(PAUSE)
        try:
            result = jd_post(session, "/web/job/job_list", {**query, "pageIndex": page, "pageSize": effective_size})
            page_rows = result if isinstance(result, list) else json.loads(result)
            raw_rows.extend(page_rows)
            page_log.append({"page": page, "rows": len(page_rows)})
        except Exception as exc:
            errors.append({"page": page, "error": str(exc)})
            page_log.append({"page": page, "error": str(exc)})
    dedup: dict[str, dict[str, Any]] = {}
    duplicate_rows = 0
    missing_id = 0
    for row in raw_rows:
        ident = str(row.get("requirementId") or row.get("id") or "")
        if not ident:
            missing_id += 1
            continue
        if ident in dedup:
            duplicate_rows += 1
            continue
        url = f"{JD_BASE}/web/job-info-detail?requementId={ident}"
        dedup[ident] = build_record(
            company="京东", ident=ident,
            title=row.get("positionNameOpen") or row.get("positionName") or "未知",
            duty=row.get("workContent") or "", requirement=row.get("qualification") or "",
            category=row.get("jobType") or "未知", locations=row.get("workCity") or "未知",
            posting_date=row.get("formatPublishTime") or row.get("publishTime"), url=url,
            raw=row, manual_quote_ids=manual_quote_ids,
        )
        dedup[ident]["category_code"] = row.get("jobTypeCode") or "未知"
        dedup[ident]["department_path_raw"] = row.get("positionDeptCodeFullpath") or "未知"
        dedup[ident]["position_subsequence_raw"] = row.get("positionSubsequence") or "未知"
        dedup[ident]["request_number"] = row.get("reqNumber") or "未知"
        dedup[ident]["position_code"] = row.get("positionCode") or "未知"
    records = sorted(dedup.values(), key=lambda x: (x["posted_date"], x["id"]), reverse=True)
    audit = {
        "employer": "京东", "scope": "official public social/open job listing; blank keyword; no login",
        "access_date": dt.datetime.now(TZ).date().isoformat(), "query_keyword": "",
        "reported_total_initial": reported, "page_size_requested": PAGE_SIZE,
        "page_size_effective": effective_size, "pages_expected": pages,
        "pages_fetched": len([p for p in page_log if "rows" in p]), "page_log": page_log,
        "raw_rows_fetched": len(raw_rows), "unique_positions": len(records),
        "duplicate_rows": duplicate_rows, "rows_missing_id": missing_id,
        "detail_full": sum(r["detail_status"] == "full" for r in records),
        "detail_partial": sum(r["detail_status"] != "full" for r in records),
        "short_quote_missing": sum(not r["short_quote"] for r in records),
        "errors": errors, "skill_dictionary": SKILLS,
        "limitation": "Single official list snapshot. Exact publication date is retained only where returned. Full duty/requirement fields were processed in memory and represented by hashes, lengths, skill/topic coding and one excerpt; unknown values remain unknown. List response does not confirm remaining headcount.",
    }
    return records, audit


def ali_post(session: requests.Session, csrf: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = session.post(
        ALI_BASE + "/position/search", params={"_csrf": csrf}, json=payload,
        headers={"Origin": ALI_BASE, "Referer": ALI_BASE + "/off-campus/position-list?lang=zh",
                 "X-XSRF-TOKEN": csrf}, timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"Alibaba API error {data.get('errorCode')}: {data.get('errorMsg')}")
    return data.get("content") or {}


def collect_alibaba(manual_quote_ids: set[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
    landing = session.get(ALI_BASE + "/off-campus/position-list?lang=zh", timeout=40)
    landing.raise_for_status()
    csrf = session.cookies.get("XSRF-TOKEN")
    if not csrf:
        match = re.search(r"XSRF-TOKEN=([^;,]+)", landing.headers.get("Set-Cookie", ""))
        csrf = match.group(1) if match else ""
    if not csrf:
        raise RuntimeError("Anonymous XSRF token unavailable on public Alibaba landing page")
    base = {"batchId": "", "corpCode": "", "pageIndex": 1, "pageSize": PAGE_SIZE,
            "key": "", "categoryType": "off-campus", "channel": "group_official_site", "language": "zh"}
    first = ali_post(session, csrf, base)
    reported = int(first.get("totalCount") or 0)
    first_rows = first.get("datas") or []
    effective_size = len(first_rows) if 0 < len(first_rows) < PAGE_SIZE and reported > len(first_rows) else PAGE_SIZE
    pages = math.ceil(reported / effective_size) if effective_size else 0
    page_data = [first]
    page_log = [{"page": 1, "rows": len(first_rows), "reported_total": reported}]
    errors: list[dict[str, Any]] = []
    for page in range(2, pages + 1):
        time.sleep(PAUSE)
        try:
            content = ali_post(session, csrf, {**base, "pageIndex": page, "pageSize": effective_size})
            page_data.append(content)
            page_log.append({"page": page, "rows": len(content.get("datas") or []),
                             "reported_total": content.get("totalCount")})
        except Exception as exc:
            errors.append({"page": page, "error": str(exc)})
            page_log.append({"page": page, "error": str(exc)})
    rows: list[dict[str, Any]] = []
    for content in page_data:
        rows.extend(content.get("datas") or [])
    dedup: dict[str, dict[str, Any]] = {}
    duplicate_rows = 0
    missing_id = 0
    for row in rows:
        ident = str(row.get("id") or "")
        if not ident:
            missing_id += 1
            continue
        if ident in dedup:
            duplicate_rows += 1
            continue
        url = f"{ALI_BASE}/off-campus/position-detail?positionId={ident}"
        record = build_record(
            company="阿里巴巴", ident=ident, title=row.get("name") or "未知",
            duty=row.get("description") or "", requirement=row.get("requirement") or "",
            category=row.get("categories") or "未知", locations=row.get("workLocations") or [],
            posting_date=row.get("publishTime"), url=url, raw=row,
            manual_quote_ids=manual_quote_ids,
        )
        record.update({
            "category_raw": row.get("categories") or "未知",
            "work_locations_raw": row.get("workLocations") or [],
            "region_en_name_map_raw": row.get("regionEnNameMap") or {},
            "interview_locations_raw": row.get("interviewLocations") or [],
            "updated_date": to_date(row.get("modifyTime")),
            "graduation_time_raw": row.get("graduationTime"),
            "tags_raw": row.get("tags") or [],
            "source_position_url": row.get("positionUrl") or url,
            "country": str(row.get("countryName") or row.get("country") or row.get("countryCode") or "未明示"),
        })
        record["field_availability"]["country"] = record["country"] != "未明示"
        dedup[ident] = record
    records = sorted(dedup.values(), key=lambda x: (x["posted_date"], x["id"]), reverse=True)
    audit = {
        "employer": "阿里巴巴", "scope": "official public all-open jobs API, group off-campus channel; blank key; no login",
        "access_date": dt.datetime.now(TZ).date().isoformat(), "query_keyword": "",
        "reported_total_initial": reported, "page_size_requested": PAGE_SIZE,
        "page_size_effective": effective_size, "pages_expected": pages,
        "pages_fetched": len(page_data), "page_log": page_log,
        "raw_rows_fetched": len(rows), "unique_positions": len(records),
        "duplicate_rows": duplicate_rows, "rows_missing_id": missing_id,
        "detail_full": sum(r["detail_status"] == "full" for r in records),
        "detail_partial": sum(r["detail_status"] != "full" for r in records),
        "short_quote_missing": sum(not r["short_quote"] for r in records),
        "errors": errors, "skill_dictionary": SKILLS,
        "limitation": "Scope is the official group off-campus/all-open-jobs channel, not the separate campus portal. Single snapshot. Country is retained only from an explicit API field; city names are not assumed to imply country. Full duty/requirement fields were processed in memory and represented by hashes, lengths, skill/topic coding and one excerpt; list response does not confirm remaining headcount.",
    }
    return records, audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = now_iso()
    manual_quote_ids = read_manual_quote_ids()
    jd, jd_audit = collect_jd(manual_quote_ids)
    ali, ali_audit = collect_alibaba(manual_quote_ids)
    dump(OUT / "jd_all_bulk.json", jd)
    dump(OUT / "alibaba_all_bulk.json", ali)
    audit = {
        "started_at": started, "finished_at": now_iso(),
        "run_result": {"exit_code": 0, "status": "completed; observed process exit code 0"},
        "method": "Anonymous public employer list APIs; no login and no verification bypass; blank-key full list; deduplicate by stable position ID.",
        "companies": {"京东": jd_audit, "阿里巴巴": ali_audit},
        "combined_unique_positions": len(jd) + len(ali),
        "caution": "Company counts have different scopes and should not be pooled into a market-share denominator. Full descriptions are not reproduced; all access/capture counts and field completeness are auditable.",
    }
    dump(OUT / "all_public_bulk_audit.json", audit)
    print(json.dumps({
        "jd_reported": jd_audit["reported_total_initial"], "jd_fetched": len(jd),
        "jd_full": jd_audit["detail_full"], "jd_errors": len(jd_audit["errors"]),
        "alibaba_reported": ali_audit["reported_total_initial"], "alibaba_fetched": len(ali),
        "alibaba_full": ali_audit["detail_full"], "alibaba_errors": len(ali_audit["errors"]),
        "combined": len(jd) + len(ali),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
