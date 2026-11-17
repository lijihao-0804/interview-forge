"""Public employer JD archives, China-filtered where the official site supports it.
No applications, accounts, fingerprint alterations or challenge bypass.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from job_common_v2 import ROOT,now,plain,hits,digest,archive,summary,split_body

OUT=ROOT/'evidence'; PROBE=ROOT/'analysis'/'foreign_probe'
lock=threading.Lock();last=0.0
def request(method,url,**kwargs):
    global last
    with lock:
        wait=.22-(time.monotonic()-last)
        if wait>0:time.sleep(wait)
        last=time.monotonic()
    headers=dict(kwargs.pop('headers',{}) or {});headers.setdefault('Accept-Encoding','gzip, deflate')
    r=requests.request(method,url,timeout=40,headers=headers,**kwargs)
    if r.status_code==429:raise RuntimeError('HTTP429; backing off rather than retrying this employer in this run')
    r.raise_for_status();return r

def make(company,slug,ident,title,url,duty,req,raw,locations=None,country=None,category=None,posted=None,parse_status='separate_official_fields',full_body=None):
    duty=plain(duty);req=plain(req);body=plain(full_body) if full_body else duty+'\n\n'+req
    if not body.strip():raise ValueError('Empty job body')
    r=dict(company=company,id=f'{company}-{ident}',source_job_id=str(ident),title=title,url=url,
      location=locations or [],city=locations or [],country=country or '未明示',category=category or '未知',
      posted_date=posted or '未知',date_semantics='雇主返回的发布日期；无明确字段则未知',retrieved_at=now(),access_date=now()[:10],
      description=duty,requirements=req,full_text=body,requirements_parse_status=parse_status,
      detail_status='full' if duty and req else 'full_combined' if len(body)>100 else 'partial',
      experience='未知',degree=[],salary='未结构化披露',source_type='雇主官方公开招聘网站/API；JD原始字段已本地存档',
      skills_in_requirement=hits(req),skills_in_responsibility=hits(duty),text_sha256=digest(body),
      summary=summary(title,duty,req),availability='访问时公开返回；未确认预算或剩余HC')
    r['archive_json']=archive(slug,ident,r,raw)
    return r

def save(slug,rows,audit):
    (OUT/(slug+'_expanded_jobs.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    audit['records']=len(rows);audit['full_separate']=sum(x['detail_status']=='full' for x in rows);audit['full_combined']=sum(x['detail_status']=='full_combined' for x in rows)
    return audit

def workday(company,tenant,host,site):
    start=now();base=f'https://{host}/wday/cxs/{tenant}/{site}';listing=[];logs=[];errors=[]
    first=request('POST',base+'/jobs',json={'appliedFacets':{},'limit':20,'offset':0,'searchText':'China'}).json()
    total=first.get('total',0)
    listing.extend(first.get('jobPostings',[]));logs.append({'offset':0,'returned':len(listing),'reported':total})
    for offset in range(20,total,20):
        d=request('POST',base+'/jobs',json={'appliedFacets':{},'limit':20,'offset':offset,'searchText':'China'}).json()
        v=d.get('jobPostings',[]);listing.extend(v);logs.append({'offset':offset,'returned':len(v),'reported':d.get('total')})
    malformed=[x for x in listing if not x.get('externalPath')]
    errors.extend({'issue':'list record has no externalPath','record':x} for x in malformed)
    unique={x['externalPath']:x for x in listing if x.get('externalPath')};rows=[]
    def detail(x):
        path=x['externalPath'];j=request('GET',base+path).json();d=j['jobPostingInfo']
        body=d.get('jobDescription','');duty,req,status=split_body(body)
        locs=[d.get('location','')]+list(d.get('additionalLocations') or [])
        country=d.get('country',{});country=country.get('descriptor','') if isinstance(country,dict) else country
        return make(company,tenant,d.get('jobReqId') or x.get('bulletFields',[''])[0] or path.split('_')[-1],d.get('title') or x['title'],f'https://{host}/{site}'+path,duty,req,j,locs,country,d.get('jobFamily') or '未知',d.get('startDate'),status,body)
    with cf.ThreadPoolExecutor(max_workers=4) as p:
        futures={p.submit(detail,x):x for x in unique.values()}
        for f in cf.as_completed(futures):
            try:rows.append(f.result())
            except Exception as e:errors.append({'path':futures[f]['externalPath'],'error':str(e)})
    # Keep ambiguous / multi-country rows, label geography later. Do not pretend text search = precise country census.
    return save(tenant,rows,{'company':company,'started_at':start,'finished_at':now(),'scope':'官方Workday searchText=China；保留详情国家与多地点，不保证全球中国岗位穷尽','reported_list_total':total,'list_rows':len(listing),'unique_list_paths':len(unique),'pages':logs,'errors':errors})

def amazon():
    start=now();rows=[];logs=[];errors=[];raw=[]
    u='https://www.amazon.jobs/en/search.json';params={'offset':0,'result_limit':100,'normalized_country_code[]':'CHN'}
    first=request('GET',u,params=params).json();total=first['hits'];raw.extend(first.get('jobs',[]));logs.append({'offset':0,'rows':len(raw),'reported':total})
    for offset in range(100,total,100):
        j=request('GET',u,params={**params,'offset':offset}).json();v=j.get('jobs',[]);raw.extend(v);logs.append({'offset':offset,'rows':len(v),'reported':j.get('hits')})
    unique={str(x.get('id_icims') or x.get('id') or x.get('job_path')):x for x in raw}
    for ident,x in unique.items():
        try:
            req='Basic qualifications\n'+plain(x.get('basic_qualifications'))+'\n\nPreferred qualifications\n'+plain(x.get('preferred_qualifications'))
            url=urljoin('https://www.amazon.jobs',x.get('job_path') or '/en/jobs/'+ident)
            rows.append(make('Amazon','amazon',ident,x.get('title','未知'),url,x.get('description',''),req,x,[x.get('location') or x.get('city')],x.get('country_code'),x.get('job_category'),x.get('posted_date')))
        except Exception as e:errors.append({'id':ident,'error':str(e)})
    return save('amazon',rows,{'company':'Amazon','started_at':start,'finished_at':now(),'scope':'官方normalized_country_code[]=CHN分页；要求国家字段核对','reported_list_total':total,'list_rows':len(raw),'pages':logs,'errors':errors})

def google_data(text):
    soup=BeautifulSoup(text,'html.parser')
    for sc in soup.select('script'):
        t=sc.get_text()
        if "key: 'ds:1'" in t and 'data:' in t:
            m=re.search(r'data:(.*), sideChannel:',t,re.S)
            if m:return json.loads(m.group(1)),soup
    raise ValueError('No public ds:1 job list data')
def google():
    start=now();raw=[];logs=[];urls={};errors=[]
    first=request('GET','https://www.google.com/about/careers/applications/jobs/results/',params={'location':'China','page':1})
    data,soup=google_data(first.text);total=data[2];pages=(total+19)//20
    for page in range(1,pages+1):
        if page>1:data,soup=google_data(request('GET','https://www.google.com/about/careers/applications/jobs/results/',params={'location':'China','page':page}).text)
        raw.extend(data[0]);logs.append({'page':page,'rows':len(data[0]),'reported':data[2]})
        for a in soup.select('a[href]'):
            h=a['href'];m=re.search(r'jobs/results/(\d+)-',h)
            if m:urls[m.group(1)]=urljoin('https://www.google.com/about/careers/applications/',h)
    rows=[]
    for x in {x[0]:x for x in raw}.values():
        try:
            ident=x[0];duty=(x[10][1] or '')+'\n'+(x[3][1] or '');req=x[4][1] or ''
            locs=[v[0] for v in x[9] or []];countries=sorted({v[5] for v in x[9] or [] if len(v)>5})
            rows.append(make('Google','google',ident,x[1],urls.get(ident,'https://www.google.com/about/careers/applications/jobs/results/'+ident),duty,req,x,locs,';'.join(countries),'未知',None))
        except Exception as e:errors.append({'id':x[0],'error':str(e)})
    return save('google',rows,{'company':'Google','started_at':start,'finished_at':now(),'scope':'官方location=China分页；公开HTML内嵌职位原始数据含完整职责与资格','reported_list_total':total,'list_rows':len(raw),'pages':logs,'errors':errors})

def eightfold(company,slug,domain,host):
    start=now();u='https://'+host;rows=[];raw=[];logs=[];errors=[]
    first=request('GET',u+'/api/pcsx/search',params={'domain':domain,'query':'','location':'China','start':0}).json()['data']
    total=first['count'];batch=len(first.get('positions',[])) or 10
    for offset in range(0,total,batch):
        d=first if offset==0 else request('GET',u+'/api/pcsx/search',params={'domain':domain,'query':'','location':'China','start':offset}).json()['data']
        v=d.get('positions',[]);raw.extend(v);logs.append({'start':offset,'rows':len(v),'reported':d.get('count')})
    unique={str(x['id']):x for x in raw}
    def detail(x):
        j=request('GET',u+'/api/pcsx/position_details',params={'domain':domain,'position_id':str(x['id'])}).json();d=j['data']
        body=d.get('jobDescription') or d.get('description') or ''
        duty,req,status=split_body(body)
        return make(company,slug,x['id'],d.get('name') or x['name'],u+(d.get('positionUrl') or x.get('positionUrl') or '/careers/job/'+str(x['id'])),duty,req,j,d.get('locations') or x.get('locations'),None,d.get('department') or x.get('department'),dt.datetime.fromtimestamp(x['postedTs'],dt.timezone.utc).date().isoformat() if x.get('postedTs') else None,status,body)
    with cf.ThreadPoolExecutor(max_workers=3) as p:
        fs={p.submit(detail,x):x for x in unique.values()}
        for f in cf.as_completed(fs):
            try:rows.append(f.result())
            except Exception as e:errors.append({'id':fs[f]['id'],'error':str(e)})
    return save(slug,rows,{'company':company,'started_at':start,'finished_at':now(),'scope':'官方location=China查询，按其reported count分页；保留实际多地点。不是全球岗位全量','reported_list_total':total,'list_rows':len(raw),'pages':logs,'errors':errors})

def main():
    tasks=[('nvidia',lambda:workday('NVIDIA','nvidia','nvidia.wd5.myworkdayjobs.com','NVIDIAExternalCareerSite')),
      ('intel',lambda:workday('Intel','intel','intel.wd1.myworkdayjobs.com','External')),
      ('amazon',amazon),('google',google),
      ('qualcomm',lambda:eightfold('Qualcomm','qualcomm','qualcomm.com','careers.qualcomm.com')),
      ('microsoft',lambda:eightfold('Microsoft','microsoft','microsoft.com','apply.careers.microsoft.com')),
      ('adobe',lambda:workday('Adobe','adobe','adobe.wd5.myworkdayjobs.com','external_experienced'))]
    audit=[]
    for slug,fn in tasks:
        try:d=fn();audit.append(d);print(slug,d.get('records'),len(d.get('errors',[])),flush=True)
        except Exception as e:audit.append({'company':slug,'failed_at':now(),'records':0,'error':str(e)});print(slug,'FAILED',str(e),flush=True)
        (OUT/'foreign_expanded_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Foreign employer collection finished',flush=True)
if __name__=='__main__':main()
