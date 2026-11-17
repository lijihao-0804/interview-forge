"""Recover already archived Apple detail snapshots after a collector timeout.
No network calls. This script never fills missing text from metadata.
"""
import json
from collect_foreign_v2 import make,save,OUT
from job_common_v2 import ROOT,now

def main():
 cp=json.loads((OUT/'apple_list_checkpoint.json').read_text(encoding='utf-8'))
 listing={str(x['positionId']):x for x in cp['positions']};rows={};errors=[]
 old=OUT/'apple_expanded_jobs.json'
 if old.exists():
  for x in json.loads(old.read_text(encoding='utf-8')):rows[x['source_job_id']]=x
 for p in sorted((ROOT/'archives/apple').glob('*.json')):
  try:
   a=json.loads(p.read_text(encoding='utf-8'));ident=str(a.get('source_job_id') or '')
   if ident not in listing:continue
   x=listing[ident];j=a.get('raw_source_payload') or {}
   if not (a.get('description') or a.get('requirements')):continue
   duty='\n\n'.join(str(j[k]) for k in ['jobSummary','description','responsibilities'] if j.get(k)) or a.get('description','')
   req='\n\n'.join(label+'\n'+str(j[key]) for label,key in [('Minimum qualifications / 最低资格','minimumQualifications'),('Preferred qualifications / 优先条件','preferredQualifications')] if j.get(key)) or a.get('requirements','')
   r=make('Apple','apple',ident,j.get('postingTitle') or x['postingTitle'],a['source_url'],duty,req,j,[v.get('name') or v.get('city') for v in j.get('locations',[])],'；'.join(sorted({v.get('countryName','') for v in j.get('locations',[])})),j.get('teamNames'),j.get('postingDateMeta') or j.get('postingDate'))
   r['managed_pipeline_role_raw']=j.get('managedPipelineRole')
   r['retrieved_at']=a.get('retrieved_at') or r['retrieved_at'];rows[ident]=r
  except Exception as e:errors.append({'file':str(p.relative_to(ROOT)),'error':str(e)})
 missing=sorted(set(listing)-set(rows))
 audit=save('apple',list(rows.values()),{'company':'Apple','recovered_at':now(),'scope':'官网中国地点完整33页列表；详情仅取已成功存档正文，离线恢复，不以元数据伪造正文','reported_list_total':cp['total'],'list_rows':len(cp['positions']),'unique_list_ids':len(listing),'last_list_page':cp['page'],'missing_detail_ids':missing,'missing_detail_count':len(missing),'errors':errors})
 (OUT/'apple_recovery_expanded_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in audit.items() if k!='missing_detail_ids'},ensure_ascii=False))
if __name__=='__main__':main()
