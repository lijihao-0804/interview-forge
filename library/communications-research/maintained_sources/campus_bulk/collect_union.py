import requests, pathlib, json, hashlib, time, re, html, datetime, zoneinfo, collections
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
archive=base/'source_archive'; archive.mkdir(parents=True,exist_ok=True)
url='https://fe.zhaopin.com/grace/api/dsc/search-job-list'
headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Origin':'https://zglt.zhaopin.com','Referer':'https://zglt.zhaopin.com/scjobs/index.html','Content-Type':'application/json'}
s=requests.Session(); allrows=[]; manifest=[]; pagesize=100; total_pages=None; total_num=None
for page in range(1,200):
 body={'orgNumbers':['105347'],'jobSource':2,'pageIndex':page,'pageSize':pagesize}
 r=s.post(url,json=body,headers=headers,timeout=45)
 if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code} page {page}: {r.text[:300]}')
 try: d=r.json()
 except Exception: raise RuntimeError(f'Non-JSON page {page}, content type={r.headers.get("content-type")}, body={r.text[:300]}')
 if d.get('code')!=200 or not isinstance(d.get('data'),dict): raise RuntimeError(f'API failure page {page}: {str(d)[:500]}')
 raw=r.content; fname=f'union_zhaopin_api_page_{page:03d}.json'; (archive/fname).write_bytes(raw)
 data=d['data']; rows=data.get('jobList',[]); allrows.extend(rows)
 pi=data.get('pageInfo',{}); total_pages=pi.get('totalPage',page); total_num=pi.get('totalNum',len(allrows))
 manifest.append({'name':fname,'url':url,'method':'POST','body':body,'http_status':r.status_code,'api_code':d.get('code'),'response_rows':len(rows),'page_index':page,'page_count':total_pages,'reported_total':total_num,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
 print(f'page {page}/{total_pages} rows={len(rows)} total={total_num} bytes={len(raw)}')
 if page>=total_pages or not rows: break
 time.sleep(0.15)
else: raise RuntimeError('pagination safety ceiling exceeded')

def plain(s):
 s=html.unescape(str(s or ''))
 s=re.sub(r'<br\s*/?>','\n',s,flags=re.I); s=re.sub(r'</(?:p|li|div|tr)>','\n',s,flags=re.I)
 s=re.sub(r'<[^>]+>','',s)
 s=s.replace('\xa0',' ').replace('\r','')
 s=re.sub(r'\n[ \t]+','\n',s); s=re.sub(r'\n{3,}','\n\n',s)
 return s.strip()
def extract_sections(s):
 s=plain(s)
 m=re.search(r'【\s*任职要求\s*】|任职要求\s*[:：]',s)
 if not m:return s,''
 return s[:m.start()].strip(),s[m.end():].strip()
def major_field(req, need):
 need=(need or '').strip()
 # capture requirement text in the major bullet; preserve the source phrase
 lines=req.splitlines()
 hits=[]
 for line in lines:
  if re.search(r'专业(?:要求|条件|背景)\s*[:：]',line):
   hits.append(line.strip())
 if need: hits.insert(0,'岗位字段 needMajor：'+need)
 return '\n'.join(dict.fromkeys(hits))
def kind(major):
 s=major.lower().replace(' ','')
 direct=any(x in s for x in ['通信工程','通信类','通信专业','通信学','信息与通信','信息通信类','信息通信工程','通讯类','通讯工程','通讯专业'])
 adjacent=any(x in s for x in ['电子信息','电子与信息','电子信息工程','电子科学与技术'])
 if direct:return 'direct'
 if adjacent:return 'adjacent'
 return 'excluded'
def status(text):
 if '2026届未就业' in text or '2026届未就业毕业生' in text:return '2027届；2026届未就业毕业生可投'
 if '2027届' in text:return '2027届'
 if '应届毕业生' in text:return '校招应届生（未明确毕业年份）'
 return '2027届联通校招批次；岗位正文未写明确毕业年份'
retrieved=datetime.datetime.now(zoneinfo.ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
records=[]; counts=collections.Counter(); duplicate_ids=0; seen=set()
for pageno,row in enumerate(allrows,1):
 job=row.get('job') or {}; company=row.get('company') or {}
 source_id=job.get('jobNumber') or str(job.get('id') or '')
 if not source_id: continue
 key=(company.get('campusOrgName',''),source_id)
 if key in seen:duplicate_ids+=1; continue
 seen.add(key)
 full=plain(job.get('detail',''))
 duties,reqs=extract_sections(full)
 major=major_field(reqs,job.get('needMajor'))
 rk=kind(major)
 counts[rk]+=1
 if rk=='excluded':continue
 page_for_row=(pageno-1)//pagesize+1
 fname=f'source_archive/union_zhaopin_api_page_{page_for_row:03d}.json'
 records.append({
  'id':f'unicom_105347_{source_id}',
  'company':company.get('campusOrgName') or company.get('slaveDisplayOrgName') or '中国联通',
  'parent_group':'中国联合网络通信集团有限公司',
  'title':job.get('title') or '',
  'source_job_id':source_id,
  'url':job.get('url') or '',
  'city':job.get('cityName') or job.get('address') or '',
  'description':duties,
  'requirements':reqs,
  'full_text':full,
  'major_raw':major,
  'degree_raw':job.get('minEducationName') or '',
  'experience_raw':job.get('workingExpName') or '',
  'posted_date':None,
  'retrieved_at':retrieved,
  'batch':'中国联通2027校园招聘（智联招聘campaign 105347）',
  'student_status':status(full),
  'source_kind':'中国联通官方授权智联校园招聘站公开API',
  'row_kind':rk,
  'source_archive':fname
 })
with (base/'records.jsonl').open('w',encoding='utf-8',newline='\n') as f:
 for r in records:f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
(base/'union_download_manifest.json').write_text(json.dumps({'captured_at':retrieved,'listing_page':'https://zglt.zhaopin.com/scjobs/index.html','api':url,'scope':{'orgNumbers':['105347'],'jobSource':2,'pageSize':pagesize},'total_reported':total_num,'pages':manifest,'unique_by_org_and_jobNumber':len(seen),'duplicate_rows_removed':duplicate_ids,'screening':{'direct':counts['direct'],'adjacent':counts['adjacent'],'excluded':counts['excluded']},'records_written':len(records)},ensure_ascii=False,indent=2),encoding='utf-8')
print('DONE total_fetch',len(allrows),'reported',total_num,'unique',len(seen),'dups',duplicate_ids,'kind_counts',dict(counts),'records',len(records))
