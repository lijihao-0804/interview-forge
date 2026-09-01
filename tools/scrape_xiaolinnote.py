"""抓取小林面试笔记的必看系列，转换为本地 Markdown 并下载图片。"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "books" / "小林面试笔记AI"
IMAGE_DIR = OUT_DIR / "images"

SITEMAP_URL = "https://xiaolinnote.com/sitemap.xml"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

# 系列目录名 -> (标题, 路径前缀)
SERIES = [
    ("agent", "Agent 面试题", "/ai/agent/"),
    ("rag", "RAG 面试题", "/ai/rag/"),
    ("tools", "LLM 工具调用面试题", "/ai/tools/"),
    ("llm", "大模型工程面试题", "/ai/llm/"),
    ("langchain", "LangChain 框架面试题", "/ai/langchain/"),
    ("tujie-agent", "图解 Agent", "/agent/"),
    ("tujie-claude-code", "图解 Claude Code", "/claudecode/"),
]

SKIP_IMAGE_HINTS = ("logo", "扫码", "二维码", "qrcode", "wechat", "公众号")


def fetch(url: str, timeout: int = 30) -> bytes:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(url, headers=HEADERS)
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - 网络重试需要兜底
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"fetch failed: {url}: {last_error}")


def collect_pages() -> dict[str, list[str]]:
    locs = re.findall(r"<loc>(.*?)</loc>", fetch(SITEMAP_URL).decode("utf-8", "ignore"))
    pages: dict[str, list[str]] = {key: [] for key, _, _ in SERIES}
    for url in locs:
        path = urlparse(url).path
        if not path.endswith(".html"):
            continue
        for key, _, prefix in SERIES:
            if not path.startswith(prefix):
                continue
            if "/ai/" in path and "_info" in path:
                continue
            pages[key].append(url)
            break
    for key in ("agent", "rag", "tools", "llm", "langchain"):
        pages[key].sort(
            key=lambda url: (
                int(match.group(1))
                if (match := re.search(r"/(\d+)_[^/]*\.html$", urlparse(url).path))
                else 999
            )
        )
    return pages


def content_root(soup: BeautifulSoup) -> object:
    for div in soup.find_all("div"):
        direct = [child.name for child in div.find_all(recursive=False)]
        if "h1" in direct and "p" in direct:
            return div
    main = soup.find("main")
    if main is not None:
        children = main.find_all(recursive=False)
        if len(children) > 2:
            return children[2]
        return main
    return soup.body or soup


def skip_image(src: str) -> bool:
    lowered = src.lower()
    path = urlparse(src).path
    name = Path(path).name.lower()
    return any(hint in name or hint in lowered for hint in SKIP_IMAGE_HINTS)


def download_image(src: str) -> str | None:
    if not src or skip_image(src):
        return None
    try:
        data = fetch(src, timeout=60)
    except Exception:
        return None
    ext = Path(urlparse(src).path).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}:
        ext = ".png"
    digest = hashlib.sha256(data).hexdigest()[:24]
    dest = IMAGE_DIR / f"{digest}{ext}"
    if not dest.exists():
        dest.write_bytes(data)
    return str(dest).replace("\\", "/")


def inline_to_md(node, page_url: str) -> str:
    if isinstance(node, str):
        return node
    if node.name is None:
        return str(node)
    if node.name == "br":
        return "\n"
    if node.name == "img":
        src = node.get("src", "")
        if not src:
            return ""
        absolute = urljoin(page_url, src)
        local = download_image(absolute)
        if local is None:
            return ""
        alt = (node.get("alt") or "").strip()
        return f"![{alt}]({local})"
    if node.name in ("strong", "b"):
        text = "".join(inline_to_md(child, page_url) for child in node.children)
        return f"**{text}**"
    if node.name in ("em", "i"):
        text = "".join(inline_to_md(child, page_url) for child in node.children)
        return f"*{text}*"
    if node.name == "code":
        return f"`{node.get_text()}`"
    if node.name == "a":
        href = node.get("href", "")
        text = "".join(inline_to_md(child, page_url) for child in node.children).strip()
        return f"[{text}]({urljoin(page_url, href)})"
    if node.name == "span":
        return "".join(inline_to_md(child, page_url) for child in node.children)
    return "".join(inline_to_md(child, page_url) for child in node.children)


def list_to_md(node, page_url: str, level: int = 0) -> str:
    lines: list[str] = []
    indent = "  " * level
    for index, li in enumerate(node.find_all("li", recursive=False), 1):
        content_parts: list[str] = []
        nested: list[object] = []
        for child in li.children:
            if getattr(child, "name", None) in ("ul", "ol"):
                nested.append(child)
            else:
                content_parts.append(inline_to_md(child, page_url))
        text = "".join(content_parts).strip()
        marker = f"{index}. " if node.name == "ol" else "- "
        lines.append(f"{indent}{marker}{text}")
        for nested_list in nested:
            lines.append(list_to_md(nested_list, page_url, level + 1))
    return "\n".join(lines)


def table_to_md(table, page_url: str) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            re.sub(r"\s+", " ", inline_to_md(cell, page_url)).strip().replace("|", "\\|")
            for cell in tr.find_all(["th", "td"])
        ]
        rows.append(cells)
    if not rows:
        return ""
    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in rows[1:]:
        padded = row + [""] * (len(header) - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def block_to_md(node, page_url: str) -> str:
    name = node.name
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        return f"{'#' * level} {node.get_text(' ', strip=True)}"
    if name == "p":
        return inline_to_md(node, page_url).strip()
    if name == "figure":
        img = node.find("img")
        caption = node.find("figcaption")
        md = inline_to_md(img, page_url) if img is not None else ""
        cap = inline_to_md(caption, page_url).strip() if caption is not None else ""
        if md and cap:
            return f"{md}\n\n*{cap}*"
        return md
    if name == "pre":
        code = node.find("code") or node
        language = ""
        classes = list(code.get("class") or []) + list(node.get("class") or [])
        for cls in classes:
            if cls.startswith("language-"):
                language = cls[len("language-") :]
                break
        text = code.get_text().strip("\n")
        fence = "```" if "```" not in text else "````"
        return f"{fence}{language}\n{text}\n{fence}"
    if name in ("ul", "ol"):
        return list_to_md(node, page_url)
    if name == "table":
        return table_to_md(node, page_url)
    if name == "blockquote":
        text = inline_to_md(node, page_url).strip()
        return "\n".join(f"> {line}" for line in text.splitlines())
    if name == "hr":
        return "---"
    if name == "div":
        parts = [
            block_to_md(child, page_url)
            for child in node.find_all(recursive=False)
            if child.name is not None
        ]
        return "\n\n".join(part for part in parts if part)
    return inline_to_md(node, page_url).strip()


def safe_filename(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "-", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] or "note"


def convert_page(url: str, index: int) -> str:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    root = content_root(soup)
    blocks = []
    for child in root.find_all(recursive=False):
        if child.name == "h1":
            continue
        md = block_to_md(child, url)
        if child.name == "p" and re.search(
            r"公众号.*持续更新|持续更新.*公众号|林友们.*关注"
            r"|记得点个赞、在看、转发三连|赶紧去试试吧，林友们",
            md,
        ):
            continue
        if md:
            blocks.append(md)
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(" ", strip=True) if soup.title else "未命名")
    title = re.sub(r"^\d+[.、]\s*", "", title).strip()
    header = f"# {title}\n\n> 原文：[{title}]({url}) · 小林面试笔记\n"
    md = header + "\n\n" + "\n\n".join(blocks) + "\n"
    md = md.replace(str(IMAGE_DIR).replace("\\", "/"), "../images")
    return md


def scrape(limit: int | None = None) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    pages = collect_pages()
    summary: list[dict[str, object]] = []
    failures: list[str] = []

    for key, title, _ in SERIES:
        urls = pages[key]
        if limit is not None:
            urls = urls[:limit]
        topic_dir = OUT_DIR / key
        topic_dir.mkdir(parents=True, exist_ok=True)
        ok = 0
        for index, url in enumerate(urls, 1):
            try:
                md = convert_page(url, index)
                filename = f"{index:02d}-{safe_filename(md.splitlines()[0].lstrip('# '))}.md"
                (topic_dir / filename).write_text(md, encoding="utf-8")
                ok += 1
                print(f"[{key}] {index}/{len(urls)} {filename}", flush=True)
            except Exception as exc:  # noqa: BLE001 - 单页失败不中断全量抓取
                failures.append(url)
                print(f"[{key}] FAIL {url}: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.15)
        summary.append({"key": key, "title": title, "pages": ok, "total": len(urls)})

    image_count = len(list(IMAGE_DIR.glob("*")))
    build_readme(image_count)
    print("SUMMARY", summary)
    print("IMAGES", image_count)
    print("FAILURES", len(failures))
    for url in failures:
        print("  FAIL", url)


def build_readme(image_count: int) -> None:
    lines = [
        "# 小林面试笔记 AI 系列",
        "",
        "本目录为个人离线学习整理的 Markdown 笔记，内容来自小林面试笔记网站，",
        "仅供个人学习使用，请勿用于二次公开转载。",
        "",
        "| 系列 | 目录 | 笔记数 |",
        "|---|---|---|",
    ]
    total = 0
    for key, title, _ in SERIES:
        pages = len(list((OUT_DIR / key).glob("*.md")))
        total += pages
        lines.append(f"| {title} | `{key}/` | {pages} |")
    lines.extend(
        [
            "",
            f"共 {total} 篇笔记，图片保存在 `images/`（已按内容去重，共 {image_count} 张）。",
            "",
            "## 系列说明",
            "",
            "- `agent/`：Agent 面试题",
            "- `rag/`：RAG 面试题",
            "- `tools/`：LLM 工具调用面试题",
            "- `llm/`：大模型工程面试题",
            "- `langchain/`：LangChain 框架面试题",
            "- `tujie-agent/`：图解 Agent",
            "- `tujie-claude-code/`：图解 Claude Code",
            "",
        ]
    )
    (OUT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="每个系列只抓前 N 篇，用于测试")
    args = parser.parse_args()
    scrape(limit=args.limit)


if __name__ == "__main__":
    main()
