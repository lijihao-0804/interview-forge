"""Read normal anonymous Microsoft career page responses in its browser context."""
import json
from playwright.sync_api import sync_playwright
from collect_foreign_v2 import make,save,OUT
from job_common_v2 import now,split_body

def main():
    started=now();pages=[];errors=[];positions={};records=[];observed=[]
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        try:
            page=b.new_page()
            def response(r):
                if '/api/pcsx/search?' in r.url and r.status==200:
                    try:observed.append(r.json())
                    except Exception:pass
            page.on('response',response)
            page.goto('https://apply.careers.microsoft.com/careers?location=China',wait_until='domcontentloaded',timeout=60000)
            page.wait_for_timeout(30000)
            if observed:first=observed[-1]['data']
            else:
                from job_common_v2 import ROOT
                first=json.loads((ROOT/'analysis/foreign_browser/microsoft_2.json').read_text(encoding='utf-8'))['data']
                errors.append({'stage':'initial_page','error':'No new successful search response; retained earlier normal browser response snapshot.'})
            total=first['count'];batch=len(first.get('positions',[])) or 10
            for offset in range(0,total,batch):
                if offset==0:d=first
                else:
                    url='/api/pcsx/search?domain=microsoft.com&query=&location=China&start='+str(offset)+'&'
                    answer=page.evaluate('async u=>{let r=await fetch(u);return {status:r.status,text:await r.text()}}',url)
                    if answer['status']!=200:errors.append({'offset':offset,'status':answer['status']});break
                    d=json.loads(answer['text'])['data'];page.wait_for_timeout(800)
                v=d.get('positions',[]);pages.append({'start':offset,'rows':len(v),'reported':d.get('count')})
                for x in v:positions[str(x['id'])]=x
            for ident,x in positions.items():
                try:
                    url='/api/pcsx/position_details?position_id='+ident+'&domain=microsoft.com&hl=en&queried_location=China'
                    answer=page.evaluate('async u=>{let r=await fetch(u);return {status:r.status,text:await r.text()}}',url)
                    if answer['status']!=200:
                        errors.append({'id':ident,'status':answer['status']})
                        if answer['status']==429:
                            if ident=='1970393557039443':
                                from job_common_v2 import ROOT
                                raw=json.loads((ROOT/'analysis/foreign_browser/microsoft_5.json').read_text(encoding='utf-8'));d=raw['data'];body=d.get('jobDescription') or d.get('description') or '';duty,req,status=split_body(body)
                                records.append(make('Microsoft','microsoft',ident,d.get('name') or x['name'],'https://apply.careers.microsoft.com/careers/job/'+ident,duty,req,raw,d.get('locations') or x.get('locations'),None,d.get('department'),None,status,body))
                            break
                        continue
                    raw=json.loads(answer['text']);d=raw['data'];body=d.get('jobDescription') or d.get('description') or '';duty,req,status=split_body(body)
                    records.append(make('Microsoft','microsoft',ident,d.get('name') or x['name'],'https://apply.careers.microsoft.com'+(x.get('positionUrl') or '/careers/job/'+ident),duty,req,raw,d.get('locations') or x.get('locations'),None,d.get('department'),None,status,body))
                    page.wait_for_timeout(650)
                except Exception as e:errors.append({'id':ident,'error':str(e)})
        finally:b.close()
    audit=save('microsoft',records,{'company':'Microsoft','started_at':started,'finished_at':now(),'scope':'官网匿名页面正常返回的location=China搜索与同源公开详情，按官网count分页；未重建签名或处理验证码','reported_list_total':total,'unique_list_ids':len(positions),'pages':pages,'errors':errors})
    (OUT/'microsoft_browser_expanded_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ['pages']},ensure_ascii=False))
if __name__=='__main__':main()
