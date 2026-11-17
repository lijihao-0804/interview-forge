import pathlib,json,collections
p=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk\source_archive\sd_union_jobs_data_js.js')
t=p.read_text(encoding='utf-8');obj=json.JSONDecoder().raw_decode(t[t.index('=')+1:].lstrip())[0]
all=[]
for org,g in obj['jobsByOrg'].items():
 a=g.get('all',[]); print(org,'all',len(a),'branch_sum',sum(map(len,g.get('byBranch',{}).values())))
 all+=a
print('sum_all',len(all),'stats',obj['stats'])
for field in ['iguopinId','zhaopinNumber']:
 print(field,'present',sum(bool(j.get(field)) for j in all),'uniq',len({j.get(field) for j in all if j.get(field)}))
print('titles',collections.Counter(j['title'] for j in all).most_common(10))
for j in all[:4]:print(j['unit'],j['title'],j.get('iguopinId'),j.get('zhaopinNumber'),j['description'][-400:])
