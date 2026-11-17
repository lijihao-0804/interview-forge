"""Rebuild an evidence-separated communications-major dataset and static handoff.
No live crawling. Inputs are immutable upstream corpus and source-specific records.jsonl.
"""
import argparse,collections,csv,gzip,hashlib,html,importlib.util,json,re,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True  # archived upstream code is read-only evidence; do not create caches there
ROOT=Path(__file__).resolve().parents[1]
UP=ROOT.parents[1]/'前端交接包_就业数据台'
OUT=ROOT/'通信工程就业数据包'
argparser=argparse.ArgumentParser(description=__doc__)
argparser.add_argument('--topic-root',type=Path,default=ROOT)
argparser.add_argument('--upstream',type=Path,default=UP)
argparser.add_argument('--output',type=Path,default=OUT)
argparser.add_argument('--as-of',default='2026-11-18',help='Snapshot compilation date YYYY-MM-DD; source dates remain on each record')
args,_=argparser.parse_known_args()
ROOT=args.topic_root.resolve();UP=args.upstream.resolve();OUT=args.output.resolve()
RULE_VERSION='communications-major-v1.1.0-20261118'
CATALOG_URL='https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/t20260427_1434931.html'
SASAC_URL='https://wap.sasac.gov.cn/n2588045/n27271785/n27271792/c14159097/content.html'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def import_module(name,path):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sys.modules[name]=m;sp.loader.exec_module(m);return m
base=import_module('major_screen_base',ROOT/'scripts/analyze_existing.py')
extractor=import_module('atomic_tech',UP/'tools/technology_enrich.py')
lexicon=load(UP/'data/technology/technology_dictionary_v4.json');nodes=extractor.make_automaton(lexicon)
terms={t['id']:{'label':t['name'],'category':t['category']} for t in lexicon['terms']}
def professional(q,structured=False):
    """Conservative admission evidence, with explicit label exception and boundary guards."""
    clauses=[x.strip() for x in re.split(r'[\n。；;]',q) if x.strip()]
    a=[];b=[];c=[]
    for x in clauses:
        if re.search(r'(?:不接受|不招|排除)[^，,。；;]{0,16}通信',x):continue
        masks=[]
        for predicate in re.finditer(r'熟悉|精通|掌握|了解|具备|具有|从事|参与|擅长|familiar\s+with|proficient\s+in|experienced\s+in',x,re.I):
            if predicate.group() in ['具备','具有'] and re.search(r'专业(?:相关)?背景|本科|硕士|博士|学士|学历|学位',x[predicate.end():predicate.end()+100]):continue
            end=re.search(r'[，,]',x[predicate.end():]);masks.append((predicate.start(),predicate.end()+end.start() if end else len(x)))
        candidate=''.join(ch if not any(start<=i<end for start,end in masks) else ' ' for i,ch in enumerate(x))
        # Professional field labels may put the accepted majors after 专业.
        label=re.search(r'(?:所学)?专业\s*(?:要求|条件|背景)?\s*[:：]\s*(.*)',candidate)
        admitted=label.group(1) if label else candidate
        tier,_=base.major_screen(candidate)
        explicit=bool(label or structured or tier or ('电子信息类' in candidate and '专业' in candidate))
        if not explicit:continue
        exact_cn=re.search(r'(?<!信息与)(?<!电子与)(?<!信息)通信工程(?!师|经验|技能|知识|能力|技术)',admitted)
        exact_en=re.search(r'telecommunications?\s+engineering',admitted,re.I) and (re.search(r'degree|major|bachelor|master|MSc|Ph\.?D',candidate,re.I) or (structured and not re.search(r'experience|skill|经验|技能',candidate,re.I)))
        if exact_cn or exact_en:a.append(x)
        elif re.search(r'信息与通信工程|电子与通信工程|信息通信(?:工程|类)|通讯(?:工程|类|专业)(?!知识|经验|技能|能力|领域|技术)|通信类|通信大类|通信电子|电子通信信息|通信信息|通信射频|通信网络技术|通[信讯](?:相关)?专业(?!知识|经验|技能|能力|领域|技术)|通[信讯](?:相关|技术)?(?:、|，|,|等|及|与|或|和|/|\.|\s|$)',admitted):
            # Reject "wireless systems ... 6G相关专业领域" without an education/major list.
            if not ('专业领域' in x and not re.search(r'通信(?:相关)?专业|本科|硕士|学历|学位|毕业',x)) or label or structured:b.append(x)
        elif '电子信息类' in admitted:c.append(x)
    if a:return 'A',a
    if b:return 'B',b
    if c:return 'C',c
    return 'D',clauses if structured else []
