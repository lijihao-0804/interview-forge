"""Offline analysis. Use only employer API records with separately read requirements.
Counts are corpus observations, not vacancies/persons in the national population.
"""
import collections
import ast
import csv
import json
import re
from pathlib import Path
from collect_tencent import SKILLS, AI, INFRA, POST, APP

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'evidence'; A=ROOT/'analysis'; C=ROOT/'charts'
C.mkdir(exist_ok=True)

NONTECH=re.compile(r'产品经理|产品专家|产品运营|运营专家|运营经理|销售|商务|市场营销|招聘|人力|设计师|法务|客户成功|解决方案|售前|咨询|生态拓展|商业化运营|产品策划|游戏策划|行业专家|产品架构',re.I)
TECH=re.compile(r'工程师|开发|研发|算法|研究员|科学家|技术专家|架构师|编译|算子|infra|sre',re.I)
INFRA_TITLE=re.compile(INFRA.pattern+r'|强化学习(?:框架|系统|平台)',re.I)
LLM_TITLE=re.compile(r'大模型|语言模型|混元|通义|文心|longcat|llm|基座模型|codebuddy|workbuddy|agent',re.I)
# Explicit reviewed titles: these positions build the Agent runtime/sandbox
# infrastructure rather than a business-facing Agent application.
TITLE_OVERRIDES={str(k):'AI Infra' for k in [2122347965157912576,2122503698335842304,2099353703831224320,2122504689126912000,2122348015627972608]}
TITLE_OVERRIDES['阿里巴巴-100026300005']='AI安全工程'
REVIEWED_AI_INFRA={'阿里巴巴-100046800002','阿里巴巴-100001863002'}

def load(n):return json.loads((E/n).read_text(encoding='utf-8'))
def txt(v):
    if isinstance(v,list):return '；'.join(txt(x) for x in v)
    if isinstance(v,dict):return json.dumps(v,ensure_ascii=False)
    return str(v or '未知')
def experience(v):
    if isinstance(v,str) and v.startswith('{'):
        try:v=ast.literal_eval(v)
        except (SyntaxError,ValueError):return v
    if isinstance(v,dict):
        lo,hi=v.get('from'),v.get('to')
        if lo is not None and hi is not None:return f'{lo}至{hi}年（API结构字段）'
        if lo is not None:return f'{lo}年以上（API结构字段）'
        if hi is not None:return f'{hi}年以内（API结构字段）'
        return '未知'
    return txt(v)
def csvwrite(path,rows,keys=None):
    if not rows:return
    keys=keys or list(rows[0])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader()
        for x in rows:
            values={k:txt(x.get(k,'')) for k in keys}
            # Excel truncates long numeric IDs; keep an employer-prefixed text key.
            if 'id' in values and values['id'].isdigit() and len(values['id'])>15:
                values['id']=txt(x.get('company','职位'))+'-'+values['id']
            for k,v in values.items():
                if v.startswith(('=','+','-','@')):values[k]="'"+v
            w.writerow(values)

def classify(x):
    t=x['title']; category=txt(x.get('category'))
    if x['company']=='腾讯':technical=category=='技术'
    elif NONTECH.search(t):technical=False
    elif category.startswith('技术'):technical=True
    elif x['company']=='京东':technical='研发' in category or bool(TECH.search(t))
    else:technical=bool(TECH.search(t))
    if not technical:return '非技术或标题未确认',False
    if str(x['id']) in TITLE_OVERRIDES:return TITLE_OVERRIDES[str(x['id'])],True
    if x['company']=='腾讯' and not x.get('ai_broad_flag',False):return '其他技术或标题未分方向',True
    if re.search(r'评测|测试|质量',t) and (AI.search(t) or APP.search(t) or INFRA_TITLE.search(t)):return 'AI评测或质量工程',True
    if re.search(r'数据(?:研发|工程|开发|平台)',t) and (AI.search(t) or APP.search(t)):return 'AI数据工程',True
    if re.search(r'sre|运维',t,re.I) and (AI.search(t) or APP.search(t)):return 'AI Infra',True
    if INFRA_TITLE.search(t):
        if AI.search(t) or LLM_TITLE.search(t) or re.search(r'模型|推理|训练|算子|cuda|gpu|智算|算力',t,re.I):return 'AI Infra',True
        return '通用Infra或需核实',True
    if POST.search(t):
        if re.search(r'后训练|post.?train|rlhf|grpo|\bdpo\b|\bsft\b|偏好对齐|模型对齐',t,re.I) or LLM_TITLE.search(t):return '后训练',True
        return '强化学习方向待核',True
    if APP.search(t):
        if re.search(r'算法|研究员|科学家',t):return 'Agent算法或交叉研究',True
        return 'AI应用/Agent开发',True
    return '其他技术或标题未分方向',True

