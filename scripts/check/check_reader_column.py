"""Measure the text column inside real rendered lessons locally or on a deployed site."""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import expect, sync_playwright

from scripts.check.check_hot100_animation_browser import site


PAGES = {
    'hot100-49': 'books/hot100/03-题解/01-哈希表/0049-字母异位词分组.html',
    'hot200-186': 'library/hot200-extra/chapter-01.html',
    'java-reader': 'library/java-core/chapter-01.html',
}
GEOMETRY = """article => {
    const box = node => { const r = node.getBoundingClientRect(); return {left:r.left, right:r.right, width:r.width}; };
    const card = article.closest('main'), r = box(card), s = getComputedStyle(card);
    const left = r.left + parseFloat(s.paddingLeft) + parseFloat(s.borderLeftWidth);
    const right = r.right - parseFloat(s.paddingRight) - parseFloat(s.borderRightWidth);
    const body = box(article), lang = document.querySelector('#forge-lang-bar');
    const rails = [...document.querySelectorAll('.site-shell-cols > :is(.sol-rail, .shelf-topic-rail)')]
        .filter(node => node.getClientRects().length).map(box);
    return {viewport:innerWidth, pageWidth:document.documentElement.scrollWidth,
        bodyWidth:body.width, available:right-left, leftGap:body.left-left, rightGap:right-body.right,
        rails:rails.length, railOverlap:rails.some(rail => rail.right > r.left + 1 && rail.left < r.right - 1 && innerWidth > 1100),
        languageBar:lang ? box(lang) : null, article:body};
}"""


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with site(args.base) as base, sync_playwright() as engine:
        browser = engine.chromium.launch(channel='chrome')
        ctx = browser.new_context(locale='zh-CN', reduced_motion='reduce')
        if args.credentials:
            if not base.startswith('https://'):
                raise ValueError('Login requires HTTPS')
            session = ctx.request.post(urljoin(base, '/api/login'), data=json.loads(args.credentials.read_bytes()),
                                       headers={'Origin':base.rstrip('/'), 'Referer':urljoin(base,'pages/login.html')})
            assert session.ok and ctx.request.get(urljoin(base,'api/me')).json().get('username')
        for width, height in [(320, 700), (390, 844), (1440, 900), (2048, 1152), (2560, 1440)]:
            for name, path in PAGES.items():
                page = ctx.new_page()
                page.set_viewport_size({'width':width,'height':height})
                try:
                    response = page.goto(urljoin(base, path), wait_until='domcontentloaded', timeout=45000)
                    assert response and response.ok, (name, response.status if response else None)
                    article = page.locator('.hot100-solution, .chapter-shell .reader-body').first
                    expect(article).to_be_visible()
                    if name != 'java-reader':
                        page.locator('#forge-lang-bar button[data-lang="python"]').click()
                        expect(article).to_have_attribute('data-active-language', 'python')
                    page.evaluate('document.fonts.ready')
                    bounds = article.evaluate(GEOMETRY)
                    image = f'{name}-{width}.png'
                    if width in (390, 2560):
                        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
                        page.screenshot(path=args.output/image, animations='disabled')
                    errors = []
                    if width > 1100 and max(abs(bounds['leftGap']), abs(bounds['rightGap'])) > 2:
                        errors.append('body does not fill the central column')
                    bar = bounds['languageBar']
                    if width > 1100 and bar and any(abs(bar[edge] - bounds['article'][edge]) > 2 for edge in ('left', 'right')):
                        errors.append('language switch and lesson edges are misaligned')
                    if bounds['pageWidth'] > width + 1 or bounds['railOverlap']:
                        errors.append('overflow or rail overlap')
                    if width >= 1800 and bounds['rails'] != 2:
                        errors.append('missing desktop navigation rail')
                    results.append({'page':name, **bounds, 'issues':errors})
                finally:
                    page.close()
        browser.close()
    (args.output/'reader-widths.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    for row in results:
        print(f"{row['page']} {row['viewport']}: {row['bodyWidth']:.1f}/{row['available']:.1f}px; {row['issues']}")
    return int(any(row['issues'] for row in results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