def years(j,q):
    found=[]
    for x in re.split(r'[\n。；;]',q):
        if re.search(r'(?:[1-9]\d*|[一二三四五六七八九十两]+)\s*(?:[-~至—]\s*\d+)?\s*年',x) and re.search(r'经验|经历|工作|研发|从业|开发',x):found.append(x.strip())
        elif re.search(r'[1-9]\d*\+?\s*(?:years?|yrs?).{0,100}experience',x,re.I):found.append(x.strip())
    raw=str(j.get('experience_raw') or j.get('experience') or '')
    if re.search(r'[1-9一二三四五六七八九十两].{0,8}年|[1-9].{0,5}(?:years?|yrs?)',raw,re.I):found.append('来源经验字段：'+raw)
    return list(dict.fromkeys(found))
def cities(raw):
    if isinstance(raw,str) and re.search(r'等\d+个地点',raw):return list(dict.fromkeys(re.findall(r'([\u4e00-\u9fff]{2,5})市',raw)))+['其他地点未结构化']
    parts=raw if isinstance(raw,list) else [x.strip() for x in re.split(r'[,，、/;；|\n]',str(raw or '').strip()) if x.strip()]
    normalized=[]
    for part in parts:
        value=str(part).strip()
        if re.fullmatch(r'[\u4e00-\u9fff]{2,4}市',value) and not any(x in value for x in ['省市','各市','地级市']):value=value[:-1]
        normalized.append(value)
    return list(dict.fromkeys(normalized)) or ['地点未明确']
def degree_words(raw,q):
    text=str(raw or '')+' '+q
    return [x for x,pat in [('本科',r'本科|Bachelor'),('硕士',r'硕士|研究生|Master|MSc'),('博士',r'博士|Ph\.?D|Doctor')] if re.search(pat,text,re.I)]
def track(title):
    # Generic 研究员 alone does not identify AI; role names take priority over the major.
    if re.search(r'支撑|行政|人力|财务|综合管理',title) and not re.search(r'技术|网络|研发|系统|运维',title):return '综合支撑与管理'
    if re.search(r'通信感知|星载|通信载荷|卫星总体',title):return '通信算法与基带'
    if re.search(r'网络|网优|无线|传输',title) and not re.search(r'安全|开发|算法|解决方案|技术支持|技术服务|售前|售后|交付|销售|产品',title):return '通信网络建设与运营'
    if '研究员' in title and not re.search(r'AI|智能|算法|数据|学习|大模型',title,re.I):return '综合科研（阅读具体方向）'
    inferred=base.career(title)
    if re.search(r'信号处理|信号算法',title) and inferred in ['AI、数据与算法','软件与系统开发','其他/需阅读职责']:return '通信算法与基带'
    if inferred=='云网、算力与运维' and re.search(r'AI|大模型|智能体|机器学习|深度学习|算法',title,re.I):return 'AI、数据与算法'
    if inferred=='云网、算力与运维' and re.search(r'解决方案|售前|售后|交付',title):return '解决方案、技术服务与交付'
    if inferred=='软件与系统开发' and not re.search(r'软件|开发|后端|前端|程序|系统|架构',title):return '综合研发（阅读具体方向）'
    return inferred
def ownership(parent,j):
    if j.get('ownership_group'):return j['ownership_group']
    if any(x in parent for x in ['联通','移动','电信','信科','中国电子','中国电科','航天科工','航天科技','国家电网','中国通号']):return '央企集团及所属单位（集团目录+来源归属）'
    if any(x in parent for x in ['地铁','广电计量','广州数字科技']):return '地方国企（来源归属）'
    if '铁塔' in parent:return '央企控股企业（非本表直接央企集团）'
    if parent=='Apple':return '外企（既有分组）'
    return '其他大型企业（未核验国资实控）'
