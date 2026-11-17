import pathlib,re,json
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
for fn in ['union_zhaopin_mjobs_js.js','union_zhaopin_scjobs_js.js']:
 t=(base/'source_archive'/fn).read_text(encoding='utf-8')
 print('\n',fn,'TAIL\n',t[-1600:])
t=(base/'source_archive'/'sd_union_jobs_data_js.js').read_text(encoding='utf-8')
i=t.index('=')+1
obj,idx=json.JSONDecoder().raw_decode(t[i:].lstrip())
print('\nSD keys:',obj.keys(),'orgs',len(obj.get('orgs',[])))
for k,v in obj.items():
 print('key',k,'type',type(v).__name__,'len',len(v) if hasattr(v,'__len__') else '-')
 if isinstance(v,list) and v: print('sample',json.dumps(v[0],ensure_ascii=False)[:3000])
 if isinstance(v,dict):
  print('subkeys',list(v)[:10])
  for kk,vv in v.items():
   if isinstance(vv,list): print('sample',kk,len(vv),json.dumps(vv[0],ensure_ascii=False)[:1600] if vv else '')
