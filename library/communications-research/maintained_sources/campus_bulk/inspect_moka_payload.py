import pathlib,re
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\mokahr_recruitmentWeb-20261104-1624-f8380-release.js');t=p.read_text(encoding='utf-8')
for term in ['isCampusJob:x,departmentIds','function fetchJobList','UPDATE_JOBLIST,payload','jobHireMode','getSiteType()']:
 print('\nTERM',term)
 for m in list(re.finditer(re.escape(term),t))[:5]:print(t[max(0,m.start()-2200):m.start()+1300])