def normalize(j,source,tier,proofs):
    q=str(j.get('requirements_analysis') or j.get('requirements') or '')
    original=source=='existing'
    rawkind=str(j.get('row_kind') or j.get('record_kind') or '')
    scope=str(j.get('major_evidence_scope') or j.get('major_scope') or ('job_specific' if original else 'unknown'))
    is_batch=any(x in rawkind.lower() for x in ['batch','announcement','批次','公告','shared','招聘池']) or 'batch' in scope
    is_table=any(x in rawkind.lower() for x in ['table','表行','需求表','简版']) or scope=='table_row'
    full_enum=rawkind.lower() in ['full','full_jd','fulljd','individual_jd','independent_jd','jd','具体职位广告','独立jd','独立职责/资格jd']
    kind='batch' if is_batch else 'table' if is_table else 'full' if (original or (full_enum and scope=='job_specific')) else 'table'
    schema_review=not original and (scope not in ['job_specific','table_row','batch_shared'] or not (is_batch or is_table or full_enum))
    if kind=='batch':tier='D';scope='batch_shared'
    if scope not in ['job_specific','table_row','batch_shared']:tier='D'
    sid=str(j.get('source_job_id') or j.get('id') or '')
    parent=str(j.get('parent_group') or j.get('company') or '')
    if '联通' in parent or '联合网络通信' in parent:parent='中国联通'
    if '移动' in parent:parent='中国移动'
    if '中国电信' in parent:parent='中国电信'
    if '中国通信服务' in parent:parent='中国电信'
    if '电子科技集团' in parent or '中国电科' in parent:parent='中国电科'
    elif '中国电子信息产业' in parent:parent='中国电子'
    if '中国信科' in parent or '中国信息通信科技' in parent:parent='中国信科'
    if '航天科工' in parent:parent='中国航天科工'
    if '航天科技集团' in parent:parent='中国航天科技'
    if '国家电网' in parent:parent='国家电网'
    status=str(j.get('student_status') or '')
    channel=' '.join(str(j.get(k) or '') for k in ['source_kind','source_type','batch'])
    campus=bool(re.search(r'校招|校园招聘|campus|实习(?:职位|招聘|岗位)',status+' '+channel,re.I))
    explicit_grad=bool(re.search(r'^(?:202\d届|应届毕业生|应届生)',status)) and not re.search(r'是否|未确认|未知|不明确|未明确|未核验',status)
    contradiction=bool(re.search(r'社招|非校招|非应届|不接受应届',status))
    student=(j.get('student_confirmed') is True or campus or explicit_grad) and not contradiction
    if j.get('student_confirmed') is False:student=False
    if original:student=any(x in status for x in ['实习职位','校招/毕业生入口','资格段明确提及应届'])
    yr=years(j,q);date=str(j.get('source_snapshot') or j.get('retrieved_at') or '2026-11-18')[:10]
    deadline=j.get('application_deadline') or j.get('deadline')
    current=str(j.get('source_current_status') or j.get('current_status') or 'not_verified')
    if current in ['visible_at_capture','publicly_visible','public_page_visible','listed_at_capture']:current='visible'
    if deadline and re.fullmatch(r'202\d-\d\d-\d\d',str(deadline)) and str(deadline)<args.as_of:current='deadline_passed'
    quote='\n'.join(dict.fromkeys(proofs)) or str(j.get('major_raw') or '')
    if not quote and j.get('major_evidence'):
        quote='\n'.join(x.get('quote','') if isinstance(x,dict) else str(x) for x in j['major_evidence'])
    degree=str(j.get('degree_raw') or '')
    catalog_phrase_present='电子信息类' in quote
    undergraduate_catalog_applicable=catalog_phrase_present and '本科' in degree_words(degree,q)
    if tier=='C' and not undergraduate_catalog_applicable:tier='D'
    m={**j,'id':str(j['id']),'company':str(j.get('company') or j.get('hiring_unit') or parent),'parent_group':parent,'ownership_group':ownership(parent,j),'tier':tier,'major_quote':quote,'major_scope':scope,'major_scope_label':{'job_specific':'逐岗专业条件','table_row':'岗位需求表对应行','batch_shared':'批次共享条件，逐岗待核'}.get(scope,scope),'kind':kind,'kind_label':{'full':'独立职责/资格JD','table':'岗位表行/简版要求','batch':'批次共享条件'}[kind],'student_confirmed':student,'student_status':status or '学生入口未确认','experience_signal':bool(yr),'experience_note':'\n'.join(yr),'source_snapshot':date,'current_status':current,'current_status_label':{'deadline_passed':'公告截止日已过','not_verified':'招聘状态未逐岗确认','archive_reference':'历史/存档参考','visible':'采集时公开可见','open':'来源标注开放'}.get(current,'状态：'+current),'career_track':track(j['title']),'city_tags':cities(j.get('city_tags') or j.get('city')),'degree_words':degree_words(degree,q),'degree_raw':degree,'requirements':q,'major_note':('“信息与通信工程”涉及研究生学科名称；不能据此自动认定本科专业准入。' if '信息与通信工程' in quote else '')+(' 专业不限/优先专业语境，名称列举不是硬性专业门槛。' if '专业不限' in q else ''),'rule_version':RULE_VERSION,'skill_eligible':kind=='full' and bool(q.strip()),'source_collection':source}
    tech_matches=extractor.find_matches(q,nodes)
    m['technology_ids']=sorted({x['term_id'] for x in tech_matches})
    m['technology_duty_ids']=sorted({x['term_id'] for x in extractor.find_matches(str(j.get('description') or ''),nodes)})
    m['technology_evidence']=[{'term_id':x['term_id'],'field':'requirements','offset_start':x['start'],'offset_end_exclusive':x['end'],'matched_text':q[x['start']:x['end']]} for x in tech_matches]
    clarity={'duty_180_characters':len(str(j.get('description') or ''))>=180,'qualification_150_characters':len(q)>=150,'three_duty_actions':len(re.findall(r'负责|设计|开发|研发|建设|维护|实施|推动|完成|参与|分析',str(j.get('description') or '')))>=3,'two_named_technologies':len(m['technology_ids'])>=2,'education_explicit':bool(m['degree_words']),'major_evidence_explicit':tier in ['A','B','C'] and bool(quote)}
    m['clarity_signals']=clarity;m['clarity_score']=sum(clarity.values());m['detailed_jd']=kind=='full' and m['clarity_score']>=5
    m['official_id_verified']=original or (source=='campus_bulk' and bool(j.get('source_job_id')) and not re.search(r'synthetic|合成|定位',str(j.get('source_job_id_note') or j.get('source_id_stability') or ''),re.I))
    m['schema_review_required']=schema_review
    m['source_job_id']=sid
    m['hiring_unit_name']=str(j.get('hiring_unit') or m['company'])
    m['hiring_unit_key']=m['company']+' / '+m['hiring_unit_name'] if m['hiring_unit_name']!=m['company'] else m['company']
    m['major_catalog_phrase_present']=catalog_phrase_present;m['undergraduate_catalog_applicable']=undergraduate_catalog_applicable
    if catalog_phrase_present and not undergraduate_catalog_applicable:m['major_note']+=' 原文列电子信息类，但未确认本科目录可适用；未据此自动纳入C层。'
    if schema_review:m['skill_eligible']=False;m['kind_label']='来源完整度待核（不进技能分母）'
    if source=='soe_sources' and (j.get('skill_denominator_eligible') is not True or j.get('qualification_text_verbatim') is not True):m['skill_eligible']=False
    if source=='soe_sources' and j.get('professional_access_denominator_eligible') is not True:
        m['tier']='D';m['major_note']+=' 本来源只存部分页面或索引摘录，专业证据留作线索，不纳入严格A/B/C统计。'
    if m['tier']=='D':m['clarity_signals']['major_evidence_explicit']=False
    m['clarity_score']=sum(m['clarity_signals'].values());m['detailed_jd']=m['skill_eligible'] and m['clarity_score']>=5
    if current=='deadline_future':m['current_status_label']='公告截止日尚未到（受理待核）'
    m['student_entry_evidence']={'status_raw':status,'source_channel_raw':channel,'campus_channel_signal':campus,'explicit_graduate_signal':explicit_grad,'contradictory_social_signal':contradiction,'source_boolean':j.get('student_confirmed')}
    m['cohort_years_raw']=sorted(set(re.findall(r'202\d届',status+' '+channel)))
    m['provenance']={'source_url':j.get('url'),'source_job_id':sid,'source_collection':source,'source_archive':j.get('source_archive'),'source_snapshot':date,'retrieved_at':j.get('retrieved_at'),'text_sha256':hashlib.sha256(str(j.get('full_text') or '').encode()).hexdigest(),'upstream_source_file':j.get('source_file'),'original_parent_group':j.get('parent_group'),'occurrences':j.get('source_occurrences',[])}
    return m
