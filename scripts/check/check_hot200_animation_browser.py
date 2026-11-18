"""Visit the published Hot 200 lesson in Chrome and compare each rendered frame to its source."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from scripts.build.hot200_execution_traces import FENCE, multiline_statements, sections, supplement
from scripts.check.hot200_graph_answers import check_graph
from scripts.check.check_hot100_animation_browser import CONTROL_LAYOUT, FRAME, ROOT, VIEWPORTS, shot, site

SEQUENCE = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")


def reference(row):
    pid = int(row["id"].split("-")[1])
    path = ROOT / f"books/hot200-extra/solutions/{pid}.md"
    code = FENCE.search(sections(path.read_text(encoding="utf-8-sig"))["Python"])[2]
    cases = [supplement(pid, path, code, sample) for sample in row["samples"]]
    lines = code.splitlines()
    return {"cases": cases, "source": lines, "statements": multiline_statements(code, set(range(1, len(lines)+1)))}


async def visit(page, row, ref, base, width, evidence):
    result = {"id": row["id"], "title": row["title"], "viewport": [width, VIEWPORTS[width]],
              "solution": row["solution_url"], "examples": [], "issues": []}
    errors = []
    def on_error(error):
        errors.append(str(error))
    page.on("pageerror", on_error)
    try:
        response = await page.goto(urljoin(base, row["solution_url"]), wait_until="domcontentloaded")
        assert response and response.ok, f"lesson HTTP {response.status if response else 'unknown'}"
        host = page.locator(FRAME)
        await host.scroll_into_view_if_needed()
        frame = await (await host.element_handle()).content_frame()
        await frame.locator(".dk-select").wait_for()
        assert await frame.evaluate("String(Hot200Execution.id)") == row["id"].split("-")[1]
        result["demo"] = frame.url
        graph = await frame.locator("#problemExample").text_content()
        graph = json.loads(graph)
        assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
        control = frame.locator(".dk-select")
        labels = await control.locator("option").all_text_contents()
        assert len(labels) == len(row["samples"]) + 1
        for i, label in enumerate(labels):
            await control.select_option(index=i)
            first_image = None
            if evidence:
                folder = evidence / row["id"] / str(width)
                folder.mkdir(parents=True, exist_ok=True)
                if i == 0:
                    result["lesson_capture"] = await shot(page, folder, "lesson", False)
                first = await shot(frame.locator(".dk-stage"), folder, f"{i}-start", True)
                first_image = str((folder / f"{i}-start.png").relative_to(evidence)), first["sha256"]
            await frame.get_by_role("button", name=re.compile("下一步")).click()
            await frame.get_by_role("button", name=re.compile("上一步")).click()
            await frame.get_by_role("button", name=re.compile("自动播放")).click()
            assert await frame.evaluate("window.__dk.idx > 0"), "play did not advance"
            await frame.get_by_role("button", name=re.compile("重置")).click()
            assert await frame.evaluate("window.__dk.idx === 0"), "reset did not restore the first step"
            entry = await frame.evaluate(SEQUENCE, {"graph": graph if i == 0 else None,
                "sample": ref["cases"][i-1] if i else None, "source": ref["source"], "statements": ref["statements"]})
            entry["label"] = label
            if not i:
                entry["expected"], issues = check_graph(int(graph["no"]), entry["history"])
                entry["issues"].extend(issues)
            if i:
                wanted = json.loads(row["samples"][i-1]["expected"])
                entry["expected"] = wanted
                actual = entry["actual"]
                assert (math.isclose(actual, wanted, abs_tol=1e-6) if row["id"] == "hot200-774"
                        else actual == wanted and type(actual) is type(wanted)), f"{actual!r} != {wanted!r}"
            for _ in range(8):
                await frame.evaluate("() => new Promise(r=>requestAnimationFrame(r))")
                layout = await frame.evaluate(CONTROL_LAYOUT)
                if not layout:
                    break
            entry["issues"].extend(layout)
            if evidence:
                entry["start_screenshot"], entry["start_sha256"] = first_image
                last = await shot(frame.locator("body"), folder, f"{i}-end", True)
                entry["screenshot"] = str((folder / f"{i}-end.png").relative_to(evidence))
                entry["sha256"] = last["sha256"]
            result["examples"].append(entry)
            result["issues"].extend(f"{label}: {e}" for e in entry["issues"])
    except Exception as exc:
        result["issues"].append(str(exc) or repr(exc))
    finally:
        page.remove_listener("pageerror", on_error)
    result["issues"].extend(errors)
    return result


async def sweep(base, opts):
    rows = json.loads((ROOT / "data/acm/hot200-extra.json").read_bytes())
    if opts.only:
        rows = [r for r in rows if r["id"].split("-")[1] in opts.only]
        assert len(rows) == len(set(opts.only))
    refs = {r["id"]: reference(r) for r in rows}
    opts.report.parent.mkdir(parents=True, exist_ok=True)
    failures = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome")
        storage = None
        if opts.credentials:
            assert base.startswith("https://hot100.xyz/")
            account = json.loads(opts.credentials.read_text(encoding="utf-8-sig"))
            auth = await pw.request.new_context(base_url=base)
            signed = await auth.post("/api/login", data={k:account[k] for k in ("username","password")})
            assert signed.ok, f"sign-in HTTP {signed.status}"
            assert (await (await auth.get("/api/me")).json()).get("effective_role") == "user"
            storage = await auth.storage_state()
            await auth.dispose()
        async def run_width(width, out):
            nonlocal failures
            ctx = await browser.new_context(storage_state=storage, viewport={"width":width,"height":VIEWPORTS[width]},
                is_mobile=width==390, has_touch=width==390, reduced_motion="reduce" if width==390 else "no-preference")
            page = await ctx.new_page()
            page.set_default_timeout(12000)
            for row in rows:
                record = await visit(page, row, refs[row["id"]], base, width, opts.evidence)
                if record["issues"]:
                    failures += 1
                out.write(json.dumps(record, ensure_ascii=False)+"\n")
                out.flush()
                if opts.base_url:
                    await asyncio.sleep(.35)
            await ctx.close()
        with opts.report.open("x", encoding="utf-8") as out:
            await asyncio.gather(*(run_width(w, out) for w in VIEWPORTS))
        await browser.close()
    print(f"{len(rows)*len(VIEWPORTS)} visits, {failures} with issues: {opts.report}")
    return int(bool(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    if os.environ.get("PYTHONHASHSEED") != "0":
        import subprocess
        sys.exit(subprocess.call([sys.executable, "-m", "scripts.check.check_hot200_animation_browser", *sys.argv[1:]],
                                 env={**os.environ, "PYTHONHASHSEED":"0"}))
    with site(args.base_url) as origin:
        sys.exit(asyncio.run(sweep(origin, args)))
