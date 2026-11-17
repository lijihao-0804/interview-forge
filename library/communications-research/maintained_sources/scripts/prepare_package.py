"""Freeze an offline rebuilding workbench and public source evidence into the handoff."""
import gzip,json,shutil,hashlib,zipfile
from pathlib import Path
from build_topic import ROOT,UP,OUT,RULE_VERSION,lexicon,write,sha
def copyfile(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def main():
    work=OUT/'maintained_sources';work.mkdir(exist_ok=True)
    for src in (ROOT/'scripts').glob('*.py'):copyfile(src,work/'scripts'/src.name)
    shutil.copytree(ROOT/'frontend_src',work/'frontend_src',dirs_exist_ok=True)
    shutil.copytree(ROOT/'major_audit',work/'major_audit',dirs_exist_ok=True)
    if (ROOT/'archives/soe_browser_pages/manifest.json').exists():copyfile(ROOT/'archives/soe_browser_pages/manifest.json',work/'archives/soe_browser_pages/manifest.json')
    for name in ['campus_bulk','soe_sources']:
        for src in (ROOT/name).glob('*'):
            if src.is_file() and src.suffix in ['.py','.js','.md','.json','.jsonl']:
                if src.name.startswith('captures_batch'):continue
                copyfile(src,work/name/src.name)
    selected={json.loads(x)['id'] for x in gzip.open(OUT/'data/corpus.ndjson.gz','rt',encoding='utf-8') if json.loads(x)['source_collection']=='existing'}
    selected.add('小米-7660104107810326822') # keep rejected source evidence for reproducible exclusion audit
    upstream=work/'upstream';(upstream/'data/technology').mkdir(parents=True,exist_ok=True)
    with gzip.open(UP/'data/corpus.ndjson.gz','rt',encoding='utf-8') as src,gzip.open(upstream/'data/corpus.ndjson.gz','wt',encoding='utf-8') as dst:
        for line in src:
            if json.loads(line)['id'] in selected:dst.write(line)
    cat=json.loads((UP/'data/catalog.json').read_text(encoding='utf-8'));cat['jobs']=[j for j in cat['jobs'] if j['id'] in selected];write(upstream/'data/catalog.json',cat)
    copyfile(UP/'data/technology/technology_dictionary_v4.json',upstream/'data/technology/technology_dictionary_v4.json')
    copyfile(UP/'tools/technology_enrich.py',upstream/'tools/technology_enrich.py')
    original_ids=ROOT/'evidence/existing_major_stats.json'
    copyfile(original_ids,work/'upstream/original_major_screen_stats.json')
    write(work/'upstream/INPUT_SCOPE.json',{'scope':'Only existing employer records selected for this communications topic; not the complete 28,344-record v4 corpus.','selected_existing_records':len(selected),'original_v4_corpus_sha256':sha(UP/'data/corpus.ndjson.gz'),'upstream_dictionary_sha256':sha(UP/'data/technology/technology_dictionary_v4.json'),'extractor_sha256':sha(UP/'tools/technology_enrich.py'),'rule_version':RULE_VERSION,'original_v4_corpus_required_for_expanding_recall':True})
    evidence_manifest=[]
    roots=[('topic_archives',ROOT/'archives'),('campus_bulk/source_archive',ROOT/'campus_bulk/source_archive'),('soe_sources/captures',ROOT/'soe_sources/captures')]
    with zipfile.ZipFile(OUT/'source_archives.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for prefix,folder in roots:
            if not folder.exists():continue
            for f in sorted(folder.rglob('*')):
                if not f.is_file() or '__pycache__' in f.parts:continue
                rel=prefix+'/'+f.relative_to(folder).as_posix();z.write(f,rel);evidence_manifest.append({'archive_path':rel,'bytes':f.stat().st_size,'sha256':sha(f)})
    write(OUT/'data/source-archive-manifest.json',{'schema':'communications-raw-archives/1','zip':'source_archives.zip','files':evidence_manifest,'zip_sha256':sha(OUT/'source_archives.zip'),'note':'Public source HTML/JS/JSON/PDF are evidence downloads; never execute or embed archived website HTML in the frontend.'})
    rules={'version':RULE_VERSION,'professional_rule_source':'maintained_sources/scripts/build_topic.py','professional_rule_sha256':sha(ROOT/'scripts/build_topic.py'),'major_catalog':{'undergraduate_code':'080703','undergraduate_name':'通信工程','family_code':'0807','family_name':'电子信息类','parallel_major':'080701电子信息工程','source_url':'https://www.moe.gov.cn/srcsite/A08/moe_1034/s3882/202604/W020260427440749576927.pdf','pdf_sha256':sha(ROOT/'archives/教育部_2026本科专业目录.pdf'),'pdf_physical_page':15,'printed_page':17},'technology_dictionary_version':lexicon['dictionary_version'],'dictionary_sha256':sha(UP/'data/technology/technology_dictionary_v4.json'),'extractor_sha256':sha(UP/'tools/technology_enrich.py'),'offset_units':'Unicode code points, end exclusive'}
    write(OUT/'data/rules/processing-version.json',rules)
    copyfile(ROOT/'archives/教育部目录依据.json',OUT/'data/rules/教育部目录依据.json')
    copyfile(ROOT/'archives/教育部_2026本科专业目录.pdf',OUT/'archives/教育部_2026本科专业目录.pdf')
    guide='''# 重建与再采集命令\n\n本包的 maintained_sources 是可移交的离线工作台，不依赖 E盘原路径。包内上游输入只包含本专题选出的既有大厂记录；要扩大既有语料的召回范围，需换成封存v4的完整上游数据。此限制在 INPUT_SCOPE.json 中记录。\n\n在本数据包目录运行（Python 3.10+ 标准库即可，无需安装依赖）：\n\n```powershell\nE:\\python\\python.exe maintained_sources/scripts/build_topic.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt\nE:\\python\\python.exe maintained_sources/scripts/build_report.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt\nE:\\python\\python.exe maintained_sources/scripts/verify_major_rules.py --topic-root maintained_sources --upstream maintained_sources/upstream --output rebuilt\n```\n\n工具路径可换成其他机器的python。输出写入 rebuilt，不覆盖封存交接包。元数据、完整文本、分片与报告均从冻结输入重建。\n\n联通全量公开池再次采集示例（使用新的日期输出目录，已存在则拒绝覆盖）：\n\n```powershell\nE:\\python\\python.exe maintained_sources/scripts/collect_unicom_public.py --output snapshots/2026-12-18/unicom_105347 --campaign 105347\n```\n\n这只执行本期已验证的匿名公开API配方；将来页面迁移需先普通浏览器核验新的公开入口。遇HTTP限制/非JSON/登录要求则停止，不尝试签名、解密或绕过。每页原始响应和请求参数留档，末尾核对total/行数/唯一官方ID；直播列表在采集中变动造成总数不一致时不要把结果当完整快照。\n\n规范化记录必须保留 id、source_job_id、company、parent_group、title、url、description、requirements、full_text、major_raw、major_evidence_scope、degree_raw、city/city_tags、student_status、batch、application_deadline、retrieved_at、source_archive 和来源类型。逐岗JD用job_specific；表中专业按table_row；批次共享条件用batch_shared，禁止给所有岗位强行套专业准入。\n\n山东联通按jobNumber与主池交叉去重；缺jobNumber保留站点定位ID及其稳定性说明。烽火/中兴使用正常渲染的详情和官方UUID，不将仅岗位列表当作完整JD。央国企学校公告需要保留雇主发布主体、原文/表格对应行和截止时间。原采集器位于 maintained_sources/campus_bulk 与 soe_sources；这些历史采集脚本有本机路径，迁移时修改其输入输出参数，不应直接盲跑。\n\n每期再生成规则/词表/提取器文件哈希与source-archive-manifest。专业/技术规则变更后同规则重算两期，再比较共同渠道、职业、城市与集团的提及率。\n'''
    guide+='''\n## 下期与真实跨期比较\n\n新期规范化记录与来源文件放入新的工作台，使用 --as-of 指定实际整理日期，输出到新的目录，不覆盖本期。来源retrieved_at继续逐岗保留。\n\n```powershell\nE:\\python\\python.exe maintained_sources/scripts/build_topic.py --topic-root next_sources --upstream next_sources/upstream --output snapshots/2026-12-18 --as-of 2026-12-18\nE:\\python\\python.exe maintained_sources/scripts/compare_periods.py snapshots/2026-11-18 snapshots/2026-12-18 --output comparisons/20261118_20261218.json\n```\n\n比较器只接受两个真实且日期有先后的期间，校验专业规则代码、版本、字典和提取器哈希一致。分别输出全样本、共同集团×渠道、共同官方岗位ID三种口径。表格/批次定位ID不作为已核验官方ID配对；消失ID只称“观测缺失”，不认定关闭。可加 --city 北京、--track 软件与系统开发；默认限A/B学生完整资格JD，--include-nonstudents才纳入职业参考社招。\n\n## SQLite与统计例子\n\n数据库 data/communications.sqlite 使用TEXT保存官方ID，避免长ID精度丢失。jobs含全文及专业、学生、来源字段；cities为多值地点；terms为970项词典；job_technologies分qualification/duty；technology_evidence保留Unicode码点偏移。FTS5可用时另建jobs_fts。\n\n```sql\n-- 学生A/B池：按集团、职业统计完整资格JD，不混入批次公告\nSELECT parent_group,career_track,COUNT(*) AS qualification_jobs\nFROM jobs\nWHERE student_confirmed=1 AND tier IN ('A','B') AND skill_eligible=1\nGROUP BY parent_group,career_track ORDER BY qualification_jobs DESC;\n\n-- 北京学生A/B完整JD里，各技术提及了多少条岗位；多城市先用EXISTS防止重复\nSELECT t.label,COUNT(DISTINCT j.id) AS mentions\nFROM jobs j JOIN job_technologies x ON x.job_id=j.id\nJOIN terms t ON t.id=x.term_id\nWHERE j.student_confirmed=1 AND j.tier IN ('A','B') AND j.skill_eligible=1\nAND x.field='qualification'\nAND EXISTS(SELECT 1 FROM cities c WHERE c.job_id=j.id AND c.city='北京')\nGROUP BY t.id ORDER BY mentions DESC;\n```\n\n完整详细度子集为 data/detailed-jds.ndjson.gz，是corpus的派生筛选，不能再次相加计数。专业候选CSV的字段用于投递筛选，技术聚合CSV包含零值，适合后续长期比较。\n'''
    guide+='\n比较器还会要求新期记录有晚于旧期整理日的真实source_snapshot；只更改--as-of会被拒绝。保留在新语料库中的旧期记录会列入stale排除计数，不自动当作新期重新观察。比较时同时核对届别/批次与来源覆盖，不能把未重采或未进入筛选条件解释成岗位关闭。\n'
    (OUT/'REBUILD.md').write_text(guide.replace('python.exe maintained_sources','python.exe -B maintained_sources'),encoding='utf-8')
    maintenance=OUT/'MAINTENANCE.md';text=maintenance.read_text(encoding='utf-8');text=text.replace('从maintained_sources恢复来源专用采集器，先采集并交付记录JSONL；用tools/build_topic.py重建、tools/build_report.py出报告。构建工具默认以本目录为交接包，需要显式--topic-root/--upstream参数时见工具说明；本期工具中ROOT路径可在本地项目结构内复用。','先采集并交付规范记录JSONL；离线重建和公开池重采集的完整命令见 REBUILD.md。maintained_sources/scripts 支持显式--topic-root、--upstream、--output；历史来源采集器的本机路径需迁移，不宣称其全部可直接运行。').replace('tools/atomic、data/rules','maintained_sources/upstream、data/rules');maintenance.write_text(text,encoding='utf-8')
    print(json.dumps({'raw_archive_files':len(evidence_manifest),'raw_zip_bytes':(OUT/'source_archives.zip').stat().st_size,'frozen_existing_records':len(selected)},ensure_ascii=False))
if __name__=='__main__':main()
