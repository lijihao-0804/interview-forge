import pathlib,re,html,json,requests
b=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive')
for nm in ['zte_mokahr.html','fiberhome_mokahr.html']:
 t=(b/nm).read_text(encoding='utf-8',errors='replace')
 print('\nPAGE',nm)
 for pat in [r'<script[^>]+src=["\']([^"\']+)',r'<script[^>]*id=["\']([^"\']+)["\'][^>]*>(.*?)</script>',r'window\.[A-Za-z_$][\w$]*\s*=']:
  hits=re.findall(pat,t,re.I|re.S)
  print('PAT',pat,'n',len(hits))
  if pat.startswith('<script[^>]*id'):print([(x[0],len(x[1]),x[1][:150]) for x in hits[:5]])
  elif 'src' in pat:print(hits[:10])
  else:print(hits[:20])
 print('body around setup',t.find('window.__'))
print('\nJS API endpoint strings')
urls=['https://static-ats.mokahr.com/recruitment-web-client/javascripts/recruitmentWeb-20261104-1624-f8380-release.js','https://static-ats.mokahr.com/recruitment-web-client/javascripts/initial-d0540dff6f0a85d6fed2eeaa05519b92.js']
s=requests.Session();s.headers['User-Agent']='Mozilla/5.0'
for url in urls:
 r=s.get(url,timeout=40); print('download',r.status_code,len(r.content));name='mokahr_'+url.rsplit('/',1)[-1]; (b/name).write_bytes(r.content); t=r.text
 patterns=sorted(set(re.findall(r'["\']([^"\']*/api/[^"\']{0,150})["\']',t,re.I)))
 print('api patterns',len(patterns));print('\n'.join(patterns[:100]))
 for term in ['jobs','search','campus-recruitment','job-list']:
  print('\nterm',term)
  for m in list(re.finditer(term,t,re.I))[:5]:print(t[max(0,m.start()-100):m.start()+200])
