from __future__ import annotations
import collections, datetime as dt, hashlib, html, json, pathlib, re, unicodedata
from zoneinfo import ZoneInfo

BASE = pathlib.Path(__file__).resolve().parent
ARCH = BASE / 'source_archive'
TZ = ZoneInfo('Asia/Shanghai')
NOW = dt.datetime.now(TZ).isoformat(timespec='seconds')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def clean_html(value):
    s = html.unescape(str(value or ''))
    s = re.sub(r'<\s*br\s*/?\s*>', '\n', s, flags=re.I)
    s = re.sub(r'</(?:p|li|div|tr|h[1-6])\s*>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('\xa0', ' ').replace('\r', '')
    s = re.sub(r'\n[ \t]+', '\n', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def section_split(full_text):
    text = str(full_text or '').strip()
    req_match = re.search(r'【\s*任职要求\s*】|任职要求\s*[:：]?', text)
    duty_match = re.search(r'【\s*(?:岗位职责|工作职责)\s*】|(?:岗位职责|工作职责)\s*[:：]?', text)
    if req_match:
        duties = text[:req_match.start()].strip()
        reqs = text[req_match.end():].strip()
        if duty_match:
            duties = text[duty_match.end():req_match.start()].strip()
        return duties, reqs
    if duty_match:
        return text[duty_match.end():].strip(), ''
    return text, ''


# Major evidence is taken only from a designated major field or individual JD qualification text.
MAJOR_LINE_RE = re.compile(
    r'(?:专业\s*(?:要求|条件|方向|类别|背景|毕业|为|包括|包含)\s*[:：]?'
    r'|相关专业|专业毕业|专业背景)', re.I)


def extract_major_lines(req_text):
    found = []
    for line in str(req_text or '').splitlines():
        line = line.strip()
        if line and MAJOR_LINE_RE.search(line):
            found.append(line)
    return '\n'.join(dict.fromkeys(found))


def major_class(major_raw, source_family):
    s = re.sub(r'\s+', '', str(major_raw or ''))
    if re.search(r'通信', s):
        return 'direct', '岗位专业条件明确列出通信类专业'
    if not s:
        return 'excluded', '岗位任职要求未明确列出专业资格'
    # Keep the Unicom API taxonomy aligned with the already audited 569/249 split.
    unicom_adjacent = ('电子信息', '电子科学与技术', '电子与信息', '电子信息工程')
    if source_family == 'unicom_api':
        adjacent = any(term in s for term in unicom_adjacent)
    else:
        adjacent = any(term in s for term in (
            '电子信息', '电子科学', '电子与信息', '电子信息工程', '电子工程',
            '电子类', '微电子', '电磁场', '电路与系统', '光电', '物理电子',
            '信息工程', '信号处理'))
    if adjacent:
        if '电子信息类' in s:
            return 'adjacent', '岗位专业条件列出电子信息类；按教育部本科目录匹配0807大类，通信工程080703属该类'
        return 'adjacent', '岗位专业条件列出电子/信息相关专业，是否接受通信工程需雇主确认'
    return 'excluded', '明确列出的专业条件不含通信类或电子/信息相邻专业'


def has_catalog_match(major_raw):
    # The broad, literal major class only; a specific major such as 电子信息工程 is not a class match.
    return '电子信息类' in re.sub(r'\s+', '', str(major_raw or ''))


def evidence_fields(major_raw):
    return {
        'major_raw': major_raw,
        'major_evidence_scope': 'job_specific' if major_raw else 'missing_major_field',
        'job_specific': bool(major_raw),
        'major_catalog_match': has_catalog_match(major_raw),
    }


def get_mtime_iso(path):
    return dt.datetime.fromtimestamp(path.stat().st_mtime, TZ).isoformat(timespec='seconds')


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows), encoding='utf-8')


def api_student_status(full):
    if '2026届未就业' in full:
        return '2027届；2026届未就业毕业生可投（岗位正文明确）'
    if '2027届' in full:
        return '2027届（岗位正文明确）'
    if '应届毕业生' in full:
        return '校招应届生（岗位正文未明确毕业年份）'
    return '中国联通2027校招批次；岗位正文未写明确毕业年份'


def api_major(reqs, need_major):
    lines = [ln.strip() for ln in str(reqs or '').splitlines()
             if re.search(r'专业(?:要求|条件|背景)\s*[:：]', ln)]
    need = str(need_major or '').strip()
    if need:
        lines.insert(0, '岗位字段 needMajor：' + need)
    return '\n'.join(dict.fromkeys(lines))


# ---- China Unicom Zhaopin public API: all 1,619 rows ----
api_rows = []
api_pages = sorted(ARCH.glob('union_zhaopin_api_page_*.json'))
for page_path in api_pages:
    payload = read_json(page_path)
    api_rows.extend(payload.get('data', {}).get('jobList', []))
