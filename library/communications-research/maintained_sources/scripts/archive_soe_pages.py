"""Normal public-page navigation in a task-owned headless Edge; no CDP or login."""
import asyncio,datetime,hashlib,json,re
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'archives/soe_browser_pages'
async def main():
    records=[json.loads(x) for x in (ROOT/'soe_sources/records.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    urls=sorted({str(j.get('url') or j.get('source_url') or '') for j in records if str(j.get('url') or j.get('source_url') or '').startswith(('https://','http://'))})
    assert len(urls)<=80,'Unexpected scope expansion';OUT.mkdir(parents=True,exist_ok=True);results=[];sem=asyncio.Semaphore(3)
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        context=await browser.new_context()
        async def capture(url):
            async with sem:
                page=await context.new_page();key=hashlib.sha256(url.encode()).hexdigest()[:18];entry={'url':url,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'normal headless Edge page navigation; no authentication or modified request signing'}
                try:
                    response=await page.goto(url,wait_until='domcontentloaded',timeout=25000);await page.wait_for_timeout(500)
                    body=await page.locator('body').inner_text(timeout=5000);source=await page.content();(OUT/(key+'.html')).write_text(source,encoding='utf-8');(OUT/(key+'.txt')).write_text(body,encoding='utf-8')
                    status=response.status if response else None;garbled=sum('\ue000'<=ch<='\uf8ff' for ch in body)/max(1,len(body))
                    entry.update(http_status=status,final_url=page.url,html_archive=key+'.html',text_archive=key+'.txt',html_sha256=hashlib.sha256(source.encode()).hexdigest(),text_sha256=hashlib.sha256(body.encode()).hexdigest(),text_characters=len(body),private_use_character_ratio=garbled,body_available=status==200 and len(body)>500 and garbled<.01 and not re.search(r'just a moment|access denied|验证您|人机验证',body[:2000],re.I))
                except Exception as e:entry['error']=str(e)
                finally:await page.close();results.append(entry)
        try:await asyncio.gather(*(capture(u) for u in urls))
        finally:await context.close();await browser.close()
    (OUT/'manifest.json').write_text(json.dumps({'sources':results,'scope':'Actual rendered page archive; webpage body is not automatically a full standalone job-specific qualification section.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source_urls':len(urls),'bodies_available':sum(x.get('body_available',False) for x in results),'errors':sum('error'in x for x in results)},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
