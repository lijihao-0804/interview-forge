"""Render the web root twice in local Chromium and build page-family contact sheets.

Run python -m scripts.check.site_page_audit --output output/playwright/site-audit.
Only reviewed static routes and the public catalog use application code. Account
and workspace data are offline fixtures. Private archives stay outside the scan.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import html
import json
import socket
import subprocess
import tempfile
from collections import Counter, defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from interview_forge.api.routers import catalog, private_archive, static
from interview_forge.core.paths import ROOT
from interview_forge.core.web_access import (
    is_admin_path,
    is_public_get,
    is_sensitive_path,
)
from interview_forge.services import hot200, study
from interview_forge.services.annual_report import build_annual_report

WIDTHS = (2560, 390)
ALIASES = ("/", "/research/market/", "/research/jobs/", "/research/communications/")
PRIVATE = (
    "/library/agenthub/",
    "/library/development-history/",
    "/library/voltedu-study/",
)


def inventory():
    paths = [p for p in ROOT.glob("*.html") if p.is_file()]
    for name in ("books", "library", "pages", "docs", "research", "assets"):
        paths.extend((ROOT / name).rglob("*.html"))
    records = []
    for path in sorted(
        {"/" + p.relative_to(ROOT).as_posix() for p in paths} | set(ALIASES)
    ):
        parts = path.strip("/").split("/")
        family = (
            "/".join(parts[:2])
            if len(parts) > 2
            else parts[0]
            if len(parts) > 1
            else "root"
        )
        if path.startswith(PRIVATE):
            access = "private_archive_excluded"
        elif is_sensitive_path(path):
            access = "unpublished"
        else:
            access = (
                "admin_fixture"
                if is_admin_path(path)
                else "public"
                if is_public_get(path)
                else "member_fixture"
            )
        records.append({"path": path, "family": family, "access": access})
    return records


def fixture_app(study_db, private=False):
    app = FastAPI(openapi_url=None)
    bootstrap = {
        "dashboard": study.dashboard_cached(study_db),
        "daily": study.daily_data(study_db),
        "settings": study.get_settings(study_db),
        "capabilities": {"ai_coach": False},
    }
    supplement = hot200.snapshot(study_db)
    if private:
        app.include_router(private_archive.router)
    app.include_router(catalog.router)

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
    )
    def fixture(request: Request, path: str):
        member = {
            "id": 1,
            "username": "layout_fixture",
            "nickname": "测试学习者",
            "lang": "python",
            "role": "admin",
        }
        if path == "me":
            if urlsplit(request.headers.get("referer", "")).path in (
                "/pages/login.html",
                "/pages/register.html",
                "/pages/forgot-password.html",
            ):
                return JSONResponse({"error": "guest"}, status_code=401)
            return member
        if path == "report/annual":
            return build_annual_report(db_paths=[])
        if path == "bootstrap":
            return bootstrap
        if path == "hot200-extra/bootstrap":
            return supplement
        if path in {"plan", "chat/sessions", "favorites", "coach/insights/recent"}:
            return {"items": []}
        return JSONResponse(
            {"error": "layout fixture: data service unavailable"}, status_code=503
        )

    app.include_router(static.router)
    return app


METRICS = """() => {
 const doc=document.documentElement, body=document.body, text=body.innerText.trim();
 const width=doc.clientWidth, actual=Math.max(doc.scrollWidth,body.scrollWidth);
 const heading=[...document.querySelectorAll('h1')].find(e=>e.getClientRects().length);
 const offenders=actual>width+2?[...document.querySelectorAll('body *')].filter(e=>{
   const r=e.getBoundingClientRect();return r.width>0 && r.right>width+2 && !e.closest('pre,svg');
 }).slice(0,6).map(e=>e.tagName.toLowerCase()+'.'+String(e.className).slice(0,65)):[];
 return {title:document.title,h1:heading?.innerText.trim().slice(0,120)||'',width,actual,
   text_chars:text.length,styles:document.styleSheets.length,body_font:getComputedStyle(body).fontFamily,
   offenders,canvas:!!document.querySelector('canvas,svg,iframe')};
}"""


def sheets(output, rows):
    families = defaultdict(list)
    for row in rows:
        if "views" in row:
            families[row["family"]].append(row)
    folder = output / "sheets"
    folder.mkdir(exist_ok=True)
    links = []
    examples = []
    for family, pages in families.items():
        family_cards = []
        examples.extend(pages[:1])
        for start in range(0, len(pages), 42):
            batch = pages[start : start + 42]
            sheet = Image.new("RGB", (6 * 232, ((len(batch) + 5) // 6) * 115), "white")
            draw = ImageDraw.Draw(sheet)
            for i, row in enumerate(batch):
                x, y = i % 6 * 232, i // 6 * 115
                for j, view in enumerate(row["views"]):
                    image = output / view["image"]
                    with Image.open(image) as thumb:
                        thumb.thumbnail((180 if j == 0 else 46, 88))
                        sheet.paste(thumb, (x + (182 if j else 0), y))
                draw.text((x, y + 90), row["key"], fill="black")
            name = family.replace("/", "_") + f"-{start // 42 + 1}.jpg"
            sheet.save(folder / name)
            family_cards.append(
                f'<a href="sheets/{html.escape(name)}">{start + 1}–{start + len(batch)}</a>'
            )
        links.append(
            f"<details><summary>{html.escape(family)} · {len(pages)}</summary>{' · '.join(family_cards)}"
        )
        for row in pages:
            visual = "".join(
                f'<a href="{html.escape(v["image"])}">{v["viewport"]}px</a> '
                for v in row["views"]
            )
            links.append(
                f"<p><code>{row['key']}</code> {html.escape(row['path'])} {visual}</p>"
            )
        links.append("</details>")
    for start in range(0, len(examples), 24):
        batch = examples[start : start + 24]
        sheet = Image.new("RGB", (4 * 334, ((len(batch) + 3) // 4) * 192), "#eeedf6")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(batch):
            x, y = i % 4 * 334, i // 4 * 192
            for j, view in enumerate(row["views"]):
                with Image.open(output / view["image"]) as thumb:
                    thumb.thumbnail((248 if j == 0 else 75, 158))
                    sheet.paste(thumb, (x + (251 if j else 0), y))
            label = row["family"].encode("ascii", errors="replace").decode()
            draw.text((x + 4, y + 162), f"{label} · {row['key']}", fill="black")
        sheet.save(output / f"families-{start // 24 + 1}.jpg")
    (output / "index.html").write_text(
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>页面巡检清单</title>
        <style>body{background:#f2f0fa;color:#222039;font:16px/1.6 system-ui;margin:2rem auto;max-width:84rem;
        padding:0 1rem}details{background:white;border:1px solid #d9d6e6;margin:.5rem 0;padding:.7rem 1rem}
        summary{cursor:pointer;font-weight:bold}p{overflow-wrap:anywhere}a{color:#5147a7}</style>
        <h1>页面巡检清单</h1><p>展开页面家族查看联系表、路径及两种屏宽的首屏缩略图。
        逐页测量和异常记录见 <a href="pages.jsonl">JSONL</a>，汇总见 <a href="summary.json">JSON</a>。</p>"""
        + "".join(links),
        encoding="utf8",
    )