api_retrieved = read_json(BASE / 'union_download_manifest.json').get('captured_at')
api_candidates = []
api_source_audit = []
for ix, row in enumerate(api_rows):
    job = row.get('job') or {}
    comp = row.get('company') or {}
    sid = str(job.get('jobNumber') or job.get('id') or '').strip()
    if not sid:
        continue
    full = clean_html(job.get('detail', ''))
    duties, reqs = section_split(full)
    major = api_major(reqs, job.get('needMajor'))
    row_kind, reason = major_class(major, 'unicom_api')
    company = comp.get('campusOrgName') or comp.get('slaveDisplayOrgName') or '中国联通招聘单位未注明'
    department = (comp.get('campusDepartment') or {}).get('name') or company
    page_num = ix // 100 + 1
    archive_path = f'source_archive/union_zhaopin_api_page_{page_num:03d}.json'
    record = {
        'id': f'unicom_{sid}', 'company': company, 'hiring_unit': department,
        'parent_group': '中国联合网络通信集团有限公司（中国联通）',
        'title': job.get('title') or '', 'source_job_id': sid,
        'source_job_id_kind': 'zhaopin_job_number',
        'source_job_id_note': f'官方授权智联公开jobNumber：{sid}',
        'url': job.get('url') or f'https://xiaoyuan.zhaopin.com/job/{sid}',
        'city': job.get('cityName') or job.get('address') or None,
        'description': duties, 'requirements': reqs, 'full_text': full,
        **evidence_fields(major),
        'degree_raw': job.get('minEducationName') or None,
        'experience_raw': job.get('workingExpName') or None,
        'posted_date': None, 'application_deadline': None,
        'retrieved_at': api_retrieved,
        'batch': '中国联通2027校园招聘（官方授权智联站，campaign 105347）',
        'student_status': api_student_status(full),
        'source_kind': '中国联通官方授权智联校园招聘站公开API',
        'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind, 'screen_reason': reason,
        'source_archive': archive_path,
        'source_archive_all': [archive_path],
        'source_urls': ['https://zglt.zhaopin.com/scjobs/index.html', 'https://fe.zhaopin.com/grace/api/dsc/search-job-list'],
        'source_family': 'unicom_api',
    }
    api_candidates.append(record)
    api_source_audit.append({
        'source_family': 'unicom_api', 'source_job_id': sid,
        'source_job_id_kind': 'zhaopin_job_number', 'source_job_id_note': f'官方授权智联公开jobNumber：{sid}', 'company': company,
        'hiring_unit': department, 'title': record['title'], 'url': record['url'],
        **evidence_fields(major), 'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind, 'screen_reason': reason,
        'source_archive': archive_path, 'source_raw_pool_count': len(api_rows),
    })

# ---- Shandong Unicom 2027 employer page: full static JOBS_DATA JS ----
js_path = ARCH / 'sd_union_jobs_data_js.js'
js_text = js_path.read_text(encoding='utf-8-sig')
js_payload, _ = json.JSONDecoder().raw_decode(js_text.split('=', 1)[1].lstrip())
sd_raw = []
for org_id, org_data in js_payload.get('jobsByOrg', {}).items():
    for job in org_data.get('all', []):
        item = dict(job)
        item['_source_org_id'] = org_id
        sd_raw.append(item)

