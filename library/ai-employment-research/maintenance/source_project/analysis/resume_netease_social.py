"""Resume the public NetEase social list from archived pages; never refetch saved pages."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis'))
import collect_software_employers as c  # noqa: E402


AUDIT_PATH = ROOT / 'evidence' / 'software_expanded_audit.json'
EVIDENCE_PATH = ROOT / 'evidence' / 'netease_expanded_jobs.json'
RAW_PATH = ROOT / 'archives' / 'netease' / 'netease_official_public_payloads.jsonl'
PAGE_SIZE = 10


def fetch(session: requests.Session, page: int, page_size: int):
    last = None
    for attempt in range(1, 5):
        try:
            response = session.post(
                c.NETEASE_ENDPOINT,
                json={'currentPage': page, 'pageSize': page_size},
                headers={'Referer': c.NETEASE_SOCIAL_PAGE, 'Origin': c.NETEASE_BASE},
                timeout=30,
            )
            response.raise_for_status()
            body = response.json()
            if body.get('code') != 200:
                raise ValueError(f"public list API code={body.get('code')}: {body.get('msg')}")
            return body.get('data') or {}, None
        except Exception as exc:
            last = f'{type(exc).__name__}: {exc}'
            if attempt < 4:
                time.sleep(min(1.5 * attempt, 5))
    return None, {'page': page, 'attempts': 4, 'error': last}


def main():
    audit_doc = json.loads(AUDIT_PATH.read_text(encoding='utf-8'))
    netease_audit = audit_doc['companies']['netease']
    social_audit = netease_audit['social']
    access_time = c.now_iso()

    old_raw = []
    with RAW_PATH.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():
                old_raw.append(json.loads(line))
    social_raw = [x for x in old_raw if x.get('source') == 'social_job']
    campus_raw = [x for x in old_raw if x.get('source') != 'social_job']
    old_pages = {int(x['page']) for x in social_audit.get('pages', []) if x.get('page') is not None}

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36'})
    session.get(c.NETEASE_SOCIAL_PAGE, timeout=30)

    # Confirm total and page count using the same page size as the archived pages.
    # In this endpoint `pages` changes when pageSize changes, so pageSize=1 would
    # incorrectly turn 2,654 jobs into 2,654 pages. Page 1 is only a count probe;
    # its ten archived job records remain untouched.
    count_data, count_error = fetch(session, 1, PAGE_SIZE)
    if count_error:
        reported_total = int(social_audit.get('reported_total') or 0)
        reported_pages = int(social_audit.get('reported_pages') or 0)
        count_probe = {'error': count_error['error'], 'fallback': 'prior official response'}
    else:
        reported_total = int(count_data.get('total') or 0)
        reported_pages = int(count_data.get('pages') or 0)
        count_probe = {'reported_total': reported_total, 'reported_pages': reported_pages,
                       'response_code': 200, 'page_size': PAGE_SIZE}
    missing_pages = sorted(set(range(1, reported_pages + 1)) - old_pages)
    added_raw = []
    added_page_audit = []
    errors = []

    for page in missing_pages:
        data, error = fetch(session, page, PAGE_SIZE)
        if error:
            errors.append(error)
            print(f'[netease] page {page} unavailable after retries', flush=True)
            continue
        page_rows = data.get('list') or []
        page_total = int(data.get('total') or reported_total)
        if not page_rows:
            errors.append({'page': page, 'attempts': 1, 'error': 'empty page before reported last page'})
        added_page_audit.append({'page': page, 'records': len(page_rows), 'reported_total': page_total})
        for row in page_rows:
            added_raw.append({'source': 'social_job', 'page': page,
                              'query': {'currentPage': page, 'pageSize': PAGE_SIZE}, 'job': row})
        if page % 20 == 0 or page == missing_pages[-1]:
            print(f'[netease] resumed through page {page}; added {len(added_raw)} raw rows', flush=True)
        time.sleep(.35)

    # Reconstruct page labels for the already saved ordered social rows, then append
    # only newly fetched pages. Raw job objects remain verbatim inside their wrappers.
    for index, item in enumerate(social_raw):
        if 'page' not in item:
            page = index // PAGE_SIZE + 1
            item['page'] = page
            item['query'] = {'currentPage': page, 'pageSize': PAGE_SIZE}
    all_social_raw = social_raw + added_raw

    records = json.loads(EVIDENCE_PATH.read_text(encoding='utf-8'))
    by_id = {str(r.get('source_job_id')): r for r in records if r.get('source_job_id') not in ('', None, '未知')}
    for item in added_raw:
        raw = item['job']
        record = c.netease_record(raw, access_time, c.NETEASE_SOCIAL_PAGE)
        by_id.setdefault(str(record['source_job_id']), record)
    records = list(by_id.values())
    for record in records:
        if 'queryPage' in record.get('source_type', ''):
            record['url_resolution'] = '官方社招列表入口；接口提供完整岗位正文及职位ID，未返回独立职位详情URL。可在列表接口按 source_job_id 精确定位。'
        elif 'getJobList' in record.get('source_type', ''):
            record['url_resolution'] = '官方校园招聘项目列表入口（project_id）；接口提供完整岗位正文及职位ID，未返回独立职位详情URL。可在项目列表按 source_job_id 精确定位。'
    records.sort(key=lambda x: (x.get('source_page', ''), x.get('title', ''), x.get('source_job_id', '')))
    archive_ref = str(RAW_PATH.relative_to(ROOT))
    for record in records:
        record['archive_json'] = archive_ref
        record['archive_key'] = record.get('source_job_id', '未知')
    c.save_json(EVIDENCE_PATH, records)
    c.save_jsonl(RAW_PATH, all_social_raw + campus_raw)

    page_audit = {int(x['page']): x for x in social_audit.get('pages', []) if x.get('page') is not None}
    page_audit.update({int(x['page']): x for x in added_page_audit})
    social_ids = {str(x['job'].get('id')) for x in all_social_raw if x.get('job', {}).get('id') not in (None, '')}
    social_audit.update({
        'reported_total': reported_total,
        'reported_pages': reported_pages,
        'list_rows': len(all_social_raw),
        'unique_source_ids': len(social_ids),
        'duplicate_rows': len(all_social_raw) - len(social_ids),
        'detail_full': sum(r.get('detail_status') == 'full' and 'position/getJobList' not in r.get('source_type', '') for r in records),
        'detail_partial': 0,
        'pages': [page_audit[k] for k in sorted(page_audit)],
        'errors': errors,
        'count_probe': count_probe,
        'resumed_from_archived_pages': sorted(old_pages),
        'resumed_missing_pages': missing_pages,
        'scope': '官网匿名公开社招列表；前168页复用同次运行归档响应，只请求当时未成功保存的页；完整职责与资格来自接口列表正文。',
    })

    # Recheck public employment-type totals with bounded retries to keep the
    # observed all-jobs count and visible filters in the audit.
    work_type_totals = {}
    for work_type in ('0', '1'):
        result = None
        last_error = None
        for attempt in range(1, 5):
            try:
                response = session.post(
                    c.NETEASE_ENDPOINT,
                    json={'currentPage': 1, 'pageSize': PAGE_SIZE, 'workType': work_type},
                    headers={'Referer': c.NETEASE_SOCIAL_PAGE + f'?workType={work_type}', 'Origin': c.NETEASE_BASE},
                    timeout=30,
                )
                response.raise_for_status()
                body = response.json()
                if body.get('code') != 200:
                    raise ValueError(f"public filter API code={body.get('code')}: {body.get('msg')}")
                data = body.get('data') or {}
                result = {'reported_total': int(data.get('total') or 0),
                          'reported_pages': int(data.get('pages') or 0), 'page_size': PAGE_SIZE,
                          'response_code': body.get('code')}
                break
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                if attempt < 4:
                    time.sleep(min(1.5 * attempt, 5))
        work_type_totals[work_type] = result or {'error': last_error}
    netease_audit['work_type_filter_counts_verified'] = {
        'workType_0': work_type_totals['0'], 'workType_1': work_type_totals['1'],
        'unclassified_or_other_from_all_total': reported_total - sum(
            v.get('reported_total', 0) for v in work_type_totals.values() if 'reported_total' in v
        ),
    }
    netease_audit['reported_portal_counts']['social_all'] = reported_total
    netease_audit['reported_portal_counts']['social_intern_workType_1'] = work_type_totals['1'].get('reported_total')
    netease_audit['unique_jobs'] = len(records)
    netease_audit['detail_full'] = sum(r.get('detail_status') == 'full' for r in records)
    netease_audit['detail_partial'] = sum(r.get('detail_status') == 'partial' for r in records)
    netease_audit['list_only'] = sum(r.get('detail_status') == 'list_only' for r in records)
    netease_audit['errors'] = errors + netease_audit.get('campus', {}).get('errors', [])
    netease_audit['unique_jobs_written'] = len(records)
    netease_audit['full_text_jobs'] = netease_audit['detail_full']
    netease_audit['partial_text_jobs'] = netease_audit['detail_partial']
    netease_audit['list_only_jobs'] = netease_audit['list_only']
    netease_audit['source_ids_missing'] = sum(r.get('source_job_id') in ('', '未知') for r in records)
    netease_audit['jobs_with_responsibility_text'] = sum(bool(r.get('description')) for r in records)
    netease_audit['jobs_with_requirement_text'] = sum(bool(r.get('requirements')) for r in records)
    netease_audit['jobs_with_bonus_text'] = sum(bool(r.get('bonus')) for r in records)
    netease_audit['jobs_with_unknown_country'] = sum(r.get('country') == '未知' for r in records)
    audit_doc['last_run_access_time'] = access_time
    audit_doc.setdefault('collection_runs', []).append({'access_time': access_time, 'companies': ['netease'],
                                                        'mode': 'resume only uncaptured social pages'})
    c.save_json(AUDIT_PATH, audit_doc)
    print(json.dumps({'reported_total': reported_total, 'reported_pages': reported_pages,
                      'pages_already_archived': len(old_pages), 'pages_fetched_now': len(added_page_audit),
                      'pages_failed_now': errors, 'social_unique_ids': len(social_ids),
                      'company_unique_jobs': len(records), 'full_text_jobs': netease_audit['full_text_jobs'],
                      'work_type_counts': work_type_totals}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
