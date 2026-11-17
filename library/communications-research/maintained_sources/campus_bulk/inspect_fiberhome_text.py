import json,pathlib
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\fiberhome_rendered_details.json');d=json.loads(p.read_text(encoding='utf-8-sig'));d=json.loads(d) if isinstance(d,str) else d
for x in d[:3]:print('\n===',x['title'],'===\n',x['visible_text'][:3000])