def adapt_soe_record(raw):
    """Separate the source team's recruitment-status field from actual student-entry evidence.
    Only recover skill qualifications from an exact archived source substring, never a synopsis.
    """
    j=dict(raw)
    j['degree_raw']=str(j.get('education_raw') or '')
    j['batch']=str(j.get('recruitment_batch') or '')
    j['retrieved_at']=str(j.get('capture_time') or '')
    j['source_current_status']=str(j.get('student_status') or 'not_verified')
    j['source_status_raw']=j.get('student_status');j['recruiting_status_note']=j.get('student_status_detail')
    j['student_status']=j['batch']+'入口有证据，具体届别/学历见原文' if re.search(r'校园招聘|校招',j['batch']) else '学生入口未确认'
    j['description']=str(j.get('responsibilities_raw') or '')
    place=str(j.get('city') or '')
    provinces=['北京','天津','上海','重庆','河北','河南','湖北','湖南','广东','广西','山东','山西','江苏','浙江','江西','福建','安徽','辽宁','吉林','黑龙江','四川','贵州','云南','陕西','甘肃','青海','海南','内蒙古','宁夏','新疆','西藏']
    city_names=['北京','天津','上海','重庆','广州','深圳','杭州','成都','贵阳','南宁','沈阳','无锡','武汉','西安','长春','长沙','福州','厦门','宁德','南平','泉州','漳州','龙岩','三明','莆田','青岛','新乡']
    if re.search(r'未按.*(?:岗位|表行)|未(?:逐岗|在岗位行).*城市|(?:城市|地点)未|公告介绍.*基地',place):
        province=next((p for p in provinces if place.startswith(p+'省')),None);j['city_tags']=[province+'省（城市未明确）'] if province else ['地点未明确']
    else:
        clean=re.sub(r'[（(].*?[）)]','',place);tags=[]
        for part in re.split(r'[，,、/;；|\n]',clean):
            names=[name for name in city_names if name in part]
            if names:tags.extend(names)
            elif part.strip() in provinces:tags.append(part.strip()+'（省级地区，城市未明确）')
        j['city_tags']=list(dict.fromkeys(tags)) or ['地点未明确']
    full=str(j.get('full_text') or '')
    heading=re.search(r'(?:任职要求|岗位要求|任职资格|资格条件|应聘要求|岗位条件|招聘要求)\s*(?:[:：]|(?=\n|$))',full)
    if not heading:heading=re.search(r'(?:学历要求|专业要求)\s*(?:[:：]|(?=\n|$))',full)
    q='';qoffset=None
    if heading:
        end=re.search(r'(?:岗位职责|工作职责|工作内容|职责描述)\s*(?:[:：]|(?=\n|$))',full[heading.end():])
        q=full[heading.end():heading.end()+end.start() if end else len(full)].strip();qoffset=full.find(q)
    else:
        candidate=str(j.get('qualification_raw') or '').strip()
        if candidate and candidate in full:q=candidate;qoffset=full.find(q)
    j['requirements']=q or str(j.get('qualification_raw') or '')
    j['qualification_text_verbatim']=bool(q)
    j['qualification_parse_provenance']={'method':'exact substring of archived per-job text' if q else 'source synopsis/table reference; excluded from independent skill denominator','full_text_offset_start':qoffset,'full_text_offset_end_exclusive':qoffset+len(q) if qoffset is not None else None}
    duty_heading=re.search(r'(?:岗位职责|工作职责|工作内容|职责描述)\s*(?:[:：]|(?=\n|$))',full)
    if duty_heading:
        j['description']=full[duty_heading.end():heading.start() if heading and heading.start()>duty_heading.end() else len(full)].strip();j['description_text_verbatim']=True
    else:j['description_text_verbatim']=False
    source_ownership=str(j.get('ownership_type') or '')
    if re.search(r'地方|市属|省属',source_ownership):j['ownership_group']='地方国企（来源归属）'
    elif re.search(r'央企|中央企业',source_ownership):j['ownership_group']='央企集团及所属单位（集团目录+来源归属）'
    if '岗位单列要求' in str(j.get('row_kind')):j['row_kind']='table';j['source_row_kind_raw']=raw.get('row_kind')
    if '市属国有' in str(j.get('parent_group')) and '集团' not in str(j.get('parent_group')):j['parent_group']=j['company']
    return j
