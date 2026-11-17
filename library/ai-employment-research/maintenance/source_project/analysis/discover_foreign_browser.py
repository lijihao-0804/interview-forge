"""Observe public career pages using an ordinary task-owned browser context."""
from pathlib import Path
import json
import re
from playwright.sync_api import sync_playwright
from job_common_v2 import ROOT,now

out=ROOT/'analysis'/'foreign_browser';out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    try:
        for slug,url in [('sap','https://jobs.sap.com/en/jobs/?location=China'),('microsoft','https://apply.careers.microsoft.com/careers?location=China')]:
            page=b.new_page();records=[]
            def response(resp):
                if 'application/json' not in resp.headers.get('content-type',''):return
                if not any(k in resp.url.lower() for k in ['job','position','/api/']):return
                try:
                    data=resp.json();idx=len(records);name=f'{slug}_{idx}.json'
                    (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                    safe=re.sub(r'([?&](?:token|signature|_signature|key)=[^&]+)',r'\1[redacted]',resp.url,flags=re.I)
                    records.append({'url':safe,'status':resp.status,'file':name})
                except Exception:pass
            page.on('response',response)
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=45000)
                page.wait_for_timeout(12000)
                text=page.locator('body').inner_text()
                (out/(slug+'_body.txt')).write_text(text,encoding='utf-8')
                (out/(slug+'_page.html')).write_text(page.content(),encoding='utf-8')
                (out/(slug+'_audit.json')).write_text(json.dumps({'at':now(),'url':url,'title':page.title(),'responses':records,'links':page.locator('a[href]').evaluate_all('(a)=>a.map(x=>({text:x.innerText,url:x.href}))')},ensure_ascii=False,indent=2),encoding='utf-8')
                print(slug,page.title(),'JSON responses',len(records),'body',text[:250].replace('\n',' '),flush=True)
            except Exception as e:print(slug,'ERROR',str(e),flush=True)
            page.close()
    finally:b.close()
