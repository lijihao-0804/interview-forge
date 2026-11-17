"""Observe public recruiting pages in an isolated browser. No authentication or request signing."""
import hashlib,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'archives/browser';OUT.mkdir(parents=True,exist_ok=True)
def main():
    records=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        try:
            for name,url in [('mobile-beijing','https://job.10086.cn/personal/campus/campus_job_list.html?cId=3'),('mobile-cloud','https://job.10086.cn/personal/campus/campus_job_list.html?cId=79'),('mobile-research','https://job.10086.cn/personal/campus/campus_job_list.html?cId=97')]:
                page=browser.new_page();responses=[]
                def capture(response):
                    if not ('/job-app/job/' in response.url or 'GetJob' in response.url):return
                    try:
                        body=response.body();ident=hashlib.sha256(body).hexdigest();(OUT/(name+'-'+ident[:16]+'.json')).write_bytes(body)
                        responses.append({'url':response.url.split('?')[0],'status':response.status,'bytes':len(body),'sha256':ident,'archive':name+'-'+ident[:16]+'.json'})
                    except Exception:pass
                page.on('response',capture)
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=60000);page.wait_for_timeout(5000)
                    text=page.locator('body').inner_text();(OUT/(name+'.html')).write_text(page.content(),encoding='utf-8');page.screenshot(path=str(OUT/(name+'.png')))
                    records.append({'name':name,'url':page.url,'text':text[:7000],'links':page.locator('a').evaluate_all('(nodes)=>nodes.map(a=>({text:a.textContent.trim(),href:a.href})).filter(a=>a.text).slice(0,40)'),'responses':responses})
                except Exception as e:records.append({'name':name,'url':url,'error':str(e),'responses':responses})
                finally:page.close()
        finally:browser.close()
    (ROOT/'evidence/browser-units-probe.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(records,ensure_ascii=False))
if __name__=='__main__':main()
