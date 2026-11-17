"""Apple China / AMD China / Arm China, public official structured pages."""
import concurrent.futures as cf
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from collect_foreign_v2 import request,make,save,OUT
from job_common_v2 import now,split_body

def apple_data(text):
    soup=BeautifulSoup(text,'html.parser')
    script=next((x.get_text() for x in soup.select('script') if 'window.__staticRouterHydrationData' in x.get_text()),'')
    m=re.search(r'JSON.parse\(("(?:[^"\\]|\\.)*")\)',script,re.S)
    if not m:raise ValueError('No public Apple page hydration data')
    return json.loads(json.loads(m.group(1)))['loaderData'],soup
def apple():
    start=now();listing=[];logs=[];errors=[];urls={}
    first=request('GET','https://jobs.apple.com/zh-cn/search',params={'location':'china-CHNC','page':1})
    data,soup=apple_data(first.text);initial=data['search'];total=initial['totalRecords'];batch=len(initial['searchResults']) or 20
    for page in range(1,(total+batch-1)//batch+1):
        if page>1:
            for attempt in range(3):
                try:
                    data,soup=apple_data(request('GET','https://jobs.apple.com/zh-cn/search',params={'location':'china-CHNC','page':page}).text)
                    break
                except Exception as e:
                    if '429' in str(e):raise
                    if attempt==2:
                        errors.append({'page':page,'error':str(e)});data=None
                    else:__import__('time').sleep(2+attempt*2)
            if data is None:continue
        d=data['search'];v=d['searchResults'];listing.extend(v);logs.append({'page':page,'rows':len(v),'reported':d['totalRecords']})
        for a in soup.select('a[href]'):
            h=a['href'];m=re.search(r'/details/([^/]+)/',h)
            if m and 'locationPicker' not in h:urls[m.group(1)]=urljoin('https://jobs.apple.com',h)
        (OUT/'apple_list_checkpoint.json').write_text(json.dumps({'total':total,'page':page,'positions':listing,'urls':urls,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
    unique={x['positionId']:x for x in listing};rows=[]
    def detail(x):
        ident=x['positionId'];url=urls.get(ident) or 'https://jobs.apple.com/zh-cn/details/'+ident+'/'+x['transformedPostingTitle']
        d,_=apple_data(request('GET',url).text);j=d['jobDetails']['jobsData']
        req='\n\n'.join(label+'\n'+j[key] for label,key in [('Minimum qualifications / 最低资格','minimumQualifications'),('Preferred qualifications / 优先条件','preferredQualifications')] if j.get(key))
        duty='\n\n'.join(str(j[k]) for k in ['jobSummary','description','responsibilities'] if j.get(k))
        loc=[v.get('name') or v.get('city') for v in j.get('locations',[])];country='；'.join(sorted({v.get('countryName','') for v in j.get('locations',[])}))
        return make('Apple','apple',ident,j.get('postingTitle') or x['postingTitle'],url,duty,req,j,loc,country,j.get('teamNames'),j.get('postingDateMeta') or j.get('postingDate'))
    with cf.ThreadPoolExecutor(max_workers=4) as p:
        fs={p.submit(detail,x):x for x in unique.values()}
        for f in cf.as_completed(fs):
            try:rows.append(f.result())
            except Exception as e:errors.append({'id':fs[f]['positionId'],'error':str(e)})
    return save('apple',rows,{'company':'Apple','started_at':start,'finished_at':now(),'scope':'官网中国内地筛选china-CHNC，逐页公开SSR状态及逐岗详情；含零售等非研发','reported_list_total':total,'list_rows':len(listing),'unique_list_ids':len(unique),'pages':logs,'errors':errors})
def amd():
    start=now();listing=[];logs=[];errors=[];u='https://careers.amd.com/api/jobs';params={'country':'China','limit':100,'page':1,'sortBy':'posted_date','descending':'true'}
    first=request('GET',u,params=params).json();total=first['totalCount'];batch=100
    for page in range(1,(total+batch-1)//batch+1):
        j=first if page==1 else request('GET',u,params={**params,'page':page}).json();v=j['jobs'];listing.extend(v);logs.append({'page':page,'rows':len(v),'reported':j['totalCount']})
    rows=[]
    for j in {str(x['data']['req_id']):x for x in listing}.values():
        x=j['data'];body=x.get('description','');duty,req,status=split_body(body)
        if x.get('qualifications'):req=x['qualifications'];status='separate_official_fields'
        if x.get('responsibilities'):duty=x['responsibilities']
        ident=str(x['req_id']);r=make('AMD','amd',ident,x['title'],'https://careers.amd.com/careers-home/jobs/'+ident+'?lang=en-us',duty,req,j,[x.get('full_location') or x.get('short_location') or x.get('city')],x.get('country'),x.get('categories'),x.get('posted_date'),status,body);rows.append(r)
    return save('amd',rows,{'company':'AMD','started_at':start,'finished_at':now(),'scope':'官方country=China搜索API，正文与资格字段原样归档','reported_list_total':total,'list_rows':len(listing),'pages':logs,'errors':errors})
def arm():
    start=now();u='https://careers.arm.com/search-jobs/China';r=request('GET',u);s=BeautifulSoup(r.text,'html.parser');container=s.select_one('#search-results-list') or s
    urls=list(dict.fromkeys(urljoin('https://careers.arm.com',a['href']) for a in container.select('a[href]') if a['href'].startswith('/job/')))
    h=s.select_one('h1');m=re.search(r'(\d+) results',h.get_text(' ',strip=True) if h else '');total=int(m.group(1)) if m else None
    errors=[];rows=[]
    def detail(url):
        p=BeautifulSoup(request('GET',url).text,'html.parser');ld=None
        for sc in p.select('script[type="application/ld+json"]'):
            j=json.loads(sc.get_text());objs=j if isinstance(j,list) else [j]
            for v in objs:
                if v.get('@type')=='JobPosting':ld=v;break
        if not ld:raise ValueError('No JobPosting JSON-LD')
        body=ld.get('description','');duty,req,status=split_body(body);locs=[];countries=[]
        loc=ld.get('jobLocation',[]);loc=loc if isinstance(loc,list) else [loc]
        for v in loc:
            ad=v.get('address',{});locs.append(', '.join(str(ad.get(k,'')) for k in ['addressLocality','addressRegion','addressCountry'] if ad.get(k)));countries.append(str(ad.get('addressCountry','')))
        ident=str(ld.get('identifier',{}).get('value','')) if isinstance(ld.get('identifier'),dict) else str(ld.get('identifier',''))
        ident=ident or url.rstrip('/').split('/')[-1]
        return make('Arm','arm',ident,ld.get('title','未知'),url,duty,req,ld,locs,'；'.join(countries),None,ld.get('datePosted'),status,body)
    with cf.ThreadPoolExecutor(max_workers=3) as p:
        fs={p.submit(detail,u):u for u in urls}
        for f in cf.as_completed(fs):
            try:rows.append(f.result())
            except Exception as e:errors.append({'url':fs[f],'error':str(e)})
    return save('arm',rows,{'company':'Arm','started_at':start,'finished_at':now(),'scope':'官方China结果容器内职位链接与逐岗JSON-LD；排除页面推荐岗位','reported_list_total':total,'list_rows':len(urls),'errors':errors})
def main():
    audits=[]
    for slug,fn in [('amd',amd),('arm',arm),('apple',apple)]:
        try:d=fn();audits.append(d);print(slug,d['records'],'errors',len(d['errors']),flush=True)
        except Exception as e:audits.append({'company':slug,'records':0,'error':str(e),'failed_at':now()});print(slug,'FAILED',e,flush=True)
        (OUT/'foreign_extra_expanded_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
