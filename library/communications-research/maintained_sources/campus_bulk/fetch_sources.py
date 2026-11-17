import requests, pathlib, hashlib, re, json
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
urls={
 'union_zhaopin_home':'https://zglt.zhaopin.com/mjobs/',
 'union_zhaopin_campus':'https://zglt.zhaopin.com/scjobs/index.html',
 'sd_union_2027_home':'https://sdlt.kongxuan.com/index.html',
 'zte_mokahr':'https://app.mokahr.com/campus-recruitment/zte/46903',
 'fiberhome_mokahr':'https://app.mokahr.com/campus-recruitment/whfhtx/73922',
}
s=requests.Session(); s.headers['User-Agent']='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36'
manifest=[]
for name,url in urls.items():
 try:
  r=s.get(url,timeout=30); print(name,r.status_code,r.url,len(r.content),r.headers.get('content-type'))
  ext='.html' if 'html' in r.headers.get('content-type','') or '<html' in r.text[:1000].lower() else '.bin'
  path=base/'source_archive'/f'{name}{ext}'; path.write_bytes(r.content)
  manifest.append({'name':name,'url':url,'resolved_url':r.url,'status':r.status_code,'path':str(path.relative_to(base)),'sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content),'content_type':r.headers.get('content-type')})
  if name in ('union_zhaopin_home','union_zhaopin_campus','sd_union_2027_home'):
   print(' scripts:',re.findall(r'<script[^>]+src=["\']([^"\']+)',r.text,re.I)[:40])
 except Exception as e: print('ERR',name,repr(e))
(base/'source_archive'/'initial_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
