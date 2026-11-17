"""Conservative probe for ByteDance's public China jobs endpoint.

This collector only uses ordinary unauthenticated HTTP. It does not emulate a
browser fingerprint, obtain a signature, use cookies, or bypass a challenge.
If the public JSON endpoint returns a normal response, it paginates a bounded
set of AI/Infra searches, deduplicates by posting ID, and records the fields
actually returned. If the endpoint is unavailable, the result remains empty
and the reason is written to evidence/bytedance_collection_audit.json.

Run from this folder with E:\\python\\python.exe analysis/collect_bytedance.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

# Use the same auditable skills vocabulary and broad-direction patterns as the
# Tencent collector for cross-company feature parity.
from collect_tencent import AI, INFRA, SKILLS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence"
API = "https://jobs.bytedance.com/api/v1/search/job/posts"
DETAIL_URL = "https://jobs.bytedance.com/experienced/position/{id}/detail"
KEYWORDS = ["AI", "大模型", "训练", "推理", "算子", "GPU", "Infra"]
PAGE_SIZE = 50
MAX_PAGES_PER_KEYWORD = 12
PAUSE_SECONDS = 0.6
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://jobs.bytedance.com",
    "Referer": "https://jobs.bytedance.com/experienced/position",
    "Content-Type": "application/json",
}


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(text(v) for v in value if text(v))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def parse_json_response(response: requests.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def rows_and_total(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    data = payload.get("data") or payload.get("Data") or {}
    if not isinstance(data, dict):
        return [], None
    rows = data.get("job_post_list") or data.get("posts") or data.get("list") or []
    total = data.get("count") or data.get("total") or data.get("Count")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return ([r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else [], total)


def canonical_record(raw: dict[str, Any], keyword: str) -> dict[str, Any]:
    post_id = str(raw.get("id") or raw.get("job_id") or raw.get("position_id") or raw.get("code") or "")
    title = text(raw.get("title") or raw.get("name") or raw.get("RecruitPostName"))
    responsibility = text(
        raw.get("responsibility") or raw.get("description") or raw.get("Responsibility")
        or raw.get("job_description")
    )
    requirement = text(raw.get("requirement") or raw.get("Requirement") or raw.get("job_requirement"))
    all_text = title + "\n" + responsibility + "\n" + requirement
    detail_status = "full" if responsibility and requirement else ("partial" if responsibility or requirement else "list_only")
    posting_url = text(raw.get("url") or raw.get("post_url") or raw.get("PostURL"))
    if not posting_url and post_id:
        posting_url = DETAIL_URL.format(id=post_id)
    short_source = requirement or responsibility
    quote_chars: list[str] = []
    han_count = 0
    for ch in re.sub(r"^[\s\d.、-]+", "", short_source):
        if "\u4e00" <= ch <= "\u9fff":
            if han_count == 16:
                break
            han_count += 1
        quote_chars.append(ch)
    return {
        "id": post_id,
        "title": title,
        "url": posting_url,
        "description": responsibility,
        "requirement": requirement,
        "experience": text(raw.get("experience") or raw.get("require_work_years") or raw.get("RequireWorkYearsName")) or "未知（接口未返回）",
        "education_mentions": [x for x in ["本科", "硕士", "博士"] if x in requirement],
        "detail_status": detail_status,
        "text_sha256": hashlib.sha256((responsibility + "\n" + requirement).encode("utf-8")).hexdigest(),
        "short_quote": "".join(quote_chars),
        "skills_in_requirement": [name for name, pattern in SKILLS.items() if re.search(pattern, requirement, re.I)],
        "skills_in_responsibility": [name for name, pattern in SKILLS.items() if re.search(pattern, responsibility, re.I)],
        "ai_broad_flag": bool(AI.search(all_text)),
        "infra_flag": bool(INFRA.search(all_text)),
        "query_keyword": keyword,
        "raw_posting_date": raw.get("publish_time") or raw.get("PublishTime") or raw.get("create_time") or "",
        "raw_status": raw.get("status") or raw.get("IsValid") or "",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    started = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    audit: dict[str, Any] = {
        "started_at": started,
        "employer": "字节跳动",
        "endpoint": API,
        "access_method": "普通匿名HTTP；未发送Cookie、签名、浏览器指纹或登录信息",
        "queries": KEYWORDS,
        "page_size": PAGE_SIZE,
        "max_pages_per_keyword": MAX_PAGES_PER_KEYWORD,
        "post_probe": None,
        "get_diagnostic": None,
        "list_rows": 0,
        "unique_rows": 0,
        "ai_infra_rows": 0,
        "full_details": 0,
        "records": 0,
        "limitations": [],
    }
    session = requests.Session()
    payload = {
        "keyword": "AI Infra", "limit": 10, "offset": 0, "portal_type": 1,
        "job_category_id_list": [], "location_code_list": [], "subject_id_list": [],
    }
    try:
        response = session.post(API, json=payload, headers=HEADERS, timeout=25)
        parsed = parse_json_response(response)
        audit["post_probe"] = {
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "bytes": len(response.content),
            "json_response": parsed is not None,
            "body_prefix": " ".join(response.text[:240].split()),
        }
    except Exception as exc:
        response, parsed = None, None
        audit["post_probe"] = {"error": str(exc)}

    all_rows: dict[str, dict[str, Any]] = {}
    page_log: list[dict[str, Any]] = []
    if response is not None and response.ok and parsed is not None:
        # A successful anonymous JSON response is sufficient to use the public
        # endpoint. Stop on the first non-JSON/error response; do not retry it.
        for keyword in KEYWORDS:
            offset = 0
            for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
                body = {
                    "keyword": keyword, "limit": PAGE_SIZE, "offset": offset, "portal_type": 1,
                    "job_category_id_list": [], "location_code_list": [], "subject_id_list": [],
                }
                try:
                    r = session.post(API, json=body, headers=HEADERS, timeout=25)
                    j = parse_json_response(r)
                    if not r.ok or j is None:
                        page_log.append({"keyword": keyword, "page": page, "http_status": r.status_code, "error": "non-JSON or HTTP error; stopped without retry"})
                        break
                    rows, total = rows_and_total(j)
                    page_log.append({"keyword": keyword, "page": page, "offset": offset, "rows": len(rows), "reported_total": total})
                    if not rows:
                        break
                    audit["list_rows"] += len(rows)
                    for raw in rows:
                        canonical = canonical_record(raw, keyword)
                        if canonical["id"]:
                            all_rows.setdefault(canonical["id"], canonical)
                    offset += PAGE_SIZE
                    if total is not None and offset >= total:
                        break
                    time.sleep(PAUSE_SECONDS)
                except Exception as exc:
                    page_log.append({"keyword": keyword, "page": page, "error": str(exc)})
                    break
    else:
        # One ordinary GET is diagnostic only. The collector does not follow
        # any signature, login, CAPTCHA, or browser-runtime instructions.
        try:
            r = session.get(API, params={"keyword": "AI Infra", "limit": 10, "offset": 0, "portal_type": 1, "language": "zh"},
                            headers={"User-Agent": HEADERS["User-Agent"], "Accept": "application/json"}, timeout=25)
            audit["get_diagnostic"] = {
                "http_status": r.status_code,
                "content_type": r.headers.get("Content-Type", ""),
                "bytes": len(r.content),
                "json_response": parse_json_response(r) is not None,
                "body_prefix": " ".join(r.text[:240].split()),
            }
        except Exception as exc:
            audit["get_diagnostic"] = {"error": str(exc)}
        audit["limitations"].append("匿名POST没有返回JSON；GET诊断也未返回招聘JSON，未尝试模拟签名、登录或验证码。")

    records = [r for r in all_rows.values() if r["ai_broad_flag"] and r["infra_flag"]]
    records.sort(key=lambda x: (x["title"], x["id"]))
    audit.update({
        "finished_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        "unique_rows": len(all_rows),
        "ai_infra_rows": sum(r["ai_broad_flag"] and r["infra_flag"] for r in all_rows.values()),
        "full_details": sum(r["detail_status"] == "full" for r in records),
        "records": len(records),
        "page_log": page_log,
        "dedupe_key": "官方职位ID",
        "denominator_note": "此接口探测为单一企业公开招聘页的可访问性测试，不是招聘市场份额或全市场普查。",
    })
    (OUT / "bytedance_bulk.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "bytedance_collection_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ["list_rows", "unique_rows", "ai_infra_rows", "full_details", "records", "post_probe", "get_diagnostic"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
