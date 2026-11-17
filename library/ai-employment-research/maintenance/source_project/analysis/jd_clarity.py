"""Requirements clarity, not employer desirability or candidate admission odds."""
import re

DOMAIN=[r'Python|Java(?:Script)?|C\+\+|Golang|SQL|Linux|Rust',r'PyTorch|TensorFlow|JAX|机器学习|deep learning',r'CUDA|Triton|GPU|编译器|kernel',r'RAG|检索增强|retrieval',r'Agent|智能体|工具调用|tool.call',r'SFT|RLHF|GRPO|DPO|微调|后训练',r'Kubernetes|Docker|容器|distributed|分布式',r'数据分析|data analysis|statistics|统计学',r'A/B|AB测试|实验设计|causal|因果',r'Excel|Tableau|Power.?BI|CRM|Salesforce|SAP',r'供应链|采购|库存|supply.chain|procurement',r'客户开发|销售目标|pipeline|account.management|sales.target',r'交互设计|Figma|UX|用户研究|user.research',r'安全攻防|漏洞|security|risk|风控',r'预算|财务分析|financial.analysis|IFRS|会计']
DOMAIN += [r'React|Vue|TypeScript|JavaScript|前端|frontend',r'Android|iOS|Kotlin|Swift|移动端',r'FPGA|Verilog|RTL|ASIC|芯片|SoC',r'嵌入式|RTOS|固件|firmware',r'MySQL|Redis|Kafka|Spark|Flink|数据库',r'光学|射频|通信协议|通信系统|RF|wireless',r'制造工艺|制程|良率|manufacturing|yield|机械设计|结构设计',r'TVM|MLIR|LLVM|图编译|指令调度|算子融合',r'量化|蒸馏|剪枝|quantization|distillation|pruning']
ACT=re.compile(r'负责|设计|开发|建设|优化|研究|实现|搭建|维护|制定|交付|评估|测试|验证|分析|管理|推动|develop|design|build|implement|optimi[sz]e|research|maintain|evaluate|test|deliver|analy[sz]e|manage|lead',re.I)
CONDITION=re.compile(r'\d+\s*(?:年|\+?\s*years?)|本科|硕士|博士|应届|实习|bachelor|master|Ph\.?D|degree|graduate|intern',re.I)
PREFERRED=re.compile(r'加分|优先|preferred|nice.to.have|bonus|plus|ways.to.stand.out',re.I)
MANDATORY=re.compile(r'要求|资格|必须|熟悉|熟练|精通|required|requirements|qualifications|must|what.we.need',re.I)
DELIVER=re.compile(r'性能|吞吐|延迟|成本|稳定性|评测|指标|验收|回归|质量|安全|生产|上线|交付|转化率|收入|预算|performance|latency|throughput|cost|reliab|benchmark|metric|quality|production|deliver|revenue|budget|KPI',re.I)
CONTEXT=re.compile(r'业务|场景|团队|产品|客户|平台|系统|电商|游戏|金融|医疗|制造|研发|team|product|customer|platform|system|commerce|game|finance|health|manufactur',re.I)

def score_clarity(duty,requirements,title='',parse_status=''):
    duty=duty or '';requirements=requirements or '';parts=[s.strip() for s in re.split(r'[\n。；;]+',duty) if s.strip()]
    action_clauses=sum(bool(ACT.search(s)) and len(s)>=12 for s in parts)
    domains=sum(bool(re.search(p,requirements,re.I)) for p in DOMAIN)
    points={};reasons=[]
    points['职责与任务具体']=2 if action_clauses>=3 else 1 if action_clauses>=1 else 0
    if points['职责与任务具体']==2:reasons.append('有至少3项可辨认的行动职责')
    points['独立资格条件']=2 if len(requirements)>=100 else 1 if len(requirements)>=40 else 0
    if points['独立资格条件']==2:reasons.append('独立任职要求内容较完整')
    points['能力可核对']=2 if domains>=3 else 1 if domains>=1 else 0
    if points['能力可核对']==2:reasons.append('至少3类具体技术或业务能力可核对')
    points['准入条件明确']=int(bool(CONDITION.search(requirements+' '+title)))
    if points['准入条件明确']:reasons.append('经验、学历或招聘类型至少一项明确')
    points['必备优先分层']=int(bool(PREFERRED.search(requirements)) and bool(MANDATORY.search(requirements)))
    if points['必备优先分层']:reasons.append('可辨认必备与优先/加分分层')
    points['业务场景']=int(len(duty)>=100 and bool(CONTEXT.search(duty)))
    if points['业务场景']:reasons.append('有业务、团队或系统场景')
    points['交付约束']=int(bool(DELIVER.search(duty)))
    if points['交付约束']:reasons.append('提到交付、性能、质量或业务目标')
    score=sum(points.values())
    if not requirements:score=min(score,4)
    selected=score>=8 and len(requirements)>=100 and action_clauses>=3
    return {'clarity_score':score,'clarity_candidate':selected,'clarity_reasons':reasons,'clarity_components':points,'clarity_review':'规则初筛；不是岗位价值或录用概率评分','action_clauses':action_clauses,'specific_ability_groups':domains}
