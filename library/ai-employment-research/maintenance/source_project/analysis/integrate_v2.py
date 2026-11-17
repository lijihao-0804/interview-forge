"""Merge public job collections, archive coverage, taxonomy and JD clarity."""
import collections
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from job_common_v2 import ROOT,plain,hits,digest,summary,archive,split_body,SKILLS,requirement_analysis_text
from jd_clarity import score_clarity
from analyze_jobs import family as legacy_family,experience

E=ROOT/'evidence';A=ROOT/'analysis'
PAYLOAD_CACHE={}
def jsonl_payloads(path,key):
    if path not in PAYLOAD_CACHE:
        lookup=collections.defaultdict(list)
        with path.open(encoding='utf-8-sig') as f:
            for line in f:
                if not line.strip():continue
                value=json.loads(line);job=value.get('job',{})
                ids={str(job[k]) for k in ['id','Id','code','postId','jobId','JobAdId','positionId','jobPostId','RecordGuid'] if job.get(k) is not None}
                for ident in ids:lookup[ident].append(value)
        PAYLOAD_CACHE[path]=lookup
    return PAYLOAD_CACHE[path].get(str(key),[])
ALIASES={'ByteDance':'字节跳动','bytedance':'字节跳动','腾讯云':'腾讯','Alibaba':'阿里巴巴','JD':'京东','NetEase':'网易','Baidu':'百度','Huawei':'华为','Xiaomi':'小米','HONOR':'荣耀','iFLYTEK':'科大讯飞','PDD':'拼多多','英伟达':'NVIDIA','英特尔':'Intel','亚马逊':'Amazon','微软':'Microsoft','高通':'Qualcomm','谷歌':'Google','苹果':'Apple'}
SLUGS={'腾讯':'tencent','阿里巴巴':'alibaba','京东':'jd','字节跳动':'bytedance','拼多多':'pdd','网易':'netease','百度':'baidu','科大讯飞':'iflytek','华为':'huawei','小米':'xiaomi','荣耀':'honor'}
AI=re.compile(r'(?<![a-z])(?:ai|llm|aigc)(?![a-z])|agentic|人工智能|大模型|智能体|机器学习|深度学习|神经网络|计算机视觉|多模态|强化学习|machine.learning|deep.learning|generative|foundation.model|artificial.intelligence',re.I)
AGENT=re.compile(r'agent|智能体|(?:大模型|AI)[\s-]*应用|RAG|retrieval.augmented|codebuddy|workbuddy',re.I)
INFRA=re.compile(r'(?<![a-z])infra(?![a-z])|AI.?infra|Agent.?Runtime|算子|编译器|异构计算|训练(?:框架|系统|平台)|推理(?:引擎|框架|系统|平台|服务|优化|加速)|智算|算力|CUDA|Triton|TensorRT|vLLM|SGLang|inference|compiler|training.(?:framework|system|platform)|GPU|high.performance.comput',re.I)
POST=re.compile(r'后训练|post[- ]?train|RLHF|GRPO|DPO|SFT|偏好对齐|模型对齐|reward.model|reinforcement.learning|强化学习',re.I)
TECH_FAMILIES={'开发工程','算法与研究','基础设施与系统','运维与SRE','测试与质量','数据工程与分析','硬件嵌入式与通信','安全与风险','技术职能待细分'}

def txt(x):
    if x is None:return ''
    if isinstance(x,list):return '；'.join(txt(i) for i in x if txt(i))
    if isinstance(x,dict):
        for k in ['name','descriptor','label','title','text','city','location_name','city_names_raw','city_raw','job_address_raw','work_area_raw','work_place_raw','work_place_list_raw']:
            if x.get(k):return txt(x[k])
        return json.dumps(x,ensure_ascii=False)
    return str(x)
def load(path):
    j=json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(j,dict):
        for k in ['jobs','records','positions','data']:
            if isinstance(j.get(k),list):return j[k]
        return []
    return j
