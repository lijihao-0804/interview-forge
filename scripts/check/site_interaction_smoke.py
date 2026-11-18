"""Exercise public and signed-in controls with Chromium at real CSS viewport sizes.

Local runs use the site audit's offline catalog and a disposable study database.
With --base and --credentials, authenticate a dedicated acceptance account via
the normal form. Other mutating requests are blocked before they reach the host.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlsplit
from unittest.mock import patch

from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright

from interview_forge.api.routers import static
from scripts.check.site_page_audit import fixture_app


VIEWPORTS = [(320, 700), (390, 844), (2560, 1440)]

HIT_TARGETS = """() => {
 const targets = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab]')]
   .filter(el => el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) &&
       !el.matches(':disabled,[aria-disabled=true]') &&
       (!el.closest('details:not([open])') || el.closest('summary')?.parentElement === el.closest('details:not([open])')));
 const groups = new Map();
 for (const el of targets) {
   const key = el.tagName + (el.id ? '#' + el.id : '.' + [...el.classList].join('.') + '/' + (el.parentElement?.className || ''));
   if (!groups.has(key)) groups.set(key, []);
   groups.get(key).push(el);
 }
 const issues = [];
 let tested = 0;
 const oldX = scrollX, oldY = scrollY;
 for (const [key, collection] of groups) {
   const samples = collection.length < 5 ? collection : [...new Set([collection[0], collection[Math.floor(collection.length/2)], collection.at(-1)])];
   for (const el of samples) {
     tested++;
     if (el.matches('a.skip,a.skip-link,a.cockpit-skip')) el.focus({preventScroll:true});
     let reachable = false, covering = '';
     for (const block of ['center','start','end']) {
       el.scrollIntoView({block, inline:'center', behavior:'instant'});
       for (const r of el.getClientRects()) {
         const l = Math.max(0,r.left), t = Math.max(0,r.top), w = Math.min(innerWidth,r.right)-l, h = Math.min(innerHeight,r.bottom)-t;
         if (w < 1 || h < 1) continue;
         for (const [x,y] of [[.5,.5],[.12,.5],[.88,.5],[.5,.18],[.5,.82]]) {
           const hit = document.elementFromPoint(l+x*w,t+y*h);
           if (hit && (el.contains(hit) || hit.closest('label')?.control === el)) { reachable = true; break; }
           covering = hit ? hit.tagName + '#' + hit.id + '.' + String(hit.className).slice(0,80) : '';
         }
         if (reachable) break;
       }
       if (reachable) break;
     }
     if (!reachable) issues.push({key, name:(el.getAttribute('aria-label') || el.innerText || el.name || '').trim().slice(0,80), covering});
   }
 }
 scrollTo({left:oldX,top:oldY,behavior:'instant'});
 return {eligible:targets.length, groups:groups.size, tested, issues};
}"""


def cockpit(page):
    query = page.locator("#launchQuery")
    query.fill("两数之和")
    query.press("Enter")
    expect(page.locator("#search")).to_have_value("两数之和")
    expect(page.locator("#grid .card")).to_have_count(1)
    page.locator("#search").fill("zz_没有此题")
    page.locator("#emptyReset").click()
    expect(page.locator("#search")).to_be_focused()
    page.locator("#loadMore").click()
    expect(page.locator("#grid .card")).to_have_count(48)


def guest_prompt(page):
    button = page.locator("#forge-fb-btn")
    button.focus()
    button.press("Enter")
    modal = page.get_by_role("dialog")
    expect(modal).to_be_visible()
    expect(modal.get_by_role("link", name="登录", exact=True)).to_have_attribute(
        "href", re.compile(r"login\.html\?next=")
    )
    modal.get_by_role("link", name="登录", exact=True).focus()
    page.keyboard.press("Tab")
    assert page.evaluate(
        "!document.activeElement.closest('body') || document.activeElement === document.body || !!document.activeElement.closest('[role=dialog],dialog')"
    ), "Tab moved to a background control"
    page.keyboard.press("Escape")
    expect(modal).to_have_count(0)
    expect(button).to_be_focused()


def auth_links(page):
    page.locator("#registerLink").click()
    expect(page.locator("#email")).to_be_visible()
    page.locator("#email").fill("invalid")
    expect(page.locator("#sendCode")).to_be_disabled()
    page.locator("#submit").click()
    expect(page.locator("#msg")).to_contain_text("邮箱")
    page.locator("#loginLink").click()
    page.locator("#forgotLink").click()
    expect(page.locator("#confirm")).to_be_visible()


def library_filters(page):
    search = page.locator("#shelfSearch")
    search.fill("zz_没有此章节")
    expect(page.locator("#shelfResult")).to_contain_text("0")
    search.press("Escape")
    expect(search).to_have_value("")
    track = page.locator("button[data-track-filter]").nth(1)
    track.click()
    expect(track).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#chipRow")).to_be_visible()


def catalog_filter_widths(page, member):
    expect(page.locator("body")).to_have_class(
        re.compile(r"\b" + ("is-authenticated" if member else "is-guest") + r"\b")
    )
    # The category list is populated from the volume's actual problems.
    expect(page.locator("#category option").nth(1)).to_be_attached()
    selectors = page.locator(".controls select:visible, #sortOrder:visible")
    expect(selectors).to_have_count(5 if member else 3)
    if member:
        page.locator("#progressLanguage").select_option("python")
        page.locator("#status").select_option("repeat")
    page.locator("#sortOrder").select_option("difficulty")
    page.evaluate("document.fonts.ready")
    # A single-option clone uses the browser's own font, native arrow and padding.
    # Measuring text alone misses exactly the clipping this check guards against.
    measurements = selectors.evaluate_all("""selects => selects.map(select => {
      const rect = select.getBoundingClientRect();
      const probe = select.cloneNode(false);
      probe.removeAttribute('id');
      probe.setAttribute('aria-hidden', 'true');
      probe.tabIndex = -1;
      probe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;width:max-content!important;min-width:0!important;max-width:none!important';
      const sample = new Option();
      probe.add(sample);
      select.after(probe);
      const intrinsic = text => {
        sample.text = text;
        return probe.getBoundingClientRect().width;
      };
      const chrome = intrinsic('');
      const options = Array.from(select.options, option => ({
        label:option.label, value:option.value, required:intrinsic(option.label)
      }));
      const style = getComputedStyle(probe);
      const decoration = ['paddingLeft','paddingRight','borderLeftWidth','borderRightWidth']
        .reduce((sum, p) => sum + parseFloat(style[p]), 0);
      probe.remove();
      return {id:select.id, width:rect.width, x:rect.x, y:rect.y,
              selected:select.value, native_chrome:chrome, native_arrow:chrome-decoration, options};
    })""")
    category = next(field for field in measurements if field["id"] == "category")
    longest = max(category["options"], key=lambda option: option["required"])
    page.locator("#category").select_option(longest["value"])
    expect(page.locator("#category")).to_have_value(longest["value"])
    category["selected"] = longest["value"]
    if member:
        expect(page.locator("#progressLanguage")).to_have_value("python")
        expect(page.locator("#status")).to_have_value("repeat")
    for field in measurements:
        assert field["native_arrow"] > 0, f"{field['id']} native arrow was not measured"
    clipped = [
        f"{field['id']} {option['label']} ({option['required']:.1f} > {field['width']:.1f}px)"
        for field in measurements for option in field["options"]
        if option["required"] > field["width"] + 0.1
    ]
    return {"filter_widths": measurements, "clipped_options": clipped}


def library_search(page):
    page.locator("h1").click()
    page.keyboard.press("/")
    query = page.locator("#searchInput")
    expect(query).to_be_focused()
    query.fill("MVCC")
    expect(page.locator("#results .chapter-card").first).to_be_visible()


def code_wrap(page):
    page.locator("a[href='#hot100-topics']").click()
    expect(page.locator("#hot100-topics")).to_be_attached()
    assert urlsplit(page.url).fragment == "hot100-topics"
    control = page.locator(".code-toolbar button[aria-pressed]:visible").first
    expect(control).to_be_visible()
    block = control.locator("xpath=../../pre")
    wrapped = lambda: block.evaluate(
        "el => getComputedStyle(el).whiteSpace.includes('wrap')"
    )
    before = wrapped()
    assert control.get_attribute("aria-pressed") == str(before).lower(), (
        "aria-pressed differs from line wrapping"
    )
    control.press("Enter")
    assert wrapped() != before, "first activation kept the same line wrapping"
    control.click()
    assert wrapped() == before
    copy = control.locator("xpath=preceding-sibling::button")
    copy.click()
    expect(copy).to_have_text("已复制")


def notices(page):
    choices = page.locator(".notice-item")
    choices.nth(1).click()
    expect(choices.nth(1)).to_have_attribute("aria-current", "true")
    frame = page.frame_locator("#noticeFrame")
    expect(frame.locator("h1").first).to_be_visible()
    query = page.locator("#noticeFilter")
    query.fill("zz_没有此通知")
    expect(choices).to_have_count(0)
    query.fill("")
    page.locator("#btnReload").click()
    expect(frame.locator("h1").first).to_be_visible()
    with page.expect_popup() as popup:
        page.locator("#btnNew").click()
    expect(popup.value.locator("h1").first).to_be_visible()
    popup.value.close()


def quiz(page):
    page.locator("#catGrid .cat-card").first.click()
    expect(page.locator("#studyPanel")).to_be_visible()
    page.locator("[data-mode=exam]").click()
    expect(page.locator("#btnStart")).to_be_visible()
    page.locator("#btnHome").click()
    page.locator("#bankSelect").select_option("ai-exam")
    expect(page.locator("#companyFilter")).to_be_visible()
    page.locator("#catGrid .cat-card").first.click()
    expect(page.locator("#crumbCat")).not_to_be_empty()


def market(page):
    jobs = page.locator("#jobs .job")
    expect(jobs.first).to_be_visible(timeout=30000)
    page.locator("#next").click()
    expect(page.locator("#page")).to_contain_text("2 /")
    page.locator("#prev").click()
    first = jobs.first
    first.click()
    expect(page.locator("#viewer #jobTitle")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#viewer")).to_be_hidden()
    expect(first).to_be_focused()
    page.locator("#q").fill("zz_没有此职位")
    expect(jobs).to_have_count(0)
    page.locator("#reset").click()
    expect(jobs.first).to_be_visible()
    with page.expect_download() as download:
        page.locator("#export").click()
    assert download.value.suggested_filename.endswith(".csv")


def module(page):
    chapter = page.locator(".chapter-card a").first
    expect(chapter).to_be_visible()
    href = chapter.get_attribute("href")
    if chapter.get_attribute("target") == "_blank":
        with page.expect_popup() as opened:
            chapter.click()
        reader = opened.value
    else:
        chapter.click()
        reader = page
    expect(reader.locator("h1")).to_be_visible()
    assert (
        urlsplit(href).path.split("/")[-1] == urlsplit(reader.url).path.split("/")[-1]
    )
    if reader is not page:
        reader.close()


def chapter_contents(page):
    link = (
        page.locator(".reader-body a[href='chapter-02.html']")
        .filter(has_text="LangChain")
        .first
    )
    expect(link).to_be_visible()
    if link.get_attribute("target") == "_blank":
        with page.expect_popup() as opened:
            link.click()
        reader = opened.value
    else:
        link.click()
        reader = page
    expect(reader.locator("h1").first).to_contain_text("LangChain")
    assert urlsplit(reader.url).path.endswith("/chapter-02.html")
    with reader.expect_download() as download:
        reader.locator("#exportChapter").click()
    assert download.value.suggested_filename.endswith(".html")
    if reader is not page:
        reader.close()


def callout_link(page):
    link = page.locator('a[href="#_6"]').filter(has_text="易错").first
    if link.is_visible():
        link.click()
    else:
        # Narrow layouts hide the desktop rail. Open the same bookmarked section.
        page.goto(page.url.split("#", 1)[0] + "#_6")
    expect(page.locator("#_6 .aside-title")).to_contain_text("易错")
    assert urlsplit(page.url).fragment == "_6"


def theme(page):
    button = page.locator("#forge-theme-btn")
    title = button.get_attribute("title")
    button.click()
    assert button.get_attribute("title") != title
    button.press("Enter")
    button.click()
    assert button.get_attribute("title") == title


def exams(page):
    items = page.locator(".exam-list li:visible")
    expect(items.first).to_be_visible()
    query = page.locator("#q")
    query.fill("zz_未收录")
    expect(items).to_have_count(0)
    query.fill("")
    companies = page.locator("#company")
    companies.select_option(index=1)
    expect(items.first).to_be_visible()
    assert all(
        x == companies.input_value()
        for x in items.evaluate_all("els=>els.map(e=>e.dataset.company)")
    )


def research_tabs(page):
    for name in ("research", "explore", "overview"):
        tab = page.locator(f'button[role="tab"][data-tab="{name}"]')
        tab.click()
        expect(tab).to_have_attribute("aria-selected", "true")
        expect(page.locator("#" + name)).to_be_visible()
        assert urlsplit(page.url).fragment == "view=" + name


def tools_booking(page):
    page.locator("a[href*='nju-booking']").click()
    expect(page.locator("#slot-add")).to_be_visible()
    rows = page.locator("#slot-rows > *")
    count = rows.count()
    page.locator("#slot-add").click()
    expect(rows).to_have_count(count + 1)
    last = rows.last
    start, end = last.locator("select").all()
    start.select_option("20")
    assert int(end.input_value()) > 20
    last.get_by_role("button").click()
    expect(rows).to_have_count(count)


def admin_sections(page):
    picker = page.locator("#admin-section-select")
    if picker.is_visible():
        picker.select_option("#admin-registration")
    else:
        page.locator(".admin-topic-nav a[href='#admin-registration']").click()
    expect(page.locator("#admin-registration")).to_be_visible()
    page.locator("#count").fill("2")
    page.locator("#days").fill("2")
    expect(page.locator("#gen")).to_be_enabled()
    if picker.is_visible():
        picker.select_option("#admin-overview")
    else:
        page.locator(".admin-topic-nav a[href='#admin-overview']").click()
    page.locator('[data-admin-tab="logs"]').click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1"), (
        "admin log filters overflow"
    )


def ai_drawer(page):
    opener = page.locator("#if-ai-launcher:visible,.fap-ai:visible").first
    opener.click()
    drawer = page.locator(".if-ai-drawer")
    expect(drawer).to_be_visible()
    close = drawer.get_by_role("button", name="关闭", exact=True)
    expect(close).to_be_focused()
    frame = page.frame_locator(".if-ai-drawer iframe")
    frame.locator("textarea").first.focus()
    page.keyboard.press("Escape")
    expect(drawer).to_have_count(0)
    expect(opener).to_be_focused()


def panel(page, launcher, panel_id):
    button = page.locator(launcher)
    button.focus()
    button.press("Enter")
    opened = page.locator(panel_id)
    expect(opened).to_be_visible()
    assert opened.evaluate("el=>el.contains(document.activeElement)"), (
        "focus stayed outside the opened panel"
    )
    assert opened.evaluate(
        "el=>{const r=el.getBoundingClientRect();return r.left>=-1 && r.top>=-1 && r.right<=innerWidth+1 && r.bottom<=innerHeight+1}"
    ), "panel extends beyond viewport"
    page.keyboard.press("Escape")
    expect(opened).to_have_count(0)
    expect(button).to_be_focused()


def feedback(page):
    panel(page, "#forge-fb-btn", "#forge-fb-panel")
    button = page.locator("#forge-fb-btn")
    button.click()
    page.locator("#fb-content").fill("本地草稿")
    page.locator(".fap-close").click()
    button.click()
    expect(page.locator("#fb-content")).to_have_value("本地草稿")
    page.locator("#fb-content").fill("")
    page.locator(".fap-close").click()


def annual(page):
    picker = page.locator("#pageSelect")
    expect(picker).to_be_visible()
    before = picker.input_value()
    page.locator("#pageNext").click()
    expect(picker).not_to_have_value(before)
    page.locator("#pagePrev").click()
    expect(picker).to_have_value(before)


def favorites(page):
    page.locator("#typeContent").click()
    expect(page.locator("#typeContent")).to_have_class(re.compile("active"))
    page.locator("#searchInput").fill("没有的收藏")
    page.locator("#typeAll").click()
    expect(page.locator("#typeAll")).to_have_class(re.compile("active"))


CASES = [
    ("guest", "hot100-guest-filter-widths", "/index.html", lambda p: catalog_filter_widths(p, False)),
    ("guest", "hot200-guest-filter-widths", "/library/hot200-extra/index.html", lambda p: catalog_filter_widths(p, False)),
    ("member", "hot100-member-filter-widths", "/index.html", lambda p: catalog_filter_widths(p, True)),
    ("member", "hot200-member-filter-widths", "/library/hot200-extra/index.html", lambda p: catalog_filter_widths(p, True)),
    ("guest", "cockpit-to-catalog-search-reset-load", "/", cockpit),
    ("guest", "feedback-login-dialog", "/", guest_prompt),
    ("guest", "auth-form-navigation", "/pages/login.html", auth_links),
    ("guest", "shelf-filters", "/library/index.html", library_filters),
    ("guest", "full-text-search", "/library/search.html", library_search),
    ("guest", "module-chapter-navigation", "/library/java-core/index.html", module),
    (
        "guest",
        "chapter-authored-contents-and-export",
        "/library/langchain/chapter-01.html",
        chapter_contents,
    ),
    (
        "guest",
        "reader-callout-anchor",
        "/books/company-solutions/Array/0016-最接近的三数之和.html",
        callout_link,
    ),
    ("guest", "theme-three-modes", "/guide.html", theme),
    ("guest", "reader-copy-wrap", "/guide.html", code_wrap),
    ("guest", "market-filter-paging-detail", "/research/market/", market),
    ("guest", "exam-archive-company-search", "/books/ai-exam/index.html", exams),
    (
        "guest",
        "research-hash-tabs",
        "/library/ai-employment-research/index.html",
        research_tabs,
    ),
    ("member", "notice-filter-iframe-refresh-popup", "/pages/notices.html", notices),
    ("member", "quiz-bank-study-exam-navigation", "/pages/quiz.html", quiz),
    ("member", "chat-panel", "/", lambda p: panel(p, ".fap-chat", "#forge-chat-panel")),
    ("member", "profile-panel", "/", lambda p: panel(p, ".fap-name", "#forge-profile")),
    ("member", "feedback-panel-draft", "/", feedback),
    ("member", "ai-drawer-keyboard", "/", ai_drawer),
    ("member", "annual-report-chapters", "/pages/annual-report.html", annual),
    ("member", "favorites-filters", "/pages/favorites.html", favorites),
    ("admin", "toolbox-booking-draft", "/pages/tools.html", tools_booking),
    ("admin", "admin-section-navigation", "/pages/admin.html", admin_sections),
]


def native_guest_navigation(browser, base, output, widths):
    """Visit the production shell with normal cache, service worker and network."""
    snapshots = []
    context = browser.new_context(
        locale="zh-CN", reduced_motion="reduce", service_workers="allow"
    )
    page = context.new_page()
    try:
        page.goto(base + "/", wait_until="domcontentloaded")
        page.wait_for_function(
            "navigator.serviceWorker.controller !== null", timeout=30000
        )
        for width, height in VIEWPORTS:
            if widths and width not in widths:
                continue
            page.set_viewport_size({"width": width, "height": height})
            for name, path in (
                ("cockpit", "/cockpit.html"),
                ("catalog", "/index.html"),
                ("shelf", "/library/index.html"),
                ("guide", "/guide.html"),
            ):
                resp = page.goto(base + path, wait_until="load")
                expect(page.locator("h1").first).to_be_visible()
                measured = page.evaluate(
                    "({width:document.documentElement.scrollWidth,controlled:!!navigator.serviceWorker.controller})"
                )
                assert (
                    resp.ok
                    and measured["width"] <= width + 1
                    and measured["controlled"]
                ), (path, width, measured)
                if name == "catalog":
                    expect(page.locator("#grid .card").first).to_be_visible()
                image = f"native-{name}-{width}.png"
                page.screenshot(path=output / image)
                snapshots.append(
                    {
                        "path": path,
                        "viewport": width,
                        "height": height,
                        "status": resp.status,
                        "from_service_worker": resp.from_service_worker,
                        "screenshot": image,
                        **measured,
                    }
                )
    finally:
        context.close()
    return snapshots


def run(args):
    base = args.base.rstrip("/") if args.base else "http://localhost"
    if args.credentials and (not args.base or not base.startswith("https://")):
        raise ValueError("Live credentials require an explicit HTTPS --base")
    results = []
    hits = []
    native = []
    native_error = ""
    blocked_writes = Counter()
    args.output.mkdir(exist_ok=True, parents=True)
    with ExitStack() as stack:
        client = None
        identity = {
            "id": 12345,
            "username": "interaction_fixture",
            "nickname": "验收",
            "role": "user",
            "lang": "java",
        }
        if not args.base:
            db = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "study.db"
            client = stack.enter_context(
                TestClient(fixture_app(db), raise_server_exceptions=False)
            )
            stack.enter_context(patch.object(static, "_record_view"))
            stack.enter_context(
                patch.object(
                    static,
                    "current_user",
                    side_effect=lambda req: identity if role != "guest" else None,
                )
            )
        pw = stack.enter_context(sync_playwright())
        browser = pw.chromium.launch()
        stack.callback(browser.close)
        if args.native_navigation:
            if not args.base:
                raise ValueError("--native-navigation requires --base")
            try:
                native = native_guest_navigation(
                    browser, base, args.output, args.widths
                )
            except Exception as exc:
                native_error = str(exc)[:600]
        for role in ("guest", "member", "admin"):
            if args.base and role == "admin":
                continue
            identity["role"] = "admin" if role == "admin" else "user"
            cases = [
                case
                for case in CASES
                if case[0] == role and (not args.case or case[1] in args.case)
            ]
            if not cases or (args.base and role == "member" and not args.credentials):
                continue
            context = browser.new_context(
                locale="zh-CN", service_workers="block", reduced_motion="reduce"
            )

            def transport(route):
                req = route.request
                url = urlsplit(req.url)
                if url.netloc != urlsplit(base).netloc:
                    route.abort()
                elif req.method not in ("GET", "HEAD") and not (
                    args.base
                    and role == "member"
                    and req.method == "POST"
                    and url.path == "/api/login"
                ):
                    blocked_writes[url.path] += 1
                    route.fulfill(status=405, json={"error": "验收只读"})
                elif client is None:
                    route.continue_()
                elif url.path == "/api/me":
                    route.fulfill(
                        json=identity if role != "guest" else {"error": "游客"},
                        status=200 if role != "guest" else 401,
                    )
                else:
                    response = client.get(
                        req.url,
                        headers={
                            k: v
                            for k, v in req.headers.items()
                            if k in ("referer", "accept", "sec-fetch-dest")
                        },
                    )
                    route.fulfill(
                        status=response.status_code,
                        body=response.content,
                        headers={
                            k: v
                            for k, v in response.headers.items()
                            if k not in ("content-length", "content-encoding")
                        },
                    )

            context.route("**/*", transport)
            if args.base and role == "member":
                credentials = json.loads(
                    args.credentials.read_text(encoding="utf-8-sig")
                )
                login = context.new_page()
                login.goto(base + "/pages/login.html")
                login.locator("#username").fill(credentials["username"])
                login.locator("#password").fill(credentials["password"])
                with login.expect_response(
                    lambda res: urlsplit(res.url).path == "/api/login"
                ) as response:
                    login.locator("#btn").click()
                assert response.value.ok, f"Login returned HTTP {response.value.status}"
                assert context.request.get(base + "/api/me").ok
                login.close()
            for width, height in VIEWPORTS:
                if args.widths and width not in args.widths:
                    continue
                for _, name, path, action in cases:
                    page = context.new_page()
                    page.set_viewport_size({"width": width, "height": height})
                    page.set_default_timeout(7000)
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)[:300]))
                    row = {
                        "role": role,
                        "case": name,
                        "width": width,
                        "height": height,
                        "path": path,
                    }
                    try:
                        response = page.goto(
                            base + path, wait_until="domcontentloaded", timeout=30000
                        )
                        assert response and response.ok
                        details = action(page)
                        if isinstance(details, dict):
                            row.update(details)
                            name_and_width = f"{name}-{width}.png"
                            page.locator(".controls").screenshot(path=args.output / name_and_width)
                            row["filter_screenshot"] = name_and_width
                            assert not row["clipped_options"], ", ".join(row["clipped_options"])
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth+1"
                        ), "horizontal overflow"
                        assert not errors, errors
                        row["passed"] = True
                    except Exception as exc:
                        row.update(passed=False, error=str(exc)[:600])
                        page.screenshot(
                            path=args.output / f"failure-{name}-{width}.png",
                            timeout=10000,
                            mask=[
                                page.locator(
                                    ".fap-name,#forge-profile .fp-sub,#username,#password"
                                )
                            ],
                        )
                    finally:
                        row["final_path"] = unquote(urlsplit(page.url).path)
                        if args.hit_targets and not any(
                            h["role"] == role
                            and h["width"] == width
                            and h["path"] == row["final_path"]
                            for h in hits
                        ):
                            hits.append(
                                {
                                    "role": role,
                                    "width": width,
                                    "path": row["final_path"],
                                    **page.evaluate(HIT_TARGETS),
                                }
                            )
                        results.append(row)
                        page.close()
            context.close()
    unreachable = sum(len(inspection["issues"]) for inspection in hits)
    report = {
        "base": base,
        "results": results,
        "native_browser_navigation": native,
        "native_error": native_error,
        "pointer_hit_tests": hits,
        "unreachable_controls": unreachable,
        "blocked_writes": dict(blocked_writes),
        "not_sent": [
            "发布聊天或反馈、修改账号与头像、保存第三方凭据、同步力扣、创建预约、发邮件、修改管理配置均会写入账户或联系第三方。",
            "外部招聘及第三方站点未遍历。",
            "生产普通验收账号仅执行本工具的用户操作，管理入口和私人正文受身份限制。",
        ],
    }
    (args.output / "interactions.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )
    failed = [r for r in results if not r["passed"]]
    for row in failed:
        print(row["case"], row["width"], row["error"].splitlines()[0], flush=True)
    print(
        f"{len(results) - len(failed)}/{len(results)} interaction flows passed; {unreachable} unreachable pointer targets",
        flush=True,
    )
    if native_error:
        print("Native browser navigation:", native_error, flush=True)
    return int(bool(failed or unreachable or native_error))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", help="Explicit live base URL; default uses the offline test app"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        help="Dedicated test account JSON; values are never logged",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--widths", type=int, nargs="+", choices=[width for width, _ in VIEWPORTS]
    )
    parser.add_argument(
        "--hit-targets",
        action="store_true",
        help="Check pointer hit points after scrolling template controls into view",
    )
    parser.add_argument(
        "--native-navigation",
        action="store_true",
        help="Also capture unauthenticated live pages with normal networking and the active service worker",
    )
    parser.add_argument("--case", nargs="+", choices=[case[1] for case in CASES])
    raise SystemExit(run(parser.parse_args()))
