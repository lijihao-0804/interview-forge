import requests,json,pathlib
h={'User-Agent':'Mozilla/5.0','Origin':'https://zglt.zhaopin.com','Referer':'https://zglt.zhaopin.com/scjobs/index.html','Content-Type':'application/json'}
url='https://fe.zhaopin.com/grace/api/dsc/get-search-aggregation'
for facets in [['SOU_COMPANY_ID'],['SOU_COMPANY_ID','JD_WORK_CITY_CODE']]:
 body={'orgNumber':'105347','jobSource':2,'facetFields':facets}
 r=requests.post(url,json=body,headers=h,timeout=30); print(r.status_code,len(r.content),r.text[:300]);
 d=r.json();p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive')/('union_aggregation_'+str(len(facets))+'.json');p.write_bytes(r.content)
 if d.get('data'):
  m=d['data'].get('itemMap') or {}
  for f,v in m.items():
   if isinstance(v,dict):print(f,'total',sum(x.get('count',0) for xs in v.values() if isinstance(xs,list) for x in xs),'keys',len(v))
   elif isinstance(v,list):print(f,'total',sum(x.get('count',0) for x in v),'n',len(v),'top',[(x.get('name'),x.get('count')) for x in v[:5]])
