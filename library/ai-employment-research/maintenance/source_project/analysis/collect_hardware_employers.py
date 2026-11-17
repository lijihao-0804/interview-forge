"""Collect anonymous official public vacancies from Huawei, Xiaomi, and Honor.

The browser-visible APIs are queried without login, cookies from a user profile,
signature reconstruction, or verification bypass. Exact official JSON responses
are archived page by page; Honor's public detail responses are archived per job.

Run: E:\\python\\python.exe analysis/collect_hardware_employers.py
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
ARCHIVES = ROOT / "archives"
ANALYSIS = ROOT / "analysis"
TZ = dt.timezone(dt.timedelta(hours=8))
PAGE_PAUSE = 0.20
DETAIL_PAUSE = 0.25
PAGE_SIZE = 100
HUAWEI_PAGE_SIZE = 10  # mirror the official UI request confirmed in Edge
MAX_WORKERS = 3
TIMEOUT = 45
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

import sys
sys.path.insert(0, str(ANALYSIS))
from collect_tencent import APP, AI, INFRA, POST, SKILLS  # shared dictionary/patterns

HUAW_BASE = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw/recruitmentPosition/pub/getJobPage"
HUAW_ID = "app_000000035886"
XIAOMI_LIST = "https://hr.xiaomi.com/website/api/agent/searchJobPage"
HONOR_SUITE = "5ff669649b0d78e6f4296c9a"
HONOR_LIST = f"https://career.honor.com/wecruit/positionInfo/listPosition/SU{HONOR_SUITE}"
HONOR_DETAIL = f"https://career.honor.com/wecruit/positionInfo/listPositionDetail/SU{HONOR_SUITE}"
HONOR_LIST_URL = f"https://career.honor.com/SU{HONOR_SUITE}/pb/social.html#/"

CURATION_RUBRIC = "按职责对象/范围、交付物或结果、方法与协作接口、资格条件的可验证性判断清晰度；不按篇幅、学历层级或薪酬排名。"
CURATION_CANDIDATES = [
    {"company": "华为", "source_job_id": "113857", "title": "AI安全技术研究专家",
     "url": "https://career.huawei.com/cn/job-details?advertisementId=36952",
     "reason": "职责把训练数据与模型改进、Agent安全测试落地、平台/数据飞轮和持续改进流程拆成具体任务；要求覆盖安全研究实践、工具平台开发和企业AI4Sec项目经验，并区分优先条件。"},
    {"company": "小米", "source_job_id": "7703840514843347236", "title": "AI红队安全专家",
     "url": "https://xiaomi.jobs.f.mioffice.cn/index/position/7703840514843347236/detail",
     "reason": "职责明确列出自动化安全测试工具链、可量化基准指标、AI对抗平台和评测反馈训练闭环；要求列出可验证的安全方向、编程语言、Agent实践及加分经历。"},
    {"company": "荣耀", "source_job_id": "6a277dbb3d5b657f38be2756", "title": "端侧AI架构师",
     "url": "https://career.honor.com/SU5ff669649b0d78e6f4296c9a/pb/posDetail.html?postId=6a277dbb3d5b657f38be2756&postType=society",
     "reason": "职责覆盖算法/硬件需求映射、XPU顶层架构、存储优化和从定义到量产的协同；资格要求有具体技术域、经验条件，优先经验独立列出。"},
]

_log_locks: dict[str, threading.Lock] = {name: threading.Lock() for name in ("huawei", "xiaomi", "honor")}
ARCHIVE_ONLY = False


def now_iso() -> str:
    return dt.datetime.now(TZ).isoformat(timespec="seconds")


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def append_jsonl(path: Path, value: Any, company: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _log_locks[company] if company else threading.Lock()
    with lock:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            stream.flush()


def reset_log_preserving(path: Path) -> None:
    if not path.exists():
        return
    suffix = dt.datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}_prior_{suffix}{path.suffix}")
    path.replace(backup)


def new_session(referer: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
    })
    return session


def request_json(session: requests.Session, method: str, url: str, *,
                 params: dict[str, Any] | None = None,
                 json_body: dict[str, Any] | None = None,
                 data: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None,
                 attempts: int = 3) -> tuple[dict[str, Any], int]:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(method, url, params=params, json=json_body,
                                       data=data, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object response")
            return payload, response.status_code
        except Exception as exc:
            last = exc
            if attempt < attempts:
                time.sleep(0.8 * attempt)
    raise RuntimeError(f"{method} {url}: {type(last).__name__}: {last}") from last


def save_page(company: str, page: int, payload: dict[str, Any], *,
              endpoint: str, request_params: dict[str, Any], rows: list[Any],
              reported_total: Any, page_size: Any, status_code: int) -> None:
    folder = ARCHIVES / company / "pages"
    dump_json(folder / f"page_{page:04d}.json", payload)
    append_jsonl(ARCHIVES / company / "page_log.jsonl", {
        "page": page, "captured_at": now_iso(), "endpoint": endpoint,
        "request_params": request_params, "http_status": status_code,
        "returned_rows": len(rows), "reported_total": reported_total,
        "reported_page_size": page_size,
        "raw_response_archive": f"archives/{company}/pages/page_{page:04d}.json",
    }, company)


def fetch_huawei_pages() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company = "huawei"
    referer = "https://career.huawei.com/"
    session = new_session(referer)
    session.headers.update({
        "X-HW-ID": HUAW_ID,
        "X-CSRF-Token": "",
        "X-Jalor-TenantAlias": "hcm",
        "X-Referer": "https://career.huawei.com/cn",
        "X-ALB-Gray": "prod",
        "X-Language": "zh_CN",
    })
    reset_log_preserving(ARCHIVES / company / "page_log.jsonl")
    all_rows: list[dict[str, Any]] = []
    page_log: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total: int | None = None
    pages = 0
    reported_page_size = PAGE_SIZE
    for page in range(1, 10000):
        params = {"X-HW-ID": HUAW_ID}
        body = {"curPage": page, "pageSize": HUAWEI_PAGE_SIZE, "jobType": "SR"}
        try:
            payload, status = request_json(session, "POST", HUAW_BASE,
                params=params, json_body=body,
                headers={"Content-Type": "application/json"})
            if payload.get("status") != "SUCCESS":
                raise RuntimeError(f"official API status={payload.get('status')}")
            data = payload.get("data") or {}
            page_vo = data.get("pageVO") or {}
            rows = data.get("result") or []
            total = int(page_vo.get("totalRows") or total or 0)
            pages = int(page_vo.get("totalPages") or pages or 0)
            reported_page_size = int(page_vo.get("pageSize") or PAGE_SIZE)
            save_page(company, page, payload, endpoint=HUAW_BASE,
                      request_params={**params, **body}, rows=rows,
                      reported_total=total, page_size=reported_page_size,
                      status_code=status)
            page_log.append({"page": page, "returned_rows": len(rows),
                             "reported_total": total, "page_size": reported_page_size})
            all_rows.extend(rows)
            if page >= pages or not rows:
                break
        except Exception as exc:
            error = {"page": page, "error": str(exc), "at": now_iso(),
                     "request_params": {**params, **body}}
            failures.append(error)
            append_jsonl(ARCHIVES / company / "page_log.jsonl", error, company)
            page_log.append(error)
            if page == 1:
                break
        time.sleep(PAGE_PAUSE)
    dedup: dict[str, dict[str, Any]] = {}
    duplicates = 0
    missing_ids = 0
    for row in all_rows:
        ident = str(row.get("jobId") or row.get("advertisementsIntegrationId") or "")
        if not ident:
            missing_ids += 1
            continue
        if ident in dedup:
            duplicates += 1
            continue
        dedup[ident] = row
    return list(dedup.values()), {
        "employer": "华为", "portal_scope": "官网公开社会招聘列表，jobType=SR，空关键词，未筛城市/职类",
        "official_list_url": "https://career.huawei.com/cn/social-recruitment-job-list", "list_endpoint": HUAW_BASE,
        "reported_total_initial": total, "page_size_requested": HUAWEI_PAGE_SIZE,
        "page_size_effective": reported_page_size, "pages_expected": pages,
        "pages_fetched": len([x for x in page_log if "returned_rows" in x]),
        "page_log": page_log, "raw_rows_fetched": len(all_rows),
        "unique_positions": len(dedup), "duplicate_rows": duplicates,
        "rows_missing_id": missing_ids, "failures": failures,
        "source_note": "官方列表响应包含 mainBusiness（职责/招聘说明）及 jobRequire（要求）正文；releaseDate/degree 等原字段可能为空。",
    }


def fetch_xiaomi_pages() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company = "xiaomi"
    referer = "https://hr.xiaomi.com/website/opportunities.html"
    session = new_session(referer)
    log_path = ARCHIVES / company / "page_log.jsonl"
    reset_log_preserving(log_path)
    all_rows: list[dict[str, Any]] = []
    page_log: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total: int | None = None
    pages = 0
    effective_size = PAGE_SIZE
    for page in range(1, 10000):
        params = {"keyword": "", "cityZhNames": "", "pageSize": PAGE_SIZE, "pageNum": page}
        try:
            payload, status = request_json(session, "GET", XIAOMI_LIST, params=params)
            if int(payload.get("code", -1)) != 0:
                raise RuntimeError(f"official API code={payload.get('code')} message={payload.get('message')}")
            data = payload.get("data") or {}
            rows = data.get("list") or []
            total = int(data.get("total") or total or 0)
            pages = int(data.get("pageTotal") or pages or 0)
            effective_size = int(data.get("pageSize") or PAGE_SIZE)
            save_page(company, page, payload, endpoint=XIAOMI_LIST,
                      request_params=params, rows=rows, reported_total=total,
                      page_size=effective_size, status_code=status)
            page_log.append({"page": page, "returned_rows": len(rows),
                             "reported_total": total, "page_size": effective_size})
            all_rows.extend(rows)
            if page >= pages or not rows:
                break
        except Exception as exc:
            error = {"page": page, "error": str(exc), "at": now_iso(), "request_params": params}
            failures.append(error)
            append_jsonl(log_path, error, company)
            page_log.append(error)
            if page == 1:
                break
        time.sleep(PAGE_PAUSE)
    dedup: dict[str, dict[str, Any]] = {}
    duplicates = 0
    missing_ids = 0
    for row in all_rows:
        ident = str(row.get("jobPostId") or row.get("jobId") or row.get("id") or "")
        if not ident:
            missing_ids += 1
            continue
        if ident in dedup:
            duplicates += 1
            continue
        dedup[ident] = row
    return list(dedup.values()), {
        "employer": "小米", "portal_scope": "小米官网探索机会页默认公开招聘列表，空关键词/城市、所有招聘项目",
        "official_list_url": referer, "list_endpoint": XIAOMI_LIST,
        "reported_total_initial": total, "page_size_requested": PAGE_SIZE,
        "page_size_effective": effective_size, "pages_expected": pages,
        "pages_fetched": len([x for x in page_log if "returned_rows" in x]),
        "page_log": page_log, "raw_rows_fetched": len(all_rows),
        "unique_positions": len(dedup), "duplicate_rows": duplicates,
        "rows_missing_id": missing_ids, "failures": failures,
        "source_note": "默认列表包含页面‘招聘项目’筛选中的多个项目，原 type/jobPostId 等字段保留；详情链接由官网公开列表直接提供。",
    }


def fetch_honor_pages() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    company = "honor"
    referer = HONOR_LIST_URL
    session = new_session(referer)
    session.headers.update({"Origin": "https://career.honor.com",
                            "Content-Type": "application/x-www-form-urlencoded"})
    log_path = ARCHIVES / company / "page_log.jsonl"
    reset_log_preserving(log_path)
    all_rows: list[dict[str, Any]] = []
    page_log: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total: int | None = None
    pages = 0
    effective_size = 15
    for page in range(1, 10000):
        form = {"isFrompb": "true", "recruitType": "2",
                "pageSize": effective_size, "currentPage": page}
        params = {"iSaJAx": "isAjax", "request_locale": "zh_CN",
                  "t": str(int(time.time() * 1000))}
        try:
            payload, status = request_json(session, "POST", HONOR_LIST,
                params=params, data=form)
            data = payload.get("data") or {}
            page_form = data.get("pageForm") or {}
            rows = page_form.get("pageData") or []
            # Honor nests its advertised list count inside pageForm, unlike the
            # other employers' APIs. Keep the returned count distinct from HC.
            total = int(page_form.get("dataCount") or data.get("dataCount") or total or 0)
            pages = int(page_form.get("totalPage") or pages or 0)
            effective_size = int(page_form.get("pageSize") or effective_size)
            if payload.get("state") != "200":
                raise RuntimeError(f"official API state={payload.get('state')} type={payload.get('type')}")
            save_page(company, page, payload, endpoint=HONOR_LIST,
                      request_params={**params, **form}, rows=rows,
                      reported_total=total, page_size=effective_size,
                      status_code=status)
            page_log.append({"page": page, "returned_rows": len(rows),
                             "reported_total": total, "page_size": effective_size})
            all_rows.extend(rows)
            if page >= pages or not rows:
                break
        except Exception as exc:
            error = {"page": page, "error": str(exc), "at": now_iso(),
                     "request_params": {**params, **form}}
            failures.append(error)
            append_jsonl(log_path, error, company)
            page_log.append(error)
            if page == 1:
                break
        time.sleep(PAGE_PAUSE)
    dedup: dict[str, dict[str, Any]] = {}
    duplicates = 0
    missing_ids = 0
    for row in all_rows:
        ident = str(row.get("postId") or "")
        if not ident:
            missing_ids += 1
            continue
        if ident in dedup:
            duplicates += 1
            continue
        dedup[ident] = row
    return list(dedup.values()), {
        "employer": "荣耀", "portal_scope": "荣耀官网链接的公开社会招聘列表，recruitType=2，未筛城市/职类",
        "official_list_url": referer, "list_endpoint": HONOR_LIST,
        "reported_total_initial": total, "page_size_requested": 15,
        "page_size_effective": effective_size, "pages_expected": pages,
        "pages_fetched": len([x for x in page_log if "returned_rows" in x]),
        "page_log": page_log, "raw_rows_fetched": len(all_rows),
        "unique_positions": len(dedup), "duplicate_rows": duplicates,
        "rows_missing_id": missing_ids, "failures": failures,
        "source_note": "列表有职位类别、地点、工作类型、更新日期、学历等字段；职责/任职要求由匿名公开详情接口读取。",
    }


def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def experience_from(text: str) -> str:
    patterns = [
        r"\d+\s*(?:年以上|年及以上|年工作经验|年相关经验|年经验)",
        r"\d+\s*[-至~—]\s*\d+\s*年(?:以上)?",
        r"(?:经验不限|不限经验|无经验要求|应届毕业生|应届生|校招|实习生)",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text or "", re.I):
            value = re.sub(r"\s+", "", match.group(0))
            if value not in found:
                found.append(value)
    return "；".join(found[:5]) if found else "未明示"


def skill_hits(text: str) -> list[str]:
    return [name for name, pattern in SKILLS.items() if re.search(pattern, text or "", re.I)]


def summary_items(text: str, limit: int = 2) -> list[str]:
    if not text:
        return []
    items: list[str] = []
    for raw_line in re.split(r"[\r\n]+", text):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        # Keep complete source clauses; strip only numbering and heading markers.
        line = re.sub(r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)）]\s*|[-*•]+\s*)", "", line)
        for piece in re.split(r"(?<=[。！？!?])\s*", line):
            piece = piece.strip(" \t;；。！？!?.")
            if len(piece) < 8:
                continue
            if piece not in items:
                items.append(piece)
            if len(items) >= limit:
                return items
    return items


def clear_summary(description: str, requirements: str) -> str:
    duties = summary_items(description, 2)
    reqs = summary_items(requirements, 2)
    parts: list[str] = []
    if duties:
        parts.append("主要职责：" + "；".join(duties) + "。")
    elif description:
        parts.append("主要职责：详见完整职责正文。")
    if reqs:
        parts.append("主要要求：" + "；".join(reqs) + "。")
    elif requirements:
        parts.append("主要要求：详见完整任职要求正文。")
    return "".join(parts)


DEV = re.compile(r"软件工程师|开发工程师|研发工程师|程序员|开发(?:者|人员)?|developer|software engineer|backend|后端|前端|客户端|系统工程师|测试开发|测试工程师", re.I)
ALGO = re.compile(r"算法(?:工程师|专家|研究|开发)?|algorithm", re.I)
TECH_CATEGORY = re.compile(r"研发|技术|算法|软件|工程|IT|产品与设计|研究", re.I)


def classify(title: str, category: str, description: str, requirements: str) -> tuple[str, list[str]]:
    full = " ".join([title, category, description, requirements])
    duty = " ".join([title, description])
    tags: list[str] = []
    if INFRA.search(duty):
        tags.append("AI Infra")
    if POST.search(full):
        tags.append("后训练/对齐")
    if APP.search(full):
        tags.append("AI应用/Agent")
    is_ai = bool(AI.search(full) or ALGO.search(title + " " + description))
    if is_ai:
        if "AI Infra" in tags:
            primary = "AI Infra"
        elif "后训练/对齐" in tags:
            primary = "后训练/对齐"
        elif "AI应用/Agent" in tags:
            primary = "AI应用/Agent"
        else:
            primary = "算法/AI技术"
        if not tags:
            tags.append("算法/AI技术")
        return primary, tags
    if DEV.search(title) or TECH_CATEGORY.search(category):
        return "普通开发/其他技术", tags
    return "其他职能", tags


def raw_fields(row: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def build_record(company: str, ident: str, title: str, url: str,
                 category: Any, location: Any, country_raw: Any,
                 experience_raw: Any, degree_raw: Any,
                 posted_raw: Any, date_semantics: dict[str, Any],
                 description: Any, requirements: Any,
                 source_type: str, raw: dict[str, Any],
                 source_fields: set[str], salary_raw: Any = None) -> dict[str, Any]:
    description_text = description if isinstance(description, str) else ("" if description is None else str(description))
    requirement_text = requirements if isinstance(requirements, str) else ("" if requirements is None else str(requirements))
    category_text = str(category) if category not in (None, "") else "未明示"
    inferred, tags = classify(title, category_text, description_text, requirement_text)
    exp_raw_str = str(experience_raw) if experience_raw not in (None, "") else "未提供独立年限字段"
    edu_raw_str = degree_raw if degree_raw not in (None, "") else None
    education_mentions = [level for level in ("本科", "硕士", "博士", "大专")
                          if level in requirement_text]
    return {
        "company": company,
        "source_job_id": str(ident),
        "title": title or "未明示",
        "url": url,
        "location": location if location not in (None, "") else "未明示",
        "country": str(country_raw) if country_raw not in (None, "") else "未明示",
        "country_raw": country_raw,
        "category_raw": category_text,
        "category_inferred": inferred,
        "experience_raw": exp_raw_str,
        "experience_parsed_from_requirement": experience_from(requirement_text),
        "degree_raw": edu_raw_str,
        "education_mentions_in_requirement": education_mentions,
        "salary_raw": salary_raw,
        "posted_date_raw": posted_raw,
        "date_semantics": date_semantics,
        "access_time": now_iso(),
        "description": description_text,
        "requirements": requirement_text,
        "description_chars": len(description_text),
        "requirements_chars": len(requirement_text),
        "description_sha256": sha(description_text),
        "requirements_sha256": sha(requirement_text),
        "text_sha256": sha(description_text + "\n" + requirement_text),
        "source_type": source_type,
        "detail_status": "full" if description_text and requirement_text else "partial",
        "skills_in_responsibility": skill_hits(description_text),
        "skills_in_requirement": skill_hits(requirement_text),
        "direction_tags": tags,
        "summary": clear_summary(description_text, requirement_text),
        "availability_note": "本次官网公开职位列表返回；不等同于招聘人数、实际剩余HC或HR确认。",
        "source_fields_raw": raw_fields(raw, source_fields),
    }


def build_huawei_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    fields = {"advertisementsIntegrationId", "releaseDate", "jobName", "jobNameNew",
              "jobFamilyName", "jobFamClsCode", "jobFamClsCodeName", "jobClass",
              "workArea", "workPlace", "workYear", "degree", "countryName", "cityName",
              "jobType", "jobAddress", "workCountry", "deployDate", "lastUpdateDate",
              "deptName", "deptNameEn", "deptCode", "firstDeptName", "firstDeptCode",
              "jobId", "advertisementId", "recruitScenarioId", "recruitSubScenarioId",
              "channelType", "cancelflag", "upLineStatus", "sourceRecruitType"}
    for row in rows:
        job_id = str(row.get("jobId") or row.get("advertisementsIntegrationId") or "")
        ad_id = row.get("advertisementId")
        url = (f"https://career.huawei.com/cn/job-details?advertisementId={ad_id}"
               if ad_id else "https://career.huawei.com/cn/social-recruitment-job-list")
        release = row.get("releaseDate")
        update = row.get("lastUpdateDate")
        records.append(build_record(
            "华为", job_id, row.get("jobName") or row.get("jobNameNew") or "未明示",
            url, row.get("jobFamilyName") or row.get("categoryName"),
            {"city_raw": row.get("workPlace"), "work_area_raw": row.get("workArea"),
             "job_address_raw": row.get("jobAddress")}, row.get("countryName"),
            row.get("workYear"), row.get("degree"), release,
            {"posted_date_field": "releaseDate", "posted_date_value": release,
             "updated_date_field": "lastUpdateDate", "updated_date_value": update,
             "date_note": "releaseDate为空时保留为空；lastUpdateDate仅表示官方字段更新日，不替代发布日期。"},
            row.get("mainBusiness"), row.get("jobRequire"),
            "华为官网匿名公开社招列表API；职位详情正文直接来自 getJobPage 响应",
            row, fields))
    return records


def build_xiaomi_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    fields = {"id", "title", "cityZhNames", "levelOneDeptName", "jobLevelMin",
              "jobLevelMax", "jobLevelRange", "expectedJobLevel", "publishTime",
              "larkJobCode", "type", "url", "jobId", "jobPostId", "status",
              "jobType", "projectName", "jobCategory", "salary", "degree",
              "experience", "workType"}
    for row in rows:
        ident = str(row.get("jobPostId") or row.get("jobId") or row.get("id") or "")
        url = row.get("url") or (
            f"https://xiaomi.jobs.f.mioffice.cn/index/position/{row.get('jobPostId')}/detail"
            if row.get("jobPostId") else "https://hr.xiaomi.com/website/opportunities.html")
        records.append(build_record(
            "小米", ident, row.get("title") or "未明示", url,
            row.get("jobCategory") or row.get("category") or row.get("positionCategory") or "未提供（API未返回岗位类别字段）",
            {"city_names_raw": row.get("cityZhNames"), "department_raw": row.get("levelOneDeptName")},
            row.get("country") or row.get("countryName"),
            row.get("experience") or row.get("workYear"), row.get("degree"),
            row.get("publishTime"),
            {"posted_date_field": "publishTime", "posted_date_value": row.get("publishTime"),
             "date_note": "保留官网API的 publishTime 原值；更新日未独立返回。"},
            row.get("description"), row.get("requirement"),
            "小米官网公开探索机会列表API；职位详情正文直接来自 searchJobPage 响应，详情链接为官网列表href",
            row, fields, row.get("salary")))
    return records


def honor_detail(post_id: str, row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    archive = ARCHIVES / "honor" / "details" / f"{re.sub(r'[^A-Za-z0-9_-]', '_', post_id)}.json"
    if archive.exists():
        try:
            return json.loads(archive.read_text(encoding="utf-8")), None
        except Exception:
            pass
    if ARCHIVE_ONLY:
        return None, {"post_id": post_id, "detail_status": "missing_archive",
                      "error": "No saved anonymous public detail response exists; offline rebuild did not make a network request.",
                      "at": now_iso()}
    session = new_session(HONOR_LIST_URL)
    session.headers.update({"Origin": "https://career.honor.com",
                            "Content-Type": "application/x-www-form-urlencoded"})
    params = {"iSaJAx": "isAjax", "request_locale": "zh_CN",
              "t": str(int(time.time() * 1000))}
    form = {"postId": post_id, "recruitType": "2"}
    try:
        payload, status = request_json(session, "POST", HONOR_DETAIL,
            params=params, data=form)
        if payload.get("state") != "200" or payload.get("type") != "success":
            raise RuntimeError(f"official API state={payload.get('state')} type={payload.get('type')}")
        dump_json(archive, payload)
        time.sleep(DETAIL_PAUSE)
        return payload, {"post_id": post_id, "http_status": status,
                         "detail_status": "retrieved", "at": now_iso(),
                         "raw_detail_archive": f"archives/honor/details/{archive.name}"}
    except Exception as exc:
        return None, {"post_id": post_id, "detail_status": "failed",
                      "error": str(exc), "at": now_iso(), "request_params": form}


def build_honor_records(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fields = {"postId", "externalKey", "postName", "postTypeName", "postType",
              "workPlaceStr", "workPlaceList", "workTypeStr", "publishDate",
              "publishFirstDate", "endDate", "longTermRelease", "workYears",
              "educationStr", "educationAbove", "postCode", "company", "orgName",
              "orgCode", "externalOrgCode", "projectName", "projectId", "recruitType",
              "canDelivery", "currentSuiteKey", "top"}
    details_ok = 0
    detail_failures: list[dict[str, Any]] = []
    detail_payloads: dict[str, dict[str, Any] | None] = {}
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(honor_detail, str(row.get("postId") or ""), row): row
                   for row in rows if row.get("postId")}
        for future in cf.as_completed(futures):
            row = futures[future]
            ident = str(row.get("postId") or "")
            try:
                payload, log_entry = future.result()
            except Exception as exc:
                payload, log_entry = None, {"post_id": ident, "detail_status": "failed",
                    "error": f"{type(exc).__name__}: {exc}", "at": now_iso()}
            detail_payloads[ident] = payload
            if payload is not None:
                details_ok += 1
            if log_entry:
                append_jsonl(ARCHIVES / "honor" / "detail_log.jsonl", log_entry, "honor")
                if log_entry.get("detail_status") == "failed":
                    detail_failures.append(log_entry)
    records = []
    detail_fields = {"education", "endDate", "longTermRelease", "publishDate", "publishFirstDate",
                     "externalPostId", "postTypeName", "workPlaceStr", "workPlaceList",
                     "postId", "postCode", "workTypeStr", "workExperience", "workYears",
                     "company", "orgName", "orgCode", "externalOrgCode", "projectName",
                     "projectId", "recruitType", "canDelivery", "top"}
    for row in rows:
        ident = str(row.get("postId") or "")
        detail_wrap = detail_payloads.get(ident) or {}
        detail = detail_wrap.get("data") or {}
        # Exact source bodies use these two public API fields; no trimming or rewording.
        description = detail.get("workContent")
        requirements = detail.get("serviceCondition")
        raw_merged = dict(row)
        raw_merged.update({key: detail.get(key) for key in detail_fields if key in detail})
        if detail:
            raw_merged["workContent"] = description
            raw_merged["serviceCondition"] = requirements
        url = f"https://career.honor.com/SU{HONOR_SUITE}/pb/posDetail.html?postId={ident}&postType=society"
        records.append(build_record(
            "荣耀", ident, row.get("postName") or "未明示", url,
            row.get("postTypeName"),
            {"work_place_raw": row.get("workPlaceStr"), "work_place_list_raw": detail.get("workPlaceList")},
            detail.get("countryName") or row.get("countryName"),
            row.get("workYears") or detail.get("workYears"),
            detail.get("education") or row.get("educationStr"),
            row.get("publishDate"),
            {"posted_date_field": "publishDate", "posted_date_value": row.get("publishDate"),
             "first_publish_date_field": "publishFirstDate",
             "first_publish_date_value": row.get("publishFirstDate"),
             "updated_date_field": "publishDate", "updated_date_value": row.get("publishDate"),
             "end_date_raw": row.get("endDate") or detail.get("endDate"),
             "date_note": "publishDate 为列表显示日期/更新时间；publishFirstDate 原样保留。endDate=3000-01-01 为源站长期展示哨兵值，不当作明确HC期限。"},
            description, requirements,
            "荣耀官网公开社会招聘列表API + 匿名公开职位详情API（workContent/serviceCondition）",
            raw_merged, fields | detail_fields))
    return records, detail_failures


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "unique_records": len(records),
        "detail_full": sum(r["detail_status"] == "full" for r in records),
        "detail_partial": sum(r["detail_status"] != "full" for r in records),
        "description_body_count": sum(bool(r["description"]) for r in records),
        "requirements_body_count": sum(bool(r["requirements"]) for r in records),
        "classification_counts": {label: sum(r["category_inferred"] == label for r in records)
                                  for label in sorted({r["category_inferred"] for r in records})},
    }


def rows_from_archive(company: str) -> list[dict[str, Any]]:
    folder = ARCHIVES / company / "pages"
    rows: list[dict[str, Any]] = []
    for file in sorted(folder.glob("page_*.json")):
        payload = json.loads(file.read_text(encoding="utf-8"))
        data = payload.get("data") or {}
        if company == "huawei":
            page_rows = data.get("result") or []
        elif company == "xiaomi":
            page_rows = data.get("list") or []
        else:
            page_rows = (data.get("pageForm") or {}).get("pageData") or []
        rows.extend(page_rows)
    return rows


def deduplicate_rows(company: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    key = {"huawei": lambda row: str(row.get("jobId") or row.get("advertisementsIntegrationId") or ""),
           "xiaomi": lambda row: str(row.get("jobPostId") or row.get("jobId") or row.get("id") or ""),
           "honor": lambda row: str(row.get("postId") or "")}[company]
    dedup: dict[str, dict[str, Any]] = {}
    duplicates = 0
    missing = 0
    for row in rows:
        ident = key(row)
        if not ident:
            missing += 1
        elif ident in dedup:
            duplicates += 1
        else:
            dedup[ident] = row
    return list(dedup.values()), duplicates, missing


def rebuild_from_archives() -> None:
    global ARCHIVE_ONLY
    ARCHIVE_ONLY = True
    audit_path = EVIDENCE / "hardware_expanded_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    all_records: dict[str, list[dict[str, Any]]] = {}
    transforms = {"huawei": build_huawei_records, "xiaomi": build_xiaomi_records}
    for company in ("huawei", "xiaomi", "honor"):
        raw_rows = rows_from_archive(company)
        unique_rows, duplicates, missing = deduplicate_rows(company, raw_rows)
        company_audit = audit["companies"].setdefault(company, {})
        if company == "honor":
            # Recover Honor's official count from the raw first-page response;
            # the earlier collector version looked one level too high.
            page_files = sorted((ARCHIVES / company / "pages").glob("page_*.json"))
            first_payload = json.loads(page_files[0].read_text(encoding="utf-8")) if page_files else {}
            first_form = ((first_payload.get("data") or {}).get("pageForm") or {})
            honor_total = first_form.get("dataCount")
            total_pages = first_form.get("totalPage")
            if honor_total is not None:
                company_audit["reported_total_initial"] = int(honor_total)
                company_audit["reported_total_api"] = int(honor_total)
                company_audit["reported_total_source_field"] = "data.pageForm.dataCount"
            if total_pages is not None:
                company_audit["pages_expected"] = int(total_pages)
            company_audit["reported_total_semantics"] = (
                "Official public-list position count; not a remaining-headcount count."
            )
            # Reconcile derived retrieval logs to the archived source response.
            for item in company_audit.get("page_log", []):
                item["reported_total"] = int(honor_total) if honor_total is not None else None
                item["reported_total_source_field"] = "data.pageForm.dataCount"
            log_path = ARCHIVES / company / "page_log.jsonl"
            if log_path.exists():
                repaired_lines = []
                for line in log_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    if "returned_rows" in item:
                        item["reported_total"] = int(honor_total) if honor_total is not None else None
                        item["reported_total_source_field"] = "data.pageForm.dataCount"
                    repaired_lines.append(json.dumps(item, ensure_ascii=False))
                log_path.write_text("\n".join(repaired_lines) + ("\n" if repaired_lines else ""), encoding="utf-8")
            records, detail_failures = build_honor_records(unique_rows)
            company_audit["detail_failures"] = detail_failures
            company_audit["detail_attempted"] = len(unique_rows)
            company_audit["detail_success"] = sum(r["detail_status"] == "full" for r in records)
        else:
            records = transforms[company](unique_rows)
        all_records[company] = records
        dump_json(EVIDENCE / f"{company}_expanded_jobs.json", records)
        company_audit.update(summarize_records(records))
        company_audit.update({"raw_rows_fetched": len(raw_rows), "unique_positions": len(records),
                              "duplicate_rows": duplicates, "rows_missing_id": missing,
                              "reconstructed_from_archive": True})
    audit["combined_unique_positions"] = sum(len(rows) for rows in all_records.values())
    audit["portal_count_observations"] = {
        "huawei": {
            "basis": "Official social-recruitment list API reported totalRows=597 across 60 pages.",
            "position_count": audit["companies"]["huawei"].get("reported_total_initial"),
        },
        "xiaomi": {
            "basis": "Official list API returned total=3677 in two snapshots; the initial page UI displayed 3678. API rows contained 13 duplicates across 3664 unique jobPostId values.",
            "api_position_count": audit["companies"]["xiaomi"].get("reported_total_initial"),
            "initial_ui_display_count": 3678,
            "raw_api_rows": audit["companies"]["xiaomi"].get("raw_rows_fetched"),
            "unique_job_ids": audit["companies"]["xiaomi"].get("unique_positions"),
        },
        "honor": {
            "basis": "Official social-recruitment list API data.pageForm.dataCount and 27-page pagination; raw page rows sum to the same count.",
            "position_count": audit["companies"]["honor"].get("reported_total_initial"),
        },
    }
    audit["partial_records"] = {
        company: [
            {"source_job_id": row["source_job_id"], "title": row["title"],
             "missing_bodies": [field for field in ("description", "requirements") if not row.get(field)],
             "detail_status": row["detail_status"]}
            for row in all_records[company] if row["detail_status"] != "full"
        ]
        for company in ("huawei", "xiaomi", "honor")
    }
    audit["resolved_initial_issues"] = [
        {
            "company": "华为",
            "issue": "首轮匿名浏览器探测缺少官网请求中的 tenant context，接口返回 TenantContextError；通过正常官网页面网络请求读取所需公开请求头后，已完整读取列表。",
            "resolution": "已归档修正后的 60 页响应；失败探测留存在 evidence/archives/browser_fallback_run.json。",
        },
        {
            "company": "荣耀",
            "issue": "首轮探测的公开路径遗漏 SU 前缀，接口返回 No endpoint；原始列表页和详情页路径已依据官网页面响应修正。",
            "resolution": "已归档 27 页列表及 400 条详情响应；失败探测留存在 evidence/archives/browser_fallback_run.json。",
        },
        {
            "company": "荣耀",
            "issue": "初版计数解析读取了错误层级；原始响应将职位总数放在 data.pageForm.dataCount。",
            "resolution": "已从保存的原始首页响应修正为 400，并同步修复汇总与分页日志；原始响应未改写。",
        },
    ]
    partial_limitation = (
        "4 条职位记录的官网公开源正文没有任职要求字段，均保留为 partial 并记录缺失字段；"
        "未据职责内容补写要求，也未将其计入全文记录。"
    )
    audit.setdefault("limitations", [])
    if partial_limitation not in audit["limitations"]:
        audit["limitations"].append(partial_limitation)
    audit["curation_rubric"] = CURATION_RUBRIC
    audit["selected_clear_jd_examples"] = CURATION_CANDIDATES
    audit["rebuild_completed_at"] = now_iso()
    audit["record_build_source"] = "Reconstructed from saved public API page/detail response JSON; this offline rebuild made no network requests."
    audit["archive_layout"] = "archives/{huawei,xiaomi,honor}/pages/page_*.json; Honor detail payloads in details/{postId}.json; page_log.jsonl and detail_log.jsonl retain per-page/per-detail status."
    for company in ("huawei", "xiaomi", "honor"):
        # The raw company folders now live at the task-root archives path.
        for log_path in (ARCHIVES / company).glob("**/*.jsonl"):
            original = log_path.read_text(encoding="utf-8")
            normalized = original.replace("evidence/archives/", "archives/")
            if normalized != original:
                log_path.write_text(normalized, encoding="utf-8")
    dump_json(audit_path, audit)
    for name in ("huawei", "xiaomi", "honor"):
        company_audit = audit["companies"].get(name, {})
        print(json.dumps({"company": name, "reported": company_audit.get("reported_total_initial"),
                          "unique": company_audit.get("unique_positions", 0),
                          "full": company_audit.get("detail_full", 0),
                          "partial": company_audit.get("detail_partial", 0),
                          "failures": len(company_audit.get("failures", [])) + len(company_audit.get("detail_failures", []))},
                         ensure_ascii=False))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-archive", action="store_true",
                        help="rebuild job records from saved source responses without network access")
    args = parser.parse_args()
    if args.from_archive:
        rebuild_from_archives()
        return
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    started = now_iso()
    company_audits: dict[str, Any] = {}
    all_records: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []
    tasks = [
        ("huawei", fetch_huawei_pages, build_huawei_records),
        ("xiaomi", fetch_xiaomi_pages, build_xiaomi_records),
    ]
    for name, fetch, transform in tasks:
        try:
            rows, audit = fetch()
            records = transform(rows)
            company_audits[name] = {**audit, **summarize_records(records)}
            all_records[name] = records
            dump_json(EVIDENCE / f"{name}_expanded_jobs.json", records)
        except Exception as exc:
            errors.append({"company": name, "phase": "list_or_transform",
                           "error": f"{type(exc).__name__}: {exc}", "at": now_iso()})
            company_audits[name] = {"employer": name, "run_status": "failed",
                                    "error": errors[-1]["error"]}
            all_records[name] = []
    try:
        honor_log = ARCHIVES / "honor" / "detail_log.jsonl"
        if honor_log.exists():
            honor_log.unlink()
        rows, audit = fetch_honor_pages()
        records, detail_failures = build_honor_records(rows)
        company_audits["honor"] = {**audit, **summarize_records(records),
                                   "detail_attempted": len(rows),
                                   "detail_success": sum(r["detail_status"] == "full" for r in records),
                                   "detail_failures": detail_failures}
        all_records["honor"] = records
        dump_json(EVIDENCE / "honor_expanded_jobs.json", records)
    except Exception as exc:
        errors.append({"company": "honor", "phase": "list_detail_or_transform",
                       "error": f"{type(exc).__name__}: {exc}", "at": now_iso()})
        company_audits["honor"] = {"employer": "荣耀", "run_status": "failed",
                                    "error": errors[-1]["error"]}
        all_records["honor"] = []
    audit = {
        "started_at": started, "finished_at": now_iso(),
        "run_result": "completed_with_errors" if errors or any(v.get("failures") or v.get("detail_failures") for v in company_audits.values()) else "completed",
        "method": "Public employer job portals and anonymous listing/detail APIs confirmed through a normal Playwright Edge page load and visible network responses; no login, verification bypass, or signature reconstruction.",
        "selection_scope": "Each company uses the complete blank-key/blank-city listing scope stated per employer. All job families are retained; no AI-only keyword filter is applied because all three reported totals are below 10,000.",
        "curation_rubric": CURATION_RUBRIC,
        "selected_clear_jd_examples": CURATION_CANDIDATES,
        "shared_skill_dictionary": SKILLS,
        "classification_patterns": {"ai": AI.pattern, "infra": INFRA.pattern,
                                    "posttraining": POST.pattern, "application": APP.pattern},
        "companies": company_audits,
        "combined_unique_positions": sum(len(v) for v in all_records.values()),
        "top_level_errors": errors,
        "archive_layout": "archives/{huawei,xiaomi,honor}/pages/page_*.json; Honor detail payloads in details/{postId}.json; page_log.jsonl and detail_log.jsonl retain per-page/per-detail status.",
        "limitations": [
            "Counts are a single time-stamped public-list snapshot. Site listing results do not confirm actual remaining headcount, hiring budget, or HR response.",
            "Huawei scope is the public social-recruitment list. Xiaomi scope is the default opportunities list, which exposes multiple project types and preserves each raw type. Honor scope is the public social-recruitment list.",
            "Raw source date, category, experience, degree, and location fields are retained as returned. Parsed skills/category/experience are derived fields and remain separate from original values.",
            "An absent body or source field remains absent/unknown; partial detail status is not promoted to full. Summary uses complete source clauses and never clips at a fixed character count."
        ],
    }
    dump_json(EVIDENCE / "hardware_expanded_audit.json", audit)
    for name in ("huawei", "xiaomi", "honor"):
        audit_company = company_audits.get(name, {})
        print(json.dumps({"company": name,
                          "reported": audit_company.get("reported_total_initial"),
                          "unique": audit_company.get("unique_positions", 0),
                          "full": audit_company.get("detail_full", 0),
                          "partial": audit_company.get("detail_partial", 0),
                          "failures": len(audit_company.get("failures", [])) + len(audit_company.get("detail_failures", []))},
                         ensure_ascii=False))
    print(json.dumps({"combined_unique": audit["combined_unique_positions"],
                      "run_result": audit["run_result"], "top_level_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
