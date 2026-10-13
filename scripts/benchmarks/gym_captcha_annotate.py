"""Render captcha images with box indices and the OCR guess, for human review.

Ground truth for the real site captchas only exists in someone's head, so when a
route disagrees with the site the fastest way forward is a picture: this draws
each detected box with its index, the std/beta top-1 character and score under
it, and the mapping the production route would click.

Usage:
    # one image, prompt known
    python scripts/benchmarks/gym_captcha_annotate.py \\
        --image data/logs/gym/captures/20261013-094808/captcha-attempt1.png \\
        --targets 定,们,来 --out /tmp/annotated

    # every captcha saved by the latest run, no prompt (boxes + guesses only)
    python scripts/benchmarks/gym_captcha_annotate.py --image 'data/logs/gym/captures/*/*.png'
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import ddddocr
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interview_forge.services import gym_automation as gym  # noqa: E402

FONT_CANDIDATES = (r"C:\Windows\Fonts\msyh.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
SCALE = 3


def load_font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def top1(model, crop):
    """(character, score) of one crop, skipping index 0 (the CTC blank)."""
    result = model.classification(crop, probability=True)
    charset = result["charset"]
    peak = np.asarray(result["probabilities"], dtype=float).reshape((-1, len(charset))).max(axis=0)
    best, char = -1.0, "?"
    for index, candidate in enumerate(charset):
        if index == 0 or not candidate:
            continue
        if peak[index] > best:
            best, char = float(peak[index]), candidate
    return char, round(best, 3)


def annotate(path: Path, targets: list[str], out_dir: Path, det, std, beta, font) -> dict:
    img = Image.open(path).convert("RGB")
    boxes = sorted([[int(v) for v in b] for b in det.detection(path.read_bytes())
                    if b[2] - b[0] >= 10 and b[3] - b[1] >= 10], key=lambda b: (b[0], b[1]))
    std_top = [top1(std, img.crop(tuple(b))) for b in boxes]
    beta_top = [top1(beta, img.crop(tuple(b))) for b in boxes]

    mapping = {}
    diag = {}
    if targets and len(boxes) >= len(targets):
        assignment, diag = gym.match_click_targets_probability(img, boxes, targets, std, beta)
        for target in targets:
            entry = assignment.get(target)
            if entry:
                mapping[target] = boxes.index([int(v) for v in entry["box"]]) + 1

    canvas = Image.new("RGB", (img.width * SCALE, img.height * SCALE + 46), "white")
    canvas.paste(img.resize((img.width * SCALE, img.height * SCALE), Image.Resampling.NEAREST), (0, 46))
    draw = ImageDraw.Draw(canvas)
    draw.text((4, 4), f"{path.name}   题面={','.join(targets) if targets else '未提供'}", fill="black", font=font)
    if targets:
        line = "  ".join(f"{t}->#{mapping[t]}" for t in targets if t in mapping) or "未分配"
        extra = ""
        if diag:
            gap = diag.get("log_gap")
            extra = (f"   log_gap={gap:.2f}" if isinstance(gap, (int, float)) else "")
            extra += f"  std/beta一致={diag.get('model_agreement')}"
        draw.text((4, 24), f"当前路线认定: {line}{extra}", fill="darkred", font=font)
    for index, box in enumerate(boxes, 1):
        draw.rectangle([box[0] * SCALE, 46 + box[1] * SCALE, box[2] * SCALE, 46 + box[3] * SCALE],
                       outline="red", width=2)
        draw.text((box[0] * SCALE, 46 + box[1] * SCALE - 15), f"#{index}", fill="red", font=font)
        draw.text((box[0] * SCALE, 46 + box[3] * SCALE + 1),
                  f"std={std_top[index - 1][0]}{std_top[index - 1][1]:.2f} "
                  f"beta={beta_top[index - 1][0]}{beta_top[index - 1][1]:.2f}",
                  fill="blue", font=font)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}-annotated.png"
    canvas.save(out_path)
    return {"image": str(path), "output": str(out_path), "boxes": boxes,
            "std_top1": std_top, "beta_top1": beta_top,
            "claimed_mapping": mapping, "log_gap": diag.get("log_gap")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", action="append", default=[], required=True,
                        help="图片路径或 glob（可重复）")
    parser.add_argument("--targets", default=None, help="逗号分隔的题面，例如 定,们,来")
    parser.add_argument("--out", default=str(ROOT / "data" / "logs" / "gym" / "annotated"),
                        help="输出目录")
    args = parser.parse_args(argv)

    paths: list[Path] = []
    for pattern in args.image:
        hits = [Path(p) for p in glob.glob(pattern, recursive=True)]
        paths.extend(sorted(hits) if hits else [Path(pattern)])
    missing = [p for p in paths if not p.exists()]
    if missing:
        for path in missing:
            print(f"找不到图片：{path}", file=sys.stderr)
        return 2

    targets = [t.strip() for t in args.targets.split(",")] if args.targets else []
    font = load_font(15)
    det = ddddocr.DdddOcr(det=True, show_ad=False)
    std = ddddocr.DdddOcr(show_ad=False)
    beta = ddddocr.DdddOcr(show_ad=False, beta=True)

    rows = [annotate(path, targets, Path(args.out), det, std, beta, font) for path in paths]
    print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