async def audit(args):
    records = inventory()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    thumbs = output / "thumbs"
    thumbs.mkdir(exist_ok=True)
    (output / "inventory.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf8"
    )
    if args.private_fixture:
        candidates = [r for r in records if r["access"] == "private_archive_excluded"]
    else:
        candidates = [
            r
            for r in records
            if r["access"] not in ("unpublished", "private_archive_excluded")
        ]
    if args.prefix:
        candidates = [
            r for r in candidates if any(r["path"].startswith(p) for p in args.prefix)
        ]
    if args.limit:
        candidates = candidates[: args.limit]
    previous = {}
    if args.retry:
        for line in (output / "pages.jsonl").read_text(encoding="utf8").splitlines():
            entry = json.loads(line)
            previous[entry["path"]] = entry
        candidates = [
            r
            for r in candidates
            if r["path"] not in previous
            or flagged(previous[r["path"]])
            or not all(v["h1"] for v in previous[r["path"]]["views"])
            or any(
                r["path"] == value
                or (
                    value != "/" and value.endswith("/") and r["path"].startswith(value)
                )
                for value in args.refresh
            )
        ]
    queue = asyncio.Queue()
    for row in candidates:
        queue.put_nowait(row)
    host = "127.0.0.1"
    with socket.socket() as listener:
        listener.bind((host, 0))
        base = f"http://{host}:{listener.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(
                fixture_app(args.study_db, args.private_fixture),
                log_level="error",
                lifespan="off",
                access_log=False,
            )
        )
        runner = asyncio.create_task(server.serve(sockets=[listener]))
        while not server.started:
            await asyncio.sleep(0.02)
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    args=[
                        "--disable-background-networking",
                        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                    ]
                )

                async def worker(log):
                    context = await browser.new_context(
                        service_workers="block", reduced_motion="reduce", locale="zh-CN"
                    )
                    if args.private_fixture:
                        await context.set_extra_http_headers(
                            {"X-Layout-Identity": "archive-owner"}
                        )

                    async def local_only(route):
                        if urlsplit(route.request.url).netloc != urlsplit(base).netloc:
                            await route.abort()
                        else:
                            await route.continue_()

                    await context.route("**/*", local_only)
                    page = await context.new_page()
                    session = await context.new_cdp_session(page)
                    errors = []
                    page.on("pageerror", lambda exc: errors.append(str(exc)[:300]))
                    while not queue.empty():
                        row = queue.get_nowait()
                        row["key"] = hashlib.sha256(row["path"].encode()).hexdigest()[
                            :12
                        ]
                        errors.clear()
                        try:
                            row["views"] = []
                            route_path = row["path"]
                            if args.private_fixture:
                                route_path = route_path.replace(
                                    "/library/agenthub/", "/api/private-archive/"
                                )
                                row["fixture_only"] = True
                                row["access_responses"] = {}
                                for role, expected in (
                                    ("guest", 401),
                                    ("member", 403),
                                    ("admin", 403),
                                ):
                                    denied = await context.request.get(
                                        base + route_path,
                                        headers={"X-Layout-Identity": role},
                                    )
                                    row["access_responses"][role] = denied.status
                                    assert denied.status == expected, (
                                        role,
                                        denied.status,
                                    )
                                    await denied.dispose()
                            for i, width in enumerate(WIDTHS):
                                height = 1000 if i == 0 else 844
                                await page.set_viewport_size(
                                    {"width": width, "height": height}
                                )
                                resp = await page.goto(
                                    base + route_path, wait_until="load", timeout=90000
                                )
                                redirected = {
                                    "/pages/ai-exam-coding.html": "/books/ai-exam/index.html",
                                    "/library/hot100/index.html": "/index.html",
                                }
                                if row["path"] in redirected:
                                    await page.wait_for_url(
                                        base + redirected[row["path"]]
                                    )
                                if row["path"] == "/pages/annual-report.html":
                                    await page.locator("h1").first.wait_for(
                                        timeout=8000
                                    )
                                is_catalog = unquote(urlsplit(page.url).path) in (
                                    "/index.html",
                                    "/library/hot200-extra/index.html",
                                )
                                if is_catalog:
                                    await page.locator("#connection.online").wait_for(
                                        timeout=12000
                                    )
                                    await page.locator(
                                        "#grid .card [data-problem-id]"
                                    ).first.wait_for(timeout=12000)
                                await page.evaluate(
                                    "new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))"
                                )
                                metrics = await page.evaluate(METRICS)
                                if is_catalog:
                                    metrics[
                                        "visible_problem_cards"
                                    ] = await page.locator(
                                        "#grid .card:visible"
                                    ).count()
                                result = await session.send(
                                    "Page.captureScreenshot",
                                    {
                                        "format": "jpeg",
                                        "quality": 65,
                                        "clip": {
                                            "x": 0,
                                            "y": 0,
                                            "width": width,
                                            "height": height,
                                            "scale": min(1, 320 / width, 180 / height),
                                        },
                                    },
                                )
                                file = thumbs / f"{row['key']}-{width}.jpg"
                                file.write_bytes(base64.b64decode(result["data"]))
                                row["views"].append(
                                    {
                                        **metrics,
                                        "viewport": width,
                                        "status": resp.status if resp else 0,
                                        "final_path": unquote(urlsplit(page.url).path),
                                        "image": file.relative_to(output).as_posix(),
                                    }
                                )
                        except (PlaywrightError, OSError, AssertionError) as exc:
                            row["error"] = str(exc)[:500]
                        row["js_errors"] = list(dict.fromkeys(errors))
                        log.write(json.dumps(row, ensure_ascii=False) + "\n")
                        log.flush()
                    await context.close()

                with (output / "pages.jsonl").open(
                    "a" if args.retry else "w", encoding="utf8"
                ) as log:
                    await asyncio.gather(*(worker(log) for _ in range(args.workers)))
                await browser.close()
        finally:
            server.should_exit = True
            await runner
    refreshed = len(candidates)
    previous.update({r["path"]: r for r in candidates})
    candidates = sorted(previous.values(), key=lambda r: r["path"])
    sheets(output, candidates)
    issues = [r["path"] for r in candidates if flagged(r)]
    revision = await asyncio.to_thread(
        subprocess.run,
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "working_tree_base": revision.stdout.strip(),
        "engine": "Chromium",
        "widths": WIDTHS,
        "family_count": len({r["family"] for r in candidates}),
        "data_mode": "synthetic archive"
        if args.private_fixture
        else "public pages and offline account fixtures",
        "refreshed_this_run": refreshed,
        "inventory": dict(Counter(r["access"] for r in records)),
        "rendered_paths": len(candidates),
        "rendered_views": sum(len(r["views"]) for r in candidates),
        "issues": issues,
        "missing_h1": [
            r["path"] for r in candidates if any(not v["h1"] for v in r["views"])
        ],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(
        f"{len(candidates)} paths, {summary['rendered_views']} views, {len(issues)} flagged, "
        f"{len(summary['missing_h1'])} without a visible H1",
        flush=True,
    )
    return int(bool(issues or summary["missing_h1"]))


def flagged(row):
    return (
        row.get("error")
        or row["js_errors"]
        or any(
            v["status"] != 200
            or v["actual"] > v["width"] + 2
            or v["text_chars"] < 5
            and not v["canvas"]
            for v in row["views"]
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Recheck missing/flagged pages and rebuild combined sheets",
    )
    parser.add_argument(
        "--refresh",
        action="append",
        default=[],
        help="With --retry, also refresh an exact path or directory",
    )
    parser.add_argument(
        "--private-fixture",
        action="store_true",
        help="Test archive gates and render synthetic content only",
    )
    args = parser.parse_args()
    identity = {"username": "layout_fixture", "role": "admin", "id": 1}
    with ExitStack() as stack:
        args.study_db = (
            Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="forge-audit-study-")
                )
            )
            / "fixture.db"
        )
        stack.enter_context(patch.object(static, "current_user", return_value=identity))
        stack.enter_context(patch.object(static, "_record_view"))
        if args.private_fixture:
            temp = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="forge-synthetic-archive-")
                )
            )
            for prop, slug in (
                ("AGENTHUB_DIR", "agenthub"),
                ("REPORT_DIR", "development-history"),
                ("VOLTEDU_DIR", "voltedu-study"),
            ):
                stack.enter_context(patch.object(private_archive, prop, temp / slug))
            for item in inventory():
                if item["access"] != "private_archive_excluded":
                    continue
                path = temp / item["path"].removeprefix("/library/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
                    <meta name="viewport" content="width=device-width,initial-scale=1"><title>合成阅读示例</title>
                    <link rel="stylesheet" href="/assets/site.css"></head><body><main class="site-shell">
                    <article class="reader-card chapter-article"><h1>合成阅读示例</h1><p>本页用于检查档案阅读器导航、排版和窄屏交互。</p>
                    <h2>章节示例</h2><p>验证目录、正文与操作栏之间的间距。</p></article></main></body></html>""",
                    encoding="utf8",
                )

            def private_identity(request):
                role = request.headers.get("X-Layout-Identity")
                if role == "guest":
                    return None
                return {
                    "id": 1,
                    "username": role or "member",
                    "is_active": 1,
                    "role": "admin" if role in ("admin", "archive-owner") else "user",
                }

            stack.enter_context(
                patch.object(private_archive.support, "current_user", private_identity)
            )
            stack.enter_context(
                patch.object(
                    private_archive,
                    "server_runtime",
                    SimpleNamespace(PERMANENT_ADMIN_USERNAME="archive-owner"),
                )
            )
        raise SystemExit(asyncio.run(audit(args)))
