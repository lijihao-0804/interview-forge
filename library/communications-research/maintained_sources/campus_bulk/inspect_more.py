import pathlib,re
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\union_zhaopin_mjobs_js.js');t=p.read_text(encoding='utf-8')
for pat in ['dscGetJobDetail','modifiedTime','publishedTime','publishTime']:
 print('\n',pat)
 for m in list(re.finditer(pat,t,re.I))[:10]:print(t[max(0,m.start()-400):m.start()+700])
