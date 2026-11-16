"""Check the private shelf with real synthetic session cookies; no user content."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from tests.test_private_archive import PrivateArchiveTests
from interview_forge.api.routers import private_archive


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    fixture = PrivateArchiveTests()
    fixture.setUp()
    token = [None]
    unavailable = [False]
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=['--no-sandbox', '--no-zygote', '--single-process'])
            context = browser.new_context(service_workers='block', locale='zh-CN', viewport={'width':1920,'height':1080})
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            def transport(route):
                url = urlsplit(route.request.url)
                if url.hostname != 'localhost':
                    route.abort(); return
                if url.path.startswith('/api/private-archive'):
                    if unavailable[0]:
                        route.fulfill(status=503, json={'error':'fixture unavailable'}); return
                    response = fixture.request(url.path, token[0])
                elif url.path == '/api/me':
                    if token[0] is None:
                        route.fulfill(status=401, json={'error':'anonymous'}); return
                    route.fulfill(status=200, json={'id':1,'username':token[0].split('-')[0],'role':'admin' if token[0]!='reader-token' else 'user','nickname':'合成测试账号'}); return
                elif url.path.startswith('/api/'):
                    route.fulfill(status=503, json={'error':'unrelated service fixture'}); return
                else:
                    response = fixture.request(url.path, token[0])
                route.fulfill(status=response.status_code, body=response.content, headers={k:v for k,v in response.headers.items() if k not in ('content-length','content-encoding')})
            context.route('**/*', transport)
            for identity in (None, 'reader-token', 'admin-token', 'owner-token'):
                token[0] = identity
                page.goto('http://localhost/library/index.html')
                host = page.locator('#privateTeachingShelf')
                track = page.locator('#projectNotesTrack')
                expect(host).to_be_hidden()
                if identity == 'owner-token':
                    track.click()
                    expect(host).to_be_visible()
                    expect(host.locator('h2')).to_have_text('AgentHub 教学档案')
                else:
                    expect(track).to_be_hidden()
                    expect(host).to_be_empty()
                    expect(host).to_be_hidden()
                assert page.locator('#moduleGrid .module-card').count() > 20
            reader = context.new_page()
            reader.on('pageerror', lambda error: errors.append(str(error)))
            reader.goto('http://localhost/api/private-archive/index.html')
            expect(reader.locator('.forge-archive-back')).to_have_attribute('href', '/library/index.html')
            reader.close()
            page.bring_to_front()
            page.evaluate('dispatchEvent(new Event("focus"))')
            expect(host).to_be_visible()
            public_count = page.locator('#moduleGrid .module-card').count()
            for width,height in ((1920,1080),(2560,1440),(390,844)):
                page.set_viewport_size({'width':width,'height':height})
                for theme in ('light','dark'):
                    page.evaluate('(theme)=>document.documentElement.setAttribute("data-theme",theme)', theme)
                    host.scroll_into_view_if_needed()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(output/f'shelf-{width}-{theme}.png'))
            page.locator('#shelfSearch').fill('NO_MATCH_FIXTURE')
            expect(host).to_be_hidden()
            assert page.locator('#moduleGrid .module-card').count() == public_count
            page.locator('#shelfSearch').fill('')
            unavailable[0] = True
            page.evaluate('dispatchEvent(new Event("focus"))')
            expect(host).to_be_empty(); expect(host).to_be_hidden()
            unavailable[0] = False
            with patch.object(private_archive, '_read_member', side_effect=FileNotFoundError):
                page.evaluate('dispatchEvent(new Event("focus"))')
                page.wait_for_timeout(150)
                expect(host).to_be_empty()
            page.evaluate('dispatchEvent(new Event("focus"))')
            track.click()
            expect(host).to_be_visible()
            token[0] = 'admin-token'
            page.evaluate('document.dispatchEvent(new CustomEvent("interviewforge:auth-change",{detail:{status:"checking"}}))')
            expect(host).to_be_empty()
            page.evaluate('dispatchEvent(new Event("storage"))')
            page.wait_for_timeout(150); expect(host).to_be_empty()
            token[0] = 'owner-token'
            page.evaluate('dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))')
            track.click()
            expect(host).to_be_visible()
            page.evaluate('dispatchEvent(new PageTransitionEvent("pagehide",{persisted:true}))')
            expect(host).to_be_empty()
            token[0] = None
            page.evaluate('dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))')
            page.wait_for_timeout(150); expect(host).to_be_empty()
            token[0] = 'owner-token'
            page.evaluate('dispatchEvent(new Event("focus"))')
            track.click()
            expect(host).to_be_visible()
            with fixture.connect() as db:
                db.execute("UPDATE users SET role='user' WHERE username='owner'")
            page.evaluate('dispatchEvent(new Event("focus"))')
            expect(host).to_be_empty()
            assert not errors, errors
            browser.close()
        print(json.dumps({'ok':True,'roles':4,'viewports':3,'themes':2,'revocation':True,'page_errors':errors}))
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
