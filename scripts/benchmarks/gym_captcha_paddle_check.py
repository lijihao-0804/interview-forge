"""Check what the PaddleOCR route actually contributes on real captchas.

Runs the production `_paddle_read` and `_legacy_click_assignment` over
  * the 13 manually labelled images (.maintenance/ocr-static-20261012), and
  * every captcha captured under data/logs/gym/captures/<run>/ — the prompt for
    those comes from the booking log with the same run stamp.

Useful as a regression check whenever the PaddleOCR stack changes: it prints
what Paddle read per image, the legacy full-location rate, and the probability
route's rate for comparison.

NOTE: `_get_paddle` targets the PaddleOCR 3.x API (`engine=`, `predict()`), so
run this where the venv has PaddleOCR 3.7 (e.g. the deployment venv). On a
PaddleOCR 2.x interpreter the route degrades to nothing and this script will
say so.

Usage:
    python scripts/benchmarks/gym_captcha_paddle_check.py
    python scripts/benchmarks/gym_captcha_paddle_check.py --no-labelled
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import ddddocr
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interview_forge.services import gym_automation as gym  # noqa: E402

MANIFEST = ROOT / ".maintenance" / "ocr-static-20261012" / "manifest.json"
CAPTURES = ROOT / "data" / "logs" / "gym" / "captures"
LOGS = ROOT / "data" / "logs" / "gym"
PROMPT = re.compile(r"点选验证码第 (\d+) 次：依次点击 \[(.+?)\]")


def prompt_for(run_stamp: str, attempt: int) -> list[str] | None:
    """Prompt of attempt N in the booking log that shares the capture stamp."""
    log_path = LOGS / f"booking-{run_stamp}.log"
    if not log_path.exists():
        return None
    wanted = None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = PROMPT.search(line)
        if match and int(match.group(1)) == attempt:
            wanted = [t.strip().strip("'\"") for t in match.group(2).split(",")]
    return wanted


def cases(include_labelled: bool):
    rows = []
    if include_labelled and MANIFEST.exists():
        for item in json.loads(MANIFEST.read_text(encoding="utf-8")):
            rows.append((item["name"], Path(item["image"]), list(item["targets"]),
                         item["truth"], "labelled"))
    for image in sorted(CAPTURES.glob("*/captcha-attempt*.png")):
        attempt = int(re.search(r"attempt(\d+)", image.stem).group(1))
        targets = prompt_for(image.parent.name, attempt)
        if targets:
            rows.append((f"{image.parent.name}/a{attempt}", image, targets, None, "captured"))
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-labelled", action="store_true", help="只看抓图，不看标注集")
    args = parser.parse_args(argv)

    rows = cases(not args.no_labelled)
    if not rows:
        print("没有可用样本", file=sys.stderr)
        return 2

    det = ddddocr.DdddOcr(det=True, show_ad=False)
    std = ddddocr.DdddOcr(show_ad=False)
    beta = ddddocr.DdddOcr(show_ad=False, beta=True)

    started = time.perf_counter()
    if gym._get_paddle() is None:
        print("!! PaddleOCR 不可用（该解释器可能不是 PaddleOCR 3.x），legacy 会退化成 std/beta")
    else:
        print(f"PaddleOCR 就绪（初始化 {time.perf_counter() - started:.1f}s）")

    print(f"\n{'样本':26s} {'题面':10s} {'概率路线':8s} {'legacy':8s} Paddle 读到的行")
    print("-" * 104)
    legacy_full = legacy_total = prob_full = 0
    for name, image_path, targets, truth, cohort in rows:
        img = Image.open(image_path).convert("RGB")
        boxes = sorted([[int(v) for v in b] for b in det.detection(image_path.read_bytes())
                        if b[2] - b[0] >= 10 and b[3] - b[1] >= 10], key=lambda b: (b[0], b[1]))
        legacy = gym._legacy_click_assignment(img, boxes, targets, std, beta, None)
        prob, _ = gym.match_click_targets_probability(img, boxes, targets, std, beta)
        lines = " | ".join(t for t, _ in gym._paddle_read(img)) or "(空)"
        ok_legacy = len(legacy) == len(targets)
        ok_prob = len(prob) == len(targets)
        legacy_total += 1
        legacy_full += ok_legacy
        prob_full += ok_prob
        verdict = ""
        if truth is not None:
            got = [boxes.index([int(v) for v in legacy[t]["box"]]) + 1 for t in targets
                   if t in legacy] if ok_legacy else []
            verdict = "✓" if got == truth else "✗"
        print(f"{name:26s} {','.join(targets):10s} {'全' if ok_prob else '缺':^8s} "
              f"{'全' if ok_legacy else '缺':^8s} {verdict} {lines[:40]}")

    print(f"\n概率路线完整定位：{prob_full}/{legacy_total}")
    print(f"legacy（std+beta+paddle）完整定位：{legacy_full}/{legacy_total}")
    print("注：legacy 只在概率路线定位不全时才被当复核用，这里的对比不代表线上触发比例。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
