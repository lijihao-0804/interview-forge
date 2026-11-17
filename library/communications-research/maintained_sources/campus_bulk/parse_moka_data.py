import pathlib,re,html,json
from html.parser import HTMLParser
class P(HTMLParser):
 def handle_starttag(self,tag,attrs):
  if tag=='input' and dict(attrs).get('id')=='init-data': self.val=dict(attrs).get('value')
b=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive')
for nm in ['zte_mokahr.html','fiberhome_mokahr.html']:
 p=P();p.feed((b/nm).read_text(encoding='utf-8',errors='replace')); data=json.loads(html.unescape(p.val)); print('\n',nm,data.keys()); print('org',data['org']['id'],data['org']['siteId']); print('top-level types',[(k,type(v).__name__,len(v) if hasattr(v,'__len__') else None) for k,v in data.items()]);
 for k,v in data.items():
  if isinstance(v,list) and v:print(' sample list',k,json.dumps(v[0],ensure_ascii=False)[:1000])
  elif isinstance(v,dict): print(' dictkeys',k,list(v.keys())[:50])
