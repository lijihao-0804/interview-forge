"""Archive the employer-authorized public Unicom campaign, with new output per run.
Recipe observed at https://zglt.zhaopin.com/scjobs/index.html on 2026-11-18.
No login, cookie replay, request signing, decryption or access-control bypass.
"""
import argparse,datetime,hashlib,json,time,urllib.request
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--campaign',default='105347');args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    endpoint='https://fe.zhaopin.com/grace/api/dsc/search-job-list';pages=[];ids=[];rawrows=0
    for page in range(1,201):
        body={'orgNumbers':[args.campaign],'jobSource':2,'pageIndex':page,'pageSize':100}
        req=urllib.request.Request(endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':'https://zglt.zhaopin.com','Referer':'https://zglt.zhaopin.com/scjobs/index.html','User-Agent':'Mozilla/5.0'},method='POST')
        # HTTP errors intentionally stop the collector; do not retry around a site restriction.
        with urllib.request.urlopen(req,timeout=45) as response:raw=response.read();status=response.status
        data=json.loads(raw);assert data.get('code')==200,'API error: stop and inspect archived source'
        payload=data['data'];jobs=payload.get('jobList',[]);info=payload.get('pageInfo',{})
        filename=f'page_{page:03d}.json';(args.output/filename).write_bytes(raw)
        pages.append({'file':filename,'url':endpoint,'method':'POST','request_json':body,'status':status,'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(jobs),'page_info':info})
        rawrows+=len(jobs);ids.extend(str(x.get('job',{}).get('jobNumber') or x.get('job',{}).get('id') or '') for x in jobs)
        print(f'archived page {page}, rows {len(jobs)}')
        (args.output/'manifest.partial.json').write_text(json.dumps({'pages':pages},ensure_ascii=False,indent=2),encoding='utf-8')
        if page>=int(info.get('totalPage',page)) or not jobs:break
        time.sleep(.5)
    else:raise RuntimeError('Pagination limit reached; do not treat as a complete sample')
    reported=int(info.get('totalNum',rawrows));unique=len(set(ids));assert all(ids),'missing official ID';assert rawrows==reported,'Incomplete pagination or changing live pool; do not compare as complete'
    result={'source_page':'https://zglt.zhaopin.com/scjobs/index.html','captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'campaign':args.campaign,'raw_rows':rawrows,'unique_ids':unique,'duplicate_ids':rawrows-unique,'reported_total':reported,'pages':pages}
    (args.output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='pages'}))
if __name__=='__main__':main()