def first(x,keys,default=''):
    for k in keys:
        if x.get(k) not in (None,'',[]):return x[k]
    return default
def source_id(x,co):
    ident=txt(first(x,['source_job_id','position_id','job_id','jobId','post_id','requisition_id','requirement_id','id']))
    # JD requirement ID is the official vacancy key; a position ID may be shared.
    if co=='京东':ident=txt(first(x,['source_job_id','requirement_id','id','position_id']))
    for pref in [co+'-',co+':','腾讯云-']:
        if ident.startswith(pref):ident=ident[len(pref):]
    return ident
def english_family(title,category):
    if '设计管培生' in title:return '设计与用户体验'
    if re.search(r'安全.*(?:研究|技术|工程|专家|架构)',title):return '安全与风险'
    if re.search(r'研究专家|研究科学家',title):return '算法与研究'
    if re.search(r'partnership|ecosystem.partn',title,re.I):return '销售商务与解决方案'
    if re.search(r'AI.*(?:framework|tool.chain)',title,re.I):return '基础设施与系统'
    if re.search(r'建模|动画|特效|视觉设计',title) and re.search(r'算法|研究员|科学家|研究工程',title):return '算法与研究'
    if re.search(r'动画|特效|建模',title) and re.search(r'开发|研发',title) and not re.search(r'设计师|美术师',title):return '开发工程'
    if re.search(r'GPU.*(?:perf|performance.analysis)|AI.*(?:inference|training).*(?:intern|engineer)',title,re.I):return '基础设施与系统'
    rules=[('产品',r'product.manager|product.management'),('销售商务与解决方案',r'sales|account.(?:manager|executive)|business.development|solution.(?:advisor|consultant)|solutions?.architect|technical.marketing|field.applications?'),('零售门店与现场业务',r'store.leader|retail|specialist.*store|CN-Store|CN-Specialist'),('运营内容与市场',r'marketing|content|operations.manager'),('人力财务法务行政',r'recruit|human.resources|finance|accountant|legal.counsel|administrative'),('设计与用户体验',r'UX|UI.designer|user.experience|graphic.design'),('测试与质量',r'quality|QA.engineer|test.engineer|validation.engineer'),('运维与SRE',r'\bSRE\b|site.reliability|DevOps|cloud.operations'),('数据工程与分析',r'data.engineer|data.analyst|data.scientist|analytics'),('硬件嵌入式与通信',r'ASIC|RTL|silicon|physical.design|hardware|embedded|SoC|FPGA|GPU.architecture|manufacturing|industrial.engineer|facilities|mechanical|electrical.engineer|process.engineer'),('安全与风险',r'security.engineer|cyber|vulnerability|security.research'),('算法与研究',r'scientist|researcher|research.engineer|machine.learning|deep.learning|algorithm'),('基础设施与系统',r'infrastructure|compiler|kernel|inference|distributed.system|HPC'),('开发工程',r'software|developer|programmer|engineer|engineering|architect')]
    if re.search('[A-Za-z]{3}',title):
        for label,p in rules:
            if re.search(p,title,re.I):return label
        if re.search(r'(?<![a-z])(?:eng\.|swe|sde)(?![a-z])',title,re.I):return '开发工程'
    result=legacy_family({'title':title,'category':category})
    if result=='其他或待核实':
        if re.match(r'产品',category):return '产品'
        if re.match(r'研发',category):return '技术职能待细分'
    return result

