import requests,json,pathlib
url='https://fe.zhaopin.com/grace/api/dsc/search-job-list'
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Origin':'https://zglt.zhaopin.com','Referer':'https://zglt.zhaopin.com/scjobs/index.html','Content-Type':'application/json'}
for org,source in [('105347',2),('105348',2),('105347',1)]:
 body={'orgNumbers':[org],'jobSource':source,'pageIndex':1,'pageSize':10}
 try:
  r=requests.post(url,json=body,headers=h,timeout=30); print(org,source,r.status_code,len(r.content),r.text[:300])
  p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive')/f'union_api_probe_{org}_{source}.json'; p.write_bytes(r.content)
 except Exception as e: print('ERR',repr(e))
