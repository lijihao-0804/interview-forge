"""Small, evidence-backed corrections kept apart from archived source material."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXES = ROOT / "data/ai_exam/practice-code-fixes.json"


def apply_reviewed_fixes(entries: list[dict], root: Path = ROOT, path: Path = FIXES) -> None:
    records = json.loads(path.read_text(encoding="utf-8"))["items"]
    by_url = {entry["url"]: entry for entry in entries}
    for url, record in records.items():
        if url not in by_url:
            raise ValueError(f"Unknown ACM correction: {url}")
        target = (root / "books/ai-exam" / url).with_suffix(".md")
        text = target.read_text(encoding="utf-8")
        for language, replacements in record.get("replace", {}).items():
            pattern = re.compile(r"(```" + re.escape(language) + r"\s*\n)(.*?)(```)", re.S)
            match = pattern.search(text)
            if not match:
                raise ValueError(f"Missing language to correct: {url} {language}")
            code = match.group(2)
            for replacement in replacements:
                old, new = replacement["old"], replacement["new"]
                if code.count(old) != 1:
                    raise ValueError(f"ACM correction source changed: {url} {language} {old[:60]}")
                code = code.replace(old, new, 1)
            text = text[:match.start(2)] + code + text[match.end(2):]
        for replacement in record.get("markdown_replace", []):
            if text.count(replacement["old"]) != 1:
                raise ValueError(f"ACM prose correction source changed: {url}")
            text = text.replace(replacement["old"], replacement["new"], 1)
        note = record.get("note", "")
        if note:
            lines = text.splitlines()
            lines[4:4] = [f"> 站内勘误：{note}", ""]
            text = "\n".join(lines) + "\n"
        target.write_text(text, encoding="utf-8")
