"""批量把 Hot 100 题源里的“核心题意”更新为力扣官方中文题面。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
HOT100 = ROOT / "books" / "hot100"
BUILD_HOT100 = ROOT / "tools" / "build_hot100.py"
ASSET_DIR = ROOT / "assets" / "leetcode"
LC_IMG_PREFIX = "https://__LC_IMG_ROOT__/"

HEADING_RE = re.compile(r"^\s*### 📝 算法笔记：(\d+)\.")
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://leetcode.cn/problemset/",
}


def fetch_statement(slug: str) -> str:
    query = (
        "query questionData($titleSlug: String!) { "
        "question(titleSlug: $titleSlug) { translatedContent } }"
    )
    payload = json.dumps({"query": query, "variables": {"titleSlug": slug}}).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            req = Request("https://leetcode.cn/graphql/", data=payload, headers=HEADERS)
            with urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("data", {}).get("question", {}).get("translatedContent") or ""
            if content:
                return content
            raise RuntimeError("empty translatedContent")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2 * (2**attempt))
    raise RuntimeError(f"fetch {slug} failed: {last_error}")


def download_image(src: str) -> str:
    """下载力扣题面图片到 assets/leetcode/，返回问题页可用的相对路径。"""
    if not src.startswith(("http://", "https://")):
        return ""
    ext = Path(urlparse(src).path).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}:
        ext = ".png"
    digest = hashlib.sha1(src.encode("utf-8")).hexdigest()[:14]
    filename = f"lc-{digest}{ext}"
    dest = ASSET_DIR / filename
    if not dest.exists():
        try:
            request = Request(src, headers={"User-Agent": HEADERS["User-Agent"]})
            data = urlopen(request, timeout=30).read()
            ASSET_DIR.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        except Exception:  # noqa: BLE001 - 单张图片失败不影响题面更新
            return ""
    return filename


def inline_md(node, in_code: bool = False) -> str:
    if isinstance(node, str):
        text = node.replace("\xa0", " ")
        return text.replace("!=", "≠") if not in_code else text
    if node.name is None:
        text = str(node).replace("\xa0", " ")
        return text.replace("!=", "≠") if not in_code else text
    if node.name == "br":
        return "\n"
    if node.name in ("strong", "b"):
        text = "".join(inline_md(child, in_code) for child in node.children).strip()
        return f"**{text}**" if text else ""
    if node.name in ("em", "i"):
        text = "".join(inline_md(child, in_code) for child in node.children).strip()
        return f"*{text}*" if text else ""
    if node.name == "code":
        return "`" + node.get_text().replace("\xa0", " ") + "`"
    if node.name == "sup":
        return "^" + "".join(inline_md(child, in_code) for child in node.children) + "^"
    if node.name == "sub":
        return "~" + "".join(inline_md(child, in_code) for child in node.children) + "~"
    if node.name == "a":
        href = node.get("href", "")
        text = "".join(inline_md(child, in_code) for child in node.children).strip()
        return f"[{text}]({href})"
    if node.name == "img":
        alt = (node.get("alt") or "").strip()
        filename = download_image(node.get("src", ""))
        return f"![{alt}]({LC_IMG_PREFIX}{filename})" if filename else (alt or "")
    return "".join(inline_md(child, in_code) for child in node.children)


def list_md(node) -> str:
    lines: list[str] = []
    for index, li in enumerate(node.find_all("li", recursive=False), 1):
        content: list[str] = []
        nested: list[object] = []
        for child in li.children:
            if getattr(child, "name", None) in ("ul", "ol"):
                nested.append(child)
            else:
                content.append(inline_md(child))
        marker = f"{index}. " if node.name == "ol" else "- "
        lines.append(marker + "".join(content).strip())
        for nested_list in nested:
            for line in list_md(nested_list).splitlines():
                lines.append("  " + line)
    return "\n".join(lines)


def html_to_md(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    for child in soup.children:
        if getattr(child, "name", None) is None:
            continue
        if child.name in ("p", "div"):
            text = inline_md(child).strip()
        elif child.name == "pre":
            text = inline_md(child, in_code=True).strip().replace("\n", "<br>")
        elif child.name in ("ul", "ol"):
            text = list_md(child)
        elif child.name == "blockquote":
            text = "\n".join("> " + line for line in inline_md(child).strip().splitlines())
        elif child.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = f"{'#' * int(child.name[1])} {inline_md(child).strip()}"
        else:
            text = inline_md(child).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def bullet_lines(markdown: str) -> list[str]:
    lines = ["- **📌 核心题意**：", ""]
    for line in markdown.splitlines():
        lines.append("  " + line if line.strip() else "")
    lines.append("")
    return lines


def replace_section_bullet(section: list[str], markdown: str) -> list[str]:
    bullet_index = next(
        (
            idx
            for idx, line in enumerate(section)
            if line.startswith("- **") and "📌 核心题意" in line
        ),
        None,
    )
    new_lines = bullet_lines(markdown)
    if bullet_index is None:
        insert_index = next(
            (idx for idx, line in enumerate(section) if line.startswith("- **")),
            None,
        )
        if insert_index is None:
            insert_index = next(
                (idx + 1 for idx, line in enumerate(section) if line.strip() == "------"),
                len(section),
            )
        return section[:insert_index] + new_lines + section[insert_index:]
    end_index = next(
        (
            idx
            for idx, line in enumerate(section[bullet_index + 1 :], bullet_index + 1)
            if line.startswith("- **")
        ),
        len(section),
    )
    return section[:bullet_index] + new_lines + section[end_index:]


def update_source_files(statements: dict[int, str]) -> tuple[int, int]:
    changed_files = 0
    changed_sections = 0
    for path in sorted(HOT100.glob("[0-9][0-9]-*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        output: list[str] = []
        index = 0
        file_changed = False
        while index < len(lines):
            match = HEADING_RE.match(lines[index])
            if not match:
                output.append(lines[index])
                index += 1
                continue
            pid = int(match.group(1))
            end = index + 1
            while end < len(lines) and not HEADING_RE.match(lines[end]):
                end += 1
            section = lines[index:end]
            statement = statements.get(pid)
            if statement:
                new_section = replace_section_bullet(section, statement)
                if new_section != section:
                    section = new_section
                    changed_sections += 1
                    file_changed = True
            output.extend(section)
            index = end
        if file_changed:
            path.write_text("\n".join(output), encoding="utf-8")
            changed_files += 1
    return changed_files, changed_sections


def update_hardcoded_226(statement: str) -> bool:
    text = BUILD_HOT100.read_text(encoding="utf-8")
    pattern = re.compile(r"(### 题目与约束\n\n).*?(?=\n### 思路推导)", re.S)
    updated, count = pattern.subn(lambda m: m.group(1) + statement.strip() + "\n", text, count=1)
    if count:
        BUILD_HOT100.write_text(updated, encoding="utf-8")
    return bool(count)


def main() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from build_hot100 import LEETCODE_SLUGS

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    statements: dict[int, str] = {}
    for index, (pid, slug) in enumerate(LEETCODE_SLUGS.items(), 1):
        if args.limit and index > args.limit:
            break
        try:
            html = fetch_statement(slug)
            md = html_to_md(html)
            if len(md) < 40:
                raise RuntimeError("markdown too short")
            statements[pid] = md
            print(f"[fetch] {pid} {slug} len={len(md)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[fetch] FAIL {pid} {slug}: {exc}", file=sys.stderr, flush=True)
        time.sleep(0.2)

    if not statements:
        print("no statements fetched", file=sys.stderr)
        return

    files, sections = update_source_files(statements)
    print(f"source files changed: {files}; sections changed: {sections}")

    if 226 in statements:
        print("hardcoded 226 updated:", update_hardcoded_226(statements[226]))


if __name__ == "__main__":
    main()