def get_records():
    rows=[];excluded=[]
    with gzip.open(UP/'data/corpus.ndjson.gz','rt',encoding='utf-8') as f:
        for line in f:
            j=json.loads(line)
            if not j.get('requirements_available'):continue
            if j['id']=='小米-7660104107810326822':excluded.append({'id':j['id'],'reason':'专业领域描述不构成毕业专业准入；100条抽样复核发现'});continue
            q=j.get('requirements_analysis') or j.get('requirements') or ''
            tier,proofs=professional(q)
            if tier=='D':continue
            st,_=base.student_status(j,q);j['student_status']=st;j['source_snapshot']='2026-11-17'
            rows.append(normalize(j,'existing',tier,proofs))
    cats={x['id']:x['city_tags'] for x in load(UP/'data/catalog.json')['jobs']}
    for j in rows:j['city_tags']=cats[j['id']]
    for source in ['campus_bulk','soe_sources']:
        p=ROOT/source/'records.jsonl'
        if not p.exists():continue
        for line_number,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            if not line.strip():continue
            j=json.loads(line)
            if source=='soe_sources':j=adapt_soe_record(j)
            for key,alias in [('id','record_id'),('title','job_title'),('url','source_url')]:
                if not j.get(key) and j.get(alias):j[key]=j[alias]
            missing=[key for key in ['id','title','company','url','full_text'] if not j.get(key)]
            if missing:raise ValueError(f'{source}/records.jsonl line {line_number}: missing required archived record fields {missing}')
            major=str(j.get('major_raw') or '')
            if not major:
                ev=j.get('major_evidence')
                if isinstance(ev,str):major=ev
                elif isinstance(ev,dict):major=str(ev.get('quote') or ev.get('text') or '')
                elif isinstance(ev,list):major='\n'.join(str(v.get('quote') or v.get('text') or '') if isinstance(v,dict) else str(v) for v in ev)
            tier,proofs=professional(major,structured=True)
            if not major:
                tier,proofs=professional(str(j.get('requirements') or ''))
            elif tier=='D' and str(j.get('row_kind','')).lower() in ['full_jd','fulljd']:
                qt,qp=professional(str(j.get('requirements') or ''))
                if qt!='D':tier,proofs=qt,qp;j['major_evidence_source_field']='requirements'
            rows.append(normalize(j,source,tier,proofs))
    page_manifest=ROOT/'archives/soe_browser_pages/manifest.json'
    if page_manifest.exists():
        sources={x['url']:x for x in load(page_manifest)['sources']}
        for j in rows:
            if j['source_collection']=='soe_sources' and j['url'] in sources:
                archived=sources[j['url']]
                j['provenance']['rendered_public_page_archive']=archived
    # Stable employer ID deduplication; mirror occurrences remain attached.
    bykey={};dups=[]
    for j in rows:
        sid=j.get('source_job_id');key=(j['parent_group'],str(sid)) if sid and j['official_id_verified'] else ('source-record',j['id'])
        if key in bykey:
            old=bykey[key];dups.append({'kept':old['id'],'duplicate':j['id'],'key':key});old['provenance']['occurrences'].append(j['provenance']);continue
        bykey[key]=j
    return sorted(bykey.values(),key=lambda j:(not j['student_confirmed'],j['tier'],j['parent_group'],j['title'],j['id'])),excluded,dups
