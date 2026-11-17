# 数据字段与统计契约

统一统计使用下列规范字段。来源专用的direct/adjacent、explicit_communication_acceptance等旧字段仅为审计保留，不能代替统一tier或skill_eligible。

| 字段 | 含义与限制 |
|---|---|
| id | 本专题唯一文本键；不能据其外形认定为官网岗位ID |
| source_job_id / official_id_verified | 源ID与是否能作为官方ID配对；央国企公告行定位键不视为官方岗位ID |
| company / hiring_unit_name / hiring_unit_key | 公司原名称、招聘子单位、公司+子单位统计键；名称数不是独立法人计数 |
| parent_group | 统一母集团/公司聚合层级，原披露层级在provenance.original_parent_group；中通服按官网控股股东披露归中国电信 |
| ownership_group | 来源核验分组；未核验国资实控的大型企业不自动称纯民营 |
| tier | A明确通信工程；B通信专业组/相关学科；C本科电子信息类目录适用；D相邻专业、摘录或关联待核。A/B也不自动等于本人可报考 |
| major_quote / major_scope | 专业证据原句与范围：job_specific、table_row、batch_shared；共享批次不进入逐岗准入 |
| student_confirmed / student_status | 有学生招聘入口证据，不表示确定符合届别、学历、专业代码和截止要求 |
| current_status | 招聘状态，与学生身份分开。not_verified不能解释为开放；deadline_passed只是公告期限已过 |
| experience_signal / experience_note | 年限原文或结构字段信号，不是已核验的最低经验；未检出不等于零经验 |
| degree_raw / degree_words | 原学历字段与多值学历词。关键词可重叠，不是最低学历分布 |
| city / city_tags | 原地点字段与规范标签。总部/基地注释不当作工作城市；省级地区未列城市时明确标记，不猜城市 |
| career_track | 按标题规则作职业初分；泛研发不一律算软件，疑难项需读职责 |
| kind / skill_eligible | full独立JD、table表行/简版、batch共享批次；只有具备独立可统计资格段的完整JD进入技术分母 |
| requirements / description / full_text | 已存资格、职责与完整记录文本。来源可能是HTML/API正文，也可能是逐行页面抽取；完整性与采集范围见来源字段和manifest |
| technology_ids / technology_duty_ids | 原子技术在资格段/职责段的提及集合，单岗位同技术计一次；不能脱离skill_eligible直接算技能需求率 |
| technology_evidence | 资格段证据偏移，Unicode码点，end exclusive；对应requirements字段。浏览器处理需按Unicode码点而非UTF-16码元切片 |
| detailed_jd / clarity_score / clarity_signals | 详细度规则初筛，六项至少五项且为可用完整JD；不是公司质量或录用概率评分 |
| source_snapshot / retrieved_at | 原来源采集日与时间；不能把重建日期当成重新观察日期 |
| provenance | URL、源文件、正文SHA-256、原集团层级、出现记录及可用的浏览器页面档案 |

data/analysis.json为固定基线聚合；前端图表使用catalog按筛选重算。技术分母必须在同一专业、学生、来源完整度、城市/职业范围内计算。城市和学历多值不能求和当总量。

template_diagnostics给出学生A/B完整资格JD的岗位权重、去空白精确资格模板权重与集团等权平均。模板组内技术取并集；这些是样本敏感性分析，不是全国市场份额。

corpus为完整规范记录；catalog是轻量索引，详情分片为同一记录的展示副本；detailed-jds、筛选CSV、来源审计均为派生视图，不能再次相加。既有source_collection=existing是主看板28,344条中的子集。

跨期比较必须使用同版本规则/代码/词表/提取器，并且新一期有真实较新的source_snapshot。仅改--as-of不会被比较器接受。保留旧语料有利于存档，但它们不自动成为新一期重新观察的数据。
