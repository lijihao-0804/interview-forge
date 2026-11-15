"""Browser-check an extracted synthetic teaching site; never load user content."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
import zipfile

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright, expect
from interview_forge.api.app import app
from interview_forge.api.routers import private_archive
from scripts.install_private_archive import install


def run():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        root=Path(temp);archive=root/'fixture.zip';site=root/'site'
        members={
            'index.html':'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>教学目录测试夹具</title><link rel="stylesheet" href="./assets/app.css"></head><body><header class="archive-bar"><h1>教学目录测试夹具</h1><div class="archive-actions"></div></header><main class="learning"><aside class="book-side">章节导航</aside><section class="reading-area"><div class="book-scroll"><article class="chapter-article"><h2>示例代码</h2><pre><code class="language-python">def add(a, b):\n    return a + b</code></pre><div class="learning-diagram"><div class="diagram-preview"><svg viewBox="0 0 400 100"><rect x="10" y="10" width="150" height="70" fill="#eeedff"/><text x="30" y="50">输入 → 输出</text></svg></div></div><output id="history"></output></article></div></section></main><script defer src="./assets/hljs.js"></script><script defer src="./assets/app.js"></script></body></html>''',
            'assets/app.css':'*{box-sizing:border-box}body{margin:0;font:16px/1.6 sans-serif}.learning{padding:20px;gap:20px}.chapter-article{padding:20px;min-width:0}pre{overflow:auto}.hljs-keyword{color:#5654d4}.hljs-title{color:#a85b00}',
            'assets/app.js':"document.querySelector('code').innerHTML=window.learningHighlighter.highlight(document.querySelector('code').textContent,{language:'python'}).value;fetch('./data/history-data.json').then(r=>r.json()).then(d=>document.querySelector('#history').textContent=d.fixture);",
            'assets/hljs.js':'throw new Error("This broken dependency must be replaced")',
            'data/manifest.json':'{}', 'data/history-data.json':'{"fixture":"history fixture intact"}',
        }
        with zipfile.ZipFile(archive,'w') as package:
            for name,body in members.items():package.writestr('site/'+name,body)
        install(archive,site)
        archive.unlink()  # Prove the application actually serves the extracted tree.
        stack.enter_context(patch.dict('os.environ',{'INTERVIEW_FORGE_PRIVATE_ARCHIVE_DIR':str(site),'INTERVIEW_FORGE_PRIVATE_ARCHIVE':''}))
        identity=[{'id':123,'username':'fixture_owner','role':'admin'}]
        stack.enter_context(patch.object(private_archive,'server_runtime',SimpleNamespace(PERMANENT_ADMIN_USERNAME='fixture_owner')))
        stack.enter_context(patch('interview_forge.api.support.current_user',side_effect=lambda *_:identity[0]))
        client=stack.enter_context(TestClient(app));pw=stack.enter_context(sync_playwright())
        browser=pw.chromium.launch(args=['--no-sandbox','--no-zygote','--single-process'])
        context=browser.new_context(service_workers='block',locale='zh-CN');page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def transport(route):
            url=urlsplit(route.request.url)
            if url.hostname!='localhost':route.abort();return
            response=client.get(url.path)
            route.fulfill(status=response.status_code,body=response.content,headers={k:v for k,v in response.headers.items() if k not in ('content-length','content-encoding')})
        context.route('**/*',transport)
        for width,height in [(1920,1080),(2560,1440),(1280,720),(390,844)]:
            page.set_viewport_size({'width':width,'height':height});page.goto('http://localhost/api/private-archive/index.html')
            expect(page.locator('#history')).to_have_text('history fixture intact')
            expect(page.locator('.hljs-keyword').first).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('.diagram-preview svg').bounding_box()['height']<=500
        for name in ['assets/app.js','data/history-data.json']:
            response=client.get('/api/private-archive/'+name)
            assert response.text==members[name] and 'no-store' in response.headers['cache-control']
        identity[0]={'id':124,'username':'another_admin','role':'admin'}
        assert client.get('/api/private-archive/data/history-data.json').status_code==403
        identity[0]=None
        assert client.get('/api/private-archive/assets/app.js').status_code==401
        browser.close();assert not errors,errors
        print(json.dumps({'extracted_only':True,'viewports':4,'highlighted':True,'history_bytes_unchanged':True,'page_errors':errors}))


if __name__=='__main__':run()
