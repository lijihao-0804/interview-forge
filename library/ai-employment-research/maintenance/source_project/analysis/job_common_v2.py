"""Shared public job archival and transparent enrichment helpers."""
import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from collect_tencent import SKILLS
SKILLS=dict(SKILLS)
SKILLS.update({
 'Go':r'golang|(?-i:(?<![A-Za-z])Go(?![A-Za-z]))|(?:熟悉|掌握|精通|使用)\s*go(?![a-z])|(?<![a-z])go\s*(?:语言|开发|编程)',
 'C语言':r'(?<![a-z0-9+#])c(?![a-z0-9+#])|C语言',
 'C#/.NET':r'c\s*#|\.net(?![a-z])|asp\.net',
 'JavaScript/TypeScript':r'(?<![a-z0-9])(?:javascript|typescript|js|ts)(?![a-z0-9])',
 'React/Vue':r'react\.js|reactjs|(?-i:React)|vue(?:\.js|js|[234])?',
 'Node.js':r'node\.js|nodejs',
 'Android/iOS':r'android|(?<![a-z])ios(?![a-z])|Kotlin|Swift',
 'Rust':r'(?<![a-z])rust(?![a-z])',
 'Spring生态':r'spring\s*(?:boot|cloud|mvc|framework)|Spring框架',
 'HTTP/RPC/gRPC':r'(?<![a-z])(?:http|https|rpc|grpc)(?![a-z])|REST(?:ful)?',
 '微服务':r'微服务|microservice',
 'MySQL/PostgreSQL':r'mysql|postgres(?:ql)?',
 'Redis':r'(?<![a-z])redis(?![a-z])',
 'Elasticsearch/OpenSearch':r'elasticsearch|opensearch',
 'MongoDB':r'mongodb',
 'Hadoop/Spark/Flink':r'hadoop|spark|flink',
 'Kafka/MQ':r'kafka|rabbitmq|rocketmq|消息队列|message.queue',
 'ClickHouse':r'clickhouse',
 'Git/CI/CD':r'(?<![a-z])git(?![a-z])|gitlab|github.actions|CI/CD|持续集成|continuous.integration',
 'AWS/Azure/GCP':r'(?<![a-z])aws(?![a-z])|azure|google.cloud|(?<![a-z])gcp(?![a-z])',
 'NCCL/RDMA':r'nccl|rdma|infiniband|roce',
 'Slurm/Ray':r'slurm|(?<![a-z])ray(?![a-z])',
 'TVM/MLIR/XLA/LLVM':r'(?<![a-z])(?:tvm|mlir|xla|llvm)(?![a-z])',
 'CUTLASS/TileLang':r'cutlass|tilelang',
 'CANN/昇腾/MindSpore':r'(?<![a-z])cann(?![a-z])|昇腾|mindspore|ascend',
 'verl/OpenRLHF/Slime':r'(?<![a-z])verl(?![a-z])|openrlhf|(?<![a-z])slime(?![a-z])',
 'LlamaFactory/ms-swift':r'llama.?factory|ms.?swift',
 '量化/蒸馏/剪枝':r'量化|蒸馏|剪枝|quantization|distillation|pruning',
 '嵌入式/RTOS':r'嵌入式|embedded|rtos|freertos|固件|firmware',
 'RTL/Verilog/FPGA':r'(?<![a-z])(?:rtl|fpga|vhdl)(?![a-z])|verilog|systemverilog',
 'SoC/ASIC/RISC-V':r'(?<![a-z])(?:soc|asic)(?![a-z])|risc.v',
 '英语':r'英语|英文|English|Mandarin.*English|English.*Mandarin',
})

ROOT=Path(__file__).resolve().parents[1]
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds')
def plain(value):
    if value is None:return ''
    if not isinstance(value,str):value=json.dumps(value,ensure_ascii=False)
    if re.search(r'<(?:p|div|br|ul|li|span|strong|b)\b',value,re.I):
        value=BeautifulSoup(value,'html.parser').get_text('\n',strip=True)
    return re.sub(r'\n[ \t]*\n+', '\n\n',html.unescape(value)).strip()
