"""Recompute auditable atomic-technology tables from the portable bundle (stdlib)."""
import argparse, collections, csv, datetime as dt, html, json, os
from pathlib import Path

DIRECTIONS = ['AI应用/Agent开发', 'Agent算法或交叉研究', 'AI Infra', '后训练']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--technology-index', type=Path, required=True)
    p.add_argument('--dictionary', type=Path, help='Optional full dictionary for translated category labels')
    p.add_argument('--snapshot', required=True, help='Real observation date; processing time is recorded separately')
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    catalog = json.loads(a.catalog.read_text(encoding='utf-8'))
    jobs = catalog['jobs']
    index = json.loads(a.technology_index.read_text(encoding='utf-8'))
    terms = {x['id']: x for x in index['terms']}
    dictionary_path=a.dictionary or a.technology_index.parent/'technology/technology_dictionary_v4.json'
    dictionary=json.loads(dictionary_path.read_text(encoding='utf-8')) if dictionary_path.exists() else {}
    labels={key:value['label'] for key,value in dictionary.get('category_type_values',{}).items()}
    assert len(terms) == len(index['terms'])
    assert set(index['jobs']) == {j['id'] for j in jobs}, 'Technology index must cover the exact catalog'
    for ident, fields in index['jobs'].items():
        for field in ['requirement', 'duty', 'fulltext']:
            values = fields.get(field, [])
            assert len(set(values)) == len(values), (ident, field, 'duplicate term')
            assert set(values) <= set(terms), (ident, field, 'unknown term')
    out = a.output_dir
    out.mkdir(parents=True, exist_ok=True)
    eligible = [j for j in jobs if j['requirements_available']]
    groups = [('全部记录', jobs), *[(d, [j for j in jobs if j['title_direction'] == d]) for d in DIRECTIONS]]
    rows = []
    for scope, subset in groups:
        for field in ['requirement', 'duty', 'fulltext']:
            cohort = [j for j in subset if j['requirements_available']] if field == 'requirement' else [j for j in subset if j.get('body_chars')]
            counts = collections.Counter(t for j in cohort for t in set(index['jobs'][j['id']].get(field, [])))
            company_n = collections.Counter(j['company'] for j in cohort)
            company_terms = collections.defaultdict(collections.Counter)
            for j in cohort:
                for t in set(index['jobs'][j['id']].get(field, [])):
                    company_terms[t][j['company']] += 1
            eligible_companies = [c for c, n in company_n.items() if n >= 5]
            for ident, term in terms.items():
                n = counts[ident]
                macro = sum(company_terms[ident][c] / company_n[c] for c in eligible_companies) / len(eligible_companies) * 100 if eligible_companies else None
                rows.append({'scope': scope, 'field': field, 'technology_id': ident, 'technology': term['name'], 'category': term['category'], 'category_label': labels.get(term['category'],term['category']), 'n': n, 'denominator': len(cohort), 'pct': round(n / len(cohort) * 100, 4) if cohort else None, 'employers_with_mentions': len(company_terms[ident]), 'eligible_employers_n5': len(eligible_companies), 'company_equal_pct': round(macro, 4) if macro is not None else None})
    def write_csv(name, records):
        with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    write_csv('原子技术_方向_字段_全表.csv', rows)
    # Multi-city rows overlap. Unknown locations are left explicit.
    city_counts = collections.Counter(c for j in jobs for c in set(j.get('city_tags') or []))
    cities = []
    for city, n in city_counts.most_common():
        matching = [j for j in jobs if city in (j.get('city_tags') or [])]
        cities.append({'city': city, 'records': n, 'requirements_denominator': sum(j['requirements_available'] for j in matching), **{d: sum(j['title_direction'] == d for j in matching) for d in DIRECTIONS}})
    if cities:
        write_csv('城市_四方向_覆盖.csv', cities)
    all_req = sorted((r for r in rows if r['scope'] == '全部记录' and r['field'] == 'requirement' and r['n']), key=lambda x: (-x['n'], x['technology']))
    categories = collections.defaultdict(set)
    for j in eligible:
        for ident in index['jobs'][j['id']].get('requirement', []):
            categories[terms[ident]['category']].add(j['id'])
    summary = {'dictionary_version': index['dictionary_version'], 'processed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'snapshot': a.snapshot, 'records': len(jobs), 'requirements_denominator': len(eligible), 'dictionary_terms': len(terms), 'observed_requirement_terms': len(all_req), 'jobs_with_requirement_technology': sum(bool(index['jobs'][j['id']].get('requirement')) for j in eligible), 'category_coverage': [{'category': k, 'n': len(v), 'denominator': len(eligible)} for k, v in sorted(categories.items(), key=lambda kv: -len(kv[1]))], 'tables': rows, 'city_coverage': cities}
    (out / 'technology-analysis.json').write_text(json.dumps(summary, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    lines = ['# 技术需求基线与后续观测', '', f'采集截面：{a.snapshot}。以下为保存的官方 JD 文本提及，不是全国招聘人数、必须同时掌握的清单或技术增长率。', '', f"共 {len(jobs):,} 条记录，{len(eligible):,} 条独立资格要求；原子技术词典 {len(terms):,} 项，本截面资格段检出 {len(all_req):,} 项。词典版本：`{index['dictionary_version']}`。", '', '## 从合并标签到可跟踪的技术点', '', '旧标签继续保留，新增统计分别记录 LangChain、LangGraph 等原子项。别名合并到同一技术；不同产品不再因同属一组就自动互相命中。职责、独立资格、全文分别计数，不能混用分母。全文中的提及可能来自公司介绍；资格中的提及也可能是优先或多选一，需查看证据原句。', '', '## 资格要求提及较多的技术', '', '|技术|分类|提及岗位|可用资格分母|占比|', '|---|---|---:|---:|---:|']
    for r in all_req[:30]:
        lines.append(f"|{r['technology']}|{r['category_label']}|{r['n']:,}|{r['denominator']:,}|{r['pct']:.2f}%|")
    lines += ['', '职位数会受雇主采集体量影响。全量CSV额外给出提及雇主数，以及字段内至少有5条可用记录的雇主均权提及率；每家公司先算自身占比再等权平均。共同公司仍可能存在职位构成变化，不能直接当全国份额。']
    lines += ['', '## 四方向关键技术对照', '', '下表为技术选择示例，全部词项（含零检出）在 CSV 中。方向依据职位标题的既有分类，不能解释为全部相关职责。', '', '|技术|' + '|'.join(DIRECTIONS) + '|', '|---|' + '|'.join(['---:'] * 4) + '|']
    chosen = ['Python', 'Java', 'C++', 'Go', 'LangChain', 'LangGraph', 'LlamaIndex', 'MCP', 'RAG', 'PyTorch', 'CUDA', 'Triton language', 'Triton Inference Server', 'Triton unresolved mention', 'vLLM', 'SGLang', 'DeepSpeed', 'Megatron', 'FSDP', 'SFT', 'RLHF', 'DPO', 'PPO', 'GRPO', 'verl']
    for name in chosen:
        term = next((t for t in terms.values() if t['name'].casefold() == name.casefold()), None)
        if term is None:
            term=next((t for t in terms.values() if any(alias.casefold()==name.casefold() for alias in t.get('aliases',[]) if isinstance(alias,str))),None)
        if not term:
            continue
        values = [next(r for r in rows if r['technology_id'] == term['id'] and r['scope'] == d and r['field'] == 'requirement') for d in DIRECTIONS]
        lines.append('|' + name + '|' + '|'.join(f"{r['n']}/{r['denominator']} ({r['pct']:.1f}%)" if r['pct'] is not None else '无可用分母' for r in values) + '|')
    lines += ['', '## 拆分技术后能看见什么', '']
    for scope, left, right in [('AI应用/Agent开发', 'LangChain', 'LangGraph'), ('AI Infra', 'CUDA', 'Triton')]:
        pair = [next((t for t in terms.values() if t['name'].casefold() == name.casefold()), None) for name in [left, right]]
        if not all(pair): continue
        ids_pair = [t['id'] for t in pair]
        cohort = [j for j in eligible if j['title_direction'] == scope]
        both = sum(all(t in index['jobs'][j['id']]['requirement'] for t in ids_pair) for j in cohort)
        values = [next(r for r in rows if r['scope'] == scope and r['field'] == 'requirement' and r['technology_id'] == t) for t in ids_pair]
        if not cohort: continue
        lines.append(f"{scope}的{len(cohort)}条可用资格要求中，{left}提及{values[0]['n']}条（{values[0]['pct']:.1f}%），{right}提及{values[1]['n']}条（{values[1]['pct']:.1f}%），共同出现{both}条，至少其一{values[0]['n']+values[1]['n']-both}条。合并标签会隐藏两项的覆盖差异；共同出现也可能是‘至少一种’或背景说明，须结合原句判断。")
        lines.append(f"上述两项分别覆盖{values[0]['employers_with_mentions']}与{values[1]['employers_with_mentions']}家雇主。样本量和公司构成会影响职位加权比率，后续应同时跟踪公司均权和共同职位序列。")
    triton_terms=[t for t in terms.values() if 'triton' in t['name'].casefold()]
    infra=[j for j in eligible if j['title_direction']=='AI Infra']
    if triton_terms and infra:
        fragments=[]
        for term in triton_terms:
            n=sum(term['id'] in index['jobs'][j['id']]['requirement'] for j in infra)
            fragments.append(term['name']+' '+str(n)+'条')
        union=sum(any(t['id'] in index['jobs'][j['id']]['requirement'] for t in triton_terms) for j in infra)
        lines.append('AI Infra资格段的Triton相关项分别为：'+'；'.join(fragments)+f'，任一相关项的岗位并集为{union}/{len(infra)}。裸写Triton的记录保留为未消歧提及，不能全部当编程语言或推理服务器；一个岗位也可能同时提到多个具体项。')
    lines += ['', '## 如何解释以后出现的变化', '', '- 先核对两期的公司、渠道、城市范围、抓取完整度和词典版本，使用同一词典重提取两期文本。', '- 同时查看全样本占比、共同公司占比、共同职位占比，以及同一职位资格段新增/移除的技术。占比差用百分点，不能只比较检出条数。', '- 新增广告、未重现广告、原文更新分别报告。一次采集未出现某 ID 不能确认岗位关闭。', '- 保存 source_job_id、抓取时间、原文哈希、词典哈希和运行日志。用 source_job_id 对齐广告，不能用标题近似匹配伪造同岗变化。', '- 单期统计表不能判断 LangChain、Python 或任何技术正在增长或下降；需读取真实登记簿并运行跨期工具。', '', '## 覆盖和维护边界', '', '自然语言不能靠有限词典保证“全部技术”零遗漏。本包将已审核的词典命中与未收录候选队列分开保存；候选只有复核并发布词典新版本后才进入正式统计。更新词典后应重算历史各期，而不是把新增词项的检出当市场增长。', '', '完整输出：`原子技术_方向_字段_全表.csv`、`城市_四方向_覆盖.csv`、`technology-analysis.json`。证据与候选队列见 data/technology/；分期工具和指南见 tools/ 与 MAINTENANCE.md。']
    text = '\n'.join(lines) + '\n'
    (out / '技术需求基线与维护.md').write_text(text, encoding='utf-8')
    # Basic standalone HTML, with escaped source text; Markdown is the analysis source.
    blocks, table = [], []
    def flush():
        if table:
            head, *body = table
            blocks.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+html.escape(c.strip())+'</th>' for c in head.strip('|').split('|')) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+html.escape(c.strip())+'</td>' for c in row.strip('|').split('|'))+'</tr>' for row in body if not row.startswith('|---')) + '</tbody></table></div>')
            table.clear()
    for line in lines:
        if line.startswith('|'):
            table.append(line)
            continue
        flush()
        if line.startswith('# '): blocks.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('## '): blocks.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line: blocks.append('<p>'+html.escape(line)+'</p>')
    flush()
    assets=a.catalog.resolve().parent.parent/'assets';asset_links='';back=''
    if assets.is_dir():
        try:
            relative=os.path.relpath(assets,out.resolve()).replace('\\','/')
            asset_links='<script src="'+html.escape(relative+'/theme-init.js',quote=True)+'"></script><link rel="stylesheet" href="'+html.escape(relative+'/app.css',quote=True)+'">'
            back='<p><a href="'+html.escape(relative+'/../index.html#view=research',quote=True)+'">返回研究结论</a></p>'
        except ValueError:pass
    (out / '技术需求基线与维护.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>技术需求基线与维护</title>'+asset_links+'<style>body{font-family:system-ui,"Microsoft YaHei",sans-serif}.standalone-report{max-width:1400px;width:calc(100% - 32px);margin:28px auto;padding:28px;background:var(--panel,#fff);border:1px solid var(--line,#d6dded);border-radius:14px}.standalone-report p{max-width:90ch}.standalone-report h2{margin-top:32px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%}th,td{padding:10px;border-bottom:1px solid var(--line,#d6dded);text-align:left;white-space:nowrap}@media(max-width:600px){.standalone-report{padding:16px}}</style><body><main class="standalone-report">'+back+''.join(blocks)+'</main></body></html>', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in ['tables', 'city_coverage', 'category_coverage']}, ensure_ascii=False))

if __name__ == '__main__':
    main()
