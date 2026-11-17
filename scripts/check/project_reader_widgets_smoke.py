"""Exercise the checked-in project books with a synthetic super-admin cookie."""
from contextlib import ExitStack
from urllib.parse import urlsplit
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

from interview_forge.api.routers import private_archive
from tests.test_private_archive import PrivateArchiveTests


def run():
    with ExitStack() as stack:
        fixture = PrivateArchiveTests()
        fixture.setUp()
        stack.callback(fixture.doCleanups)
        for key, folder in (('AGENTHUB_DIR', 'agenthub'), ('REPORT_DIR', 'development-history'),
                            ('VOLTEDU_DIR', 'voltedu-study')):
            stack.enter_context(patch.object(private_archive, key, private_archive.ROOT / 'library' / folder))
        pw = stack.enter_context(sync_playwright())
        browser = pw.chromium.launch()
        stack.callback(browser.close)
        page = browser.new_page(service_workers='block')
        feedback = []
        requests = []

        def transport(route):
            url = urlsplit(route.request.url)
            assert url.hostname == 'localhost'
            requests.append(url.path)
            if url.path == '/api/me':
                route.fulfill(json={'username': 'owner', 'role': 'super_admin'})
            elif url.path == '/api/feedback':
                feedback.append(route.request.post_data_json)
                route.fulfill(json={'ok': True})
            elif url.path.startswith('/api/') and not url.path.startswith('/api/private-archive'):
                route.fulfill(json={})
            else:
                response = fixture.request(url.path + ('?' + url.query if url.query else ''), 'owner-token')
                route.fulfill(status=response.status_code, body=response.content,
                              headers={'Content-Type': response.headers['content-type']})

        page.route('**/*', transport)
        for path in ('/library/development-history/chapters/origin.html',
                     '/library/voltedu-study/story/01-origin.html',
                     '/api/private-archive/index.html#view=learn&chapter=start'):
            page.goto('http://localhost' + path)
            agenthub = path.startswith('/api/')
            if agenthub:
                expect(page.locator('#chapterArticle h1')).to_be_visible()
                assert sum('/data/chapters/' in url for url in requests) == 1
                old = page.locator('#chapterArticle h1').inner_text()
                page.locator('#nextChapter').click()
                expect(page.locator('#chapterArticle h1')).not_to_have_text(old)
                assert sum('/data/chapters/' in url for url in requests) == 2
            expect(page.locator('#if-ai-launcher')).to_have_count(1)
            expect(page.locator('#forge-fb-btn')).to_have_count(1)
            page.locator('#if-ai-launcher').click()
            frame = page.frame_locator('.if-ai-drawer iframe')
            expect(frame.locator('body')).to_be_visible()
            expect(frame.locator('#if-ai-launcher, #forge-fb-btn')).to_have_count(0)
            context = frame.locator('body').evaluate("""() => new Promise(resolve => {
              addEventListener('message', function listener(event) {
                if (event.data.request_id !== 'smoke') return;
                removeEventListener('message', listener);
                resolve(event.data.context);
              });
              parent.postMessage({type:'interviewforge:request-page-context', request_id:'smoke'}, location.origin);
            })""")
            assert context['path'] == page.url.removeprefix('http://localhost')
            assert context['chapter_excerpt'] and context['heading']
            if agenthub:
                assert page.locator('#chapterArticle h1').inner_text() in context['title']
            page.locator('.if-ai-drawer-actions button').click()
            page.locator('#forge-fb-btn').click()
            page.locator('#fb-content').fill('合成章节定位检查')
            page.locator('.fap-send').click()
            expect(page.locator('#fb-hint')).to_contain_text('已提交')
            assert feedback[-1]['page'] == context['path']
            print(context['path'], 'AI, excerpt, feedback OK')
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto("http://localhost/library/development-history/chapters/origin.html")
        page.locator("#if-ai-launcher").click()
        expect(page.locator(".if-ai-drawer iframe")).to_be_visible()
        page.locator(".if-ai-drawer-actions button").click()
        page.locator("#forge-fb-btn").click()
        expect(page.locator("#fb-content")).to_be_visible()


if __name__ == '__main__':
    run()
