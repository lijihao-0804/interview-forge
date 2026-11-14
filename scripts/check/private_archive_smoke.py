"""Validate a local private archive through FastAPI; never copy it into the repo.
Usage: python -m scripts.check.private_archive_smoke /absolute/private/site.zip
Optional --output stores private screenshots outside the repository.
"""
from contextlib import ExitStack
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
import zipfile

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from interview_forge.api.app import app
from interview_forge.api.routers import private_archive


def run(archive: Path, output: Path | None):
    assert archive.is_absolute() and not archive.resolve().is_relative_to(private_archive.ROOT.resolve())
    if output:
        assert not output.resolve().is_relative_to(private_archive.ROOT.resolve())
        output.mkdir(parents=True,exist_ok=True)
    with ExitStack() as stack, zipfile.ZipFile(archive) as package:
        manifest=json.loads(package.read('site/data/manifest.json'))
        stack.enter_context(patch.dict('os.environ',{'INTERVIEW_FORGE_PRIVATE_ARCHIVE':str(archive)}))
        stack.enter_context(patch.object(private_archive,'server_runtime',SimpleNamespace(PERMANENT_ADMIN_USERNAME='qa_owner')))
        identity={'id':999999,'username':'qa_owner','role':'admin'}
        stack.enter_context(patch('interview_forge.api.support.current_user',side_effect=lambda request:identity or None))
        client=stack.enter_context(TestClient(app))
        # Prove original animation resources and scripts are unchanged on the wire.
        for name in ['assets/app.js','assets/hljs.js','data/history-data.json','data/history-templates.json','data/history-sample.json']:
            response=client.get('/api/private-archive/'+name)
            assert response.status_code==200 and response.content==package.read('site/'+name),name
        pw=stack.enter_context(sync_playwright())
        browser=pw.chromium.launch(args=['--no-sandbox','--no-zygote','--single-process'])
        context=browser.new_context(service_workers='block',locale='zh-CN')
        errors=[]
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        def transport(route):
            req=route.request;url=urlsplit(req.url)
            if url.hostname!='localhost':route.abort();return
            response=client.request(req.method,url.path+('?' + url.query if url.query else ''),
                                    headers={k:v for k,v in req.headers.items() if k not in ('host','content-length')})
            if response.status_code!=200: print('HTTP',response.status_code,url.path)
            route.fulfill(status=response.status_code,body=response.content,
                          headers={k:v for k,v in response.headers.items() if k not in ('content-length','content-encoding')})
        context.route('**/*',transport)
        page.set_viewport_size({'width':1920,'height':1080})
        page.goto('http://localhost/api/private-archive/index.html')
        try:
            expect(page.locator('#chapterArticle h1')).to_be_visible()
        except AssertionError:
            print('BOOT ERRORS',errors,page.locator('body').inner_text()[:1800]);raise
        page.wait_for_function('!!window.bookApp')
        page.evaluate("() => { readerDepth = 'deep'; }")
        total_codes=total_diagrams=0
        for chapter in manifest['chapters'] + manifest['originals']:
            page.evaluate('(id)=>window.bookApp.open(id)',chapter['id'])
            expect(page.locator('#chapterArticle h1')).to_be_visible()
            page.wait_for_function('!document.querySelector("#chapterArticle pre.mermaid:not([data-render-error])")')
            bad=page.locator('#chapterArticle [data-render-error]').count()
            assert not bad,(chapter['id'],'missing diagram')
            total_codes+=page.locator('#chapterArticle .hljs [class^="hljs-"]').count()
            total_diagrams+=page.locator('#chapterArticle .learning-diagram svg').count()
        assert total_codes>0 and total_diagrams>0,(total_codes,total_diagrams)
        # Open a real rendered diagram and exercise zoom/close.
        for chapter in manifest['chapters'] + manifest['originals']:
            page.evaluate('(id)=>window.bookApp.open(id)',chapter['id'])
            if page.locator('.diagram-open').count():break
        page.locator('.diagram-open').first.click()
        expect(page.locator('#learningDiagramDialog')).to_be_visible()
        page.locator('[data-zoom="in"]').click()
        expect(page.locator('#learningDiagramDialog output')).to_have_text('125%')
        page.locator('.diagram-close').click()
        for width,height in [(1920,1080),(2560,1440),(1536,864),(1280,720),(768,1024),(390,844)]:
            page.set_viewport_size({'width':width,'height':height})
            page.evaluate('window.dispatchEvent(new Event("resize"))')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'),width
            assert page.locator('#bookScroll').bounding_box()['height']>100,width
            if output:page.screenshot(path=str(output/f'private-reader-{width}.png'))
        page.set_viewport_size({'width':1920,'height':1080})
        for mode in ['global-directory','global-git','full-tree','full-point','full-flow','full-boundaries','sample-tree','sample-graph','sample-flow']:
            page.evaluate('(mode)=>window.archiveNavigate(mode)',mode)
            expect(page.locator('#loading')).to_be_hidden()
            expect(page.locator('#view-'+mode.split('-')[0])).to_be_visible()
        identity.clear()
        response=client.get('/api/private-archive/data/history-data.json')
        assert response.status_code==401 and 'no-store' in response.headers['cache-control']
        page.evaluate('window.dispatchEvent(new Event("focus"))')
        page.wait_for_url('**/pages/login.html?**')
        browser.close()
        assert not errors,errors
        print(f'PASS: {len(manifest["chapters"])} chapters + {len(manifest["originals"])} originals; {total_codes} highlighted tokens; {total_diagrams} diagrams; 6 viewports; 9 history views; revocation; original animation bytes unchanged')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();run(args.archive,args.output)
