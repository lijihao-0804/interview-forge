"""Collect full, currently public JDs from the official PDD, NetEase, Baidu and iFlytek portals.

Uses ordinary anonymous page/API requests only; no login, CAPTCHA, token/signature
reconstruction or application submission. Run with E:\\python\\python.exe analysis/collect_software_employers.py.
"""
from __future__ import annotations
import datetime as dt
import argparse
import hashlib
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from collect_tencent import SKILLS, AI, INFRA, POST, APP

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence'
ARCHIVES = ROOT / 'archives'
ACCESS_TZ = dt.timezone(dt.timedelta(hours=8))

def now_iso() -> str:
    return dt.datetime.now(ACCESS_TZ).isoformat(timespec='seconds')


def clean_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return '\n'.join(filter(None, (clean_text(v) for v in value)))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    s = html.unescape(str(value)).replace('\r\n', '\n').replace('\r', '\n')
    if '<' in s and '>' in s:
        s = BeautifulSoup(s, 'html.parser').get_text('\n')
    s = re.sub(r'[\t\f\v ]+', ' ', s)
    s = re.sub(r'\n[ \u00a0]+', '\n', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()




def date_display(value) -> str:
    if value in (None, ''):
        return '未知'
    text = str(value).strip()
    if re.fullmatch(r'\d{10,13}', text):
        number = int(text)
        seconds = number / 1000 if len(text) == 13 else number
        try:
            return dt.datetime.fromtimestamp(seconds, ACCESS_TZ).isoformat(timespec='seconds')
        except (OverflowError, OSError, ValueError):
            return text
    return text


def source_key(raw: dict, names) -> str:
    return next((name for name in names if name in raw and raw[name] not in (None, '')), '未结构化披露')


def value_for(raw: dict, names, default=''):
    for name in names:
        if name in raw and raw[name] not in (None, ''):
            return raw[name]
    return default


def split_items(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    lines = [re.sub(r'^\s*(?:[-•●▪]+\s*|\d+[.、)）]\s*)', '', x).strip() for x in text.splitlines()]
    lines = [x for x in lines if x]
    if len(lines) > 1:
        return lines
    parts = re.split(r'(?<=[。！？；])\s*', text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts or [text]


def summary_sentence(label: str, text: str, max_items: int = 3) -> str:
    items = split_items(text)
    if not items:
        return ''
    body = '；'.join(items[:max_items]).rstrip('。；;')
    return f'{label}包括：{body}。'


def jd_hash(description: str, requirements: str, bonus: str = '') -> str:
    text = '\n'.join([description or '', requirements or '', bonus or ''])
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


SECTION_HEADERS = {
    'responsibility': re.compile(r'(?im)^\s*(?:岗位职责|工作职责|职位职责|职责描述|工作内容|岗位描述|Responsibilities)\s*[:：]?\s*$'),
    'requirements': re.compile(r'(?im)^\s*(?:任职要求|任职资格|岗位要求|职位要求|基本要求|Qualifications|Requirements)\s*[:：]?\s*$'),
    'bonus': re.compile(r'(?im)^\s*(?:[【\[]\s*)?(?:加分项|优先条件(?:\s*[（(]加分项[）)])?|优先考虑(?:\s*[（(]加分项[）)])?|我们还希望你|Preferred Qualifications)(?:\s*[】\]])?\s*[:：]?\s*$'),
}

def split_labeled_sections(text: str) -> dict[str, str]:
    text = clean_text(text)
    matches = []
    for section, pattern in SECTION_HEADERS.items():
        matches.extend((m.start(), m.end(), section) for m in pattern.finditer(text))
    matches.sort()
    result = {'responsibility':'', 'requirements':'', 'bonus':''}
    for i, (start, end, section) in enumerate(matches):
        stop = matches[i+1][0] if i+1 < len(matches) else len(text)
        value = text[end:stop].strip()
        if value:
            result[section] = (result[section] + '\n' + value).strip() if result[section] else value
    return result


def requirements_and_bonus(text: str) -> tuple[str, str]:
    text = clean_text(text)
    if not text:
        return '', ''
    sections = split_labeled_sections(text)
    bonus_match = SECTION_HEADERS['bonus'].search(text)
    if sections['requirements']:
        requirements = sections['requirements']
    elif bonus_match:
        requirements = text[:bonus_match.start()].strip()
    else:
        requirements = text
    return requirements, sections['bonus']


def skill_matches(text: str) -> list[str]:
    return [name for name, pattern in SKILLS.items() if re.search(pattern, text or '', re.I)]


def make_record(company: str, raw: dict, *, title='', job_id='', url='', location='', country='未知',
                category='', experience='', degree='', posted='', updated='', date_semantics='',
                description='', requirements='', bonus='', source_type='official_public_page',
                access_time=None, detail_status=None, source_page='', extra=None) -> dict:
    title = clean_text(title or value_for(raw, ['title','name','jobName','positionName','RecruitPostName','postName','jobTitle']))
    job_id = clean_text(job_id or value_for(raw, ['source_job_id','jobId','id','code','jobCode','positionId','PostId','postId']))
    url = url or value_for(raw, ['url','jobUrl','detailUrl','positionUrl','postUrl','PostURL'])
    title_code_match = re.search(r'\(([A-Za-z]?\d{4,})\)', title)
    title_code = title_code_match.group(1) if title_code_match else ''
    description = clean_text(description or value_for(raw, ['description','jobDuty','responsibility','responsibilities','Responsibility','duty','workContent','jobResponsibilities']))
    country_value = clean_text(country) if country and country != '未知' else clean_text(value_for(raw,['country','countryName','CountryName']))
    if not country_value: country_value = '未知'
    requirements = clean_text(requirements or value_for(raw, ['requirements','jobRequirement','jobRequirements','Requirement','qualification','qualifications','requirement','jobRequire']))
    bonus = clean_text(bonus or value_for(raw, ['bonus','preferredQualification','plus','加分项','additionalRequirements']))
    combined = clean_text(value_for(raw,['fullText','jobContent','content','positionDescription','descriptionHtml']))
    if combined and not (description and requirements):
        sections = split_labeled_sections(combined)
        description = description or sections['responsibility'] or combined
        requirements = requirements or sections['requirements']
        bonus = bonus or sections['bonus']
    elif description and not requirements:
        sections = split_labeled_sections(description)
        if sections['responsibility'] or sections['requirements']:
            description = sections['responsibility'] or description
            requirements = sections['requirements']
            bonus = bonus or sections['bonus']
    posted_value = posted if posted not in (None, '') else value_for(raw,['postedDate','publishDate','releaseTime','createTime','PostTime'])
    updated_value = updated if updated not in (None, '') else value_for(raw,['updatedDate','updateTime','lastUpdateTime','LastUpdateTime'])
    if not detail_status:
        detail_status = 'full' if description and requirements else ('partial' if description or requirements else 'list_only')
    summary = ' '.join(x for x in [summary_sentence('岗位职责', description), summary_sentence('任职要求', requirements), summary_sentence('加分项', bonus)] if x)
    record = {
        'company': company, 'title': title or '未知', 'source_job_id': job_id or '未知',
        'url': url or '未知', 'location': clean_text(location or value_for(raw,['location','workLocation','workLocationName','city','LocationName','address'])) or '未知',
        'source_internal_id': clean_text(value_for(raw,['id','positionId','postId','PostId'])) or '未结构化披露',
        'job_code_raw': clean_text(value_for(raw,['code','jobCode','positionCode','jobNumber'])) or title_code or '未结构化披露',
        'business_unit_raw': clean_text(value_for(raw,['department','team','businessUnit','firstDepartmentName','BGName','bgName'])) or '未结构化披露',
        'employment_type_raw': clean_text(value_for(raw,['recruitType','workType','jobType','employmentType'])) or '未结构化披露',
        'source_status_raw': clean_text(value_for(raw,['status','jobStatus','publishStatus','isValid','valid'])) or '未结构化披露',
        'visible_on_public_page': True,
        'reported_hc_raw': clean_text(value_for(raw,['recruitNum','headcount','headCount','numberOfOpenings','peopleCount'])) or '未公开',
        'salary_raw': clean_text(value_for(raw,['salary','salaryRange','salaryDesc'])) or '未公开',
        'country': country_value, 'category_raw': clean_text(category or value_for(raw,['category','jobCategory','jobName','postType','CategoryName'])) or '未知',
        'experience_raw': clean_text(experience or value_for(raw,['experience','workYears','experienceRequirement','RequireWorkYearsName'])) or '未结构化披露',
        'degree_raw': clean_text(degree or value_for(raw,['degree','education','educationRequirement','academicRequirement'])) or '未结构化披露',
        'posted_date_raw': clean_text(posted_value) or '未知',
        'posted_date_display': date_display(posted_value),
        'posted_date_source_field': source_key(raw,['postedDate','publishDate','releaseTime','createTime','PostTime','PostDate']),
        'updated_date_raw': clean_text(updated_value) or '未知',
        'updated_date_display': date_display(updated_value),
        'updated_date_source_field': source_key(raw,['updatedDate','updateDate','updateTime','lastUpdateTime','LastUpdateTime','ChangeDate']),
        'date_semantics': date_semantics or '原始字段名和原始值保留；只有名称明确表示发布/更新的字段才分别填入。',
        'access_time': access_time or now_iso(), 'description': description, 'requirements': requirements, 'bonus': bonus,
        'jd_sha256': jd_hash(description, requirements, bonus),
        'responsibility_sha256': hashlib.sha256(description.encode('utf-8')).hexdigest(),
        'requirements_sha256': hashlib.sha256(requirements.encode('utf-8')).hexdigest(),
        'source_type': source_type, 'detail_status': detail_status,
        'public_status_note': '在采集时间可由该官方公开页面或其公开接口读取；不能据此确认实际剩余HC。',
        'hash_scope': 'UTF-8 SHA-256 of normalized responsibility, requirement and bonus text separated by newline; original structured payload archived separately.',
        'skills_in_responsibility': skill_matches(description), 'skills_in_requirement': skill_matches(requirements),
        'summary': summary or '招聘页面未提供可读取的职责与任职要求正文，暂无法形成内容摘要。',
        'source_page': source_page or '未知',
    }
    if extra:
        record.update(extra)
    return record


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def save_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')


def baidu_record(raw: dict, recruit_type: str, access_time: str, page_url: str) -> dict:
    post_id = clean_text(raw.get('postId') or raw.get('jobId'))
    url = f"https://talent.baidu.com/jobs/detail/{recruit_type}/{post_id}" if post_id else page_url
    requirements, parsed_bonus = requirements_and_bonus(raw.get('serviceCondition', ''))
    raw_bonus = value_for(raw,['bonusCondition','bonus','preferredQualification'])
    return make_record(
        '百度', raw, title=raw.get('name',''), job_id=post_id, url=url,
        location=raw.get('workPlace','未知'), category=raw.get('postType','未知'),
        experience=raw.get('workYears',''), degree=raw.get('education',''),
        posted=raw.get('publishDate',''), updated=raw.get('updateDate',''),
        date_semantics='publishDate为官方列表展示发布日期，updateDate为官方更新时间；两者均按原字段保留。',
        description=raw.get('workContent',''), requirements=requirements,
        bonus=raw_bonus or parsed_bonus,
        source_type='百度官方公开招聘接口（前端 getPostListNew）', access_time=access_time,
        detail_status='full' if raw.get('workContent') and raw.get('serviceCondition') else 'partial',
        source_page=page_url, extra={
            'recruit_type_raw': recruit_type, 'project_type_raw': raw.get('projectType','未结构化披露'),
            'project_type_code_raw': raw.get('projectTypeCode','未结构化披露'),
            'auxiliary_id_raw': raw.get('jobId','未结构化披露'),
            'url_resolution': '官方职位详情直达路由；匿名Edge已分别验证SOCIAL、GRADUATE、INTERN样例的页面标题与source_job_id相符。',
            'full_requirements_raw': clean_text(raw.get('serviceCondition','')),
        })


def collect_baidu_type(session: requests.Session, recruit_type: str, access_time: str,
                       page_size: int = 10) -> tuple[list[dict], list[dict], dict]:
    base = 'https://talent.baidu.com'
    page_url = base + ('/jobs/social-list' if recruit_type == 'SOCIAL' else '/jobs/list')
    endpoint = base + '/httservice/getPostListNew'
    headers = {'Referer': page_url, 'Origin': base}
    total = None
    raw_rows = []
    pages = []
    errors = []
    page_no = 1
    while True:
        payload = {'recruitType': recruit_type, 'postType': [], 'workPlace': [],
                   'pageSize': page_size, 'keyWord': '', 'curPage': page_no, 'projectType': ''}
        try:
            response = session.post(endpoint, data=payload, headers=headers, timeout=30)
            response.raise_for_status()
            body = response.json()
            if body.get('status') != 'ok':
                raise ValueError(f"public list API status={body.get('status')}: {body.get('message','')}")
            data = body.get('data') or {}
            rows = data.get('list') or []
            total = int(data.get('total') or 0)
            pages.append({'page':page_no, 'records':len(rows), 'reported_total':total})
            raw_rows.extend(rows)
            if not rows or page_no * page_size >= total:
                break
            page_no += 1
            time.sleep(0.25)
        except Exception as exc:
            errors.append({'page':page_no, 'error':f'{type(exc).__name__}: {exc}'})
            break
    unique = {}
    for row in raw_rows:
        key = clean_text(row.get('postId') or row.get('jobId') or row.get('name'))
        unique.setdefault(key, row)
    raw_unique = list(unique.values())
    records = [baidu_record(row, recruit_type, access_time, page_url) for row in raw_unique]
    records.sort(key=lambda x:(x['title'],x['source_job_id']))
    audit = {'source_page':page_url, 'endpoint':endpoint, 'recruit_type':recruit_type,
             'ui_page_size':page_size, 'reported_total':total, 'list_rows':len(raw_rows),
             'unique_source_ids':len(raw_unique), 'duplicate_rows':len(raw_rows)-len(raw_unique),
             'detail_full':sum(r['detail_status']=='full' for r in records),
             'detail_partial':sum(r['detail_status']!='full' for r in records),
             'pages':pages, 'errors':errors,
             'scope':'Official public list API; current SOCIAL, GRADUATE or INTERN jobs; all raw category types retained.'}
    # Archive every returned row; the evidence file remains deduplicated.
    return records, raw_rows, audit


def collect_baidu(access_time: str) -> tuple[list[dict], dict]:
    session = requests.Session()
    session.get('https://talent.baidu.com/jobs/list', timeout=30)
    all_records = []
    all_raw = []
    per_type = {}
    for recruit_type in ('SOCIAL','GRADUATE','INTERN'):
        records, raw_rows, audit = collect_baidu_type(session, recruit_type, access_time)
        per_type[recruit_type] = audit
        all_records.extend(records)
        all_raw.extend({'recruit_type':recruit_type,'job':row} for row in raw_rows)
    seen = set()
    deduped = []
    for record in all_records:
        key = record['source_job_id']
        if key not in seen:
            seen.add(key); deduped.append(record)
    audit = {'company':'百度','source_pages':['https://talent.baidu.com/jobs/social-list','https://talent.baidu.com/jobs/list'],
             'reported_portal_counts':{k:v['reported_total'] for k,v in per_type.items()},
             'list_rows_before_deduplication':sum(v['list_rows'] for v in per_type.values()),
             'unique_jobs':len(deduped),
             'duplicate_rows_removed_within_types':sum(v['duplicate_rows'] for v in per_type.values()),
             'duplicate_rows_removed_across_types':len(all_records)-len(deduped),
             'detail_full':sum(r['detail_status']=='full' for r in deduped),
             'detail_partial':sum(r['detail_status']!='full' for r in deduped),
             'by_recruit_type':per_type, 'errors':[e for x in per_type.values() for e in x['errors']],
             'status_note':'Official listings visible at access time; advertised recruitNum is preserved as raw site data, not treated as confirmed remaining headcount.'}
    return deduped, all_raw, audit


PDD_BASE = 'https://careers.pddglobalhr.com'
PDD_SOCIAL_PAGE = PDD_BASE + '/jobs'
PDD_CAMPUS_PAGE = PDD_BASE + '/campus/grad'


def collect_pdd_campus(session: requests.Session, access_time: str, page_size: int = 10):
    endpoint = PDD_BASE + '/api/careers/api/recruit/position/list'
    detail_endpoint = PDD_BASE + '/api/careers/api/recruit/position/detail'
    records, raw_rows, list_rows, pages, errors, detail_errors = [], [], [], [], [], []
    total = None
    page = 1
    while True:
        try:
            response = session.post(endpoint, json={'page': page, 'pageSize': page_size},
                                    headers={'Referer': PDD_CAMPUS_PAGE, 'Origin': PDD_BASE}, timeout=30)
            response.raise_for_status()
            body = response.json()
            if not body.get('success'):
                raise ValueError(f"public list API status={body.get('errorCode')}: {body.get('errorMsg')}")
            result = body.get('result') or {}
            rows = result.get('list') or []
            total = int(result.get('total') or 0)
            pages.append({'page': page, 'records': len(rows), 'reported_total': total})
            list_rows.extend(rows)
            if not rows or page * page_size >= total:
                break
            page += 1
            time.sleep(.25)
        except Exception as exc:
            errors.append({'page': page, 'error': f'{type(exc).__name__}: {exc}'})
            break
    seen = set()
    for row in list_rows:
        code = clean_text(row.get('code') or row.get('id'))
        if not code or code in seen:
            continue
        seen.add(code)
        raw_rows.append({'source': 'campus_list', 'job': row})
        detail = {}
        detail_url = PDD_BASE + '/campus/grad/detail?positionId=' + clean_text(row.get('id'))
        try:
            response = session.post(detail_endpoint, json={'id': row.get('id'), 't': None},
                                    headers={'Referer': detail_url, 'Origin': PDD_BASE}, timeout=30)
            response.raise_for_status()
            body = response.json()
            if not body.get('success'):
                raise ValueError(f"public detail API status={body.get('errorCode')}: {body.get('errorMsg')}")
            detail = body.get('result') if isinstance(body.get('result'), dict) else {}
            if detail:
                raw_rows.append({'source': 'campus_detail', 'job_id': code, 'job': detail})
            else:
                detail_errors.append({'source_job_id': code, 'error': 'detail API returned empty result'})
        except Exception as exc:
            detail_errors.append({'source_job_id': code, 'error': f'{type(exc).__name__}: {exc}'})
        merged = {**row, **detail} if detail else row
        full_requirements = clean_text(merged.get('serveRequirement', ''))
        req_text, parsed_bonus = requirements_and_bonus(full_requirements)
        bonus_text = clean_text(merged.get('bonus', '')) or parsed_bonus
        record = make_record(
            '拼多多', merged, title=merged.get('name', ''), job_id=code, url=detail_url,
            location=merged.get('workLocationName') or merged.get('workLocation') or '未知',
            category=merged.get('jobName') or '未知', posted=merged.get('releaseTime', ''),
            date_semantics='releaseTime为校招公开职位发布日期；详情接口未披露独立更新时间。',
            description=merged.get('jobDuty', ''), requirements=req_text, bonus=bonus_text,
            source_type='拼多多官方校招公开接口（前端 position/list + position/detail）', access_time=access_time,
            detail_status='full' if merged.get('jobDuty') and full_requirements else ('partial' if merged.get('jobDuty') or full_requirements else 'list_only'),
            source_page=PDD_CAMPUS_PAGE,
            extra={'business_track_raw': merged.get('recruitTypeName', '未结构化披露'),
                   'graduation_year_raw': merged.get('graduationYear', '未结构化披露'),
                   'labels_raw': merged.get('labelList', []),
                   'url_resolution': '官网校招列表卡片点击“查看详情”后的实际详情路由；positionId对应原始列表记录id，source_job_id保留官方职位编码。',
                   'full_responsibility_raw': clean_text(merged.get('jobDuty', '')),
                   'full_requirements_raw': full_requirements,
                   'bonus_raw_full': clean_text(merged.get('bonus', '')),
                   'source_status_raw': '校招职位在官网列表可见，且匿名详情接口返回正文；页面未证明剩余HC。'})
        records.append(record)
        time.sleep(.25)
    audit = {'source_page': PDD_CAMPUS_PAGE, 'endpoint': endpoint, 'reported_total': total,
             'detail_endpoint': detail_endpoint, 'list_rows': len(list_rows), 'unique_source_ids': len(records),
             'detail_full': sum(r['detail_status'] == 'full' for r in records),
             'detail_partial': sum(r['detail_status'] == 'partial' for r in records),
             'detail_list_only': sum(r['detail_status'] == 'list_only' for r in records),
             'detail_errors': detail_errors, 'pages': pages, 'errors': errors,
             'scope': '官方应届生公开职位列表与匿名详情接口；按详情返回保留完整职责、资格与加分正文。'}
    return records, raw_rows, audit


def collect_pdd_social(session: requests.Session, access_time: str):
    endpoint = PDD_BASE + '/api/recruit/position/latest_list'
    errors = []
    try:
        response = session.post(endpoint, json={}, headers={'Referer': PDD_SOCIAL_PAGE,
                                 'Origin': PDD_BASE}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if not body.get('success'):
            raise ValueError(f"featured list API status={body.get('errorCode')}: {body.get('errorMsg')}")
        result = body.get('result') or {}
        groups = [('latestPositionList', '最新发布'), ('hottestPositionList', '热招岗位')]
        by_code = {}
        counts = {}
        for field, label in groups:
            rows = result.get(field) or []
            counts[field] = len(rows)
            for raw in rows:
                code = clean_text(raw.get('code') or raw.get('jobCode'))
                if not code:
                    continue
                if code not in by_code:
                    by_code[code] = {**raw, 'featured_groups': []}
                by_code[code]['featured_groups'].append(label)
        records, raw_rows = [], []
        for code, raw in sorted(by_code.items()):
            raw_rows.append(raw)
            records.append(make_record(
                '拼多多', raw, title=raw.get('name', ''), job_id=code,
                url=PDD_SOCIAL_PAGE, source_type='拼多多官方社招公开页面热招/最新列表',
                access_time=access_time, detail_status='list_only', source_page=PDD_SOCIAL_PAGE,
                extra={'featured_groups_raw': raw.get('featured_groups', []),
                       'url_resolution': '官网社招页最新/热招卡片入口；未验证可用的独立详情URL，公开详情提示失效或要求 anti_content，故以列表入口、source_job_id和title定位。',
                       'source_status_raw': '在社招页热招/最新列表可见；公开列表快照未提供正文；未做详情访问绕过。'}))
    except Exception as exc:
        errors.append({'error': f'{type(exc).__name__}: {exc}'})
        counts, records, raw_rows = {}, [], []
    audit = {'source_page': PDD_SOCIAL_PAGE, 'endpoint': endpoint, 'visible_latest_total': counts.get('latestPositionList', 0),
             'visible_featured_total': counts.get('hottestPositionList', 0), 'unique_visible_ids': len(records),
             'detail_full': 0, 'detail_partial': 0, 'detail_list_only': len(records), 'errors': errors,
             'main_search_page_count_text': '0',
             'scope': '官网社招页的最新发布与热招区域；主列表显示共0个职位。详情页公开访问返回失效/不存在或要求 anti_content，未重建该字段。'}
    return records, raw_rows, audit


def collect_pdd(access_time: str):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'})
    session.get(PDD_CAMPUS_PAGE, timeout=30)
    campus, campus_raw, campus_audit = collect_pdd_campus(session, access_time)
    social, social_raw, social_audit = collect_pdd_social(session, access_time)
    records = campus + social
    audit = {'company': '拼多多', 'unique_jobs': len(records), 'detail_full': sum(r['detail_status'] == 'full' for r in records),
             'detail_partial': sum(r['detail_status'] == 'partial' for r in records),
             'detail_list_only': sum(r['detail_status'] == 'list_only' for r in records),
             'reported_portal_counts': {'campus_grad': campus_audit['reported_total'], 'social_main_list': 0,
                                        'social_visible_featured_latest_unique': social_audit['unique_visible_ids']},
             'by_source': {'campus_grad': campus_audit, 'social_featured_latest': social_audit},
             'errors': campus_audit['errors'] + campus_audit.get('detail_errors', []) + social_audit['errors']}
    raw = (campus_raw +
           [{'source': 'social_featured_latest', 'job': x} for x in social_raw])
    return records, raw, audit


IFLYTEK_BASE = 'https://iflytek.zhiye.com'
IFLYTEK_PAGES = {'1': IFLYTEK_BASE + '/social/jobs', '2': IFLYTEK_BASE + '/campus/jobs',
                 '3': IFLYTEK_BASE + '/intern/jobs'}


def iflytek_record(raw: dict, category_id: str, access_time: str, page_url: str) -> dict:
    raw_name = clean_text(raw.get('JobAdName', ''))
    title = clean_text(raw.get('JobAdNameWithoutJobCode')) or re.sub(r'\s*\([A-Za-z]?\d+\)\s*$', '', raw_name)
    duty = clean_text(raw.get('Duty', ''))
    req = clean_text(raw.get('Require', ''))
    req, bonus = requirements_and_bonus(req)
    cls = [clean_text(raw.get(k)) for k in ('ClassificationOne','ClassificationTwo','Classification3','Classification4','Classification5','Classification6') if raw.get(k) not in (None, '')]
    locations = raw.get('LocNames') if isinstance(raw.get('LocNames'), list) else []
    detail_segment = {'1': 'social', '2': 'campus'}.get(category_id)
    job_guid = clean_text(raw.get('Id'))
    url = f"{IFLYTEK_BASE}/{detail_segment}/detail?jobAdId={job_guid}" if detail_segment and job_guid else page_url
    return make_record(
        '科大讯飞', raw, title=title, job_id=raw.get('Id') or raw.get('JobAdId'), url=url,
        location='；'.join(clean_text(x) for x in locations) or '未知',
        category='；'.join(cls) or '未知', experience=raw.get('YearsOfWorking', ''),
        degree=raw.get('Degree', ''), posted=raw.get('PostDate', ''), updated=raw.get('ChangeDate', ''),
        date_semantics='PostDate为页面公开发布日期；ChangeDate为接口原始变更时间；两字段原值保留。',
        description=duty, requirements=req, bonus=bonus,
        source_type='科大讯飞招聘官网公开接口（GetJobAdPageList）', access_time=access_time,
        detail_status='full' if duty and req else ('partial' if duty or req else 'list_only'),
        source_page=page_url,
        extra={'source_internal_id': clean_text(raw.get('JobAdId')) or '未结构化披露',
               'job_code_raw': re.search(r'\(([A-Za-z]?\d+)\)', raw_name).group(1) if re.search(r'\(([A-Za-z]?\d+)\)', raw_name) else '未结构化披露',
               'business_unit_raw': clean_text(raw.get('ClassificationTwo')) or '未结构化披露',
               'category_levels_raw': {k: raw.get(k) for k in ('ClassificationOne','ClassificationTwo','Classification3','Classification4','Classification5','Classification6')},
               'employment_type_raw': raw.get('Kind') or '未结构化披露', 'portal_category_raw': raw.get('Category'),
               'portal_category_id_raw': category_id, 'headcount_reported_raw': raw.get('HeadCount'),
               'salary_raw': raw.get('Salary') if raw.get('Salary') not in (None, '') else '未公开',
               'end_time_raw': raw.get('EndTime', '未结构化披露'), 'detail_record_guid': raw.get('Id'),
               'page_entry_url': page_url,
               'url_resolution': ('匿名页面职位卡片 > “查看详情”实际打开的详情路由；jobAdId为列表Id GUID。'
                                  if detail_segment and job_guid else '岗位列表入口；当前页面没有可核验的独立详情路由。'),
               'full_requirements_raw': clean_text(raw.get('Require', ''))})


def collect_iflytek_category(session: requests.Session, category_id: str, access_time: str, page_size: int = 20):
    page_url = IFLYTEK_PAGES[category_id]
    endpoint = IFLYTEK_BASE + '/api/Jobad/GetJobAdPageList'
    headers = {'Referer': page_url, 'Origin': IFLYTEK_BASE}
    raw_rows, pages, errors = [], [], []
    total = None
    page = 0
    while True:
        payload = {'PageIndex': page, 'PageSize': page_size, 'Category': [category_id], 'KeyWords': '',
                   'SpecialType': 0, 'PortalId': '',
                   'DisplayFields': ['Category', 'Kind', 'LocId', 'PostDate', 'ClassificationOne', 'ClassificationTwo', 'WorkWeChatQrCode']}
        try:
            response = session.post(endpoint, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            body = response.json()
            if body.get('Code') != 200:
                raise ValueError(f"public list API Code={body.get('Code')}: {body.get('Message')}")
            rows = body.get('Data') or []
            # This recruitment portal's top-level Count is the actual UI total;
            # Total remains zero in the ordinary public list response.
            total = int(body.get('Count') or body.get('Total') or 0)
            pages.append({'page_index': page, 'records': len(rows), 'reported_total': total})
            raw_rows.extend(rows)
            if not rows or (page + 1) * page_size >= total:
                break
            page += 1
            time.sleep(.2)
        except Exception as exc:
            errors.append({'page_index': page, 'error': f'{type(exc).__name__}: {exc}'})
            break
    unique = {}
    for row in raw_rows:
        key = clean_text(row.get('Id') or row.get('JobAdId'))
        if key:
            unique.setdefault(key, row)
    records = [iflytek_record(row, category_id, access_time, page_url) for row in unique.values()]
    audit = {'source_page': page_url, 'endpoint': endpoint, 'category_id_raw': category_id, 'ui_page_size': page_size,
             'reported_total': total, 'list_rows': len(raw_rows), 'unique_source_ids': len(records),
             'duplicate_rows': len(raw_rows) - len(records), 'detail_full': sum(r['detail_status'] == 'full' for r in records),
             'detail_partial': sum(r['detail_status'] != 'full' for r in records), 'pages': pages, 'errors': errors,
             'scope': '官方公开列表；保留接口中完整 Duty/Require 正文及全部原始分类、日期和用工字段。'}
    return records, list(unique.values()), audit


def collect_iflytek(access_time: str):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'})
    for url in IFLYTEK_PAGES.values():
        try: session.get(url, timeout=30)
        except Exception: pass
    all_records, all_raw, by_category = [], [], {}
    for category_id in ('1','2','3'):
        records, raw_rows, audit = collect_iflytek_category(session, category_id, access_time)
        by_category[category_id] = audit
        all_records.extend(records)
        all_raw.extend({'portal_category_id': category_id, 'job': row} for row in raw_rows)
    seen, deduped = set(), []
    for row in all_records:
        if row['source_job_id'] not in seen:
            seen.add(row['source_job_id']); deduped.append(row)
    audit = {'company':'科大讯飞', 'unique_jobs':len(deduped),
             'reported_portal_counts':{k:v['reported_total'] for k,v in by_category.items()},
             'detail_full':sum(r['detail_status']=='full' for r in deduped),
             'detail_partial':sum(r['detail_status']!='full' for r in deduped), 'by_portal_category':by_category,
             'errors':[e for x in by_category.values() for e in x['errors']]}
    return deduped, all_raw, audit


NETEASE_BASE = 'https://hr.163.com'
NETEASE_SOCIAL_PAGE = NETEASE_BASE + '/job-list.html'
NETEASE_ENDPOINT = NETEASE_BASE + '/api/hr163/position/queryPage'
NETEASE_METRIC = NETEASE_BASE + '/api/hr163/position/queryPositionMetric'
NETEASE_CAMPUS_PAGE = 'https://campus.163.com'
NETEASE_CAMPUS_NAV = NETEASE_CAMPUS_PAGE + '/api/campuspc/project/navigation/list'
NETEASE_CAMPUS_LIST = NETEASE_CAMPUS_PAGE + '/api/campuspc/position/getJobList'


def netease_record(raw: dict, access_time: str, page_url: str) -> dict:
    description = clean_text(raw.get('description', ''))
    requirement_raw = clean_text(raw.get('requirement', ''))
    requirements, bonus = requirements_and_bonus(requirement_raw)
    places = raw.get('workPlaceNameList') if isinstance(raw.get('workPlaceNameList'), list) else []
    categories = [clean_text(raw.get(k)) for k in ('firstPostTypeName', 'secondPostTypeName') if raw.get(k) not in (None, '')]
    product = clean_text(raw.get('productName', ''))
    dept = clean_text(raw.get('firstDepName', ''))
    return make_record(
        '网易', raw, title=raw.get('name', ''), job_id=raw.get('id'), url=page_url,
        location='；'.join(clean_text(x) for x in places) or '未知',
        category='；'.join(categories) or '未知', experience=raw.get('reqWorkYearsName', ''),
        degree=raw.get('reqEducationName', ''), posted='', updated=raw.get('updateTime', ''),
        date_semantics='官方查询列表返回updateTime（原值毫秒时间戳）；列表未披露明确发布日期字段。',
        description=description, requirements=requirements, bonus=bonus,
        source_type='网易招聘官网公开列表接口（/api/hr163/position/queryPage）', access_time=access_time,
        detail_status='full' if description and requirement_raw else ('partial' if description or requirement_raw else 'list_only'),
        source_page=page_url,
        extra={'business_unit_raw': '；'.join(x for x in (dept, product) if x) or '未结构化披露',
               'employment_type_raw': raw.get('workType', '未结构化披露'),
               'reported_hc_raw': raw.get('recruitNum', '未公开'),
               'url_resolution': '官方社招列表入口；接口提供完整岗位正文及职位ID，未返回独立职位详情URL。可在列表接口按 source_job_id 精确定位。',
               'category_levels_raw': {'firstPostTypeName': raw.get('firstPostTypeName'),
                                       'secondPostTypeName': raw.get('secondPostTypeName'),
                                       'product': raw.get('product'), 'productName': raw.get('productName')},
               'source_status_raw': '可从官网公开列表接口读取；接口未提供明确在招状态字段。',
               'full_requirements_raw': clean_text(raw.get('requirement', '')),
               'official_bee_url_raw': raw.get('beeUrl') or '未结构化披露'})


def netease_campus_record(raw: dict, project: dict, access_time: str) -> dict:
    page_url = project.get('link') or NETEASE_CAMPUS_PAGE + f"/app/job/position?id={project.get('project_id')}"
    return make_record(
        '网易', raw, title=raw.get('positionName', ''), job_id=raw.get('id'), url=page_url,
        location=raw.get('workPlaceName', '未知'), category=raw.get('positionTypeName', '未知'),
        posted='', updated=raw.get('updateTime', ''),
        date_semantics='校园招聘 getJobList 返回updateTime原始毫秒值；未返回明确发布日期字段。',
        description=raw.get('positionDescription', ''), requirements=raw.get('positionRequirement', ''),
        source_type='网易校园招聘官网公开列表接口（/api/campuspc/position/getJobList）',
        access_time=access_time, detail_status='full' if raw.get('positionDescription') and raw.get('positionRequirement') else 'partial',
        source_page=page_url,
        extra={'source_internal_id': clean_text(raw.get('id')) or '未结构化披露',
               'business_unit_raw': clean_text(raw.get('businessUnitName')) or '未结构化披露',
               'url_resolution': '官方校园招聘项目列表入口（project_id）；接口提供完整岗位正文及职位ID，未返回独立职位详情URL。可在项目列表按 source_job_id 精确定位。',
               'employment_type_raw': project.get('navigation_group', '未结构化披露'),
               'category_levels_raw': {'positionTypeName': raw.get('positionTypeName'), 'tagList': raw.get('tagList')},
               'project_id_raw': raw.get('projectId'), 'project_name_raw': project.get('project_name'),
               'project_navigation_group_raw': project.get('navigation_group'),
               'source_status_raw': '项目当前列于官网公开导航；接口无独立在招/剩余HC状态字段。',
               'full_requirements_raw': clean_text(raw.get('positionRequirement', ''))})


def collect_netease_campus(session: requests.Session, access_time: str, page_size: int = 10):
    audit = {'navigation_endpoint': NETEASE_CAMPUS_NAV, 'endpoint': NETEASE_CAMPUS_LIST,
             'projects': {}, 'errors': []}
    raw_archives = []
    try:
        response = session.get(NETEASE_CAMPUS_NAV, headers={'Referer': NETEASE_CAMPUS_PAGE + '/',
                                 'Origin': NETEASE_CAMPUS_PAGE}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get('code') != 200:
            raise ValueError(f"campus navigation API code={body.get('code')}: {body.get('msg')}")
        navigation = body.get('data') or []
        raw_archives.append({'source': 'campus_navigation', 'payload': navigation})
    except Exception as exc:
        audit['errors'].append({'stage': 'navigation', 'error': f'{type(exc).__name__}: {exc}'})
        return [], raw_archives, audit
    projects = []
    for group in navigation:
        for item in group.get('children') or []:
            link = clean_text(item.get('link', ''))
            match = re.search(r'[?&]id=(\d+)', link)
            if match:
                projects.append({'project_id': int(match.group(1)), 'project_name': item.get('title', ''),
                                 'navigation_group': group.get('title', ''), 'link': link,
                                 'page_description': group.get('desc', '')})
    records, all_rows = [], []
    for project in projects:
        pid = project['project_id']
        page_no, total, page_count, pages, errors = 1, None, None, [], []
        while True:
            try:
                response = session.get(NETEASE_CAMPUS_LIST,
                                       params={'projectId': pid, 'currentPage': page_no, 'pageSize': page_size},
                                       headers={'Referer': project['link'], 'Origin': NETEASE_CAMPUS_PAGE}, timeout=30)
                response.raise_for_status()
                body = response.json()
                if body.get('code') != 200:
                    raise ValueError(f"campus list API code={body.get('code')}: {body.get('msg')}")
                data = body.get('data') or {}
                rows = data.get('list') or []
                total, page_count = int(data.get('total') or 0), int(data.get('pages') or 0)
                pages.append({'page': page_no, 'records': len(rows), 'reported_total': total})
                for row in rows:
                    all_rows.append({'source': 'campus_job', 'project': project, 'job': row})
                    records.append(netease_campus_record(row, project, access_time))
                if not rows or page_no >= page_count:
                    break
                page_no += 1
                time.sleep(.25)
            except Exception as exc:
                errors.append({'page': page_no, 'error': f'{type(exc).__name__}: {exc}'})
                break
        audit['projects'][str(pid)] = {'project_name': project.get('project_name'),
                                       'navigation_group': project.get('navigation_group'),
                                       'page_url': project.get('link'), 'reported_total': total,
                                       'reported_pages': page_count, 'list_rows': sum(x['records'] for x in pages),
                                       'unique_source_ids': len({r['source_job_id'] for r in records if r.get('project_id_raw') == pid}),
                                       'detail_full': sum(r['detail_status'] == 'full' and r.get('project_id_raw') == pid for r in records),
                                       'detail_partial': sum(r['detail_status'] != 'full' and r.get('project_id_raw') == pid for r in records),
                                       'pages': pages, 'errors': errors}
        audit['errors'].extend({'project_id': pid, **e} for e in errors)
    audit['current_navigation_projects'] = projects
    audit['navigation_excludes_legacy_project_69'] = True
    audit['legacy_project_id_69_probe'] = {'public_endpoint_total': 9, 'current_navigation_link': False,
                                           'included_in_current_results': False,
                                           'reason': '项目69虽可由历史直链返回岗位，但当前官网导航未链接，故不并入当前项目统计。'}
    return records, raw_archives + all_rows, audit


def collect_netease(access_time: str, page_size: int = 10):
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'})
    session.get(NETEASE_SOCIAL_PAGE, timeout=30)
    portal_metrics = {}
    try:
        metric_response = session.get(NETEASE_METRIC, headers={'Referer': NETEASE_BASE + '/index.html',
                                     'Origin': NETEASE_BASE}, timeout=30)
        metric_response.raise_for_status()
        metric_body = metric_response.json()
        portal_metrics = metric_body.get('data') or {}
    except Exception as exc:
        portal_metrics = {'error': f'{type(exc).__name__}: {exc}'}
    rows, pages, errors = [], [], []
    total = None
    reported_pages = None
    page = 1
    # Public list pages can intermittently lose the proxy connection. Retry each
    # page a few times and continue to later advertised pages after a persistent
    # failure, so one dropped connection does not silently truncate the census.
    while reported_pages is None or page <= reported_pages:
        page_rows = None
        last_error = None
        for attempt in range(1, 5):
            try:
                response = session.post(NETEASE_ENDPOINT, json={'currentPage': page, 'pageSize': page_size},
                                        headers={'Referer': NETEASE_SOCIAL_PAGE, 'Origin': NETEASE_BASE}, timeout=30)
                response.raise_for_status()
                body = response.json()
                if body.get('code') != 200:
                    raise ValueError(f"public list API code={body.get('code')}: {body.get('msg')}")
                data = body.get('data') or {}
                page_rows = data.get('list') or []
                total = int(data.get('total') or 0)
                reported_pages = int(data.get('pages') or 0)
                break
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                if attempt < 4:
                    time.sleep(min(1.5 * attempt, 5))
        if page_rows is None:
            errors.append({'page': page, 'attempts': 4, 'error': last_error})
            if reported_pages is None:
                break
        else:
            pages.append({'page': page, 'records': len(page_rows), 'reported_total': total})
            rows.extend(page_rows)
            if not page_rows:
                break
        if reported_pages is not None and page >= reported_pages:
            break
        page += 1
        time.sleep(.35)
    unique = {}
    for row in rows:
        key = clean_text(row.get('id'))
        if key:
            unique.setdefault(key, row)
    records = [netease_record(row, access_time, NETEASE_SOCIAL_PAGE) for row in unique.values()]
    social_audit = {'source_page': NETEASE_SOCIAL_PAGE, 'endpoint': NETEASE_ENDPOINT, 'ui_page_size': page_size,
             'reported_total': total, 'reported_pages': reported_pages, 'list_rows': len(rows),
             'unique_source_ids': len(records), 'duplicate_rows': len(rows) - len(records),
             'detail_full': sum(r['detail_status'] == 'full' for r in records),
             'detail_partial': sum(r['detail_status'] != 'full' for r in records),
             'pages': pages, 'errors': errors,
             'portal_home_metrics': portal_metrics,
             'scope': '网易社会招聘官网全部公开职位类别；当前公开列表API返回总数与首页统计口径有1条差异，分别留存。'}
    work_type_totals = {}
    for work_type in ('0', '1'):
        try:
            count_response = session.post(NETEASE_ENDPOINT,
                                         json={'currentPage': 1, 'pageSize': page_size, 'workType': work_type},
                                         headers={'Referer': NETEASE_SOCIAL_PAGE + f'?workType={work_type}',
                                                  'Origin': NETEASE_BASE}, timeout=30)
            count_response.raise_for_status()
            count_body = count_response.json()
            count_data = count_body.get('data') or {}
            work_type_totals[work_type] = {'reported_total': int(count_data.get('total') or 0),
                                           'reported_pages': int(count_data.get('pages') or 0),
                                           'response_code': count_body.get('code')}
        except Exception as exc:
            work_type_totals[work_type] = {'error': f'{type(exc).__name__}: {exc}'}
    campus_records, campus_raw, campus_audit = collect_netease_campus(session, access_time)
    all_records = records + campus_records
    deduped = {}
    for row in all_records:
        key = clean_text(row.get('source_job_id'))
        deduped.setdefault(key, row)
    audit = {'company': '网易', 'source_pages': [NETEASE_SOCIAL_PAGE] + [p.get('link') for p in campus_audit.get('current_navigation_projects', [])],
             'reported_portal_counts': {'social_all': total,
                                        'social_intern_workType_1': work_type_totals.get('1', {}).get('reported_total'),
                                        'campus_projects': {k:v.get('reported_total') for k,v in campus_audit.get('projects', {}).items()},
                                        'current_listed_campus_total': sum(v.get('reported_total') or 0 for v in campus_audit.get('projects', {}).values())},
             'work_type_filter_counts_verified': {'workType_0': work_type_totals.get('0'),
                                                   'workType_1': work_type_totals.get('1'),
                                                   'unclassified_or_other_from_all_total': (total or 0) - sum(v.get('reported_total', 0) for v in work_type_totals.values() if isinstance(v, dict) and 'reported_total' in v)},
             'unique_jobs': len(deduped), 'detail_full': sum(r['detail_status'] == 'full' for r in deduped.values()),
             'detail_partial': sum(r['detail_status'] == 'partial' for r in deduped.values()),
             'list_only': sum(r['detail_status'] == 'list_only' for r in deduped.values()),
             'social': social_audit, 'campus': campus_audit,
             'errors': social_audit['errors'] + campus_audit['errors'],
             'status_note': '项目总数反映官网列表接口返回量，不确认实际剩余HC；currentPage、页面URL、原始字段及完整正文随记录保留。'}
    raw = ([{'source': 'social_job', 'job': row} for row in rows] + campus_raw)
    return list(deduped.values()), raw, audit


def main():
    access_time = now_iso()
    collectors = {
        'pdd': collect_pdd,
        'baidu': collect_baidu,
        'iflytek': collect_iflytek,
        'netease': lambda stamp: collect_netease(stamp),
    }
    parser = argparse.ArgumentParser(description='Collect current anonymous public JDs from official employer portals.')
    parser.add_argument('--companies', nargs='*', choices=tuple(collectors), help='company keys; defaults to all four')
    args = parser.parse_args()
    selected = args.companies or list(collectors)
    prior = {}
    audit_path = EVIDENCE / 'software_expanded_audit.json'
    if audit_path.exists():
        try: prior = json.loads(audit_path.read_text(encoding='utf-8'))
        except Exception: prior = {}
    all_audits = {
        **prior,
        'collection_date': dt.datetime.now(ACCESS_TZ).date().isoformat(),
        'timezone': 'Asia/Shanghai', 'last_run_access_time': access_time,
        'scope': '四家公司官网当前匿名公开岗位快照；保留原始分类/经历/学历/日期语义和完整职责、资格、加分正文；不登录、不提交、不绕过验证码或重建签名。',
        'companies': prior.get('companies', {}),
        'collection_runs': prior.get('collection_runs', []) + [{'access_time': access_time, 'companies': selected}],
        'dedupe_policy': '公司内按官方 source_job_id 去重；不同公司和不同官方入口不跨公司合并；来源原始结构字段逐条写入 archives/<company>。',
        'hc_note': '页面列出或原始 recruitNum/HeadCount 数值不表示可确认的实际剩余HC。',
        'clarity_shortlist': prior.get('clarity_shortlist', {}),
    }
    for key in selected:
        collector = collectors[key]
        print(f'[{key}] collection starting', flush=True)
        records, raw_rows, audit = collector(access_time)
        records.sort(key=lambda x: (x.get('source_page', ''), x.get('title', ''), x.get('source_job_id', '')))
        out_path = EVIDENCE / f'{key}_expanded_jobs.json'
        raw_path = ARCHIVES / key / f'{key}_official_public_payloads.jsonl'
        archive_ref = str(raw_path.relative_to(ROOT))
        for record in records:
            record['archive_json'] = archive_ref
            record['archive_key'] = record.get('source_job_id', '未知')
        save_json(out_path, records)
        save_jsonl(raw_path, raw_rows)
        audit.update({'company': records[0]['company'] if records else {'pdd':'拼多多','netease':'网易','baidu':'百度','iflytek':'科大讯飞'}[key],
                      'unique_jobs_written': len(records),
                      'full_text_jobs': sum(r.get('detail_status') == 'full' for r in records),
                      'partial_text_jobs': sum(r.get('detail_status') == 'partial' for r in records),
                      'list_only_jobs': sum(r.get('detail_status') == 'list_only' for r in records),
                      'source_ids_missing': sum(r.get('source_job_id') in ('', '未知') for r in records),
                      'jobs_with_responsibility_text': sum(bool(r.get('description')) for r in records),
                      'jobs_with_requirement_text': sum(bool(r.get('requirements')) for r in records),
                      'jobs_with_bonus_text': sum(bool(r.get('bonus')) for r in records),
                      'jobs_with_unknown_country': sum(r.get('country') == '未知' for r in records),
                      'evidence_file': str(out_path.relative_to(ROOT)),
                      'raw_archive': str(raw_path.relative_to(ROOT))})
        all_audits['companies'][key] = audit
        print(f'[{key}] wrote {len(records)} rows; full={audit["full_text_jobs"]}; partial={audit["partial_text_jobs"]}; list_only={audit["list_only_jobs"]}', flush=True)
    save_json(audit_path, all_audits)
    print(json.dumps({k:{'unique_jobs_written':v['unique_jobs_written'],'reported_portal_counts':v.get('reported_portal_counts'),
                        'full_text_jobs':v['full_text_jobs'],'partial_text_jobs':v['partial_text_jobs'],'list_only_jobs':v['list_only_jobs']}
                      for k,v in all_audits['companies'].items()},ensure_ascii=False,indent=2), flush=True)

if __name__ == '__main__':
    main()
