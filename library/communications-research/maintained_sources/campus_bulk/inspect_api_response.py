import json,pathlib
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\union_api_probe_105347_2.json')
d=json.loads(p.read_text(encoding='utf-8')); print(d.keys(),d['data']['pageInfo']); print(json.dumps(d['data']['jobList'][0],ensure_ascii=False,indent=2)[:10000])