def hits(text):return [k for k,p in SKILLS.items() if re.search(p,text or '',re.I)]
def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()

QUAL_HEAD=re.compile(r'(?im)^\s*(?:what we need to see|what you bring|what you.ll bring|what you need|minimum qualifications|basic qualifications|qualifications|requirements|your qualifications|required qualifications|qualifications? and skills|necessary skills and experience|preferred experience|key qualifications|任职要求|职位要求|岗位要求|任职资格|资格要求|岗位资格)\s*[:：]?\s*$')
QUAL_INLINE=re.compile(r'(?i)(?:what we need to see:|minimum qualifications:|basic qualifications:|required qualifications:|qualifications:|requirements:|任职要求[:：]|任职资格[:：])')
def split_body(body):
    text=plain(body)
    matches=[x for x in [QUAL_HEAD.search(text),re.search(r'(?im)^\s*(?:job requirements|key qualifications|preferred experiences?|requested experience|mandatory\s+experience|academic\s*(?:&\s*preferred\s+qualifications|credentials)|(?:(?:required|desired|nice\s+to\s+have)\s+)?skills\s+and\s+experience)\s*[:：]?\s*$',text),QUAL_INLINE.search(text)] if x]
    m=min(matches,key=lambda x:x.start()) if matches else None
    if m:return text[:m.start()].strip(),text[m.end():].strip(),'explicit_heading'
    return text,'','combined_body_only'

BOILERPLATE=re.compile(r'(?im)^\s*(?:Benefits offered are described|Qualcomm is an equal opportunity employer|Qualcomm expects its employees|To all Staffing and Recruiting Agencies|AMD does not accept unsolicited resumes|AMD may use Artificial Intelligence|This position will be open for a minimum|Our inclusive culture empowers|Our 10x Mindset|Use of AI in Your Application|Recruitment Adjustments and Accommodations|Posting Statement\s*:|Job Type\s*:).*$')
def requirement_analysis_text(value):
    """Retain full source text elsewhere; exclude identified policy footer from skill counts."""
    matches=[m for m in [BOILERPLATE.search(value or ''),re.search(r'(?m)^\s*(?:加入我们的理由|我们提供|薪酬福利|公司福利|福利待遇|关于我们)\s*[:：]?\s*$',value or '')] if m]
    m=min(matches,key=lambda x:x.start()) if matches else None
    return (value[:m.start()] if m else value or '').strip()

