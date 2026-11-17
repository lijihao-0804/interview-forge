import pathlib,re
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\mokahr_recruitmentWeb-20261104-1624-f8380-release.js')
t=p.read_text(encoding='utf-8')
for term in ['/api/outer/ats-apply/website/jobs/v2','/api/outer/ats-apply/website/job','/api/outer/ats-apply/website/settings/jobs','/api/outer/ats-apply/website/jobs/v2/filterFieldsAggregations']:
 print('\nTERM',term,'count',t.count(term))
 for m in list(re.finditer(re.escape(term),t))[:10]:print(t[max(0,m.start()-700):m.start()+1200])