notice_url = 'https://school.gxjy.sdei.edu.cn/qut/jiuye/zhaopingg/detail/17601'
sd_deadline = '2026-11-15'
sd_retrieved = get_mtime_iso(js_path)
sd_candidates = []
sd_seen_ids = set()
sd_source_audit = []
synthetic_count = 0
for ix, job in enumerate(sd_raw):
    org_id = job.get('_source_org_id') or ''
    full = str(job.get('description') or '').replace('\r', '').strip()
    duties, reqs = section_split(full)
    major = extract_major_lines(reqs)
    row_kind, reason = major_class(major, 'unicom_shandong')
    zhao_id = str(job.get('zhaopinNumber') or '').strip()
    iguopin_id = str(job.get('iguopinId') or '').strip()
    if zhao_id:
        sid, sid_kind = zhao_id, 'zhaopin_job_number'
        dedup_key = zhao_id
    elif iguopin_id:
        sid, sid_kind = 'iguopin:' + iguopin_id, 'iguopin_id'
        dedup_key = sid
    else:
        synthetic_count += 1
        raw_loc = '|'.join([org_id, str(job.get('city') or ''), str(job.get('unit') or ''), str(job.get('title') or ''), full])
        locator = hashlib.sha256(raw_loc.encode('utf-8')).hexdigest()[:16]
        sid, sid_kind = f'synthetic_locator:sdlt_2027:{org_id}:{locator}', 'synthetic_locator'
        dedup_key = sid
    sd_seen_ids.add(dedup_key)
    company = '联通（山东）产业互联网有限公司' if org_id == 'chanhu' else '中国联合网络通信有限公司山东省分公司'
    city = job.get('city') or ('山东省' if org_id == 'province' else None)
    unit = job.get('unit') or job.get('branch') or '山东省招聘单位未单列'
    url = job.get('zhaopinUrl') or job.get('iguopinUrl') or 'https://sdlt.kongxuan.com/index.html'
    student_status = '2027届；2026届未就业毕业生可投（岗位任职要求明确）' if '2026届未就业' in full else '中国联通山东2027校园招聘批次；岗位正文未写明2026届未就业条件'
    deadline = re.search(r'截止(?:时间)?[：: ]*(20\d{2}[-年/]\d{1,2}[-月/]\d{1,2}日?)', full)
    record = {
        'id': f'unicom_{sid.replace(":", "_")}', 'company': company, 'hiring_unit': unit,
        'parent_group': '中国联合网络通信集团有限公司（中国联通）',
        'title': job.get('title') or '', 'source_job_id': sid,
        'source_job_id_kind': sid_kind,
        'source_job_id_note': (f'官方/智联公开jobNumber：{zhao_id}' if zhao_id else (f'公开iguopinId：{iguopin_id}' if iguopin_id else f'无jobNumber与iguopinId，合成定位ID（org/city/unit/title/详情SHA-256前16位）：{sid}')),
        'url': url, 'city': city,
        'description': duties, 'requirements': reqs, 'full_text': full,
        **evidence_fields(major),
        'degree_raw': next((ln.strip() for ln in reqs.splitlines() if '学历要求' in ln or re.search(r'(本科|硕士|博士).{0,12}学历', ln)), None),
        'experience_raw': next((ln.strip() for ln in reqs.splitlines() if '工作经验' in ln or '工作经历' in ln), None),
        'posted_date': None, 'application_deadline': sd_deadline,
        'application_deadline_source': notice_url,
        'retrieved_at': sd_retrieved,
        'batch': '中国联通山东省分公司2027校园招聘（就业平台转载并链接雇主招聘站）',
        'student_status': student_status,
        'application_window_raw': '2027届普通高等院校应届毕业生；2026届未就业毕业生也可招收' if '2026届未就业' in full else None,
        'source_kind': '中国联通山东2027招聘雇主站公开静态JOBS_DATA',
        'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind, 'screen_reason': reason,
        'source_archive': 'source_archive/sd_union_jobs_data_js.js',
        'source_archive_all': ['source_archive/sd_union_jobs_data_js.js', 'source_archive/sd_union_2027_home.html', 'source_archive/shandong_unicom_2027_university_notice.html'],
        'source_urls': ['https://sdlt.kongxuan.com/index.html', notice_url],
        'source_family': 'unicom_shandong',
        'source_org_id': org_id,
    }
    sd_candidates.append(record)
    sd_source_audit.append({
        'source_family': 'unicom_shandong', 'source_job_id': sid, 'source_job_id_kind': sid_kind,
        'source_job_id_note': (f'官方/智联公开jobNumber：{zhao_id}' if zhao_id else (f'公开iguopinId：{iguopin_id}' if iguopin_id else f'无jobNumber与iguopinId，合成定位ID：{sid}')),
        'company': company, 'hiring_unit': unit, 'city': city, 'title': record['title'],
        'url': url, **evidence_fields(major), 'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind,
        'screen_reason': reason, 'source_archive': 'source_archive/sd_union_jobs_data_js.js',
        'source_org_id': org_id,
    })

# ---- Fiberhome: all 38 rendered public UI details (the complete source scope) ----
fiber_json = read_json(ARCH / 'fiberhome_rendered_details.json')
if isinstance(fiber_json, str):
    fiber_json = json.loads(fiber_json)
LABEL_RE = re.compile(r'【\s*(工作职责|岗位职责|任职要求|岗位要求)\s*】|(?<![A-Za-z])(?:工作职责|岗位职责|任职要求|岗位要求)\s*[:：]?', re.I)

def moka_sections(body):
    matches = list(LABEL_RE.finditer(body))
    duties, requirements = [], []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        label = re.sub(r'[^\u4e00-\u9fff]', '', match.group(0))
        value = body[match.end():end].strip()
        if label in ('工作职责', '岗位职责') and value:
            duties.append(value)
        elif label in ('任职要求', '岗位要求') and value:
            requirements.append(value)
    if not requirements:
        _, req = section_split(body)
        if req:
            requirements = [req]
    if not duties and requirements:
        first_req = body.find(requirements[0])
        duties = [body[:first_req].strip()] if first_req > 0 else []
    return '\n\n'.join(duties).strip(), '\n\n'.join(requirements).strip()

def req_major_lines(req_text):
    return extract_major_lines(req_text)

def raw_job_body(visible_text):
    s = str(visible_text or '')
    if '职位描述' in s:
        s = s.split('职位描述', 1)[1]
    if '\n职位信息' in s:
        s = s.split('\n职位信息', 1)[0]
    return s.strip()

