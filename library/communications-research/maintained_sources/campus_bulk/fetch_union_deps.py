import requests,pathlib,hashlib,re
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
s=requests.Session();s.headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
for name in ['cms-data-41c20234.js','index-8c6c9b6f.js','index-e79edb12.js']:
 url='https://zglt.zhaopin.com/assets/'+name
 r=s.get(url,timeout=30); print(name,r.status_code,len(r.content),r.headers.get('content-type'))
 p=base/'source_archive'/('union_zhaopin_'+name);p.write_bytes(r.content)
 print('sha',hashlib.sha256(r.content).hexdigest())
 t=r.text
 for key in ['dscSearchJobList','dscGetSearchAggregation','api','https://','jobSource']:
  positions=[m.start() for m in re.finditer(re.escape(key),t,re.I)]
  if positions:
   print(key, len(positions))
   for i in positions[:4]:print(t[max(i-150,0):i+350])
