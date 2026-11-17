"""One bounded attempt per missing Apple China JD using ordinary official pages."""
import concurrent.futures as cf,json,threading,time
import requests
from collect_foreign_extra_v2 import apple_data
from collect_foreign_v2 import make,save,OUT
from job_common_v2 import ROOT,now

def main():
 start=now();cp=json.loads((OUT/'apple_list_checkpoint.json').read_text(encoding='utf-8'))
 old=json.loads((OUT/'apple_expanded_jobs.json').read_text(encoding='utf-8'));rows={x['source_job_id']:x for x in old}
 listing={str(x['positionId']):x for x in cp['positions']};missing=[x for k,x in listing.items() if k not in rows]
 local=threading.local();gate=threading.Lock();last=[0.0];errors=[];attempts=[]
 def detail(x):
  ident=str(x['positionId']);url=cp['urls'].get(ident) or 'https://jobs.apple.com/zh-cn/details/'+ident+'/'+x['transformedPostingTitle']
  if not hasattr(local,'session'):
   local.session=requests.Session();local.session.headers['Accept-Encoding']='gzip, deflate'
  with gate:
   wait=.5-(time.monotonic()-last[0])
   if wait>0:time.sleep(wait)
   last[0]=time.monotonic()
  resp=local.session.get(url,timeout=(10,20));resp.raise_for_status();data,_=apple_data(resp.text);j=data['jobDetails']['jobsData']
  if str(j.get('positionId'))!=ident:raise ValueError('Detail positionId differs from requested ID')
  duty='\n\n'.join(str(j[k]) for k in ['jobSummary','description','responsibilities'] if j.get(k))
  req='\n\n'.join(label+'\n'+str(j[key]) for label,key in [('Minimum qualifications / 最低资格','minimumQualifications'),('Preferred qualifications / 优先条件','preferredQualifications')] if j.get(key))
  r=make('Apple','apple',ident,j.get('postingTitle') or x['postingTitle'],url,duty,req,j,[v.get('name') or v.get('city') for v in j.get('locations',[])],'；'.join(sorted({v.get('countryName','') for v in j.get('locations',[])})),j.get('teamNames'),j.get('postingDateMeta') or j.get('postingDate'))
  r['managed_pipeline_role_raw']=j.get('managedPipelineRole');return r
 with cf.ThreadPoolExecutor(max_workers=4) as p:
  fs={p.submit(detail,x):x for x in missing}
  for i,f in enumerate(cf.as_completed(fs),1):
   ident=str(fs[f]['positionId'])
   try:r=f.result();rows[ident]=r;attempts.append({'id':ident,'success':True})
   except Exception as e:errors.append({'id':ident,'error':str(e)});attempts.append({'id':ident,'success':False})
   (OUT/'apple_missing_detail_attempts_v2.json').write_text(json.dumps({'started_at':start,'attempts':attempts,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
   if i%10==0:save('apple',list(rows.values()),{})
 result=save('apple',list(rows.values()),{'company':'Apple','started_at':start,'finished_at':now(),'reported_list_total':cp['total'],'unique_list_ids':len(listing),'target_missing_at_start':len(missing),'attempted':len(attempts),'missing_detail_count':len(set(listing)-set(rows)),'errors':errors,'scope':'一次有界补采，不重试限流/验证码；失败详情不以列表摘要代替正文'})
 (OUT/'apple_fill_expanded_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