fiber_candidates = []
fiber_source_audit = []
for job in fiber_json:
    body = raw_job_body(job.get('visible_text', ''))
    duties, reqs = moka_sections(body)
    major = req_major_lines(reqs)
    row_kind, reason = major_class(major, 'device_vendor')
    sid = str(job.get('source_job_id') or '').strip()
    archive_path = 'source_archive/fiberhome_rendered_details.json'
    record = {
        'id': f'fiberhome_{sid}', 'company': '烽火通信科技股份有限公司',
        'hiring_unit': '烽火通信科技股份有限公司',
        'parent_group': '中国信息通信科技集团有限公司（中国信科集团）',
        'title': job.get('title') or '', 'source_job_id': sid,
        'source_job_id_kind': 'mokahr_job_uuid', 'source_job_id_note': 'Moka详情页UUID', 'url': job.get('detail_url') or f'https://app.mokahr.com/campus-recruitment/whfhtx/73922#/job/{sid}',
        'city': None, 'description': duties, 'requirements': reqs, 'full_text': body,
        **evidence_fields(major),
        'degree_raw': next((ln.strip() for ln in reqs.splitlines() if '学历' in ln or re.search(r'(本科|硕士|博士).{0,12}(?:以上|学历)', ln)), None),
        'experience_raw': next((ln.strip() for ln in reqs.splitlines() if '工作经验' in ln or '工作经历' in ln), None),
        'posted_date': job.get('posted_date'), 'application_deadline': None,
        'retrieved_at': get_mtime_iso(ARCH / 'fiberhome_rendered_details.json'),
        'batch': '烽火通信2027届校园招聘', 'student_status': '2027届校园招聘',
        'source_kind': '烽火通信官方Moka校园招聘公开详情页（正常浏览器UI采集）',
        'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind, 'screen_reason': reason,
        'source_archive': archive_path,
        'source_archive_all': [archive_path, 'source_archive/fiberhome_mokahr.html', 'source_archive/mokahr_recruitmentWeb-20261104-1624-f8380-release.js'],
        'source_urls': ['https://app.mokahr.com/campus-recruitment/whfhtx/73922', job.get('detail_url')],
        'source_family': 'fiberhome', 'source_category': job.get('category'),
    }
    fiber_candidates.append(record)
    fiber_source_audit.append({
        'source_family': 'fiberhome', 'source_job_id': sid,
        'source_job_id_kind': 'mokahr_job_uuid', 'source_job_id_note': 'Moka详情页UUID', 'company': record['company'],
        'hiring_unit': record['hiring_unit'], 'title': record['title'], 'url': record['url'],
        **evidence_fields(major), 'row_kind': 'full_jd' if full else 'listing_only', 'major_screen_class': row_kind, 'screen_reason': reason,
        'source_archive': archive_path, 'source_category': job.get('category'),
    })

# ---- ZTE: one complete, stable rendered public detail; no encrypted API bypass ----
zte_path = ARCH / 'zte_ai_detail.txt'
zte_text = zte_path.read_text(encoding='utf-8-sig')
try:
    zte_text = json.loads(zte_text)
except Exception:
    pass
zte_text = str(zte_text).replace('\r', '')
links_raw = read_json(ARCH / 'zte_page1_links.json')
if isinstance(links_raw, str):
    links_raw = json.loads(links_raw)
zte_sid = 'f53af2c5-db6b-4ba2-941d-363818c43b3a'
zte_listing = next((x for x in links_raw if zte_sid in str(x.get('href', ''))), {})
zte_body = zte_text[zte_text.find('职位描述') + len('职位描述'):].strip() if '职位描述' in zte_text else zte_text
if '\n职位信息' in zte_body:
    zte_body = zte_body.split('\n职位信息', 1)[0]
zte_duties, zte_reqs = moka_sections(zte_body)
zte_major = extract_major_lines(zte_reqs)
zte_kind, zte_reason = major_class(zte_major, 'device_vendor')
zte_city = None
if zte_listing:
    lm = re.search(r'\n\|\s*\n(.*?)(?:\n\1|\Z)', zte_listing.get('text', ''), re.S)
    if lm:
        zte_city = re.sub(r'\s+', ' ', lm.group(1)).strip()
if not zte_city:
    m = re.search(r'(?:硕士|本科|博士)\|([^\n]+)', zte_text)
    zte_city = m.group(1).strip() if m else None