def family(x):
    t=x['title']; c=txt(x.get('category'))
    # Specific nontechnical titles before broad technical phrases.
    rules=[('产品',r'产品经理|产品专家|产品策划|产品运营|游戏策划|产品负责人'),
      ('设计与用户体验',r'设计师|美术|动画|建模|特效|视觉设计|交互设计|用户研究|体验设计'),
      ('人力财务法务行政',r'人力|招聘|财务|法务|法律|会计|税务|行政|审计|薪酬|人事|行政'),
      ('销售商务与解决方案',r'销售|商务|售前|解决方案|客户成功|客户经理|咨询|行业专家|渠道|生态拓展|(?<![a-z])(?:bd|ka|kam|kabd|kacm)(?![a-z])'),
      ('运营内容与市场',r'运营|编辑|内容|营销|品牌|公关|市场|增长策略'),
      ('测试与质量',r'测试|质量|评测|qa工程|quality'),
      ('运维与SRE',r'sre|运维|运营维护'),
      ('数据工程与分析',r'数据开发|数据工程|数据研发|数据平台|大数据|数据分析|商业分析|数据科学|bi工程'),
      ('算法与研究',r'算法|研究员|科学家|研究工程|模型训练|模型研究'),
      ('基础设施与系统',r'infra|基础架构|基础设施|编译器|算子|异构计算|高性能计算|推理引擎|训练框架|数据库内核|存储引擎|操作系统|内核'),
      ('硬件嵌入式与通信',r'硬件|嵌入式|芯片|电路|射频|机械|机器人|自动驾驶|通信'),
      ('开发工程',r'开发|研发|工程师|架构师|技术专家|程序|客户端|前端|后端|后台'),
      ('供应链物流与线下',r'物流|仓储|配送|快递|供应链|采购|仓库|保安|司机|店长|分拣')]
    for label,p in rules:
        if label=='人力财务法务行政' and TECH.search(t):continue
        if label=='运营内容与市场' and re.search(r'研发|开发|工程师|架构师|算法',t):continue
        if re.search(p,t,re.I):return label
    official={'技术':'技术职能待细分','产品':'产品','设计':'设计与用户体验','销售、服务与支持':'销售商务与解决方案','营销与公关':'运营内容与市场','内容':'运营内容与市场','行政支持':'人力财务法务行政','财务':'人力财务法务行政','法律与公共策略':'人力财务法务行政','人力资源':'人力财务法务行政'}
    if c in official:return official[c]
    fallbacks=[('硬件嵌入式与通信',r'芯片|硬件'),('安全与风险',r'安全|风险'),('算法与研究',r'算法'),('运维与SRE',r'运维'),('测试与质量',r'测试'),('数据工程与分析',r'数据'),('开发工程',r'技术.*开发|研发类'),('技术职能待细分',r'^技术'),('人力财务法务行政',r'人力|财务|公司事务|综合类|职能类'),('销售商务与解决方案',r'销售|市场拓展|直销|BD'),('运营内容与市场',r'运营|市场|金融业务'),('供应链物流与线下',r'采销|供应链'),('战略投资与管理',r'战略|投资')]
    for label,p in fallbacks:
        if re.search(p,c,re.I):return label
    return '其他或待核实'

def geography(x,city):
    if re.search(r'香港|澳门|台北|台湾|臺北|Hong Kong|Taipei',city,re.I):return '港澳台或多地区'
    if x.get('country')=='中国':return '中国大陆（国家及城市字段）'
    if re.search(r'北京|上海|杭州|深圳|广州|成都|重庆|武汉|南京|苏州|西安|天津|合肥|济南|长沙|福州|厦门|青岛|郑州|宁波|无锡|东莞|佛山|珠海|全国|中国|江苏|浙江|广东|山东|四川|河北|河南|安徽|福建|江西|湖北|湖南|辽宁|吉林|黑龙江|广西|贵州|云南|山西|陕西|内蒙|海南|甘肃|宁夏|新疆|青海|西藏',city):return '含可识别中国大陆地点'
    if city in ['未知','','其他']:return '地点未核实'
    return '海外或地点待核实'

