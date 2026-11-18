"""Regenerate the HTML editions of the site's linked Markdown and license files."""

from html import escape

import markdown

from interview_forge.core.paths import ROOT
from interview_forge.core.research_readers import DOCUMENTS, READER_ROOT, link_readers


def build():
    output = ROOT / READER_ROOT.strip("/")
    output.mkdir(exist_ok=True)
    for url, slug in DOCUMENTS.items():
        source = ROOT / url.lstrip("/")
        text = source.read_text(encoding="utf-8")
        title = escape(text.splitlines()[0].removeprefix("# "))
        if source.suffix == ".txt":
            remainder = text.partition("\n")[2].lstrip("\n")
            content = f"<h1>{title}</h1><pre>{escape(remainder)}</pre>"
        else:
            content = markdown.markdown(
                text, extensions=["tables", "fenced_code", "sane_lists"]
            )
            content = link_readers(url, content.encode()).decode()
        parent = "/" + "/".join(source.relative_to(ROOT).parts[:2]) + "/index.html"
        page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · InterviewForge</title><link rel="stylesheet" href="/assets/site.css">
<link rel="stylesheet" href="/assets/research-report.css?v=20261118-layout"></head><body>
<nav aria-label="文档导航"><a href="{parent}">返回目录</a> · <a href="{escape(url)}?download=1" download>下载原文</a></nav>
<main class="reader-card"><article class="markdown-body">{content}</article></main></body></html>
"""
        (output / (slug + ".html")).write_text(page, encoding="utf-8")


if __name__ == "__main__":
    build()
