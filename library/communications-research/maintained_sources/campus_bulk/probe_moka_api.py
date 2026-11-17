import requests,json,pathlib
h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Origin':'https://app.mokahr.com','Referer':'https://app.mokahr.com/campus-recruitment/zte/46903','Content-Type':'application/json'}
url='https://app.mokahr.com/api/outer/ats-apply/website/jobs/v2'
for org,site,ref in [('zte',46903,'https://app.mokahr.com/campus-recruitment/zte/46903'),('whfhtx',73922,'https://app.mokahr.com/campus-recruitment/whfhtx/73922')]:
 body={'orgId':org,'siteId':site,'limit':100,'offset':0,'needStat':True,'isCampusJob':True,'site':'camp','locale':'zh-CN'}
 r=requests.post(url,json=body,headers={**h,'Referer':ref},timeout=45);print(org,r.status_code,len(r.content),r.headers.get('content-type'),r.text[:400])
 if r.status_code==200:
  try:
   d=r.json();print('keys',d.keys()); print('total?',d.get('total'),d.get('count'),d.get('jobCount'), 'list',len(d.get('data',[])) if isinstance(d.get('data'),list) else type(d.get('data')).__name__);print(json.dumps(d,ensure_ascii=False)[:1200]);
   pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive'/f'{org}_jobs_probe.json').write_bytes(r.content)
  except Exception as e:print('json err',repr(e))