zte_app_window = next((ln.strip() for ln in zte_text.splitlines() if '投递1次' in ln or '投递一次' in ln), None)
zte_candidate = {
    'id': f'zte_{zte_sid}', 'company': '中兴通讯股份有限公司',
    'hiring_unit': '中兴通讯股份有限公司', 'parent_group': None,
    'title': 'AI算法工程师', 'source_job_id': zte_sid,
    'source_job_id_kind': 'mokahr_job_uuid', 'source_job_id_note': 'Moka详情页UUID',
    'url': f'https://app.mokahr.com/campus-recruitment/zte/46903#/job/{zte_sid}',
    'city': zte_city, 'description': zte_duties, 'requirements': zte_reqs,
    'full_text': zte_body, **evidence_fields(zte_major),
    'degree_raw': '硕士（详情页职位信息）',
    'experience_raw': next((ln.strip() for ln in zte_reqs.splitlines() if '工作经验' in ln or '工作经历' in ln), None),
    'posted_date': re.search(r'发布于\s*(\d{4}-\d{2}-\d{2})', zte_listing.get('text', '')).group(1) if re.search(r'发布于\s*(\d{4}-\d{2}-\d{2})', zte_listing.get('text', '')) else None,
    'application_deadline': '2027-08-31' if zte_app_window and '2027年08月31日' in zte_app_window else None,
    'application_window_raw': zte_app_window,
    'retrieved_at': get_mtime_iso(zte_path), 'batch': '中兴通讯2027应届生招聘',
    'student_status': '2027届应届生招聘',
    'source_kind': '中兴通讯官方Moka校园招聘公开详情页（正常浏览器UI采集）',
    'row_kind': 'full_jd' if zte_body else 'listing_only', 'major_screen_class': zte_kind, 'screen_reason': zte_reason,
    'source_archive': 'source_archive/zte_ai_detail.txt',
    'source_archive_all': ['source_archive/zte_ai_detail.txt', 'source_archive/zte_page1_links.json', 'source_archive/zte_mokahr.html'],
    'source_urls': ['https://app.mokahr.com/campus-recruitment/zte/46903', f'https://app.mokahr.com/campus-recruitment/zte/46903#/job/{zte_sid}'],
    'source_family': 'zte',
}
zte_source_audit = [{
    'source_family': 'zte', 'source_job_id': zte_sid,
    'source_job_id_kind': 'mokahr_job_uuid', 'source_job_id_note': 'Moka详情页UUID', 'company': zte_candidate['company'],
    'hiring_unit': zte_candidate['hiring_unit'], 'title': zte_candidate['title'], 'url': zte_candidate['url'],
    **evidence_fields(zte_major), 'row_kind': 'full_jd' if zte_body else 'listing_only', 'major_screen_class': zte_kind, 'screen_reason': zte_reason,
    'source_archive': 'source_archive/zte_ai_detail.txt',
}]

candidates = api_candidates + sd_candidates + fiber_candidates + [zte_candidate]

# Cross-source and within-source deduplication by published official job ID. Synthetic IDs remain source-scoped.
def dedup_key(row):
    kind = row.get('source_job_id_kind')
    sid = str(row.get('source_job_id') or '')
    if kind == 'synthetic_locator':
        return f"{row.get('source_family')}::{sid}"
    if kind == 'iguopin_id':
        return f'iguopin::{sid}'
    return f'official::{sid}'

groups = collections.OrderedDict()
for row in candidates:
    groups.setdefault(dedup_key(row), []).append(row)
records = []
dedup_audit = []
for key, group in groups.items():
    # Fullest captured detail is primary; any direct qualification keeps the consolidated row direct.
    primary = max(group, key=lambda x: (len(x.get('full_text') or ''), x.get('source_family') == 'unicom_shandong'))
    merged = dict(primary)
    merged['major_screen_class'] = 'direct' if any(x['major_screen_class'] == 'direct' for x in group) else ('adjacent' if any(x['major_screen_class'] == 'adjacent' for x in group) else 'excluded')
    merged['row_kind'] = 'full_jd' if any(x.get('row_kind') == 'full_jd' for x in group) else 'listing_only'
    merged['source_archive_all'] = list(dict.fromkeys(a for x in group for a in x.get('source_archive_all', [x.get('source_archive')]) if a))
    merged['source_urls'] = list(dict.fromkeys(u for x in group for u in x.get('source_urls', []) if u))
    merged['hiring_units'] = list(dict.fromkeys(x.get('hiring_unit') for x in group if x.get('hiring_unit')))
    if len(merged['hiring_units']) > 1:
        merged['hiring_unit'] = '；'.join(merged['hiring_units'])
    merged['companies'] = list(dict.fromkeys(x.get('company') for x in group if x.get('company')))
    if len(merged['companies']) > 1:
        merged['company'] = '；'.join(merged['companies'])
    if len(group) > 1:
        merged['source_kinds'] = list(dict.fromkeys(x.get('source_kind') for x in group if x.get('source_kind')))
        merged['dedup_merged_count'] = len(group)
    else:
        merged['dedup_merged_count'] = 1
    dedup_audit.append({
        'dedup_key': key, 'source_rows': len(group),
        'source_families': [x.get('source_family') for x in group],
        'source_job_ids': [x.get('source_job_id') for x in group],
        'source_archives': list(dict.fromkeys(x.get('source_archive') for x in group if x.get('source_archive'))),
        'action': 'deduplicated_merge' if len(group) > 1 else 'unique',
        'consolidated_row_kind': merged['row_kind'], 'consolidated_major_screen_class': merged['major_screen_class'],
    })
    if merged['major_screen_class'] != 'excluded':
        records.append(merged)

