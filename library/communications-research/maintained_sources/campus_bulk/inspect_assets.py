import requests,pathlib,hashlib,json,re,urllib.parse
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
assets={
'union_zhaopin_mjobs_js':'https://zglt.zhaopin.com/assets/mjobs-8682bb55.js',
'union_zhaopin_scjobs_js':'https://zglt.zhaopin.com/assets/scjobs-b1515ebc.js',
'sd_union_jobs_data_js':'https://sdlt.kongxuan.com/js/data/jobs-data.js?v=20260928q',
'sd_union_job_description_js':'https://sdlt.kongxuan.com/js/job-description.js?v=20260928e',
'sd_union_getJob_js':'https://sdlt.kongxuan.com/js/module/getJob.js?v=20260928z',
}
for name,url in assets.items():
 r=s.get(url,timeout=30); print('\nASSET',name,r.status_code,len(r.content),r.headers.get('content-type'))
 p=base/'source_archive'/f'{name}.js'; p.write_bytes(r.content)
 print('sha256',hashlib.sha256(r.content).hexdigest())
 txt=r.text
 for pat in [r'https?://[^"\'` ]+',r'/(?:api|interface|job|jobs|recruit)[^"\'` ]{0,150}',r'[A-Za-z0-9_]*(?:jobs?|positions?|jobList|search)[A-Za-z0-9_]*']:
  hits=re.findall(pat,txt,re.I)
  if hits: print('hits',pat, list(dict.fromkeys(hits))[:30])
 print(txt[:800] if len(txt)<1000 else txt[:600])