def counter(rows,key):
    c=collections.Counter()
    for j in rows:
        vals=j[key] if isinstance(j[key],list) else [j[key]]
        c.update(set(vals))
    return sorted(c.items(),key=lambda item:(-item[1],str(item[0])))
def aggregate(rows):
    direct=[j for j in rows if j['tier'] in ['A','B']];students=[j for j in direct if j['student_confirmed']];skill=[j for j in students if j['skill_eligible']]
    def subset(xs):return {'records':len(xs),'groups':len(set(j['parent_group'] for j in xs)),'units':len(set(j['hiring_unit_key'] for j in xs)),'tracks':counter(xs,'career_track'),'companies':counter(xs,'parent_group'),'ownership':counter(xs,'ownership_group'),'cities':counter(xs,'city_tags'),'degrees':counter(xs,'degree_words'),'kinds':counter(xs,'kind'),'status':counter(xs,'current_status'),'technology_denominator':sum(j['skill_eligible'] for j in xs),'technologies':counter([j for j in xs if j['skill_eligible']],'technology_ids')}
    a={'schema':'communications-analysis/1','compiled_at':args.as_of,'rule_version':RULE_VERSION,'all':subset(rows),'direct':subset(direct),'students':subset(students),'tiers':counter(rows,'tier'),'source_collections':counter(rows,'source_collection'),'sources':[{'name':'教育部2026本科专业目录','url':CATALOG_URL,'note':'080703通信工程属于0807电子信息类；080701电子信息工程为另一具体专业。'},{'name':'国务院国资委央企名录','url':SASAC_URL,'note':'母集团归属核验；所属招聘单位关系结合公告，不将所有国企均标直接央企。'},{'name':'中国联通2027校园招聘','url':'https://zglt.zhaopin.com/scjobs/index.html','note':'授权招聘站全量池原始响应已留档，按逐岗专业条件筛选。'},{'name':'中国移动招聘官网','url':'https://job.10086.cn/','note':'普通浏览器观察部分单位列表为空；不据此推断全集团没有岗位。'},{'name':'中国电信招聘官网','url':'https://job.chinatelecom.com.cn/','note':'本机直接请求受站点访问限制；补充公开雇主公告，不突破访问控制。'}]}
    a['sources'].append({'name':'中国通信服务：控股股东披露','url':'https://www.chinaccs.com.hk/sc/ir/faqs.php','note':'官网披露中国电信为控股股东；中通服所属记录按中国电信集团归并，原披露层级保存在溯源字段。'})
    bm=load(ROOT/'campus_bulk/source_manifest.json') if (ROOT/'campus_bulk/source_manifest.json').exists() else {}
    sm=load(ROOT/'soe_sources/source_manifest.json') if (ROOT/'soe_sources/source_manifest.json').exists() else {}
    screening=[]
    if (ROOT/'campus_bulk/screening_results.jsonl').exists():screening=[json.loads(x) for x in (ROOT/'campus_bulk/screening_results.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    browser_sources=load(ROOT/'archives/soe_browser_pages/manifest.json')['sources'] if (ROOT/'archives/soe_browser_pages/manifest.json').exists() else []
    a['collection_coverage']={'bulk_raw_rows':sum(bm.get('collection_denominators',{}).values()) if bm.get('collection_denominators') else None,'bulk_full_detail_rows':sum(x.get('row_kind')=='full_jd' for x in screening) if screening else None,'bulk_unique_id_groups':bm.get('dedup_summary',{}).get('unique_id_groups'),'bulk_retained_records':sum(j['source_collection']=='campus_bulk' for j in rows),'bulk_source_direct_labels':sum(j['source_collection']=='campus_bulk' and j.get('major_screen_class')=='direct' for j in rows),'soe_records':sum(j['source_collection']=='soe_sources' for j in rows),'soe_units':len({j['company'] for j in rows if j['source_collection']=='soe_sources'}),'soe_complete_page_text_records':sm.get('complete_record_source_archive_count'),'soe_partial_excerpt_records':sm.get('partial_or_excerpt_record_count'),'soe_skill_eligible_records':sum(j['source_collection']=='soe_sources' and j['skill_eligible'] for j in rows),'browser_source_urls':len(browser_sources),'browser_full_bodies':sum(bool(x.get('body_available')) for x in browser_sources)}
    templates={}
    for j in skill:templates.setdefault(re.sub(r'\s+','',j['requirements']),[]).append(j)
    company_q={g:[j for j in skill if j['parent_group']==g] for g in sorted({j['parent_group'] for j in skill})}
    qtech=collections.Counter(t for j in skill for t in j['technology_ids'])
    template_tech=collections.Counter(t for js in templates.values() for t in {term for j in js for term in j['technology_ids']})
    a['template_diagnostics']={'qualification_jobs':len(skill),'unique_qualification_templates':len(templates),'largest_template_job_count':max((len(x) for x in templates.values()),default=0),'jobs_with_any_named_technology':sum(bool(j['technology_ids']) for j in skill),'groups_with_qualification_jobs':len(company_q),'scope':'A/B student full qualification JD only; whitespace-normalized exact qualification templates, not semantic paraphrase deduplication','technology_sensitivity':[{'term_id':t,'job_mentions':qtech[t],'job_denominator':len(skill),'job_share':qtech[t]/len(skill) if skill else None,'template_mentions':template_tech[t],'template_denominator':len(templates),'template_share':template_tech[t]/len(templates) if templates else None,'equal_group_average_share':sum(sum(t in j['technology_ids'] for j in xs)/len(xs) for xs in company_q.values())/len(company_q) if company_q else None} for t in terms]}
    seen={s['url'] for s in a['sources']}
    for j in rows:
        if j['source_collection']=='soe_sources' and j['url'] not in seen:
            a['sources'].append({'name':j['company'],'url':j['url'],'note':str(j.get('source_archive_scope') or j.get('source_kind') or '')});seen.add(j['url'])
    a['insights']=[{'title':'◎ 专业符合与学生入口分开看','finding':f"专业名称/专业组直接匹配 {len(direct):,} 条，其中学生入口有证据 {len(students):,} 条。",'implication':'学生优先使用默认候选池；社招与未知经验记录适合认识职业要求，不能直接当作应届可投机会。'},{'title':'▦ 母集团与招聘单位分别统计','finding':f"本专题覆盖 {a['all']['groups']} 个母集团/公司、{a['all']['units']} 个招聘单位名称。",'implication':'运营商分省、分市发布大量岗位；按单位计数与按集团计数回答的是不同问题，均不代表实际招聘名额。'},{'title':'⌘ 通信专业并非只去网络岗位','finding':'职业覆盖软件、通信网络、射频、芯片、嵌入式、云网、安全、解决方案与综合支撑。','implication':'先结合自己的课程与项目选职业，再阅读该方向具体资格段。某岗位接受通信背景，不意味着其工作就是通信研发。'},{'title':'⌖ 城市选择会改变岗位结构','finding':'城市图表以JD地点标签统计，多城市岗位可同时覆盖多个城市。','implication':'用城市+职业+学生入口联合筛选；不能把总部所在地当作全部工作的实际地点。'},{'title':'◷ 这是基线，暂不输出涨跌','finding':'本次组合11月17日既有大厂语料与11月18日专题补采，不是两个可比市场截面。','implication':'后续冻结同渠道、同专业规则、同技术词表的快照，优先比较共同雇主/职位的提及比例变化。'},{'title':'◇ 学历与专业大类需要逐层核验','finding':'通信工程080703属于电子信息类0807；信息与通信工程涉及研究生学科。','implication':'C层仅作为目录大类匹配；单列电子信息工程并不自动包含通信工程，硕博岗位也不能默认本科可投。'},{'title':'▤ 技术统计限定独立资格段','finding':f"默认学生池有 {len(skill):,} 条完整JD可作为技术统计分母。",'implication':'岗位需求表与批次公告不进入该分母。技术未提及不代表工作不使用，技术出现也不代表硬性熟练要求。'},{'title':'✓ 具体原文比岗位名称更可靠','finding':'抽样复核100条既有候选，覆盖11个雇主，发现并修正专业领域误收与“专业：通信”漏召回。','implication':'边界定向审阅不用于估计总体准确率；保留审阅记录、原文证据、规则版本和来源文本，便于继续校正。'}]
    a['insights'][6]['finding']=f"默认学生池 {len(skill):,} 条完整资格JD中，{a['template_diagnostics']['jobs_with_any_named_technology']:,} 条命中至少一项技术；共有 {len(templates):,} 份去空白后的资格模板。"
    a['insights'][6]['implication']='通用校招模板会压低具名技术提及率，不能据此判断技术门槛低。报告同时比较按岗位、按资格模板和按集团平均三种权重。'
    return a
def main():
    rows,excluded,dups=get_records();OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'frontend_src',OUT,dirs_exist_ok=True)
    (OUT/'data/details').mkdir(parents=True,exist_ok=True)
    oldshards=list((OUT/'data/details').glob('*.json'))
    # Only this generated, project-local shard directory; no arbitrary recursive deletion.
    for p in oldshards:p.unlink()
    metas=[]
    keys=['id','title','company','hiring_unit_name','hiring_unit_key','parent_group','ownership_group','tier','major_quote','major_scope','major_scope_label','kind','kind_label','student_confirmed','student_status','experience_signal','experience_note','degree_raw','degree_words','city_tags','career_track','skill_eligible','technology_ids','source_snapshot','current_status','current_status_label','detailed_jd','clarity_score','url','detail_shard']
    for n in range(0,len(rows),100):
        rel=f'data/details/{n//100:03d}.json';shard={}
        for j in rows[n:n+100]:j['detail_shard']=rel;shard[j['id']]=j;metas.append({k:j.get(k) for k in keys})
        write(OUT/rel,shard)
    catalog={'schema':'communications-catalog/1','rule_version':RULE_VERSION,'technology_dictionary_version':lexicon['dictionary_version'],'terms':terms,'jobs':metas}
    write(OUT/'data/catalog.json',catalog)
    with gzip.open(OUT/'data/catalog.json.gz','wt',encoding='utf-8') as f:json.dump(catalog,f,ensure_ascii=False,separators=(',',':'))
    with gzip.open(OUT/'data/corpus.ndjson.gz','wt',encoding='utf-8') as f:
        for j in rows:f.write(json.dumps(j,ensure_ascii=False,separators=(',',':'))+'\n')
    a=aggregate(rows);write(OUT/'data/analysis.json',a);write(OUT/'data/dedup-and-exclusions.json',{'duplicates':dups,'explicit_exclusions':excluded,'screen_rule_version':RULE_VERSION})
    write(OUT/'data/rules/processing-version.json',{'version':RULE_VERSION,'professional_rule_sha256':sha(Path(__file__).resolve()),'technology_dictionary_version':lexicon['dictionary_version'],'dictionary_sha256':sha(UP/'data/technology/technology_dictionary_v4.json'),'extractor_sha256':sha(UP/'tools/technology_enrich.py'),'offset_units':'Unicode code points, end exclusive'})
    shutil.copy2(Path(__file__).resolve(),OUT/'data/rules/build_topic.py')
    shutil.copy2(UP/'tools/technology_enrich.py',OUT/'data/rules/technology_enrich.py')
    shutil.copy2(UP/'data/technology/technology_dictionary_v4.json',OUT/'data/rules/technology_dictionary_v4.json')
    write(OUT/'data/snapshot-registry.json',{'schema':'communications-snapshots/1','periods':[{'period':args.as_of,'corpus':'corpus.ndjson.gz','records':len(rows),'source_dates':counter(rows,'source_snapshot'),'rule_version':RULE_VERSION}],'note':'Only actually captured periods are registered. Add future immutable periods explicitly; do not synthesize history.'})
    write(ROOT/'evidence/merged_stats.json',a)
    print(json.dumps({'all':a['all']['records'],'direct':a['direct']['records'],'students':a['students']['records'],'tiers':a['tiers'],'groups':a['all']['groups'],'duplicates':len(dups)},ensure_ascii=False))
if __name__=='__main__':main()
