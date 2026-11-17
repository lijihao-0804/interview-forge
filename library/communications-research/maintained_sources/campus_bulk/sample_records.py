import json,pathlib,random,collections
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\records.jsonl')
rs=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
for k in ['direct','adjacent']:
 print('\n',k)
 sub=[r for r in rs if r['row_kind']==k]
 for r in sub[:10]:print(r['company'],r['title'],'|',r['major_raw'][:180])
print('\nstudent status',collections.Counter(r['student_status'] for r in rs))
print('records with no major raw',sum(not r['major_raw'] for r in rs))
