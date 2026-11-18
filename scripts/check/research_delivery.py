"""Check the research libraries through the same static route a browser visits."""

from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.research_readers import DOCUMENTS, READER_ROOT

RESEARCH_LIBRARIES = ("ai-employment-research", "communications-research")
SOURCE_PREFIXES = (
    "library/ai-employment-research/maintenance/source_project/",
    "library/communications-research/maintained_sources/",
)
TEMPLATE = "library/communications-research/maintained_sources/frontend_src/index.html"
DASHBOARD = "/library/communications-research/index.html"


def is_package_source(relative: Path) -> bool:
    return relative.as_posix().startswith(SOURCE_PREFIXES)


def check_research_delivery(root: Path, pages):
    """Return delivered HTML for reviewed pages and findings from real local HTTP responses."""
    delivered = {}
    errors = []
    checked_links = {}
    browsers = {"Accept": "text/html"}
    client = TestClient(app)
    try:
        for source, slug in DOCUMENTS.items():
            navigation = client.get(source, headers=browsers)
            reader = READER_ROOT + slug + ".html"
            if (
                navigation.status_code != 200
                or navigation.url.path != reader
                or "text/html" not in navigation.headers.get("content-type", "")
            ):
                errors.append(f"研究文档阅读路由错误：{source} -> {reader}")
                continue
            soup = BeautifulSoup(
                navigation.content, "html.parser", from_encoding="utf8"
            )
            links = [
                urljoin(reader, a["href"]) for a in soup.select("a[download][href]")
            ]
            if source + "?download=1" not in links or not soup.find("h1"):
                errors.append(f"研究文档阅读页缺少标题或下载入口：{reader}")
            raw = root / source.lstrip("/")
            download = client.get(source + "?download=1", headers=browsers)
            if (
                not raw.is_file()
                or download.status_code != 200
                or download.content != raw.read_bytes()
            ):
                errors.append(f"研究文档原文下载不一致：{source}")
        for path in pages:
            relative = path.relative_to(root)
            parts = relative.parts
            if len(parts) < 3 or parts[0] != "library":
                continue
            # Only review the historical template that had a published URL;
            # other source copies belong to the inventory of the offline package.
            historical = relative.as_posix() == TEMPLATE
            if is_package_source(relative) and not historical:
                continue
            if not historical and parts[1] not in (
                *RESEARCH_LIBRARIES,
                "document-readers",
            ):
                continue
            url = "/" + relative.as_posix()
            response = client.get(url, headers=browsers)
            if response.status_code != 200 or "text/html" not in response.headers.get(
                "content-type", ""
            ):
                errors.append(f"研究网页访问失败：{url} -> {response.status_code}")
                continue
            if historical and response.url.path != DASHBOARD:
                errors.append(f"历史研究模板未导航至完整题库：{url}")
            delivered[path] = response.text
            soup = BeautifulSoup(response.content, "html.parser", from_encoding="utf8")
            for anchor in soup.select("a[href]"):
                raw_href = anchor["href"].strip()
                if not raw_href or raw_href.startswith("#"):
                    continue
                dest = urlsplit(urljoin(str(response.url), raw_href))
                if dest.netloc != "testserver" or dest.scheme not in {"http", "https"}:
                    continue
                address = dest.path + ("?" + dest.query if dest.query else "")
                if address not in checked_links:
                    target = client.head(address, headers=browsers)
                    checked_links[address] = (
                        target.status_code,
                        target.headers.get("content-type", ""),
                        target.url.path,
                    )
                status, mime, final = checked_links[address]
                if status != 200:
                    errors.append(
                        f"在线研究页链接失败：{url} -> {address}（HTTP {status}）"
                    )
                elif (
                    dest.path.lower().endswith(".md")
                    and not anchor.has_attr("download")
                    and ("text/html" not in mime or not final.endswith(".html"))
                ):
                    errors.append(f"在线研究页正文链接未打开阅读页：{url} -> {address}")
    finally:
        client.close()
    return delivered, errors