def direction(r):
    t=r['title'];body=r['description']+'\n'+r['requirements'];f=r['job_family'];sid=r['source_job_id']
    if r['company']=='腾讯' and sid in {'2122347965157912576','2122503698335842304','2099353703831224320','2122504689126912000','2122348015627972608'}:return 'AI Infra'
    if r['company']=='阿里巴巴' and sid=='100026300005':return 'AI安全工程'
    if r['company']=='华为' and sid=='127603':return 'AI Infra'
    if r['company']=='Microsoft' and sid=='1970393556986960':return 'AI Infra'
    if f not in TECH_FAMILIES:return 'AI关联非技术职能' if AI.search(t) or AGENT.search(t) else '非技术或待细分'
    if re.search(r'评测|测试|质量|evaluation|quality|testing',t,re.I) and (AI.search(t) or AGENT.search(t)):return 'AI评测或质量工程'
    if re.search(r'安全|security',t,re.I) and (AI.search(t) or AGENT.search(t)):return 'AI安全工程'
    if re.search(r'数据(?:开发|工程|研发)|data.engineer',t,re.I) and (AI.search(t) or AGENT.search(t)):return 'AI数据工程'
    if re.search(r'渲染|图形|graphics|rendering',t,re.I) and not re.search(r'生成|神经|neural|generative|大模型',t,re.I):return '图形与渲染系统'
    if f=='硬件嵌入式与通信':return 'AI芯片或硬件' if AI.search(t) or re.search(r'GPU|NPU|AI.accelerator',t,re.I) else '硬件或嵌入式'
    if INFRA.search(t) or re.search(r'AI.*(?:framework|tool.chain)',t,re.I):
        return 'AI Infra' if AI.search(t) or AGENT.search(t) or re.search(r'GPU|CUDA|Triton|TensorRT|推理|inference|训练|大模型|算子|智算|算力',t,re.I) else '通用Infra或需核实'
    if re.search(r'SRE|运维',t,re.I) and (AI.search(t) or AGENT.search(t)):return 'AI Infra'
    if POST.search(t):
        return '后训练' if re.search(r'后训练|post[- ]?train|SFT|DPO|GRPO|RLHF|对齐|reward.model',t,re.I) or re.search(r'大模型|LLM|混元|通义|CodeBuddy|WorkBuddy',t,re.I) else '强化学习阶段待核'
    if AGENT.search(t):
        return 'Agent算法或交叉研究' if re.search(r'算法|研究|科学家|scientist|research|algorithm',t,re.I) else 'AI应用/Agent开发'
    if AI.search(t):return '其他AI算法或研究' if f=='算法与研究' else '其他AI技术'
    return '其他技术或标题未分方向'

