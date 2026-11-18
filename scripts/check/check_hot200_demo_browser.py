"""Exercise the actual demo opened by each published learning page in Chromium."""
import html
import json
import re
import argparse
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def demos():
    for volume in ("hot100", "hot200-extra"):
        rows = json.loads((ROOT / f"data/acm/{volume}.json").read_bytes())
        for row in rows:
            page = ROOT / unquote(row["solution_url"]).lstrip("/")
            iframe = re.search(r'<iframe[^>]+class="reader-visual-frame"[^>]+src="([^"]+)"',
                               page.read_text(encoding="utf-8"))
            assert iframe, row["id"]
            link = urlsplit(html.unescape(iframe[1]))
            yield row, (page.parent / unquote(link.path)).resolve().as_uri() + "?" + link.query


def check(page, row, uri, screenshots):
    page.goto(uri, wait_until="domcontentloaded")
    if page.evaluate("Boolean(window.__dk)"):
        assert page.evaluate("window.__dk.steps.length >= 3"), row["id"]
        page.get_by_role("button", name="下一步", exact=False).click()
        assert page.evaluate("window.__dk.idx") == 1
        page.get_by_role("button", name="重置", exact=False).click()
        assert page.evaluate("window.__dk.idx") == 0
    else:
        next_step = page.locator(".btn-next:visible, #nextBtn:visible").first
        assert next_step.is_visible(), row["id"]
        previous = page.locator("body").inner_text()
        next_step.click()
        page.wait_for_function("text => document.body.innerText !== text", arg=previous)

    if row["id"] in ("hot100-34", "hot100-35"):
        answers = ([[3, 4], [-1, -1], [0, 2], [-1, -1]] if row["id"] == "hot100-34" else [1, 2, 4, 0])
        for index, answer in enumerate(answers):
            page.get_by_role("combobox", name="规模选择").select_option(str(index))
            page.get_by_role("button", name="末尾", exact=False).click()
            assert page.evaluate("window.__dk.steps.at(-1).view.answer") == answer
    if row["id"] == "hot100-416":
        for nums, expected in (("1,2,5", False), ("1,5,11,5", True), ("1,2,4", False)):
            page.locator("#exampleSelect").select_option(nums)
            page.locator("#playBtn").click()
            page.locator("#resetBtn").click()
            assert page.locator("#prevBtn").is_disabled()
            page.evaluate("() => {const next=document.querySelector('#nextBtn'); "
                          "for(let i=0;i<200 && !next.disabled;i++)next.click();}")
            assert page.locator("#nextBtn").is_disabled()
            assert str(expected).lower() in page.locator("#desc1").inner_text()

    original = row["id"].startswith("hot100-")
    if original:
        page.get_by_role("link", name="查看本题输入与 Python 执行过程").click()
        page.wait_for_function("Boolean(window.__dk)")
        samples = page.evaluate("Hot200Execution.cases.map(c => ({input:c.input, expected:JSON.stringify(c.output)}))")
    else:
        samples = row["samples"]
    assert str(page.evaluate("Hot200Execution.id")) == row["id"].split("-")[1]
    for index, sample in enumerate(samples, 0 if original else 1):
        control = page.get_by_role("combobox", name="演示输入")
        if control.count():
            control.select_option(str(index))
        assert page.locator(".dk-stage pre").inner_text() == sample["input"].strip()
        page.get_by_role("button", name="自动播放", exact=False).click()
        assert page.evaluate("window.__dk.idx") > 0
        last = page.get_by_role("button", name="末尾", exact=False)
        if last.is_enabled():
            last.click()
        actual = json.loads(page.locator(".dk-stage pre").inner_text())
        assert actual == json.loads(sample["expected"]) or (
            row["id"] == "hot200-774" and abs(actual - json.loads(sample["expected"])) < 1e-6
        )
        page.get_by_role("button", name="上一步", exact=False).click()
        assert page.locator(".dk-stage dl dt").count() > 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        if screenshots and index <= 1 and row["id"] in ("hot100-34", "hot200-269"):
            for width in (390, 1024):
                page.set_viewport_size({"width": width, "height": 820})
                page.screenshot(path=screenshots / f"{row['id']}-{width}.png")
            page.set_viewport_size({"width": 390, "height": 820})
    return len(samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--only", nargs="+", help="Limit to listed ACM identifiers")
    opts = parser.parse_args()
    if opts.screenshots:
        opts.screenshots.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 390, "height": 820}, reduced_motion="reduce")
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: errors.append(f"{page.url}: {error}"))
        checked = cases = 0
        for row, uri in demos():
            if opts.only and row["id"] not in opts.only:
                continue
            try:
                cases += check(page, row, uri, opts.screenshots)
                checked += 1
            except Exception as exc:
                errors.append(f"{row['id']}: {exc}")
        browser.close()
    if errors:
        raise AssertionError("\n".join(errors))
    print(f"{checked} published demo routes stepped in Chromium; {cases} checked outputs replayed.")


if __name__ == "__main__":
    main()
