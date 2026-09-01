"""清理 agent面经.md 中的空白图片与公众号广告内容。"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "books" / "agent面经" / "agent面经.md"
IMAGES_DIR = ROOT / "books" / "agent面经" / "images"

AD_RE = re.compile(r"最新的.*公众号.*(?:加\s*群|技术群聊|二维码)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

# CJK 部首补充区里 NFKC 无法自动映射的字符，手工映射回标准简体汉字。
RADICAL_MAP = {
    0x2E9F: "母",
    0x2EC5: "见",
    0x2EC6: "角",
    0x2ECB: "车",
    0x2ED3: "长",
    0x2ED4: "门",
    0x2EDA: "页",
    0x2EDB: "风",
    0x2EDC: "飞",
    0x2EE6: "鸟",
    0x2EEC: "齐",
}


def normalize_radicals(text: str) -> str:
    """只把康熙部首/部首补充区字符映射为标准汉字，不改变全角标点。"""
    result: list[str] = []
    for char in text:
        cp = ord(char)
        if 0x2F00 <= cp <= 0x2FDF:
            mapped = unicodedata.normalize("NFKC", char)
            if cp == 0x2F3E:
                result.append("户")
            else:
                result.append(mapped if mapped != char else char)
        else:
            result.append(RADICAL_MAP.get(cp, char))
    return "".join(result)


def normalize_markdown(text: str) -> str:
    text = normalize_radicals(text)
    text = text.replace("用戶", "用户")
    text = text.replace("戶", "户")
    lines = text.splitlines()
    kept: list[str] = []
    blank_run = 0
    in_code = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            kept.append(line.rstrip())
            blank_run = 0
            continue
        if in_code:
            kept.append(line.rstrip())
            blank_run = 0
            continue
        if stripped == "":
            blank_run += 1
            if blank_run <= 2:
                kept.append("")
            continue

        blank_run = 0
        if re.match(r"^#{5,6}\s+", line):
            content = re.sub(r"^#{5,6}\s+", "", line).strip()
            if content == "代码块":
                continue
            if len(content) <= 80 and not re.search(r"[=≈×]", content):
                kept.append(f"**{content}**")
            else:
                kept.append(content)
            continue
        if re.match(r"^###\s+•\s+", line):
            kept.append("- " + re.sub(r"^###\s+•\s+", "", line).strip())
            continue
        if re.match(r"^\s*代码块\s*$", line):
            continue

        line = re.sub(r"^\s*代码块\s+", "", line)
        line = line.replace("` 代码块 `", " ")
        line = re.sub(
            r"`([^`\n]*)`",
            lambda match: match.group(1)
            if re.fullmatch(r"[\d\s×÷≈=<>+\-–—:：,，.。()（）]+", match.group(1))
            else match.group(0),
            line,
        )
        kept.append(line.rstrip())

    while kept and kept[0] == "":
        kept.pop(0)
    while kept and kept[-1] == "":
        kept.pop()
    return reconstruct_code_blocks("\n".join(kept) + "\n")


def split_code_content(content: str) -> list[str]:
    """去掉 PDF 转换带进来的行号，并把挤在一行里的多行代码拆开。"""
    content = re.sub(r"^\d+\s?", "", content.strip())
    parts = re.split(r"\s+(?=\d+\s)", content)
    return [re.sub(r"^\d+\s?", "", part).strip() for part in parts]


def is_numbered_code_bullet(line: str) -> bool:
    match = re.match(r"^\s*[-*]\s+(.*)$", line)
    if not match:
        return False
    spans = list(re.finditer(r"`([^`\n]*)`", match.group(1)))
    return len(spans) == 1 and re.match(r"^\d+", spans[0].group(1))


def reconstruct_code_blocks(text: str) -> str:
    """把带行号的连续行内代码列表恢复成围栏代码块。"""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            out.append(lines[i])
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                out.append(lines[i])
                i += 1
            if i < len(lines):
                out.append(lines[i])
                i += 1
            continue

        if not is_numbered_code_bullet(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        run: list[str] = []
        j = i
        blank_pending = False
        while j < len(lines):
            if lines[j].strip() == "":
                if run and not blank_pending:
                    blank_pending = True
                    j += 1
                    continue
                break
            if not is_numbered_code_bullet(lines[j]):
                break
            run.append(lines[j])
            blank_pending = False
            j += 1

        code_lines: list[str] = []
        usable = len(run) >= 2
        for raw in run:
            content = re.sub(r"^\s*[-*]\s+", "", raw)
            spans = list(re.finditer(r"`([^`\n]*)`", content))
            if len(spans) != 1 or "`" in spans[0].group(1):
                usable = False
                break
            outside = content[: spans[0].start()] + content[spans[0].end() :]
            if outside.strip() and not re.match(
                r"^[\u4e00-\u9fff\u3000-\u303f0-9#，。、：；！？\s]+$", outside.strip()
            ):
                usable = False
                break
            parts = split_code_content(spans[0].group(1))
            if len(parts) > 1:
                usable = True
            tail = outside.strip()
            for index, part in enumerate(parts):
                line_text = part
                if index == len(parts) - 1 and tail:
                    if line_text.endswith("#"):
                        line_text += " " + tail
                    else:
                        line_text += " " + tail
                code_lines.append(line_text)

        if usable:
            out.append("```")
            out.extend(code_lines)
            out.append("```")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out) + "\n"


def is_blank_image(path: Path) -> bool:
    """单色或近似单色图片视为空白图。"""
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        colors = len(rgb.getcolors(2**24) or [])
        stat = ImageStat.Stat(rgb.convert("L"))
        return colors <= 1 or stat.stddev[0] < 1


def main() -> None:
    text = MD_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    blank_names = {p.name for p in IMAGES_DIR.glob("*.png") if is_blank_image(p)}
    kept: list[str] = []
    ad_removed = 0
    image_removed = 0

    for line in lines:
        stripped = line.strip()
        if AD_RE.search(stripped):
            ad_removed += 1
            continue
        match = IMAGE_RE.search(stripped)
        if match and Path(match.group(1)).name in blank_names:
            image_removed += 1
            continue
        kept.append(line)

    cleaned = normalize_markdown("".join(kept))
    MD_PATH.write_text(cleaned, encoding="utf-8")

    files_deleted = 0
    for path in IMAGES_DIR.glob("*.png"):
        if path.name in blank_names:
            path.unlink()
            files_deleted += 1

    print(
        "blank_images="
        f"{len(blank_names)} ad_lines={ad_removed} "
        f"image_refs_removed={image_removed} files_deleted={files_deleted}"
    )


if __name__ == "__main__":
    main()
