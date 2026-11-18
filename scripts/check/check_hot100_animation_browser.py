"""Exercise Hot 100 animations inside their published solution pages in Chrome.

Run directly for local HTTP, or supply --base-url to verify a running site.
An optional JSON credentials file has the same username/password fields as the
normal sign-in form. Credentials and session cookies stay out of the report.
"""
import argparse
import asyncio
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import re
from threading import Thread
from urllib.parse import urljoin

from playwright.async_api import async_playwright, expect
try:
    from .hot100_graph_answers import compare_output
except ImportError:  # Running this file directly.
    from hot100_graph_answers import compare_output


ROOT = Path(__file__).resolve().parents[2]
VIEWPORTS = {390: 844, 2560: 1440}
FRAME = "iframe.reader-visual-frame"
NEXT = "button.dk-btn:has-text('下一步'):visible, .btn-next:visible, #nextBtn:visible"
PREVIOUS = "button.dk-btn:has-text('上一步'):visible, .btn-prev:visible, #prevBtn:visible"
DESCRIPTION = ".dk-desc:visible, .panel.active .vis-msg:visible, #desc1:visible"
SIZE = "#app select.dk-select:visible, .panel.active .preset-select:visible, #exampleSelect:visible"


class QuietFiles(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass


class LocalSite(ThreadingHTTPServer):
    request_queue_size = 64


@contextmanager
def site(base_url):
    if base_url:
        yield base_url.rstrip("/") + "/"
        return
    with LocalSite(("127.0.0.1", 0), partial(QuietFiles, directory=ROOT)) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/"
        finally:
            server.shutdown()
            worker.join()


def checked_examples(pid):
    # Local artifacts are regenerated from the reviewed, executed Hot 100
    # reference tests by scripts.build.hot200_execution_traces --check.
    path = ROOT / f"books/hot100/executions/{pid}.js"
    return json.loads(path.read_text(encoding="utf-8").removeprefix(
        "window.Hot200Execution=").strip().removesuffix(";"))["cases"]


# Keep the viewport of the *iframe* and its overflow-clipping ancestors in
# the calculation. Playwright can opportunistically scroll a scrolling="no"
# frame to click an otherwise permanently clipped control.
CONTROL_LAYOUT = """() => {
    const controls = [...document.querySelectorAll(
        'button, select, a[href], input, .preset-btn'
    )].filter(n => n.getClientRects().length && n.offsetWidth && n.offsetHeight);
    const issues = [], host = window.frameElement;
    const originalY = parent.scrollY;
    for (const node of controls) {
        const r = node.getBoundingClientRect();
        const name = node.getAttribute('aria-label') || node.textContent.trim().slice(0, 28) ||
                     node.id || node.className;
        const clipped = r.left + scrollX < -2 || r.right + scrollX > innerWidth + 2 ||
                        r.top + scrollY < -2 || r.bottom + scrollY > innerHeight + 2;
        if (clipped) issues.push(name + ' clipped by iframe');
        const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
        if (x >= 0 && x < innerWidth && y >= 0 && y < innerHeight) {
            const hit = document.elementFromPoint(x, y);
            if (hit && !node.contains(hit) && !hit.contains(node)) issues.push(name + ' covered by ' +
                (hit.id || hit.className || hit.tagName));
            // Move the parent just as a reader could. A permanently covered
            // target fails even when the iframe's own hit test succeeds.
            const exposed = [.5, .32, .68].some(fraction => {
                const at = host.getBoundingClientRect();
                parent.scrollBy({top:at.top + host.clientTop + y - parent.innerHeight * fraction,
                                 behavior:'instant'});
                const box = host.getBoundingClientRect();
                return parent.document.elementFromPoint(box.left + host.clientLeft + x,
                    box.top + host.clientTop + y) === host;
            });
            if (!exposed) issues.push(name + ' covered in parent page');
        }
    }
    parent.scrollTo({top:originalY, behavior:'instant'});
    return [...new Set(issues)];
}"""


# Use each player's real next button for the full sequence. A separate
# Playwright click and keyboard round-trip cover physical input and hit testing.
# Waiting for a swap only when a transition actually blocks the button keeps
# ordinary steps fast. Reading after two animation frames lets the child's
# size message and the reader's height update settle before checking geometry.
GRAPH_SEQUENCE = """async pid => {
    const visible = s => [...document.querySelectorAll(s)].find(n => n.offsetWidth && n.offsetHeight);
    const next = [...document.querySelectorAll('.dk-btn')].find(
        n => n.offsetWidth && n.textContent.includes('下一步')) || visible('.btn-next, #nextBtn');
    const last = [...document.querySelectorAll('.dk-btn')].find(
        n => n.offsetWidth && n.textContent.includes('末尾')) || visible('.btn-last');
    const description = () => visible('.dk-desc, .panel.active .vis-msg, #desc1')?.innerText.trim();
    const stage = () => visible('.dk-stage, .panel.active .vis-canvas-wrap, #dpContainer1');
    const status = () => (window.__dk && window.__dk.idx + '/' + window.__dk.steps.length) ||
        visible('.panel.active .step-info')?.textContent.trim() ||
        [description(), visible('#itemDesc1')?.textContent, visible('#jDesc1')?.textContent].join('/');
    const settled = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const bars = () => [...(stage()?.querySelectorAll('.bar-label') || [])].map(e => Number(e.textContent));
    const matrix = () => [...(stage()?.querySelectorAll('table tr') || [])].map(r =>
        [...r.querySelectorAll('td')].map(e => e.innerText.trim()).filter(x => /^-?\\d+$/.test(x)).map(Number)
    ).filter(r => r.length);
    const initial = description(), descriptions = new Set();
    const inputBars = bars(), inputMatrix = matrix(), history = [];
    const shapes = new Set();
    let constructed = 0, filledCells = 0;
    const faults = [], footprint = new Map();
    const toolbarFits = () => next.parentElement.getBoundingClientRect().bottom + scrollY <= innerHeight + 2;
    async function settleToolbar() {
        // Child ResizeObserver -> child RAF -> parent message -> parent RAF.
        // Wait only after a change which could move the controls out of view.
        for (let frame = 0; frame < 10 && !toolbarFits(); frame++) await settled();
        return toolbarFits();
    }
    let count = 0, previous = null;
    while (true) {
        const why = description() || '';
        if (['146','155','295','141'].includes(pid)) history.push(why);
        if (!why) faults.push('empty explanation at step ' + count);
        if (pid === '105' || pid === '108') {
            const attached = why.match(/(?:现在树上有|树上已有) (\\d+) 个节点/);
            if (attached) {
                constructed++;
                const n = stage().querySelectorAll('svg g:has(>circle)').length;
                if (n !== Number(attached[1])) faults.push('tree shows ' + n +
                    ' nodes when the explanation has attached ' + attached[1]);
            }
        }
        if (pid === '114' || pid === '226') {
            const labels = [...stage().querySelectorAll('svg g:has(>circle)')].map(g => {
                const c = g.querySelector('circle');
                return [g.querySelector('text').textContent,c.getAttribute('cx'),c.getAttribute('cy')];
            });
            shapes.add(JSON.stringify(labels));
        }
        if (pid === '64') {
            const cells = matrix().flat().length;
            if (cells < filledCells || cells > filledCells + 1)
                faults.push('DP table reveals future values at step ' + count);
            filledCells = cells;
        }
        descriptions.add(why.replace(/^\\d+\\.\\s*/, ''));
        const current = status();
        count++;
        if (count > 2000) throw new Error('player did not terminate after 2000 steps');
        const info = visible('.panel.active .step-info')?.textContent || '';
        const index = info.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
        const end = !next || (next.disabled && (!last || last.disabled) &&
            (!index || Number(index[1]) === Number(index[2])));
        if (end || current === previous) {
            if (!end) faults.push('next did not advance at ' + status());
            break;
        }
        if (next.disabled) {
            const until = performance.now() + 950;
            while (next.disabled && performance.now() < until) {
                await new Promise(resolve => setTimeout(resolve, 35));
            }
            if (next.disabled) { faults.push('next stayed disabled at ' + status()); break; }
        }
        if (!window.__dk) {
            if (!toolbarFits() && !footprint.has('toolbar') && !await settleToolbar())
                footprint.set('toolbar', 'toolbar extends beyond iframe at ' + status());
        }
        previous = current;
        next.click();
    }
    await settled();
    if (!await settleToolbar()) footprint.set('toolbar', 'final toolbar extends beyond iframe');
    if (!stage()) faults.push('no graphical stage');
    if ((pid === '105' || pid === '108') && constructed < 3) faults.push('missing incremental tree states');
    if ((pid === '114' || pid === '226') && shapes.size < 3) faults.push('tree structure never progressed');
    if (count > 1 && descriptions.size < 2) faults.push('explanation never changed');
    const descNode = visible('.dk-desc');
    if (descNode && descNode.scrollHeight > descNode.clientHeight + 2)
        faults.push('current explanation is vertically clipped');
    const label = stage()?.querySelector('svg g:has(>circle) text');
    if (label && parseFloat(getComputedStyle(label).fontSize) * label.getScreenCTM().a < 10.5)
        faults.push('tree node labels smaller than 10.5 CSS pixels');
    const box = stage();
    if (pid === '51') {
        const list = box.querySelector('.results-scroll'), board = list?.querySelector('.result-item');
        if (board && board.getBoundingClientRect().height > list.clientHeight + 1)
            faults.push('one N-queens solution board is taller than the result panel');
    }
    let tree = null;
    if (['105', '108', '114', '226'].includes(pid) && box) {
        const nodes = [...box.querySelectorAll('svg g:has(>circle)')].map(g => ({
            x: Number(g.querySelector('circle').getAttribute('cx')),
            y: Number(g.querySelector('circle').getAttribute('cy')), v: Number(g.querySelector('text').textContent)
        }));
        const byX = new Map(nodes.map(n => [n.x, n]));
        for (const edge of box.querySelectorAll('svg line')) {
            const p = byX.get(Number(edge.getAttribute('x1'))), c = byX.get(Number(edge.getAttribute('x2')));
            if (!p || !c || p.y >= c.y) throw new Error('unattached visible tree edge');
            p[c.x < p.x ? 'left' : 'right'] = c;
        }
        if (!nodes.length) throw new Error('tree output is empty');
        const queue = [nodes.slice().sort((a,b) => a.y-b.y)[0]];
        tree = [];
        while (queue.length) {
            const n = queue.shift(); tree.push(n ? n.v : null);
            if (n) queue.push(n.left, n.right);
            if (tree.length > nodes.length * 2 + 1) throw new Error('cycle in visible tree');
        }
        while (tree.at(-1) === null) tree.pop();
        if (tree.filter(v => v !== null).length !== nodes.length) throw new Error('detached visible node');
    }
    return {steps:count, descriptions:descriptions.size, start:initial, end:description(),
        state:box?.innerText.trim() || '', inputBars, bars:bars(), matrix:matrix(), inputMatrix,
        items:[...(box?.querySelectorAll('.result-item') || [])].map(e => e.innerText.trim()),
        tree, history, issues:[...new Set(faults), ...footprint.values()]};
}"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


async def shot(element, folder, name, isolate_figure=False):
    path = folder / (name + ".png")
    # Parent fixed-position reading progress is always at the viewport's top.
    # A stitched frame-only screenshot would paint it over the middle of the
    # figure. Keep the unaltered viewport screenshot as the separate page record.
    style = (".read-progress,.if-ai-launcher,#forge-auth-pill,#forge-theme-btn,#forge-fb-btn"
             "{visibility:hidden!important}") if isolate_figure else None
    data = await element.screenshot(path=path, animations="disabled", style=style)
    return {"path": path.relative_to(folder.parent).as_posix(), "sha256": digest(data)}


async def graph_options(frame, pid):
    modes = frame.locator(SIZE).first
    presets = frame.locator(".panel.active .preset-btn:visible")
    if pid == "208":
        sizes = frame.locator(".panel.active .size-select:visible")
        actions = frame.locator(".panel.active .action-select:visible")
        for size in await sizes.locator("option").evaluate_all("(o) => o.map(x => x.value)"):
            await sizes.select_option(size)
            for i, text in enumerate(await actions.locator("option").all_inner_texts()):
                await actions.select_option(index=i)
                yield i, text, int(size)
    elif await modes.count():
        for i, text in enumerate(await modes.locator("option").all_inner_texts()):
            await modes.select_option(index=i)
            yield i, text, None
    elif await presets.count():
        for i, text in enumerate(await presets.all_inner_texts()):
            await presets.nth(i).click()
            yield i, text, None
    else:
        yield 0, "默认", None


async def graphic(frame, pid, folder=None):
    problems = []
    nxt, prev, desc = (frame.locator(s).first for s in (NEXT, PREVIOUS, DESCRIPTION))
    await nxt.wait_for()
    assert await prev.is_disabled(), "previous enabled at the opening step"
    opening = await desc.inner_text()
    await nxt.click()
    assert await desc.inner_text() != opening, "next did not update the explanation"
    await prev.focus()
    await prev.press("Enter")
    assert await desc.inner_text() == opening, "previous did not restore the opening step"
    play = frame.locator(".dk-btn.primary:visible, .btn-auto:visible, #playBtn:visible").first
    await play.click()
    await expect(prev).to_be_enabled()
    await frame.wait_for_function("""opening => [...document.querySelectorAll(
        '.dk-desc, .panel.active .vis-msg, #desc1')].some(n =>
        n.offsetWidth && n.innerText.trim() !== opening.trim())""", arg=opening)
    if "暂停" in await play.inner_text():
        await play.click()
    first = frame.locator(".btn-first:visible, #resetBtn:visible").or_(
        frame.get_by_role("button", name=re.compile("开头"))).first
    await first.click()
    assert await desc.inner_text() == opening, "reset did not restore the start after autoplay"
    outputs = []
    async for i, option, word_count in graph_options(frame, pid):
        assert await prev.is_disabled(), f"{option}: sample did not start at the beginning"
        result = await frame.evaluate(GRAPH_SEQUENCE, pid)
        if word_count is not None:
            result["word_count"] = word_count
        if result["inputBars"] or result["inputMatrix"]:
            result["graphical_input"] = result["inputBars"] or result["inputMatrix"]
        try:
            actual, expected = compare_output(int(pid), i, option, result)
            result["actual"], result["expected"] = actual, expected
            if actual != expected or type(actual) is not type(expected):
                result["issues"].append(f"visible output {actual!r}, expected {expected!r}")
        except (AssertionError, ValueError, TypeError, KeyError, IndexError) as exc:
            result["issues"].append(f"could not verify graphical output: {exc}")
        for field in ("inputBars", "bars", "matrix", "inputMatrix", "items", "tree", "history"):
            result.pop(field)
        result["state"] = result["state"][:430]
        result["example"] = option if word_count is None else f"{word_count} 个词 · {option}"
        if folder:
            result["screenshot"] = await shot(frame.locator("body"), folder, f"graph-{len(outputs)+1}", True)
        problems.extend(f"{option}: {item}" for item in result.pop("issues"))
        outputs.append(result)
    if not outputs:
        problems.append("no graphical examples were exercised")
    if pid == "208" and {r["word_count"] for r in outputs} != {4, 6, 8, 10}:
        problems.append("did not exercise all four Trie dictionaries")
    problems.extend(await frame.evaluate(CONTROL_LAYOUT))
    return outputs, sorted(set(problems))


async def traces(frame, row, folder=None, report=None):
    pid = int(row["id"].split("-")[1])
    expected = checked_examples(pid)
    # Where the site publishes the same input as an ACM fixture, verify against
    # that separate expected value as well as the checked reference trace.
    acm = {s["input"].strip(): json.loads(s["expected"]) for s in row["samples"]}
    async with frame.page.expect_response(lambda res: res.url.split("?")[0].endswith(
            f"/books/hot100/executions/{pid}.js")) as downloaded:
        await frame.locator(".hot100-trace-switch").click()
    payload = await downloaded.value
    assert payload.ok, f"trace data HTTP {payload.status}"
    if report is not None:
        report["trace_script_sha256"] = digest(await payload.body())
        report["trace_url"] = frame.url
    control = frame.get_by_role("combobox", name="演示输入")
    await frame.locator(".dk-stage pre").wait_for()
    assert await frame.evaluate("Hot200Execution.id") == pid, "opened another problem's replay"
    labels = await control.locator("option").all_inner_texts() if await control.count() else [expected[0]["label"]]
    assert labels == [s["label"] for s in expected], "replay example labels differ"
    details, issues = [], []
    next_button = frame.locator(NEXT).first
    previous = frame.locator(PREVIOUS).first
    end = frame.get_by_role("button", name=re.compile("末尾"))
    stage = frame.locator(".dk-stage")
    for i, sample in enumerate(expected):
        if await control.count():
            await control.select_option(index=i)
        assert await previous.is_disabled(), "example did not restart"
        stdin = await stage.locator("pre").inner_text()
        assert stdin == sample["input"], f"input mismatch for {sample['label']}"
        case = {"example": sample["label"], "input": stdin, "input_sha256": digest(stdin.encode())}
        if folder:
            case["input_screenshot"] = await shot(stage, folder, f"case-{i+1}-input", True)
        await next_button.click()
        assert await stage.locator(".dk-trace-vars dt").count() > 0, "missing execution variables"
        await previous.press("Enter")
        assert await stage.locator("pre").inner_text() == sample["input"], "return to input failed"
        await end.click()
        actual = json.loads(await stage.locator("pre").inner_text())
        assert actual == sample["output"], f"{sample['label']}: output differs from reference"
        if sample["input"] in acm:
            assert actual == acm[sample["input"]], f"{sample['label']}: output differs from ACM fixture"
        assert await next_button.is_disabled(), "next enabled after final output"
        issues.extend(await frame.evaluate(CONTROL_LAYOUT))
        encoded = json.dumps(actual, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        case.update(steps=len(sample["steps"]) + 2, output=actual, expected=sample["output"], output_sha256=digest(encoded))
        if folder:
            case["output_screenshot"] = await shot(stage, folder, f"case-{i+1}-output", True)
        details.append(case)
    await frame.get_by_role("link", name="返回图形演示").click()
    await frame.locator(".hot100-trace-switch").wait_for()
    return details, sorted(set(issues))


async def check(page, row, width, base, opts):
    pid = row["id"].split("-")[1]
    result = {"id": row["id"], "viewport": width, "graph": [], "traces": [], "issues": []}
    folder = opts.evidence_dir / f"{row['id']}-{width}" if opts.evidence_dir else None
    if folder:
        folder.mkdir(parents=True, exist_ok=True)
    errors = []
    def on_error(error):
        errors.append(str(error))
    page.on("pageerror", on_error)
    try:
        response = await page.goto(urljoin(base, row["solution_url"]), wait_until="domcontentloaded")
        assert response and response.ok, f"solution HTTP {response.status if response else 'unavailable'}"
        embed = page.locator(FRAME)
        await embed.scroll_into_view_if_needed()
        frame = await (await embed.element_handle()).content_frame()
        await frame.locator(".hot100-trace-switch").wait_for()
        assert frame.parent_frame == page.main_frame and await embed.is_visible(), "missing normal iframe"
        assert await frame.locator(".hot100-trace-switch").get_attribute("href") == \
            f"assets/checked-example.html?problem={pid}", "graph route belongs to another problem"
        result["frame_width"] = await frame.evaluate("innerWidth")
        result.update(solution_url=page.url, graphical_url=frame.url, height=VIEWPORTS[width])
        if folder:
            await frame.locator(DESCRIPTION).first.evaluate("n => n.scrollIntoView({block:'center', behavior:'instant'})")
            result["solution_screenshot"] = await shot(page, folder, "solution")
        assert result["frame_width"] <= width, "iframe overflows parent horizontally"
        for key, run in (("graph", lambda: graphic(frame, pid, folder)), ("traces", lambda: traces(frame, row, folder, result))):
            try:
                result[key], issues = await run()
                result["issues"].extend(f"{key}: {msg}" for msg in issues)
            except Exception as exc:
                result["issues"].append(f"{key}: {str(exc)[:1000]}")
        if opts.screenshots and (row["id"] in opts.screenshot_ids or result["issues"]):
            await embed.scroll_into_view_if_needed()
            await page.screenshot(path=opts.screenshots / f"{row['id']}-{width}.png")
    except Exception as exc:
        result["issues"].append(str(exc)[:1000])
    finally:
        page.remove_listener("pageerror", on_error)
    result["issues"].extend("JavaScript: " + err for err in errors)
    return result


async def sweep(base, opts):
    rows = json.loads((ROOT / "data/acm/hot100.json").read_bytes())
    assert len(rows) == len({r["id"] for r in rows}) == 100
    if opts.only:
        rows = [row for row in rows if row["id"].split("-")[1] in opts.only]
        assert len(rows) == len(set(opts.only)), "unknown problem ID"
    if opts.screenshots:
        opts.screenshots.mkdir(parents=True, exist_ok=True)
    if opts.report:
        opts.report.parent.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome")
        storage = None
        if opts.credentials:
            assert opts.base_url, "credentials require an explicit --base-url"
            account = json.loads(opts.credentials.read_text(encoding="utf-8-sig"))
            auth = await pw.request.new_context(base_url=base)
            response = await auth.post("/api/login", data={k: account[k] for k in ("username", "password")})
            assert response.ok, f"sign in failed (HTTP {response.status})"
            user = await auth.get("/api/me")
            assert user.ok and (await user.json()).get("effective_role") == "user", \
                "authenticated sweep requires an ordinary user account"
            storage = await auth.storage_state()
            await auth.dispose()
        contexts = {w: await browser.new_context(storage_state=storage,
                    viewport={"width": w, "height": VIEWPORTS[w]}, has_touch=w == 390,
                    is_mobile=w == 390, reduced_motion="reduce" if w == 390 else "no-preference")
                    for w in opts.widths}
        queue = asyncio.Queue()
        for row in rows:
            for width in opts.widths:
                queue.put_nowait((row, width))

        async def worker():
            pages = {}
            while not queue.empty():
                row, width = queue.get_nowait()
                if width not in pages:
                    pages[width] = await contexts[width].new_page()
                    pages[width].set_default_timeout(opts.timeout * 1000)
                result = await check(pages[width], row, width, base, opts)
                transient = [msg for msg in result["issues"] if
                             "Timeout " in msg or "net::ERR_" in msg or "HTTP 5" in msg]
                if transient:
                    await pages[width].close()
                    pages[width] = await contexts[width].new_page()
                    pages[width].set_default_timeout(opts.timeout * 1000)
                    result = await check(pages[width], row, width, base, opts)
                    result["first_attempt"] = transient
                results.append(result)
                if opts.report:
                    with opts.report.open("a", encoding="utf-8") as out:
                        out.write(json.dumps(result, ensure_ascii=False) + "\n")
                if result["issues"]:
                    print(row["id"], width, "; ".join(result["issues"])[:200], flush=True)
            for page in pages.values():
                await page.close()

        await asyncio.gather(*(worker() for _ in range(opts.jobs)))
        await browser.close()
    print(f"{len(results)} embedded solution visits, {sum(len(r['graph']) for r in results)} graphical "
          f"examples, {sum(len(r['traces']) for r in results)} checked execution outputs, "
          f"{sum(bool(r['issues']) for r in results)} visits with issues")
    return any(result["issues"] for result in results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--only", nargs="+", help="Limit to numerical LeetCode IDs")
    parser.add_argument("--widths", nargs="+", type=int, choices=VIEWPORTS, default=list(VIEWPORTS))
    parser.add_argument("--report", type=Path, help="Append a JSON record for each lesson and viewport")
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--evidence-dir", type=Path, help="Capture every example's actual output, screenshot and SHA-256")
    parser.add_argument("--screenshot-ids", nargs="+", default=["hot100-34", "hot100-46", "hot100-416"])
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=3)
    parser.add_argument("--timeout", type=int, default=8, help="Interaction timeout in seconds")
    opts = parser.parse_args()
    with site(opts.base_url) as base:
        return asyncio.run(sweep(base, opts))


if __name__ == "__main__":
    raise SystemExit(main())
