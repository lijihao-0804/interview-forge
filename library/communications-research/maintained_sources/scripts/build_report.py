"""Generate the research report and maintenance contract from frozen topic data."""
import csv,gzip,hashlib,html,json,shutil,collections,re,urllib.parse
from pathlib import Path
from build_topic import ROOT,OUT,UP,RULE_VERSION,lexicon,sha,write
E=lambda v:html.escape(str(v))
def table(headers,rows):
    return '\n|'+'|'.join(headers)+'|\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('|'+'|'.join(str(v).replace('|','/').replace('\n',' ') for v in row)+'|\n' for row in rows)+'\n'
def md_to_html(md):
    out=[];in_table=False
    for line in md.splitlines():
        if line.startswith('|'):
            if re_separator(line):continue
            cells=line.strip('|').split('|')
            if not in_table:out.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+E(x)+'</th>' for x in cells)+'</tr></thead><tbody>');in_table=True
            else:out.append('<tr>'+''.join('<td>'+E(x)+'</td>' for x in cells)+'</tr>')
            continue
        if in_table:out.append('</tbody></table></div>');in_table=False
        if line.startswith('#'):n=len(line)-len(line.lstrip('#'));out.append(f'<h{n}>'+E(line[n:].strip())+f'</h{n}>')
        elif line.strip():out.append('<p>'+re.sub(r'https?://[^\s<>]+|\.\./index\.html\?[^\s<>]+',lambda m:'<a href="'+m[0]+'" target="_blank" rel="noopener noreferrer">'+m[0]+'</a>',E(line))+'</p>')
    if in_table:out.append('</tbody></table></div>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>通信工程专业就业报告</title><style>body{font:15px/1.9 system-ui,"Microsoft YaHei",sans-serif;background:#f5f6fb;color:#172033;margin:0}main{max-width:1280px;margin:30px auto;background:white;padding:40px;border:1px solid #d6dded;border-radius:14px}h1{font-size:32px}h2{margin-top:38px;border-left:4px solid #5654d4;padding-left:15px}h3{margin-top:28px}p{max-width:110ch;color:#43536b}.table-wrap{overflow:auto;border:1px solid #d6dded;border-radius:10px;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:11px 14px;border-bottom:1px solid #d6dded;min-width:80px}th{background:#eeedff;color:#34327f}a{color:#5654d4}@media(max-width:700px){main{margin:12px;padding:18px}h1{font-size:25px}td,th{padding:8px}}</style><main><a href="../index.html">← 返回交互筛选与图表</a>'+''.join(out)+'</main></html>'
def re_separator(s):return set(s.strip('|').replace('|','').replace(':','').replace(' ',''))=={'-'}
def main():
    rows=[json.loads(x) for x in gzip.open(OUT/'data/corpus.ndjson.gz','rt',encoding='utf-8')];a=json.loads((OUT/'data/analysis.json').read_text(encoding='utf-8'));terms={t['id']:t['name'] for t in lexicon['terms']}
    direct=[j for j in rows if j['tier'] in ['A','B']];students=[j for j in direct if j['student_confirmed']]
    usable=[j for j in students if j['skill_eligible']]
    def c(xs,k):
        co=collections.Counter()
        for j in xs:co.update(sorted(set(j[k] if isinstance(j[k],list) else [j[k]])))
        return co
    md=f"# 通信工程专业就业调研报告\n\n整理日期：{a['compiled_at']}。统计单位是已采集去重记录，不是HC、录用人数或全国招聘市场份额。\n"
    md+='\n## 先看结论与适用范围\n'
    for item in a['insights']:md+='\n### '+item['title']+'\n'+item['finding']+'\n\n'+item['implication']+'\n'
    md+='\n## 专业证据与学生入口的交叉统计\n'
    tiers={'A':'明确通信工程名称','B':'通信类/相关学科，核对学历层级','C':'电子信息本科大类映射','D':'相邻专业/批次条件待核'}
    md+=table(['专业证据','全部记录','有学生入口证据','独立完整JD','岗位表行','共享批次'],[(tiers[t],sum(j['tier']==t for j in rows),sum(j['tier']==t and j['student_confirmed'] for j in rows),sum(j['tier']==t and j['kind']=='full' for j in rows),sum(j['tier']==t and j['kind']=='table' for j in rows),sum(j['tier']==t and j['kind']=='batch' for j in rows)) for t in tiers])
    md+='专业入口与实际报考资格不能画等号。A层也可能要求博士、特定毕业届别；B层包含研究生信息与通信工程学科；C层仅在本科专业目录范围明确的情况下提供匹配依据。专业不限、优先背景、硬性专业门槛的措辞保留在原文。\n'
    md+=f"需求详细度规则初筛标记 {sum(j['detailed_jd'] for j in rows)} 条，其中学生A/B池 {sum(j['detailed_jd'] for j in students)} 条。规则为完整JD且以下六项至少五项成立：职责180字、资格150字、职责中至少3个行动词、资格提及至少2项技术、学历明确、专业条件明确。这个标签帮助找写得具体的JD，不评价公司质量或录用机会。\n"
    md+='\n## 什么职业可以去\n'
    tracks=c(rows,'career_track');sd=c(students,'career_track');dd=c(direct,'career_track')
    md+=table(['职业方向','专题全部','专业直接匹配A/B','其中学生入口','学生完整JD'],[(t,n,dd[t],sd[t],sum(j['career_track']==t for j in usable)) for t,n in tracks.most_common()])
    md+='职业方向按职位名称关键词作初步互斥分类，优先识别射频、芯片、嵌入式、网络、安全等具体方向，再归软件/数据等一般方向；不是企业官方岗位序列。具体职责可在详情中核对。综合支撑、客户经理等岗位可能接受通信背景，但工作性质与通信研发明显不同。\n'
    md+='\n## 什么公司与央国企在招收相关背景\n'
    groups=c(rows,'parent_group')
    md+=table(['母集团/公司','全部记录','A/B直接匹配','其中学生入口','招聘单位名称数'],[(g,n,sum(j['parent_group']==g for j in direct),sum(j['parent_group']==g for j in students),len({j['hiring_unit_key'] for j in rows if j['parent_group']==g})) for g,n in groups.most_common()])
    md+='\n按所有制核验分组：\n'+table(['所有制分组','记录','母集团/公司数','学生A/B记录'],[(g,n,len({j['parent_group'] for j in rows if j['ownership_group']==g}),sum(j['ownership_group']==g for j in students)) for g,n in c(rows,'ownership_group').most_common()])
    md+='运营商以分省分市单位大量发岗，和单一互联网公司发布方式不同。本次联通公开池覆盖更完整，造成样本中联通权重较大，不能据记录数断言其真实需求超过其他集团。央企集团目录只证明集团身份；所属单位关系结合来源公告。地方国企和央企控股企业分列，互联网/终端企业不未经核验推定为纯民营或国有。\n'
    md+='\n## 城市与学历：如何缩小投递范围\n'
    md+=table(['学生A/B候选城市标签','记录覆盖'],c(students,'city_tags').most_common(30))
    md+=table(['学历词或原字段','学生A/B覆盖','全部A/B覆盖'],[(d,c(students,'degree_words')[d],c(direct,'degree_words')[d]) for d in ['本科','硕士','博士']])
    md+='多城市与多学历词可以重复覆盖，因此不能相加当作总岗位数。学历词统计不是“最低学历”分布，包含“本科及以上”“硕博优先”等原句；网站提供原字段与原文，避免把同时出现本科、硕士误判成仅硕士岗位。\n'
    md+='\n## 技术需求：完整资格段里的明确提及\n'
    md+=f'本表分母为学生A/B池中{len(usable)}条独立资格段完整JD。全部采用与v4相同的970项原子技术词表及上下文边界规则。按职位是否提及计数，不按重复次数计数；不将缺失资格的表行算作没提技能。\n'
    tc=c(usable,'technology_ids');md+=table(['技术','学生完整JD提及','提及比例'],[(terms[t],n,f'{100*n/len(usable):.1f}%') for t,n in tc.most_common(50)] if usable else [])
    diag=a['template_diagnostics'];sensitivity={x['term_id']:x for x in diag['technology_sensitivity']}
    md+='\n### 模板与集团权重：结论对采集构成有多敏感\n'
    md+=f"{diag['qualification_jobs']}条学生A/B完整资格JD中，{diag['jobs_with_any_named_technology']}条命中至少一项具名技术；去除空白后资格文本完全相同的合计{diag['unique_qualification_templates']}份，最大一份模板被{diag['largest_template_job_count']}条岗位采用。相同资格模板的不同官方岗位ID仍保留为不同职位记录，不靠文本去重误合并不同地区岗位。\n"
    md+=table(['技术','岗位计数提及率','资格模板等权提及率','集团等权平均提及率'],[(terms[t],f"{x['job_share']*100:.1f}%",f"{x['template_share']*100:.1f}%",f"{x['equal_group_average_share']*100:.1f}%") for t,x in sensitivity.items() if terms[t] in ['Python','C','C++','Java','Go','MATLAB','LangChain','PyTorch','FPGA','SQL']])
    md+=f"岗位权重分母为{diag['qualification_jobs']}条；模板权重分母为{diag['unique_qualification_templates']}份去空白完全相同文本，技术取同模板组内并集；集团权重对{diag['groups_with_qualification_jobs']}个有完整资格JD的母集团/公司先求组内提及率再等权平均。三者都是本次样本的描述，不是行业真实需求比例。运营商模板较多、泛化资格较多，明显影响总体排名；少写技术名不能推出工作不需要技术。\n"
    md+='\n### 分职业方向的技术组合\n'
    md+=table(['职业方向','学生完整JD分母','最常见技术（提及记录数）'],[(t,len(xs),'；'.join(f'{terms[k]} {v}' for k,v in c(xs,'technology_ids').most_common(8))) for t,_ in sd.most_common() if (xs:=[j for j in usable if j['career_track']==t])])
    md+='出现技术名不等于硬性熟练要求，加分项与基础要求仍应阅读原文。软件方向通常需要拿真实项目证明工程能力，通信算法方向应证明信号处理/协议算法基础，硬件方向则应证明电路、器件、验证或嵌入式经验。这些是结合JD职责作出的学习路径推断，不是录用概率预测。技术词表覆盖有限，完整原文保留便于后续扩词重跑，不能宣称已穷尽所有技术。\n'
    md+='\n## 不同学生如何使用这份数据\n'
    md+=table(['学生条件/兴趣','建议先筛选','进一步核对'],[('本科、软件项目较多','学生入口+A/B+软件/云网/测试','岗位是否接受本科学历；是否要求特定技术栈与项目经验'),('本科、通信网络基础较强','学生入口+A/B+网络建设/解决方案','工作城市、值班/出差、岗位是技术还是营销交付'),('硕博、通信/信号处理研究','通信算法、射频、光通信、芯片','具体研究方向、论文/仿真/芯片与实验能力，信息与通信工程的学科要求'),('嵌入式/硬件实践较多','嵌入式、硬件、芯片、测试验证','C/C++、电路、接口、仪器或FPGA要求与自己的实际项目'),('想进央国企','所有制分组+集团+城市+学生入口','届别、学籍/学位认证、专业目录、笔试流程与截止时间')])
    md+='\n## 来源、质量与未覆盖范围\n'
    md+=table(['来源集合','纳入记录','学生A/B记录'],[(s,n,sum(j['source_collection']==s for j in students)) for s,n in c(rows,'source_collection').most_common()])
    md+=table(['来源完整度','全部记录','学生A/B记录'],[(k,n,sum(j['kind']==k for j in students)) for k,n in c(rows,'kind').most_common()])
    md+=table(['状态标签','记录'],c(rows,'current_status_label').most_common())
    md+='既有大厂语料的采集日期为2026-11-17；本专题额外渠道为2026-11-18。原始文本已存档，未来网站下架仍可审阅；公开页面存档不代表当前仍招聘。公告明示截止日已过时单列，不因列表未出现就自动认定关闭。中国电信官网本机请求遇访问限制；中国移动部分正常浏览器单位入口返回空列表，不可外推全集团需求为零。中兴等设备厂商详情覆盖有限，缺失是采集覆盖问题。\n'
    cv=a['collection_coverage']
    md+=f"联通及设备商批量采集保留{cv['bulk_raw_rows']}条源行的筛选审计，{cv['bulk_full_detail_rows']}条有完整详情，官方ID去重后{cv['bulk_unique_id_groups']}组，最终专题输入{cv['bulk_retained_records']}条完整JD；其中来源专用direct标签{cv['bulk_source_direct_labels']}条不自动等同统一专业规则下的A/B，专业知识、经验放宽与具体专业目录映射仍需区分。山东本期来源公告截止2026-11-15，标为已过期。\n"
    md+=f"央国企补充{cv['soe_records']}条来自{cv['soe_units']}个用人单位：{cv['soe_complete_page_text_records']}条有覆盖完整的页面逐行文本抽取，{cv['soe_partial_excerpt_records']}条只有部分页/索引摘录，后者全部放入D层参考；只有{cv['soe_skill_eligible_records']}条独立职责与完整原文资格段进入技能分母，其余为岗位表行/简版。另以正常Edge访问{cv['browser_source_urls']}个对应URL，实际保存{cv['browser_full_bodies']}个可用完整页面HTML/正文；其余HTTP403或连接失败均记档，未将错误页称作完整原始JD。\n"
    md+='国家电网/南方电网等另有批次共享专业公告留存在来源清单；未拿到逐岗对应关系时不计入具体岗位数，因此表内缺失不代表这些集团不招聘通信工程背景。所有单位名称计数是来源名称的聚合，不是核验过的独立法人数量。\n'
    md+='专业抽样是100条雇主分层与边界审阅，不能估计总体准确率。原始1183候选抽样中有1处研究领域误收，已修正；补“专业：通信”字段规则后新增匹配。年限筛查是原文信号而非已结构化最低年限。\n'
    md+='\n## 分期维护与需求变化分析\n'
    md+='每期保留原始响应/网页、来源清单与SHA256、采集时间、岗位官方ID、单位、专业证据、正文哈希、专业规则版本、技术词表与提取器哈希。不要覆盖上期档案。本期仅一轮专题基线，不展示需求上涨/下跌。\n'
    md+='下期先区分新增来源与同来源内容变化。对共同母集团和同渠道计算技能提及率，对同一官方职位ID比较资格文本及技术集合增减；同时报告新增/消失记录、抓取失败和过期公告。岗位从列表消失不等于确定关闭。规则或词表变更时用新版本重跑两期，再作可比比较，不把算法升级误当需求增长。\n'
    md+='未来比较“语言需求涨跌”应同时给出职位数、可用资格段分母、百分比与百分点变化；渠道构成变化可造成总体比例变化，须按职业/城市/共同雇主分层。\n'
    md+='\n## 主要核验来源\n'
    for s in a['sources']:md+=s['name']+'：'+s['url']+'\n\n'+s['note']+'\n\n'
    reports=OUT/'reports';reports.mkdir(exist_ok=True)
    (reports/'通信工程专业就业报告.md').write_text(md,encoding='utf-8');(reports/'通信工程专业就业报告.html').write_text(md_to_html(md),encoding='utf-8')
    shutil.copy2(ROOT/'major_audit/notes.md',reports/'专业筛选审阅.md')
    shutil.copytree(ROOT/'major_audit',OUT/'audit/major_audit',dirs_exist_ok=True)
    # Long-form aggregate tables suitable for spreadsheet / SQL analysis.
    with (reports/'技能分职业统计.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['scope','career_track','term_id','technology','qualification_jobs','denominator','share'])
        for scope,xs in [('students_direct',students),('all_direct',direct),('all_layers',rows)]:
            for t in ['全部职业']+sorted({j['career_track'] for j in xs}):
                ys=[j for j in xs if j['skill_eligible'] and (t=='全部职业' or j['career_track']==t)];co=c(ys,'technology_ids')
                for term,name in terms.items():w.writerow([scope,t,term,name,co[term],len(ys),co[term]/len(ys) if ys else ''])
    with (reports/'技术统计权重敏感性.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['term_id','job_mentions','job_denominator','job_share','template_mentions','template_denominator','template_share','equal_group_average_share'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(diag['technology_sensitivity'])
    with (reports/'专业候选岗位.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['id','title','company','hiring_unit_name','hiring_unit_key','parent_group','ownership_group','tier','major_quote','student_confirmed','student_status','degree_raw','city_tags','career_track','kind_label','current_status_label','source_snapshot','url'];w=csv.writer(f);w.writerow(fields)
        for j in rows:w.writerow([("'"+str(j[k]) if k=='id' else ' / '.join(j[k]) if isinstance(j[k],list) else j[k]) for k in fields])
    detailed=[j for j in rows if j['detailed_jd']]
    with gzip.open(OUT/'data/detailed-jds.ndjson.gz','wt',encoding='utf-8') as f:
        for j in detailed:f.write(json.dumps(j,ensure_ascii=False,separators=(',',':'))+'\n')
    selected=[];strata=collections.Counter()
    for j in sorted(detailed,key=lambda j:(not j['student_confirmed'],-j['clarity_score'],j['parent_group'],j['career_track'],j['id'])):
        key=(j['parent_group'],j['career_track'])
        if strata[key]>=2:continue
        selected.append(j);strata[key]+=1
        if len(selected)>=40:break
    sample='# 需求较明确的JD样本\n\n完整详细度子集：data/detailed-jds.ndjson.gz。本页按集团×职业方向每组至多2条，优先学生入口及高详细度，展示至多40条。不是企业排名，也不代表薪资或录用概率。\n'
    for j in selected:
        link='../index.html?'+urllib.parse.urlencode({'scope':'all','tier':'all','search':j['id']})
        sample+='\n## '+j['parent_group']+' · '+j['title']+'\n\n职业：'+j['career_track']+'；详细度：'+str(j['clarity_score'])+'/6；学生入口：'+str(j['student_confirmed'])+'。\n\n专业证据：'+j['major_quote']+'\n\n原始招聘来源：'+j['url']+'\n\n'
        sample+='查看存档：'+link+'\n'
    (reports/'需求明确JD样本.md').write_text(sample,encoding='utf-8');(reports/'需求明确JD样本.html').write_text(md_to_html(sample),encoding='utf-8')
    (OUT/'README.md').write_text('''# 通信工程就业数据包\n\n本目录为独立静态前端和分析数据。不要覆盖已封存v4主看板；建议部署到 /research/communications/。\n\n本地预览：在本目录运行 E:\\python\\python.exe -m http.server 8765，然后访问 http://127.0.0.1:8765/。需HTTP服务，不能双击HTML加载数据。\n\n入口 index.html；报告 reports/通信工程专业就业报告.html；完整文本 data/corpus.ndjson.gz；轻量目录 data/catalog.json.gz，浏览器不支持解压时回退明文；详情 data/details/*.json 按需加载。全部路径相对，支持嵌套路由。需正确提供 .mjs 为JavaScript、JSON为application/json，不要对普通gzip文件重复套Content-Encoding。\n\n后续分析使用 data/analysis.json、reports/技能分职业统计.csv、专业候选岗位.csv。字典970项，零提及项也留在技能聚合CSV；city_tags与degree_words可多值重复，不能相加作总量。\n\n不要将原始网页HTML直接嵌入站点；前端详情以文本展示。原始采集文件另见 archives/ 和 source_archives.zip。详情包含source_job_id、来源时间、文本哈希与专业证据。请保留审阅和专业分层，不把相邻专业、社招参考与应届直接候选混合宣称可投。\n''',encoding='utf-8')
    (OUT/'MAINTENANCE.md').write_text('''# 采集、版本与趋势分析指南\n\n1. 每次新建日期目录，保留source_archive原始HTML/JSON/PDF与URL、时间、SHA256；不能覆盖旧快照。API应沿用正常公开页面允许的匿名请求。遇登录、风控或加密限制停止该路径，记录覆盖缺口，不绕过。\n2. 运营商公开池全页保存，审计返回total、分页、原始行、唯一官方ID与重复数；品牌分站按同jobNumber合并并保留来源出现记录。学校转发公告只使用雇主发布在官方学校的正文；岗位表行与批次共享专业分别标注。\n3. 专业规则先用资格段或结构专业字段：A明确通信工程、B通信专业组/相关学科、C本科电子信息类目录映射、D相邻/批次待核。职责通信协议、研究专业领域、通信工程师标题不能作为毕业专业证据。“电子信息工程”不是“电子信息类”。本科目录映射不能无条件套用硕士学科。\n4. 学生入口、学历、经验信号、申请截止时间独立字段；未知年限不能写0年。记录当前采集时可见，不自动推断在招名额。\n5. 从maintained_sources恢复来源专用采集器，先采集并交付记录JSONL；用tools/build_topic.py重建、tools/build_report.py出报告。构建工具默认以本目录为交接包，需要显式--topic-root/--upstream参数时见工具说明；本期工具中ROOT路径可在本地项目结构内复用。不要修改封存v4；新词表版本必须独立保存。\n6. 当前版本通信专业规则 communications-major-v1.1.0-20261118；技术词表和提取器沿用v4，其原文件与哈希在tools/atomic、data/rules。变更后先跑专业边界fixtures、全量证据完整性与浏览器测试。\n7. 趋势分析限定共同渠道/集团，按职业和城市分层；用岗位官方ID配对比较资格文本、技术集合、采集可用性。分别报告提及数、完整资格分母、提及率及百分点。缺失/访问失败不等于岗位关闭；新加来源不当作招聘增长。\n8. 字典更新后将两期原始文本用同一新规则重跑，再比较；保留原始处理版本及哈希，避免用词表扩容制造技术需求增长。批次共享记录不并入逐岗技能分母。\n\n本专题尚只有一个真实基线，报告不含时间涨跌结论。\n''',encoding='utf-8')
    print('report generated',len(rows),'records',len(md),'characters')
if __name__=='__main__':main()
