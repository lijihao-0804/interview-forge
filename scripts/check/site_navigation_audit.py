"""Inventory navigable links from published HTML after the server's delivery rewrites."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from interview_forge.api.routers.static import _inject_html
from interview_forge.core.paths import ROOT
from interview_forge.core.web_access import is_sensitive_path
from scripts.check.site_page_audit import PRIVATE, inventory
from scripts.check.server_page_links import is_registered_server_page

ORIGIN = "http://localhost"
ALIASES = {
    "/": "/cockpit.html",
    "/research/market/": "/research/market/index.html",
    "/research/jobs/": "/library/ai-employment-research/index.html",
    "/research/communications/": "/library/communications-research/index.html",
    "/library/communications-research/maintained_sources/frontend_src/index.html": "/library/communications-research/index.html",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a":
            if attrs.get("name"):
                self.ids.add(attrs["name"])
            if attrs.get("href"):
                self.links.append(attrs["href"])


@lru_cache(maxsize=None)
def resolve(path):
    if path.startswith(("/research/jobs/", "/research/communications/")):
        prefix, destination = (
            ("/research/jobs/", "/library/ai-employment-research/")
            if path.startswith("/research/jobs/")
            else ("/research/communications/", "/library/communications-research/")
        )
        path = destination + (path.removeprefix(prefix) or "index.html")
    path = ALIASES.get(path, path)
    if path.startswith(PRIVATE) or is_registered_server_page(path):
        return "protected", path
    if path.startswith("/api/"):
        return "application-endpoint", path
    if is_sensitive_path(path):
        return "restricted", path
    return ("file" if (ROOT / path.lstrip("/")).is_file() else "missing"), path


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    routes = inventory()
    pages = {}
    for entry in routes:
        if entry["access"] in ("private_archive_excluded", "unpublished"):
            continue
        path = ALIASES.get(entry["path"], entry["path"])
        if path in pages:
            continue
        parser = Links()
        parser.feed(
            _inject_html(path, (ROOT / path.lstrip("/")).read_bytes()).decode(
                "utf-8-sig"
            )
        )
        parser.close()
        pages[path] = parser
    totals = Counter()
    examples = {}
    bad = {}
    with (output / "links.jsonl").open("w", encoding="utf8") as log:
        for path, parser in pages.items():
            seen = Counter()
            for href in parser.links:
                target = urlsplit(urljoin(ORIGIN + path, href))
                if (target.scheme, target.netloc) != ("http", "localhost"):
                    kind = "external-or-protocol"
                else:
                    kind, final = resolve(unquote(target.path))
                    fragment = unquote(target.fragment)
                    if (
                        kind == "file"
                        and fragment
                        and final in pages
                        and fragment in pages[final].ids
                    ):
                        kind = "fragment"
                    elif (
                        kind == "file"
                        and final == "/library/ai-employment-research/index.html"
                        and fragment
                        in ("view=overview", "view=research", "view=explore")
                        and fragment.removeprefix("view=") in pages[final].ids
                    ):
                        kind = "research-tab"
                    elif kind == "file" and fragment and final in pages:
                        kind = "fragment-needs-runtime"
                    if kind in {
                        "missing",
                        "restricted",
                        "fragment-needs-runtime",
                        "application-endpoint",
                    }:
                        key = kind, final + ("#" + fragment if fragment else "")
                        record = bad.setdefault(
                            key,
                            {
                                "kind": kind,
                                "target": key[1],
                                "occurrences": 0,
                                "examples": [],
                            },
                        )
                        record["occurrences"] += 1
                        if (
                            len(record["examples"]) < 3
                            and path not in record["examples"]
                        ):
                            record["examples"].append(path)
                totals[kind] += 1
                seen[kind] += 1
                examples.setdefault(kind, {"source": path, "href": href})
            log.write(
                json.dumps({"path": path, "counts": seen}, ensure_ascii=False) + "\n"
            )
    report = {
        "rendered_html_sources": len(pages),
        "aliases": ALIASES,
        "anchor_occurrences": sum(totals.values()),
        "counts": totals,
        "examples": examples,
        "review": list(bad.values()),
    }
    (output / "navigation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
    )
    print(len(pages), sum(totals.values()), dict(totals))
    return int(
        any(
            totals[kind]
            for kind in (
                "missing",
                "restricted",
                "fragment-needs-runtime",
                "application-endpoint",
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
