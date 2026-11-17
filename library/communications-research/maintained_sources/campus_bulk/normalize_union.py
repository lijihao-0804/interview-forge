import pathlib,json,glob,re,html,datetime,collections
base=pathlib.Path(r'E:\JAVA\AI+agent\笔记\AI就业调研_2026-11-17\专题\通信工程_2026-11-18\campus_bulk')
archive=base/'source_archive'; dl=json.loads((base/'union_download_manifest.json').read_text(encoding='utf-8'))
retrieved=dl['captured_at']; rows=[]
for p in sorted(archive.glob('union_zhaopin_api_page_*.json')):
 d=json.loads(p.read_text(encoding='utf-8-sig')); rows.extend(d.get('data',{}).get('jobList',[]))
def plain(s):
 s=html.unescape(str(s or ''));s=re.sub(r'<br\s*/?>','\n',s,flags=re.I);s=re.sub(r'</(?:p|li|div|tr)>','\n',s,flags=re.I);s=re.sub(r'<[^>]+>','',s);s=s.replace('\xa0',' ').replace('\r','');s=re.sub(r'\n[ \t]+','\n',s);s=re.sub(r'\n{3,}','\n\n',s);return s.strip()
def section(full):
 m=re.search(r'【\s*任职要求\s*】|任职要求\s*[:：]',full)
 return (full[:m.start()].strip(),full[m.end():].strip()) if m else (full,'')
def major_field(req,need):
 hits=[ln.strip() for ln in req.splitlines() if re.search(r'专业(?:要求|条件|背景)\s*[:：]',ln)]
 need=str(need or '').strip()
 if need:hits.insert(0,'岗位字段 needMajor：'+need)
 return '\n'.join(dict.fromkeys(hits))
def classify(major):
 s=major.replace(' ','')
 if '通信' in s:return ('direct','岗位专业条件明确列出通信工程/通信类/通信专业或通信专业名称')
 if any(x in s for x in ['电子信息','电子科学与技术','电子与信息','电子信息工程']):return ('adjacent','专业条件仅列电子信息/相关电子类，雇主需确认是否接受通信工程')
 return ('excluded','专业条件未明确列出通信类或电子信息类')
def student_status(full):
 if '2026届未就业' in full:return '2027届；2026届未就业毕业生可投'
 if '2027届' in full:return '2027届'
 if '应届毕业生' in full:return '校招应届生（岗位正文未明确毕业年份）'
 return '中国联通2027校招批次；岗位正文未写明确毕业年份'
allres=[];records=[];seen=set();dups=0;counts=collections.Counter()
for ix,row in enumerate(rows):
 job=row.get('job') or {};co=row.get('company') or {};sid=str(job.get('jobNumber') or job.get('id') or '')
 if not sid:continue
 if sid in seen:dups+=1;continue
 seen.add(sid)
 full=plain(job.get('detail',''));duties,reqs=section(full);major=major_field(reqs,job.get('needMajor'));rk,reason=classify(major);counts[rk]+=1
 unit=co.get('campusOrgName') or co.get('slaveDisplayOrgName') or '中国联通'
 page=((ix)//100)+1
 arch=f'source_archive/union_zhaopin_api_page_{page:03d}.json'
 screen={'source_job_id':sid,'company':unit,'hiring_unit':unit,'title':job.get('title') or '','major_raw':major,'row_kind':rk,'screen_reason':reason,'source_archive':arch}
 allres.append(screen)
 if rk=='excluded':continue
 records.append({'id':f'unicom_{sid}','company':unit,'hiring_unit':unit,'parent_group':'中国联合网络通信集团有限公司（中国联通集团）','title':job.get('title') or '','source_job_id':sid,'url':job.get('url') or '', 'city':job.get('cityName') or job.get('address') or '', 'description':duties,'requirements':reqs,'full_text':full,'major_raw':major,'degree_raw':job.get('minEducationName') or '', 'experience_raw':job.get('workingExpName') or '', 'posted_date':None,'application_deadline':None,'retrieved_at':retrieved,'batch':'中国联通2027校园招聘（智联招聘campaign 105347）','student_status':student_status(full),'source_kind':'中国联通官方授权智联校园招聘站公开API','row_kind':rk,'source_archive':arch})
(base/'union_records.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in records),encoding='utf-8')
(base/'union_screening_results.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in allres),encoding='utf-8')
print('raw_rows',len(rows),'unique_jobIDs',len(seen),'dups',dups,'screens',dict(counts),'relevant',len(records),'sample direct')
for x in [r for r in records if r['row_kind']=='direct'][:8]:print(x['company'],x['title'],x['major_raw'])