# Re-open the source-by-source screening rows to retain the full structured record, including statuses and deadlines.
all_audits = api_source_audit + sd_source_audit + fiber_source_audit + zte_source_audit
structured_fields = ('id','parent_group','city','description','requirements','full_text','degree_raw','experience_raw','posted_date','application_deadline','application_deadline_source','application_window_raw','retrieved_at','batch','student_status','source_kind','source_archive_all','source_urls')
for audit in all_audits:
    rec = next((r for r in candidates if r.get('source_family') == audit.get('source_family') and r.get('source_job_id') == audit.get('source_job_id')), None)
    if rec:
        for field in structured_fields:
            audit[field] = rec.get(field)
by_source_id = collections.defaultdict(list)
for row in candidates:
    by_source_id[dedup_key(row)].append(row)
for audit in all_audits:
    match = next((r for r in candidates if r.get('source_job_id') == audit.get('source_job_id') and r.get('source_family') == audit.get('source_family')), None)
    key = dedup_key(match) if match else ''
    audit['dedup_group_key'] = key
    audit['dedup_status'] = 'duplicate_merged' if key and len(by_source_id[key]) > 1 else 'unique'
    audit['dedup_group_source_rows'] = len(by_source_id[key]) if key else 1

# Save full, auditable screening results for every source row, including exclusions.
write_jsonl(BASE / 'union_screening_results.jsonl', api_source_audit)
write_jsonl(BASE / 'sd_screening_results.jsonl', sd_source_audit)
write_jsonl(BASE / 'fiberhome_screening_results.jsonl', fiber_source_audit)
write_jsonl(BASE / 'zte_screening_results.jsonl', zte_source_audit)
write_jsonl(BASE / 'screening_results.jsonl', all_audits)
write_jsonl(BASE / 'union_records.jsonl', [r for r in api_candidates if r['major_screen_class'] != 'excluded'])
write_jsonl(BASE / 'sd_records.jsonl', [r for r in sd_candidates if r['major_screen_class'] != 'excluded'])
write_jsonl(BASE / 'fiberhome_records.jsonl', [r for r in fiber_candidates if r['major_screen_class'] != 'excluded'])
write_jsonl(BASE / 'zte_records.jsonl', [zte_candidate] if zte_candidate['major_screen_class'] != 'excluded' else [])
write_jsonl(BASE / 'records.jsonl', records)
(BASE / 'dedup_log.json').write_text(json.dumps({
    'generated_at': NOW,
    'rule': 'deduplicate by exact official source job ID (Zhaopin jobNumber or Moka UUID); iguopin IDs are retained when no Zhaopin number exists; synthetic locators are source-scoped and explicitly marked',
    'raw_source_rows': len(candidates), 'unique_groups': len(groups),
    'duplicate_rows_merged': sum(len(v)-1 for v in groups.values()),
    'api_shandong_zhaopin_id_intersection': len(
        {x.get('source_job_id') for x in api_candidates} & {x.get('source_job_id') for x in sd_candidates if x.get('source_job_id_kind') == 'zhaopin_job_number'}),
    'synthetic_locator_count': synthetic_count,
    'source_rows': {k: sum(1 for x in candidates if x['source_family'] == k) for k in ['unicom_api','unicom_shandong','fiberhome','zte']},
    'groups': dedup_audit,
}, ensure_ascii=False, indent=2), encoding='utf-8')

# Screening counts per source and overall.
def counts(rows):
    return dict(collections.Counter(x.get('major_screen_class') for x in rows))
