import json
import time
import collect_foreign_v2 as c
from job_common_v2 import now

original=c.request
last={}
def slow(method,url,**kw):
    if 'careers.qualcomm.com' in url or 'careers.microsoft.com' in url:
        host=url.split('/')[2];wait=1.1-(time.monotonic()-last.get(host,0))
        if wait>0:time.sleep(wait)
        last[host]=time.monotonic()
    return original(method,url,**kw)
c.request=slow
tasks=[('nvidia',lambda:c.workday('NVIDIA','nvidia','nvidia.wd5.myworkdayjobs.com','NVIDIAExternalCareerSite')),
 ('amazon',c.amazon),('qualcomm',lambda:c.eightfold('Qualcomm','qualcomm','qualcomm.com','careers.qualcomm.com')),
 ('microsoft',lambda:c.eightfold('Microsoft','microsoft','microsoft.com','apply.careers.microsoft.com'))]
audit=[]
for slug,fn in tasks:
    try:r=fn();audit.append(r);print(slug,r.get('records'),len(r.get('errors',[])),flush=True)
    except Exception as e:audit.append({'company':slug,'failed_at':now(),'records':0,'error':str(e)});print(slug,'FAILED',e,flush=True)
    (c.OUT/'foreign_retry_expanded_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