def normalize(x,path,legacy=False):
    co=ALIASES.get(txt(first(x,['company','employer','company_name'])),txt(first(x,['company','employer','company_name'])))
    if not co:co=path.stem.split('_')[0]
    sid=source_id(x,co);title=plain(first(x,['title','job_title','name','positionName']))
    if not sid or not title:return None
    duty=plain(first(x,['description','responsibility','duties','job_description','work_content','workContent']))
    req=plain(first(x,['full_requirements_raw','requirements','requirement','qualification','qualifications','job_requirements','jobRequire','serviceCondition']))
    bonus=plain(first(x,['bonus','bonus_raw_full']))
    if bonus and re.sub(r'\s+','',bonus) not in re.sub(r'\s+','',req):req+='\n\n补充条件（源独立字段，层级以原文为准）：\n'+bonus
    full=plain(first(x,['full_text','jd_text','body_text','text']))
    if full and bonus and re.sub(r'\s+','',bonus) not in re.sub(r'\s+','',full):full+='\n\n补充条件（源独立字段，层级以原文为准）：\n'+bonus
    status=txt(first(x,['requirements_parse_status','parse_status']))
    if not duty and full:duty,req,status=split_body(full)
    if not full:full=duty+'\n\n'+req if duty or req else ''
    if not req and (full or duty):
        dd,rr,ss=split_body(full or duty)
        if rr:duty,req,status=dd,rr,ss
    if duty and req and not status:status='separate_source_fields'
    if re.match(r'^\s*Benefits offered are described',req,re.I):
        duty=full or duty+'\n\n'+req;req='';status='boilerplate_only_not_qualifications'
        dd,rr,ss=split_body(duty)
        if rr:duty,req,status=dd,rr,'reparsed_explicit_heading_from_full_body'
    loc=txt(first(x,['city','location','locations','work_locations','work_city']))
    category=txt(first(x,['category','category_raw','job_category','job_family','department'])) or '未知'
    if co=='字节跳动':category=txt(x.get('job_category_path')) or category
    r=dict(company=co,source_job_id=sid,id=co+'-'+sid,title=title,url=txt(first(x,['url','source_url','official_url','job_url'])),city=loc,country=txt(first(x,['country','country_name','country_code'])) or '未明示',category_original=category,experience=experience(first(x,['experience','experience_raw','experience_requirement'],'未知')),degree_raw=txt(first(x,['degree','education','education_requirement'],'未知')),posted_date=txt(first(x,['posted_date','published_at','publish_date','posting_date'],'未知')),retrieved_at=txt(first(x,['retrieved_at','access_time','collected_at','access_date'],'2026-11-17')),description=duty,requirements=req,full_text=full,requirements_parse_status=status or 'not_archived',source_file=str(path.relative_to(ROOT)).replace('\\','/'),source_type=txt(first(x,['source_type','source'],'官方公开招聘信息')),salary=txt(first(x,['salary','salary_raw'],'未披露')),archive_json=txt(first(x,['archive_json','archive_path','archive_json_path'])),legacy_only=legacy and not bool(full))
    r['job_family']=english_family(title,category)
    r['bonus_source']=bonus
    r['job_code_raw']=txt(first(x,['job_code_raw','source_post_code']))
    r['source_internal_id']=txt(x.get('source_internal_id'))
    r['archive_key']=txt(x.get('archive_key'))
    r['source_occurrences']=x.get('source_occurrences',[])
    r['source_url_resolution']=x.get('url_resolution',x.get('url_resolution_note',''))
    r['url_kind']='官网列表入口，按职位ID/标题定位' if co=='网易' or (co=='拼多多' and not full) else '官网具体职位入口'
    r['archive_json']=r['archive_json'].replace('\\','/')
    if r['archive_json'].endswith('.jsonl'):
        source_archive=ROOT/r['archive_json'];r['source_archive_jsonl']=r['archive_json']
        raw=[];seen_payloads=set()
        for key in [r['archive_key'],sid,r['source_internal_id'],r['job_code_raw']]:
            if not key:continue
            for value in jsonl_payloads(source_archive,key):
                if id(value) not in seen_payloads:raw.append(value);seen_payloads.add(id(value))
        r['archive_json']=archive(SLUGS.get(co,co.lower()),sid,r,raw or {'source_archive_jsonl':r['source_archive_jsonl'],'archive_key':r['archive_key']})
    if co=='小米' and sid=='7677821082208487723':r['job_family']='硬件嵌入式与通信'
    r['city_source']=loc
    if co=='华为' and sid=='113857' and '北京' in duty:r['city']='东莞；北京（正文补充，结构字段仅东莞）'
    if co=='Arm' and sid=='2026-17606':r['city']=loc.replace('Shenzen','Shenzhen')
    loc=r['city']
    r['source_job_id_note']='官网JSON-LD identifier.value（requisition编号）；URL另含路由ID' if co=='Arm' else '原采集记录的官方职位主键，保留原值'
    route=re.search(r'/(\d+)/?(?:[?#]|$)',r['url'])
    r['url_route_key']=route.group(1) if co=='Arm' and route else ''
    r['posted_date']=txt(first(x,['posted_date','published_at','publish_date','posting_date','posted_date_display','posted_date_raw','publish_time'],'未知'))
    r['degree_raw']=txt(first(x,['degree','degree_raw','education','education_requirement'],'未知'))
    r['title_direction']=direction(r)
    req_analysis=requirement_analysis_text(req)
    r['requirements_analysis']=req_analysis
    r['requirements_analysis_note']='已排除可识别的通用政策尾文；原资格字段完整保留' if req_analysis!=req else '与独立资格字段一致'
    r['record_kind']='分领域毕业生招聘池' if co=='NVIDIA' and sid in {'JR2024108','JR2024110'} else '具体职位广告'
    r['skills_in_requirement']=hits(req_analysis) if req_analysis else []
    r['skills_in_responsibility']=hits(duty) if duty else []
    r['historical_skill_features']=x.get('skills_in_requirement',[]) if not req else []
    r['requirements_available']=bool(req_analysis and len(req_analysis)>30)
    r['detail_status']='full' if duty and req else 'full_combined' if full else 'metadata_only'
    r['text_sha256']=digest(full) if full else x.get('text_sha256','')
    r['body_chars']=len(full);r['requirement_chars']=len(req_analysis);r['requirement_raw_chars']=len(req)
    r['ai_signal']='标题AI相关' if AI.search(title) or AGENT.search(title) else '正文AI词信号' if AI.search(req or duty) or any(k in r['skills_in_requirement'] for k in ['PyTorch','TensorFlow','RAG','Agent','Prompt','SFT/微调','RL/对齐']) else '未检出AI标识'
    r['education_mentions']=[d for d,p in [('本科',r'本科|bachelor|baccalaureate'),('硕士',r'硕士|master.?s|M\.?S\.? degree'),('博士',r'博士|Ph\.?D|doctor(?:al|ate)')] if re.search(p,req_analysis,re.I)]
    mainland_city=bool(re.search(r'北京|上海|杭州|深圳|广州|成都|武汉|苏州|南京|西安|合肥|天津|东莞|无锡|长沙|重庆|济南|大连|Beijing|Shanghai|Hangzhou|Shenzhen|Guangzhou|Chengdu|Wuhan|Suzhou|Nanjing|Xian|Hefei|Tianjin|Wuxi|Dalian',loc,re.I))
    mainland_city=mainland_city or bool(re.search(r'重庆|济南|长沙|福州|厦门|青岛|郑州|宁波|佛山|珠海|全国|江苏|浙江|广东|山东|四川|河北|河南|安徽|福建|江西|湖北|湖南|辽宁|吉林|黑龙江|广西|贵州|云南|山西|陕西|内蒙|海南|甘肃|宁夏|新疆|青海|西藏',loc))
    hkt=bool(re.search(r'Hong Kong|Taiwan|Taipei|Macao|Macau|香港|澳门|台湾|臺灣|台北',loc+' '+r['country'],re.I))
    china=bool(re.search(r'China|PRC|\bCN\b|CHN|中国',loc+' '+r['country'],re.I))
    r['geography']='含大陆及港澳台多地点' if hkt and mainland_city else '港澳台地点' if hkt else '含中国大陆地点' if china or mainland_city else '地域待核或其他地区'
    r['summary']=summary(title,duty,req_analysis,loc,r['experience'],r['job_family']) if full else '该记录仅保留公开职位元数据；本轮未取得可归档完整正文，不能据此还原JD。'
    r.update(score_clarity(duty,req_analysis,title,status))
    if full and not r['archive_json']:
        slug=SLUGS.get(co,re.sub('[^a-z0-9_-]','',co.lower()) or 'employer_'+digest(co)[:8])
        r['archive_json']=archive(slug,sid,r,None)
    p=ROOT/r['archive_json'] if r['archive_json'] else None
    if full and p and p.is_file():r['archive_status']='正文已存档' if req else '合并正文已存档，资格未可靠拆分'
    elif full:
        slug=SLUGS.get(co,re.sub('[^a-z0-9_-]','',co.lower()) or 'employer_'+digest(co)[:8]);r['archive_json']=archive(slug,sid,r,None);r['archive_status']='正文已存档' if req else '合并正文已存档，资格未可靠拆分'
    else:r['archive_status']='仅历史元数据，正文未归档' if legacy else '仅元数据，正文未归档'
    return r

