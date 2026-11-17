import pathlib,json
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
t=(base/'source_archive'/'sd_union_jobs_data_js.js').read_text(encoding='utf-8'); obj=json.JSONDecoder().raw_decode(t[t.index('=')+1:].lstrip())[0]
for org,groups in obj['jobsByOrg'].items():
 print('ORG',org,'GROUP KEYS',groups.keys())
 for k,v in groups.items():
  print('group',k,'type',type(v).__name__,'len',len(v) if hasattr(v,'__len__') else '-')
  if isinstance(v,list):
   print('sample',json.dumps(v[:1],ensure_ascii=False)[:2500])
  elif isinstance(v,dict):
   for kk,vv in list(v.items())[:2]:print(' branch',kk,'len',len(vv),'sample',json.dumps(vv[:1],ensure_ascii=False)[:2000])
 break
