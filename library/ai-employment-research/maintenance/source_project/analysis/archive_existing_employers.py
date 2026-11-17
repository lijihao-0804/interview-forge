"""Re-read public JD fields for existing Tencent / Alibaba / JD collections."""
import concurrent.futures as cf
import datetime as dt
import json
import time
from pathlib import Path
import collect_all_public_jobs as old
from collect_tencent import get
from job_common_v2 import ROOT,now,plain,hits,digest,archive,summary

OUT=ROOT/'evidence'
ORIGINAL_BUILD=old.build_record
def archival_build(**kw):
    r=ORIGINAL_BUILD(**kw)
    r.update(description=plain(kw['duty']),requirements=plain(kw['requirement']),
       source_job_id=str(kw['ident']),retrieved_at=now(),requirements_parse_status='separate_official_fields')
    r['full_text']=r['description']+'\n\n'+r['requirements']
    r['summary']=summary(r['title'],r['description'],r['requirements'],r.get('city'),r.get('experience'))
    r['source_type']='雇主官方公开职位API；JD正文已在本地归档'
    slug='alibaba' if r['company']=='阿里巴巴' else 'jd'
    r['archive_json']=archive(slug,kw['ident'],r,kw['raw'])
    return r
old.build_record=archival_build

def tencent():
    seed=json.loads((OUT/'tencent_all_jd_features.json').read_text(encoding='utf-8'))
    records=[];errors=[]
    def worker(m):
        d=get('ByPostId',dict(postId=str(m['id']),language='zh-cn'))
        duty=plain(d.get('Responsibility'));req=plain(d.get('Requirement'))
        r=dict(m,description=duty,requirements=req,full_text=duty+'\n\n'+req,
          source_job_id=str(m['id']),retrieved_at=now(),requirements_parse_status='separate_official_fields',
          detail_status='full' if duty and req else 'partial',skills_in_requirement=hits(req),skills_in_responsibility=hits(duty))
        r['text_sha256']=digest(r['full_text']);r['summary']=summary(r['title'],duty,req,r.get('city'),r.get('experience'))
        r['source_type']='腾讯官方ByPostId；JD正文已在本地归档'
        r['archive_json']=archive('tencent',m['id'],r,d)
        time.sleep(.3)
        return r
    with cf.ThreadPoolExecutor(max_workers=4) as p:
        fs={p.submit(worker,m):m for m in seed}
        for f in cf.as_completed(fs):
            try:records.append(f.result())
            except Exception as e:
                m=fs[f];errors.append({'id':m['id'],'url':m['url'],'error':str(e)})
    records.sort(key=lambda x:str(x['id']))
    (OUT/'tencent_expanded_jobs.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'target_ids':len(seed),'records':len(records),'full':sum(x['detail_status']=='full' for x in records),'errors':errors}

def main():
    start=now()
    # Independent employers; at most four Tencent detail requests and one other request.
    with cf.ThreadPoolExecutor(max_workers=2) as p:
        tf=p.submit(tencent)
        jd,jd_a=old.collect_jd(set())
        (OUT/'jd_expanded_jobs.json').write_text(json.dumps(jd,ensure_ascii=False,indent=2),encoding='utf-8')
        ali,ali_a=old.collect_alibaba(set())
        (OUT/'alibaba_expanded_jobs.json').write_text(json.dumps(ali,ensure_ascii=False,indent=2),encoding='utf-8')
        tx=tf.result()
    audit={'started_at':start,'finished_at':now(),'employers':{'腾讯':tx,'京东':jd_a,'阿里巴巴':ali_a},'method':'公开接口原职责/要求字段及原始职位记录本地存档；未使用登录、验证码绕过或外部上传'}
    (OUT/'existing_employers_archive_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'腾讯':tx,'京东':len(jd),'阿里巴巴':len(ali)},ensure_ascii=False))
if __name__=='__main__':main()