def main():
    raw=[]
    for name in ['tencent_all_jd_features.json','alibaba_all_bulk.json','jd_all_bulk.json']:
        data=load(name)
        for x in data:
            x=dict(x); x['source_file']=name; raw.append(x)
    unique={}
    for x in raw:
        key=(x['company'],str(x['id']))
        assert key not in unique,('duplicate key',key)
        unique[key]=x
    rows=[]
    for x in unique.values():
        direction,tech=classify(x)
        city=txt(x.get('city',x.get('location','未知')))
        ai_signal=('标题出现AI相关标识' if AI.search(x['title']) else
          '正文存在AI相关词信号' if x.get('ai_broad_flag') or set(x.get('skills_in_requirement',[])+x.get('skills_in_responsibility',[])) & {'PyTorch','TensorFlow','RAG','Agent','Prompt','SFT/微调','RL/对齐','vLLM/SGLang/TensorRT'} else '未检出上述AI标识')
        if x['id'] in REVIEWED_AI_INFRA:ai_signal='正文人工确认AI相关'
        rows.append(dict(company=x['company'],id=x['id'],title=x['title'],
            technical_candidate=tech,title_direction=direction,job_family=family(x),ai_signal=ai_signal,geography=geography(x,city),city=city,category_original=txt(x.get('category')),
            experience=experience(x.get('experience','未知')),experience_raw=x.get('experience_raw',x.get('experience','未知')),education_mentions=x.get('education_mentions',[]),
            skills_in_requirement=x.get('skills_in_requirement',[]),skills_in_responsibility=x.get('skills_in_responsibility',[]),
            detail_status=x.get('detail_status','unknown'),short_quote=x.get('short_quote','')[:16],
            url=x['url'],access_date=x.get('access_date','2026-11-17'),
            posted_date=x.get('posted_date','未知'),last_update=x.get('last_update','未知'),
            salary=x.get('salary','未知'),text_sha256=x.get('text_sha256',''),
            responsibility_chars=x.get('responsibility_chars',0),requirement_chars=x.get('requirement_chars',0),
            source_file=x['source_file'],classification_note='统一标题规则；开发属性仅腾讯使用官方技术大类，其余雇主按标题/原大类推断',
            original_direction_tags=x.get('direction_tags',[])))
    rows.sort(key=lambda x:(x['company'],x['title_direction'],x['title']))
    (E/'all_official_features.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    csvwrite(ROOT/'具体岗位数据.csv',rows)
    full=[x for x in rows if x['detail_status']=='full']
    tech=[x for x in full if x['technical_candidate']]
    targets=[x for x in tech if x['title_direction'] in ['AI Infra','后训练','AI应用/Agent开发']]
    companies=[]
    for co in sorted({x['company'] for x in rows}):
        d=[x for x in rows if x['company']==co]
        companies.append(dict(company=co,records=len(d),full=sum(x['detail_status']=='full' for x in d),
          technical_candidates=sum(x['detail_status']=='full' and x['technical_candidate'] for x in d),
          title_directions=dict(collections.Counter(x['title_direction'] for x in d if x['detail_status']=='full'))))
    skills=[]
    for group in ['AI应用/Agent开发','AI Infra','后训练','Agent算法或交叉研究']:
        sub=[x for x in tech if x['title_direction']==group]
        for sk in SKILLS:
            n=sum(sk in x['skills_in_requirement'] for x in sub)
            skills.append(dict(direction=group,skill=sk,mentioned=n,denominator=len(sub),pct=round(n/len(sub)*100,2) if sub else 0))
    csvwrite(A/'技能提及率.csv',skills)
    company_skills=[]
    for co in sorted({x['company'] for x in tech}):
        for group in ['AI应用/Agent开发','AI Infra','后训练','Agent算法或交叉研究']:
            sub=[x for x in tech if x['company']==co and x['title_direction']==group]
            for sk in SKILLS:
                n=sum(sk in x['skills_in_requirement'] for x in sub)
                company_skills.append(dict(company=co,direction=group,skill=sk,mentioned=n,denominator=len(sub),pct=round(n/len(sub)*100,2) if sub else None))
    csvwrite(A/'技能_公司_方向.csv',company_skills)
    city_mentions=[]
    for city in ['北京','上海','杭州','深圳','广州','成都','武汉','南京','苏州','西安']:
        for group in ['AI应用/Agent开发','AI Infra','后训练','Agent算法或交叉研究']:
            sub=[x for x in tech if x['title_direction']==group]
            city_mentions.append(dict(city=city,direction=group,positions_covering_city=sum(city in x['city'] for x in sub),denominator=len(sub)))
    csvwrite(A/'城市覆盖数.csv',city_mentions)
    pairs=[]
    for g in ['AI应用/Agent开发','Agent算法或交叉研究','AI Infra','后训练']:
        sub=[x for x in tech if x['title_direction']==g]
        for sk1,sk2 in [('Java','Agent'),('Python','Agent'),('RAG','工具调用'),('C++','CUDA/Triton'),('C++','vLLM/SGLang/TensorRT'),('PyTorch','RL/对齐'),('SFT/微调','评测')]:
            n=sum(sk1 in x['skills_in_requirement'] and sk2 in x['skills_in_requirement'] for x in sub)
            pairs.append(dict(direction=g,skill_pair=f'{sk1} + {sk2}',co_mentions=n,denominator=len(sub),pct=round(n/len(sub)*100,2) if sub else None))
    csvwrite(A/'技能组合共现.csv',pairs)
    cities=collections.Counter(x['city'] for x in targets)
    csvwrite(A/'城市字段分布.csv',[dict(city=k,records=v) for k,v in cities.most_common()])
    exp=[]; edu=[]
    for group in ['AI应用/Agent开发','AI Infra','后训练','Agent算法或交叉研究']:
        sub=[x for x in tech if x['title_direction']==group]
        for k,v in collections.Counter(x['experience'] for x in sub).most_common():exp.append(dict(direction=group,experience=k,records=v,denominator=len(sub)))
        for degree in ['本科','硕士','博士']:
            n=sum(degree in x['education_mentions'] for x in sub)
            edu.append(dict(direction=group,education_word=degree,mentioned=n,denominator=len(sub),pct=round(n/len(sub)*100,2) if sub else 0))
    csvwrite(A/'经验字段分布.csv',exp);csvwrite(A/'学历词提及率.csv',edu)
    missing=dict(salary_undisclosed=sum('未' in x['salary'] or '未知' in x['salary'] for x in full),
        experience_unknown=sum(x['experience'] in ['未知','未明示',''] for x in full),
        no_chinese_degree_term=sum(not x['education_mentions'] for x in full))
    summary=dict(total_records=len(rows),full_records=len(full),partial_records=len(rows)-len(full),
      technical_candidates=len(tech),three_direction_title_candidates=len(targets),companies=companies,
      job_families=dict(collections.Counter(x['job_family'] for x in full)),geography=dict(collections.Counter(x['geography'] for x in full)),ai_signals=dict(collections.Counter(x['ai_signal'] for x in full)),
      title_directions=dict(collections.Counter(x['title_direction'] for x in tech)),missingness=missing,
      skills=skills,company_skills=company_skills,education=edu,city_fields=dict(cities),city_mentions=city_mentions,skill_pairs=pairs,
      unique_content_hashes=len({x['text_sha256'] for x in full if x['text_sha256']}),
      content_hashes_by_company={co:len({x['text_sha256'] for x in full if x['company']==co}) for co in sorted({x['company'] for x in full})},
      reviewed_overrides=TITLE_OVERRIDES,
      classification_rules=dict(nontech=NONTECH.pattern,tech=TECH.pattern,infra=INFRA_TITLE.pattern,post=POST.pattern,llm_context=LLM_TITLE.pattern,app=APP.pattern),
      important='标题分类可复现且保守，漏掉标题宽泛但职责明确的相关岗位。不是完整市场规模或雇主招聘份额；Agent算法与应用工程分开。')
    (A/'统计结果.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'font.size':11})
    selected=['Python','Java','C++','Go','PyTorch','RAG','Agent','Prompt','LangChain/LangGraph','MCP','工具调用','评测','SFT/微调','RL/对齐','CUDA/Triton','vLLM/SGLang/TensorRT','Kubernetes/Docker','性能优化','安全']
    groups=['AI应用/Agent开发','Agent算法或交叉研究','AI Infra','后训练']
    arr=np.array([[next(z['pct'] for z in skills if z['direction']==g and z['skill']==s) for g in groups] for s in selected])
    fig,ax=plt.subplots(figsize=(10,10));im=ax.imshow(arr,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    ax.set_xticks(range(len(groups)),[g+'\nn='+str(sum(x['title_direction']==g for x in tech)) for g in groups]);ax.set_yticks(range(len(selected)),selected)
    for i in range(len(selected)):
        for j in range(len(groups)):ax.text(j,i,f'{arr[i,j]:.0f}%',ha='center',va='center',color='white' if arr[i,j]>55 else '#17324b')
    ax.set_title('任职要求中的技能词提及率\n四类明确标题候选 · 非硬门槛比例',pad=16)
    fig.colorbar(im,ax=ax,label='提及率 %');fig.text(.02,.01,'2026-11-17 官方公开职位中的标题候选；非概率抽样；多项可同时出现。',fontsize=9)
    fig.tight_layout(rect=[0,.03,1,1]);fig.savefig(C/'技能提及率.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4.8));names=[c['company'] for c in companies];counts=[c['full'] for c in companies]
    bars=ax.barh(names,counts,color=['#154f68','#338a9c','#edae49'])
    for b,n in zip(bars,counts):ax.text(n+8,b.get_y()+b.get_height()/2,str(n),va='center')
    ax.set_xlim(0,max(counts)*1.18);ax.set_xlabel('已取得职责和要求的职位ID数');ax.set_title('各公司详细JD语料覆盖\n采集范围不同，不代表招聘份额')
    ax.spines[['top','right']].set_visible(False);fig.tight_layout();fig.savefig(C/'采集覆盖.png',dpi=160);plt.close(fig)
    print(json.dumps({k:summary[k] for k in ['total_records','full_records','technical_candidates','three_direction_title_candidates','companies','title_directions','missingness']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
