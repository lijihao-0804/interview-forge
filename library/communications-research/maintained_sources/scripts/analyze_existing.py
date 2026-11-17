"""Source-grounded major eligibility screen; title/skill relevance alone is not admission evidence."""
import collections,gzip,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];UPSTREAM=ROOT.parents[1]/'前端交接包_就业数据台'
BAD_AFTER=re.compile(r'能力|技能|知识|经验|素养|水平|服务|培训|认证|技术')
CAREERS=[
 ('射频、天线与电磁',r'射频|天线|微波|电磁|RF\b|Antenna'),
 ('通信算法与基带',r'通信算法|基带|调制|解调|信道|物理层|协议栈|通信系统|无线.*算法|卫星通信|量子通信'),
 ('光通信与光电',r'光通信|光模块|光器件|光网络|光传输|光电'),
 ('芯片、FPGA与集成电路',r'FPGA|ASIC|RTL|芯片|集成电路|IC\b|SoC|数字前端|数字后端'),
 ('嵌入式与终端硬件',r'嵌入式|固件|硬件|驱动|单片机|PCB|电路|电子开发'),
 ('网络与信息安全',r'安全|Security'),
 ('测试、验证与质量',r'测试|验证|质量|可靠性|Test|QA\b'),
 ('通信网络建设与运营',r'通信技术|通信网络|网络优化|网络规划|承载网|宽带|网优|无线网络|传输|网络维护|网发建设'),
 ('云网、算力与运维',r'运维|SRE|云|算力|计算平台|基础设施|网络工程|数据中心|DevOps'),
 ('解决方案、技术服务与交付',r'解决方案|技术支持|技术服务|售前|售后|交付|项目管理|项目经理|系统集成'),
 ('AI、数据与算法',r'算法|AI\b|大模型|智能体|数据|机器学习|Agent|研究员'),
 ('软件与系统开发',r'软件|开发|研发|后端|前端|程序|系统工程|工程师|架构'),
 ('技术产品与市场商务',r'产品|市场|销售|运营|客户经理|营销|商务'),
]

def major_screen(q):
    proofs=[]
    for clause in re.split(r'[\n。；;]',q):
        for m in re.finditer('专业',clause):
            if BAD_AFTER.match(clause[m.end():]):continue
            prefix=clause[:m.start()]
            if '通信' not in prefix:continue
            tier='A_明确列出通信工程' if re.search(r'(?<!信息与)通信工程(?!师)',prefix) else 'B_列出通信专业组'
            proofs.append({'tier':tier,'field':'requirements_analysis','quote':clause.strip(),'matched_major':'通信工程' if tier.startswith('A') else '通信/信息与通信工程'})
    if not proofs:
        for clause in re.split(r'[\n.;]',q):
            if re.search(r'telecommunications?\s+engineering',clause,re.I) and re.search(r'major|degree|bachelor|master|Ph\.?D',clause,re.I):
                proofs.append({'tier':'A_明确列出通信工程','field':'requirements_analysis','quote':clause.strip(),'matched_major':'Telecommunications Engineering'})
    if not proofs:return None,[]
    return ('A_明确列出通信工程' if any(p['tier'].startswith('A') for p in proofs) else 'B_列出通信专业组'),proofs

def student_status(j,q):
    title=j['title'];source=j.get('source_file','')
    if re.search(r'实习|intern',title,re.I):return '实习职位',[]
    if re.search(r'校招|应届|校园|campus|graduate',title,re.I) or re.search(r'campus|graduate',source,re.I):return '校招/毕业生入口（届别以原文为准）',[]
    if re.search(r'应届毕业生|应届生|fresh graduate|new graduate',q,re.I):return '资格段明确提及应届',[]
    years=[]
    for pattern in [r'(\d+)\s*(?:[-~至]\s*\d+\s*)?年(?:以上)?[^\n。；;]{0,14}(?:工作|开发|研发|从业|项目|运维|测试|相关)?经验',r'(\d+)\+?\s*(?:years?|yrs?)[^\n.;]{0,30}experience']:
        for m in re.finditer(pattern,q,re.I):
            if int(m.group(1))>0:years.append({'minimum_years_signal':int(m.group(1)),'quote':q[max(0,m.start()-20):m.end()+30]})
    if years:return '有年限经验要求，需核对学生资格',years
    if j['company'] in ['华为','荣耀','阿里巴巴']:return '社招/集团非校招渠道，未确认学生资格',[]
    return '未确认学生可直接投递',[]

def career(title):return next((name for name,pattern in CAREERS if re.search(pattern,title,re.I)),'其他/需阅读职责')

def main():
    (ROOT/'evidence').mkdir(exist_ok=True)
    catalog=json.loads((UPSTREAM/'data/catalog.json').read_text(encoding='utf-8'))['jobs'];cats={j['id']:j for j in catalog}
    tech=json.loads((UPSTREAM/'data/technology-index.json').read_text(encoding='utf-8'))
    hits=[];excluded=0
    with gzip.open(UPSTREAM/'data/corpus.ndjson.gz','rt',encoding='utf-8') as f:
        for line in f:
            j=json.loads(line)
            if not j['requirements_available']:continue
            q=j.get('requirements_analysis') or j.get('requirements') or '';tier,proof=major_screen(q)
            if tier is None:
                excluded+=int('通信' in q);continue
            status,experience=student_status(j,q)
            for item in proof:
                item['field']='requirements_analysis' if j.get('requirements_analysis') else 'requirements'
                item['offset_start']=q.find(item['quote']);item['offset_end_exclusive']=item['offset_start']+len(item['quote']);assert item['offset_start']>=0
            ownership='外企（既有分组）' if cats[j['id']]['company_group']=='外企' else '其他大型互联网/终端企业（本轮未核验国资实控）'
            hits.append({**j,'source_snapshot':'2026-11-17','major_match_tier':tier,'major_evidence':proof,'student_status':status,'experience_signals':experience,'career_track':career(j['title']),'city_tags':cats[j['id']]['city_tags'],'ownership_group':ownership,'parent_group':j['company'],'technologies':tech['jobs'][j['id']],'technology_dictionary_version':tech['dictionary_version'],'source_channel':'既有雇主官方JD语料','row_kind':'具体职位广告' if j['record_kind']=='具体职位广告' else j['record_kind']})
    path=ROOT/'evidence/existing_major_jobs.ndjson.gz'
    with gzip.open(path,'wt',encoding='utf-8') as f:
        for j in hits:f.write(json.dumps(j,ensure_ascii=False,separators=(',',':'))+'\n')
    stats={'existing_corpus_records':len(catalog),'major_matched_records':len(hits),'scope':'仅专业资格文字明确列出通信工程或通信专业组；不使用职责通信词/标题相近作为专业准入','excluded_communication_mentions_without_major_evidence':excluded,'tiers':dict(collections.Counter(j['major_match_tier'] for j in hits)),'student_status':dict(collections.Counter(j['student_status'] for j in hits)),'companies':dict(collections.Counter(j['company'] for j in hits)),'careers':dict(collections.Counter(j['career_track'] for j in hits))}
    (ROOT/'evidence/existing_major_stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