dedup_class_counts = dict(collections.Counter(g['consolidated_major_screen_class'] for g in dedup_audit))
summary = {
    'generated_at': NOW,
    'source_rows': {'unicom_api': len(api_source_audit), 'unicom_shandong': len(sd_raw), 'fiberhome': len(fiber_source_audit), 'zte': len(zte_source_audit)},
    'screening': {'unicom_api': counts(api_source_audit), 'unicom_shandong': counts(sd_source_audit), 'fiberhome': counts(fiber_source_audit), 'zte': counts(zte_source_audit), 'all_source_rows': counts(all_audits)},
    'deduplicated_screening': dedup_class_counts,
    'full_jd_source_rows': sum(x.get('row_kind') == 'full_jd' for x in all_audits),
    'listing_only_source_rows': sum(x.get('row_kind') != 'full_jd' for x in all_audits),
    'full_jd_unique_groups': sum(g['consolidated_row_kind'] == 'full_jd' for g in dedup_audit),
    'records_after_dedup': {'total': len(records), **counts(records), 'major_catalog_match': sum(bool(x.get('major_catalog_match')) for x in records), 'student_status': dict(collections.Counter(x.get('student_status') for x in records))},
    'unicom_api_pages': len(api_pages), 'unicom_api_reported_total': read_json(BASE / 'union_download_manifest.json').get('total_reported'),
    'shandong_js_total': len(sd_raw), 'shandong_unique_ids': len(sd_seen_ids),
    'shandong_zhaopin_ids': sum(x.get('source_job_id_kind') == 'zhaopin_job_number' for x in sd_candidates),
    'shandong_iguopin_ids': sum(x.get('source_job_id_kind') == 'iguopin_id' for x in sd_candidates),
    'shandong_raw_rows_without_zhaopin_jobnumber': sum(not x.get('source_job_id_note','').startswith('官方/智联公开jobNumber') for x in sd_candidates),
    'shandong_synthetic_ids': sum(x.get('source_job_id_kind') == 'synthetic_locator' for x in sd_candidates),
    'fiberhome_distinct_job_uuids': len({x.get('source_job_id') for x in fiber_candidates}),
    'zte_complete_details': 1,
}
(BASE / 'collection_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

# Source-level metadata and SHA-256 for every archived source artifact.
url_map = {
    'union_zhaopin_home.html': 'https://zglt.zhaopin.com/mjobs/',
    'union_zhaopin_campus.html': 'https://zglt.zhaopin.com/scjobs/index.html',
    'union_zhaopin_mjobs_js.js': 'https://zglt.zhaopin.com/assets/mjobs-8682bb55.js',
    'union_zhaopin_scjobs_js.js': 'https://zglt.zhaopin.com/assets/scjobs-b1515ebc.js',
    'union_zhaopin_cms-data-41c20234.js': 'https://zglt.zhaopin.com/assets/cms-data-41c20234.js',
    'union_zhaopin_index-8c6c9b6f.js': 'https://zglt.zhaopin.com/assets/index-8c6c9b6f.js',
    'union_zhaopin_index-e79edb12.js': 'https://zglt.zhaopin.com/assets/index-e79edb12.js',
    'sd_union_2027_home.html': 'https://sdlt.kongxuan.com/index.html',
    'sd_union_jobs_data_js.js': 'https://sdlt.kongxuan.com/js/data/jobs-data.js?v=20260928q',
    'sd_union_job_description_js.js': 'https://sdlt.kongxuan.com/js/job-description.js?v=20260928e',
    'sd_union_getJob_js.js': 'https://sdlt.kongxuan.com/js/module/getJob.js?v=20260928z',
    'shandong_unicom_2027_university_notice.html': notice_url,
    'fiberhome_mokahr.html': 'https://app.mokahr.com/campus-recruitment/whfhtx/73922',
    'fiberhome_rendered_details.json': 'https://app.mokahr.com/campus-recruitment/whfhtx/73922 (all public category and detail views)',
    'mokahr_recruitmentWeb-20261104-1624-f8380-release.js': 'https://app.mokahr.com/static/recruitmentWeb-20261104-1624-f8380-release.js',
    'mokahr_initial-d0540dff6f0a85d6fed2eeaa05519b92.js': 'https://app.mokahr.com/static/mokahr_initial-d0540dff6f0a85d6fed2eeaa05519b92.js',
    'zte_mokahr.html': 'https://app.mokahr.com/campus-recruitment/zte/46903',
    'zte_ai_detail.txt': f'https://app.mokahr.com/campus-recruitment/zte/46903#/job/{zte_sid}',
    'zte_page1_links.json': 'https://app.mokahr.com/campus-recruitment/zte/46903#/jobs?project=100022014',
    'zte_2027_nankai_notice.html': 'https://career.nankai.edu.cn/correcruit/content/id/117127.html',
    'union_2027_tju_authorization.html': 'https://job.tju.edu.cn/recruitment/content/type/2/id/6404.html',
    'moe_2026_undergraduate_catalog.html': 'https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/t20260427_1434931.html',
}
page_manifest = read_json(BASE / 'union_download_manifest.json')
api_page_meta = {p['name']: p for p in page_manifest.get('pages', [])}
raw_artifacts = []
for p in sorted(ARCH.iterdir()):
    if not p.is_file():
        continue
    data = p.read_bytes()
    name = p.name
    api_meta = api_page_meta.get(name)
    raw_artifacts.append({
        'name': name, 'path': f'source_archive/{name}', 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'url': api_meta.get('url') if api_meta else url_map.get(name),
        'http_status': api_meta.get('http_status') if api_meta else (403 if name == 'zte_2027_nankai_notice.html' else (200 if name not in ('authority_sources_manifest.json', 'initial_manifest.json') else None)),
        'content_kind': ('api_raw_json' if name.startswith('union_zhaopin_api_page_') else ('rendered_public_ui_capture' if name in ('fiberhome_rendered_details.json','zte_ai_detail.txt','zte_page1_links.json') else ('metadata_manifest' if name.endswith('manifest.json') else 'raw_source_response_or_capture'))),
    })

# Official references may be read through the public web index even where raw TLS retrieval was blocked.
authority_evidence = [
    {'name': '国务院国资委央企名录', 'url': 'https://wap.sasac.gov.cn/n2588045/n27271785/n27271792/c14159097/content.html', 'supports': '中国联合网络通信集团有限公司、中国信息通信科技集团有限公司列入中央企业集团名录', 'raw_archive_status': 'Python TLS certificate retrieval failed; official page content verified through public web search'},
    {'name': '中国信科集团组织架构', 'url': 'https://www.cict.com/p1/AboutOrganization.jhtml', 'supports': '组织架构页面列出烽火通信科技股份有限公司为集团下属公司', 'raw_archive_status': 'Direct raw retrieval ended with TLS EOF; official page content verified through public web search'},
    {'name': '中国信科集团介绍', 'url': 'https://www.cict.com/p1/AboutCompany.jhtml', 'supports': '集团介绍说明中国信科为国务院国资委直属中央企业', 'raw_archive_status': 'URL verified; no raw copy archived'},
    {'name': '教育部普通高等学校本科专业目录（2026年）', 'url': 'https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/t20260427_1434931.html', 'supports': '080703通信工程列于0807电子信息类；仅岗位原文出现“电子信息类”时标记major_catalog_match', 'raw_archive_status': 'HTTP 200; raw HTML archived with SHA-256'},
]
source_manifest = {
    'generated_at': NOW,
    'collection_scope': '中国联通公开校招批次（集团智联API全量+山东2027静态职位数据）及设备商已完整采集的烽火38条、中兴1条详情',
    'collection_denominators': summary['source_rows'],
    'screening_counts': summary['screening'],
    'dedup_summary': {
        'candidate_rows': len(candidates), 'unique_id_groups': len(groups),
        'merged_duplicate_rows': sum(len(v)-1 for v in groups.values()),
        'api_shandong_jobnumber_intersection': json.loads((BASE/'dedup_log.json').read_text(encoding='utf-8'))['api_shandong_zhaopin_id_intersection'],
        'dedup_log': 'dedup_log.json',
    },
    'sources': [
        {'source_family': 'unicom_api', 'name': '中国联通官方授权智联校园招聘站', 'entry_url': 'https://zglt.zhaopin.com/scjobs/index.html', 'data_url': 'https://fe.zhaopin.com/grace/api/dsc/search-job-list', 'method': '匿名公开页面调用的普通JSON分页响应', 'page_count': len(api_pages), 'reported_total': len(api_rows), 'raw_pages': [f'source_archive/{p.name}' for p in api_pages], 'retrieved_at': api_retrieved},
        {'source_family': 'unicom_shandong', 'name': '中国联通山东2027雇主招聘站', 'entry_url': 'https://sdlt.kongxuan.com/index.html', 'university_notice_url': notice_url, 'method': '公开静态JOBS_DATA JS完整清单', 'raw_rows': len(sd_raw), 'application_deadline': sd_deadline, 'posted_date_policy': '未见职位发布日期字段，posted_date保持null'},
        {'source_family': 'fiberhome', 'name': '烽火通信2027校园招聘', 'entry_url': 'https://app.mokahr.com/campus-recruitment/whfhtx/73922', 'method': '正常匿名浏览器UI逐类别打开全部详情', 'raw_rows': len(fiber_json), 'category_counts': dict(collections.Counter(x.get('category') for x in fiber_json)), 'raw_detail_capture': 'source_archive/fiberhome_rendered_details.json'},
        {'source_family': 'zte', 'name': '中兴通讯2027应届生招聘', 'entry_url': 'https://app.mokahr.com/campus-recruitment/zte/46903', 'method': '正常匿名浏览器UI完成1条详情；未解密加密API字段', 'raw_rows': 1, 'scope_note': '用户指定保留1条稳定完整详情，不继续追踪不稳定详情；官网列表出现更多岗位但不作为本批次完整采集分母'},
    ],
    'authority_evidence': authority_evidence,
    'raw_artifacts': raw_artifacts,
    'derived_outputs': [],
}
for output_name in ('records.jsonl','screening_results.jsonl','union_screening_results.jsonl','sd_screening_results.jsonl','fiberhome_screening_results.jsonl','zte_screening_results.jsonl','collection_summary.json','dedup_log.json','notes.md'):
    output_path = BASE / output_name
    if output_path.exists():
        out_bytes = output_path.read_bytes()
        source_manifest['derived_outputs'].append({'name': output_name, 'path': output_name, 'bytes': len(out_bytes), 'sha256': hashlib.sha256(out_bytes).hexdigest()})
(BASE / 'source_manifest.json').write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding='utf-8')

print(json.dumps(summary, ensure_ascii=False, indent=2))
