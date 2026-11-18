"""Keep authored contents links usable after Markdown is split into published chapters."""
from __future__ import annotations

from collections import defaultdict
from html import escape, unescape
import re
import unicodedata
from urllib.parse import unquote

# Skip code examples, comments and script literals when repairing generated HTML.
TOKEN = re.compile(r'<!--.*?-->|<(script|style|pre)\b[^>]*>.*?</\1\s*>|<a\b(?P<before>[^>]*?\bhref=")#(?P<fragment>[^"]+)"(?P<after>[^>]*)>(?P<title>.*?)</a>', re.I | re.S)
HEADING = re.compile(r'<h([1-6])\b[^>]*?\bid="([^"]+)"[^>]*>(.*?)</h\1>', re.I | re.S)
TAGS = re.compile(r'<[^>]+>')
NUMBER = re.compile(r'^\s*(?:第\s*)?\d+(?:[.\-]\d+)*[.、:：)）\s]+')
APPENDIX = re.compile(r'^附录\s*([A-Za-z])(?:\s|[:：]|$)', re.I)
LEGACY_ASIDE = re.compile(rb'(<div class="aside aside-(?:warn|note)")><span class="aside-title">([^<]+)</span>')


def key(text):
    plain = unicodedata.normalize("NFKC", unescape(TAGS.sub("", text))).casefold().strip()
    return "".join(c for c in NUMBER.sub("", plain) if c.isalnum())


def repair_contents(markup, chapter_titles=()):
    """Resolve only missing fragments with an unambiguous heading or chapter match."""
    if 'href="#' not in markup:
        return markup
    ids = set(re.findall(r'\bid="([^"]+)"', markup))
    local = defaultdict(set)
    for _, target, label in HEADING.findall(markup):
        local[key(label)].add("#" + target)
    chapters = defaultdict(set)
    for index, title in enumerate(chapter_titles, 1):
        url = f"chapter-{index:02d}.html"
        chapters[key(title)].add(url)
        # Some source tables abbreviate a subtitle or an appendix to its letter.
        if separator := re.search(r"[:：]", title):
            chapters[key(title[:separator.start()])].add(url)
        appendix = APPENDIX.match(title)
        if appendix:
            chapters[key("附录" + appendix[1])].add(url)

    def link(match):
        if match["fragment"] is None:
            return match[0]
        fragment = unquote(unescape(match["fragment"]))
        if fragment in ids:
            return match[0]
        label_key = key(match["title"])
        destinations = local.get(label_key) or chapters.get(label_key)
        if not destinations and (appendix := APPENDIX.match(unescape(TAGS.sub("",match["title"])).strip())):
            destinations = chapters.get(key("附录" + appendix[1]))
        if not destinations or len(destinations) != 1:
            return match[0]
        url = escape(next(iter(destinations)), quote=True)
        return f'<a{match["before"]}{url}"{match["after"]}>{match["title"]}</a>'

    return TOKEN.sub(link, markup)


def restore_aside_ids(body: bytes) -> bytes:
    """Restore anchors lost by older generated callouts. New builds retain the id."""
    if b'<span class="aside-title">' not in body:
        return body
    def add_id(aside):
        anchor = re.search(rb'<a href="#([A-Za-z0-9_-]+)">' + re.escape(aside[2]) + rb'</a>', body)
        if not anchor or b'id="' + anchor[1] + b'"' in body:
            return aside[0]
        return aside[1] + b' id="' + anchor[1] + b'"><span class="aside-title">' + aside[2] + b'</span>'
    return LEGACY_ASIDE.sub(add_id, body)