TASKS=[
 ('智能体、工具调用和任务编排',r'agent|智能体|工具调用|function.call|tool.call|workflow'),
 ('检索、知识库和搜索能力',r'\bRAG\b|检索|知识库|retrieval|semantic search'),
 ('模型训练、对齐和数据迭代',r'训练|微调|后训练|fine.?tun|post.?train|reinforcement|rlhf|\bSFT\b'),
 ('模型推理与计算性能优化',r'推理|inference|CUDA|算子|kernel|GPU|Triton'),
 ('平台、分布式系统与稳定性建设',r'平台|分布式|稳定性|可观测|kubernetes|distributed|reliability|infrastructure'),
 ('业务系统和服务端研发',r'后端|后台|服务端|backend|back.end|microservice|server.side'),
 ('客户端、前端和交互体验',r'前端|客户端|交互|front.end|android|iOS|web application'),
 ('评估、验证与质量改进',r'评测|测试|质量|evaluation|benchmark|quality|testing'),
 ('安全检测与风险治理',r'安全|风控|risk|security|vulnerability'),
 ('数据处理、分析和数据管线',r'数据分析|数据开发|数据处理|data analysis|data pipeline|data engineering'),
 ('芯片、硬件或嵌入式系统',r'芯片|硬件|嵌入式|hardware|ASIC|RTL|embedded'),
 ('产品规划与业务方案',r'产品规划|产品设计|需求分析|product management|product roadmap'),
 ('需求对接、客户或生态协作',r'客户|销售|售前|商务|sales|account management|customer|partner'),
 ('运营、内容与市场增长',r'运营|营销|内容生产|marketing|campaign|content creation'),
]
def summary(title,duty,requirement,location=None,experience=None,job_family=None):
    substantive=duty or ''
    m=re.search(r'(?im)^\s*(?:1[.、）)]|responsibilities\s*:|key responsibilities\s*:|what you.ll be doing\s*:|工作职责[:：]|岗位职责[:：])',substantive)
    if m:substantive=substantive[m.start():]
    topics=[label for label,p in TASKS if re.search(p,substantive,re.I)]
    nontechnical=job_family in {'产品','销售商务与解决方案','运营内容与市场','人力财务法务行政','设计与用户体验','供应链物流与线下','零售门店与现场业务'}
    if nontechnical:
        technical={'模型训练、对齐和数据迭代','模型推理与计算性能优化','平台、分布式系统与稳定性建设','业务系统和服务端研发','客户端、前端和交互体验','芯片、硬件或嵌入式系统'}
        topics=[t for t in topics if t not in technical]
    if re.search(r'infra|推理|算子|编译器|GPU|CUDA|inference|compiler|kernel',title,re.I):
        order=['模型推理与计算性能优化','平台、分布式系统与稳定性建设','模型训练、对齐和数据迭代','芯片、硬件或嵌入式系统']
        topics.sort(key=lambda x:order.index(x) if x in order else len(order))
    sk=hits(requirement or '')
    sentences=[]
    if topics:sentences.append('该岗位的职责涉及'+ '、'.join(topics[:4])+'。')
    else:sentences.append('该职位为“'+str(title)+'”，具体职责和工作范围已保存在完整JD中。')
    if sk:sentences.append('任职要求明确提及'+ '、'.join(sk[:9])+'；各项熟练程度及必备、优先关系以存档正文为准。')
    elif requirement:sentences.append('要求主要以专业经验和岗位能力描述，未检出统一技术词典中的项目；可直接阅读下方资格条件。')
    else:sentences.append('正文未被可靠拆分为独立任职要求，技能统计按缺失处理。')
    if experience and str(experience) not in ['未知','未明示','未提供独立年限字段']:
        sentences.append('经验字段为'+str(experience)+'。')
    return ''.join(sentences)

def archive(company_slug,ident,record,raw=None):
    folder=ROOT/'archives'/company_slug
    folder.mkdir(parents=True,exist_ok=True)
    ident=re.sub(r'[^A-Za-z0-9_.-]','_',str(ident))
    path=folder/(ident+'.json')
    data={'retrieved_at':now(),'source_url':record.get('url'),'company':record.get('company'),'source_job_id':record.get('source_job_id',record.get('id')),'description':record.get('description',''),'requirements':record.get('requirements',''),'full_text':record.get('full_text',''),'raw_source_payload':raw,'provenance':{k:record[k] for k in ['source_file','source_occurrences','source_archive_jsonl','archive_key'] if record.get(k)}}
    if path.exists():
        try:
            old=json.loads(path.read_text(encoding='utf-8'))
            old_text=old.get('full_text') or old.get('description','')+'\n\n'+old.get('requirements','')
            new_text=data.get('full_text') or data.get('description','')+'\n\n'+data.get('requirements','')
            if old_text!=new_text:path=folder/(ident+'__'+digest(new_text)[:12]+'.json')
            elif raw is not None and old.get('raw_source_payload')!=raw:path=folder/(ident+'__payload_'+digest(json.dumps(raw,ensure_ascii=False,sort_keys=True))[:12]+'.json')
            else:return str(path.relative_to(ROOT)).replace('\\','/')
        except (ValueError,OSError):path=folder/(ident+'__'+digest(json.dumps(data,ensure_ascii=False))[:12]+'.json')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(path.relative_to(ROOT)).replace('\\','/')