def main():
    merged={};versions=[];inputs=[];excluded=[]
    legacy=E/'all_official_features.json'
    if legacy.exists():
        for x in load(legacy):
            r=normalize(x,legacy,True)
            if r:merged[(r['company'],r['source_job_id'])]=r
    for path in sorted(E.glob('*_expanded_jobs.json')):
        rows=load(path);inputs.append({'file':str(path.relative_to(ROOT)),'rows':len(rows)})
        for x in rows:
            r=normalize(x,path)
            if not r:continue
            if r['company']=='AMD' and r['source_job_id']=='92722':
                excluded.append({'id':r['id'],'title':r['title'],'reason':'一个招聘活动页汇列多个岗位且提示去其他链接投递，不是单一具体JD；原文保留在原始采集中。','archive_json':r['archive_json']});continue
            k=(r['company'],r['source_job_id'])
            if k in merged:
                prev=merged[k]
                versions.append({'id':r['id'],'old_source':prev['source_file'],'new_source':r['source_file'],'old_hash':prev['text_sha256'],'new_hash':r['text_sha256'],'same_text_hash':prev['text_sha256']==r['text_sha256']})
                if not r['full_text'] and prev['full_text']:continue
            merged[k]=r
    data=sorted(merged.values(),key=lambda x:(x['company'],x['title_direction'],x['title'],x['source_job_id']))
    (E/'all_jobs_v2.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    body=[x for x in data if x['full_text']];q=[x for x in data if x['requirements_available']]
    companies=[]
    for co in sorted({x['company'] for x in data}):
        rr=[x for x in data if x['company']==co]
        companies.append({'company':co,'records':len(rr),'body_archived':sum(bool(x['full_text']) for x in rr),'separate_requirements':sum(x['requirements_available'] for x in rr),'clarity_candidates':sum(x['clarity_candidate'] for x in rr),'geography':dict(collections.Counter(x['geography'] for x in rr))})
    groups=['AI应用/Agent开发','Agent算法或交叉研究','AI Infra','后训练']
    skillrows=[]
    for g in groups:
        rr=[x for x in q if x['title_direction']==g]
        for sk in SKILLS:
            n=sum(sk in x['skills_in_requirement'] for x in rr)
            skillrows.append({'direction':g,'skill':sk,'mentioned':n,'denominator':len(rr),'pct':round(n/len(rr)*100,2) if rr else None})
    result={'records':len(data),'body_archived':len(body),'separate_requirements':len(q),'legacy_without_body':len(data)-len(body),'companies':companies,'job_families':dict(collections.Counter(x['job_family'] for x in data)),'title_directions':dict(collections.Counter(x['title_direction'] for x in data)),'clarity_candidates':sum(x['clarity_candidate'] for x in data),'content_hashes':len({x['text_sha256'] for x in body}),'skills':skillrows,'inputs':inputs,'duplicate_id_updates':len(versions),'scope_note':'雇主公开渠道截面与历史记录并集，范围不同，不代表全国市场份额；正文词信号不等于纯AI岗位。'}
    result['metadata_without_body']=len(data)-len(body)
    result['historical_only_without_body']=sum(x['legacy_only'] and not x['full_text'] for x in data)
    result['legacy_without_body_field_note']='兼容旧字段名；此值包含本轮新发现但未取得正文的记录，通用字段为metadata_without_body。'
    result['record_kinds']=dict(collections.Counter(x['record_kind'] for x in data))
    (A/'统计结果_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (A/'技能词典_v2.json').write_text(json.dumps(SKILLS,ensure_ascii=False,indent=2),encoding='utf-8')
    (A/'跨版本去重日志_v2.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2),encoding='utf-8')
    (A/'排除非具体岗位_v2.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['records','body_archived','separate_requirements','legacy_without_body','clarity_candidates','companies']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
