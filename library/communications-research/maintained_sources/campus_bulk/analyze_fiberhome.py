import json,pathlib,re,collections
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\fiberhome_rendered_details.json')
raw=p.read_text(encoding='utf-8-sig'); d=json.loads(raw)
if isinstance(d,str): d=json.loads(d)
print('size',p.stat().st_size,'rows',len(d))
for x in d[:12]:
 text=x['visible_text']; m=re.search(r'任职要求\s*\n([\s\S]*?)(?:\n职位信息|\n职位名称|\n工作地点|\n申请职位)',text)
 req=m.group(1) if m else ''
 majors=[ln.strip() for ln in req.splitlines() if '专业' in ln]
 print(x['source_job_id'],x['title'],x['posted_date'],'|',' / '.join(majors)[:260])
print('categories',collections.Counter(x['category'] for x in d))
