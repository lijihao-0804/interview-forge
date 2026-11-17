"""Read public Tencent vacancies, deduplicate by PostId, extract auditable features.
No login, browser fingerprinting or verification bypass. Full text processed in memory;
delivered records contain links, short excerpts, hashes and coded factual attributes.
Run: E:\python\python.exe analysis/collect_tencent.py
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence'
BASE = 'https://careers.tencent.com/tencentcareer/api/post/'
SKILLS = {
 'Python': r'(?<![a-z])python(?![a-z])', 'Java': r'(?<![a-z])java(?![a-z])', 'C++': r'c\+\+',
 'Go': r'(?<![a-z])(?:golang|go)(?![a-z])', 'SQL': r'(?<![a-z])sql(?![a-z])|mysql|postgres',
 'Linux': r'linux', 'PyTorch': r'pytorch|(?<![a-z])torch(?![a-z])', 'TensorFlow': r'tensorflow',
 'RAG': r'(?<![a-z])rag(?![a-z])|检索增强', 'Agent': r'agent|智能体',
 'Prompt': r'(?<![a-z])prompt(?:s|ing|\s*engineering)?(?![a-z])|提示词', 'LangChain/LangGraph': r'langchain|langgraph',
 'MCP': r'(?<![a-z])mcp(?![a-z])', '工具调用': r'tool.?call|function.?call|工具调用',
 '评测': r'evaluat|benchmark|评测|评估', 'SFT/微调': r'(?<![a-z])sft(?![a-z])|微调|fine.?tun',
 'RL/对齐': r'(?<![a-z])(?:rl|rlhf|rlaif|ppo|grpo|dpo)(?![a-z])|强化学习|偏好对齐|后训练|post.?train',
 'DeepSpeed/Megatron/FSDP': r'deepspeed|megatron|fsdp',
 'CUDA/Triton': r'cuda|triton', 'GPU': r'(?<![a-z])gpu(?![a-z])|显卡|显存',
 'vLLM/SGLang/TensorRT': r'vllm|sglang|tensorrt',
 '分布式系统': r'distributed|分布式', 'Kubernetes/Docker': r'kubernetes|(?<![a-z])k8s(?![a-z])|docker|容器',
 '性能优化': r'profil(?:ing|er)|performance|性能|吞吐|低延迟',
 '安全': r'secur|安全|权限|沙箱', '数据库/缓存': r'数据库|database|redis|mysql|缓存',
}
AI = re.compile(r'(?<![a-z])ai(?![a-z])|aigc|llm|大模型|人工智能|智能体|机器学习|深度学习|神经网络|计算机视觉|自然语言|多模态|强化学习|推荐算法|搜索算法', re.I)
INFRA = re.compile(r'(?<![a-z])infra(?![a-z])|ai.?infra|agent.?infra|算子|编译器|异构计算|训练(?:框架|系统|平台)|推理(?:引擎|框架|系统|平台|服务|优化|加速)|高性能计算|机器学习(?:平台|系统)|ai平台|智算|算力|gpu|cuda', re.I)
POST = re.compile(r'后训练|post.?train|强化学习|rlhf|grpo|(?<![a-z])dpo(?![a-z])|(?<![a-z])sft(?![a-z])|偏好对齐|模型对齐|reward.?model|奖励模型', re.I)
APP = re.compile(r'agent|智能体|(?:大模型|ai)[\s-]*应用|(?<![a-z])rag(?![a-z])|检索增强|codebuddy|workbuddy|代码助手', re.I)

def dump(name, data):
    (OUT / name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def get(path, params):
    for attempt in range(3):
        try:
            r=requests.get(BASE+path,params=params,timeout=30)
            r.raise_for_status()
            j=r.json()
            if j.get('Code') != 200: raise ValueError(str(j.get('Code')))
            return j['Data']
        except Exception:
            if attempt == 2: raise
            time.sleep(1+attempt*2)

def main():
    start=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    first=get('Query',dict(keyword='',pageIndex=1,pageSize=100,language='zh-cn',area='cn'))
    count=first['Count']; rows=first['Posts']; page_log=[dict(page=1,count=len(rows),reported_total=count)]
    for page in range(2,(count+99)//100+1):
        time.sleep(.25)
        d=get('Query',dict(keyword='',pageIndex=page,pageSize=100,language='zh-cn',area='cn'))
        rows.extend(d['Posts']); page_log.append(dict(page=page,count=len(d['Posts']),reported_total=d['Count']))
    unique={str(x['PostId']):x for x in rows}
    metadata=[]; targets=[]
    for pid,x in unique.items():
        m=dict(company='腾讯',id=pid,title=x['RecruitPostName'],country=x.get('CountryName','未知'),
          city=x.get('LocationName','未知'),category=x.get('CategoryName','未知'),bg=x.get('BGName',''),
          experience=x.get('RequireWorkYearsName') or '未知',last_update=x.get('LastUpdateTime'),
          url=x.get('PostURL','').replace('http:','https:'),api_is_valid=x.get('IsValid'),access_date=start[:10])
        m['ai_broad_list_flag']=bool(AI.search(m['title']+' '+x.get('Responsibility','')))
        metadata.append(m)
        if m['country']=='中国': targets.append((m,x))
    dump('tencent_list_metadata.json',metadata)
    full=[]; errors=[]
    def worker(pair):
        m,x=pair
        d=get('ByPostId',dict(postId=m['id'],language='zh-cn'))
        responsibility=d.get('Responsibility') or ''
        requirement=d.get('Requirement') or ''
        text=responsibility+'\n'+requirement
        m=dict(m,detail_status='full' if responsibility and requirement else 'partial',
          responsibility_chars=len(responsibility),requirement_chars=len(requirement),
          text_sha256=hashlib.sha256(text.encode()).hexdigest(),
          short_quote=re.sub(r'^[\s\d.、]+','',requirement or responsibility)[:16],
          skills_in_requirement=[k for k,p in SKILLS.items() if re.search(p,requirement,re.I)],
          skills_in_responsibility=[k for k,p in SKILLS.items() if re.search(p,responsibility,re.I)],
          education_mentions=[k for k in ['本科','硕士','博士'] if k in requirement],
          ai_broad_flag=bool(AI.search(m['title']+' '+text)),
          salary='未结构化披露',posting_date='未知',
          status_caveat='官方接口返回有效记录及正文；未确认招聘人数、预算、实际剩余HC或HR响应')
        duty=m['title']+' '+responsibility
        m['direction_tags']=[]
        if m['ai_broad_flag']:
            if INFRA.search(duty):m['direction_tags'].append('AI Infra')
            if POST.search(duty):m['direction_tags'].append('后训练')
            if APP.search(duty):m['direction_tags'].append('AI应用/Agent')
        if m['category']!='技术': m['primary_direction']='非技术/其他职能'
        elif not m['ai_broad_flag']: m['primary_direction']='其他技术'
        elif INFRA.search(m['title']):m['primary_direction']='AI Infra'
        elif POST.search(m['title']):m['primary_direction']='后训练'
        elif APP.search(m['title']):m['primary_direction']='AI应用/Agent'
        elif POST.search(responsibility):m['primary_direction']='后训练'
        elif INFRA.search(responsibility):m['primary_direction']='AI Infra'
        elif APP.search(responsibility):m['primary_direction']='AI应用/Agent'
        else:m['primary_direction']='其他AI技术'
        time.sleep(.35) # bounded concurrent public reads
        return m
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(worker,p):p[0]['id'] for p in targets}
        for f in cf.as_completed(futures):
            try:full.append(f.result())
            except Exception as e:errors.append(dict(id=futures[f],error=str(e)))
    full.sort(key=lambda x:x['id'])
    dump('tencent_all_jd_features.json',full)
    audit=dict(started_at=start,finished_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
      employer='腾讯',list_scope='公开Query接口空关键词全部职位；包含海外；分析筛选中国',
      total_reported_initial=count,list_rows=len(rows),unique_post_ids=len(unique),
      duplicate_list_rows=len(rows)-len(unique),detail_targets=len(targets),detail_success=len(full),
      detail_full=sum(x['detail_status']=='full' for x in full),errors=errors,pages=page_log,
      limitation='非概率样本、单次截面；类别按可审计关键词规则推断。AI broad含传统ML/CV/推荐，不能等同生成式AI。未返回岗位不得当作关闭。',
      skill_dictionary=SKILLS,classification_patterns=dict(ai=AI.pattern,infra=INFRA.pattern,post=POST.pattern,application=APP.pattern))
    dump('tencent_all_collection_audit.json',audit)
    print(json.dumps({k:audit[k] for k in ['total_reported_initial','unique_post_ids','detail_targets','detail_success','detail_full','errors']},ensure_ascii=False))

if __name__=='__main__':main()
