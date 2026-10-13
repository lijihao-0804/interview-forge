"""Measure the production OCR matcher on labelled local images with fresh detection.

No browser, credentials, external requests, or booking actions are used.
Each manifest item has name, image, targets, cohort, and truth_regions (one
original-image rectangle per target). Repeats shuffle images, detector boxes,
and prompt order; they are stability checks, not new samples.

CAUTION: for the 2026-10-13 captures, truth_regions were derived from the
matcher's own boxes (padded by a few pixels), so a run over them only shows
self-consistency, not independent correctness. Only the 13-image cohort has
independently confirmed truth. See the 复核说明 section of
docs/验证码识别策略复核与本地图片测试-2026-10-13.md.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ddddocr
from PIL import Image

try:  # 内存统计是可选项，没装 psutil 也能跑完评测
    import psutil
except ImportError:  # pragma: no cover - 取决于本机是否装了 psutil
    psutil = None


def _installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interview_forge.services import gym_automation as gym  # noqa: E402


def summary(rows: list[dict]) -> dict:
    outcomes = Counter(row["outcome"] for row in rows)
    times = sorted(row["seconds"] for row in rows)
    return {
        "attempts": len(rows),
        "accepted_correct": outcomes["accepted_correct"],
        "accepted_wrong": outcomes["accepted_wrong"],
        "rejected": outcomes["rejected"],
        "target_correct": sum(row["correct_targets"] for row in rows),
        "target_total": sum(len(row["targets"]) for row in rows),
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "p95_seconds": times[max(0, (95 * len(times) + 99) // 100 - 1)],
        "max_seconds": max(times),
    }


def evaluate(item, detector, std, beta, rng, repeat):
    started = time.perf_counter()
    path = Path(item["image"])
    raw = path.read_bytes()
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    boxes = [[int(v) for v in box] for box in detector.detection(raw)
             if box[2] - box[0] >= 10 and box[3] - box[1] >= 10]
    detection_seconds = time.perf_counter() - started
    targets = list(item["targets"])
    if repeat > 1:
        rng.shuffle(boxes)
        rng.shuffle(targets)
    assignment, diagnostics = gym.match_click_targets_probability(image, boxes, targets, std, beta)
    seconds = time.perf_counter() - started
    checks = []
    predicted = {}
    for target, region in zip(item["targets"], item["truth_regions"]):
        entry = assignment.get(target)
        correct = False
        if entry:
            cx, cy = entry["center"]
            correct = region[0] <= cx <= region[2] and region[1] <= cy <= region[3]
            predicted[target] = {"box": entry["box"], "center": list(entry["center"])}
        checks.append({"target": target, "truth_region": region, "correct": correct})
    accepted = len(assignment) == len(item["targets"])
    outcome = ("accepted_correct" if all(check["correct"] for check in checks)
               else "accepted_wrong") if accepted else "rejected"
    return {
        "name": item["name"], "cohort": item["cohort"], "repeat": repeat,
        "image_sha256": hashlib.sha256(raw).hexdigest(), "targets": item["targets"],
        "input_target_order": targets, "boxes": boxes, "predicted": predicted,
        "target_checks": checks, "correct_targets": sum(check["correct"] for check in checks),
        "outcome": outcome, "diagnostics": diagnostics, "seconds": seconds,
        "detection_and_image_load_seconds": detection_seconds,
        "recognition_and_assignment_seconds": seconds - detection_seconds,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261013)
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    items = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not items or len({item["name"] for item in items}) != len(items):
        parser.error("manifest must be nonempty with unique names")
    hashes = set()
    for item in items:
        if (not item["targets"] or len(set(item["targets"])) != len(item["targets"])
                or any(len(t) != 1 for t in item["targets"])
                or len(item["truth_regions"]) != len(item["targets"])):
            parser.error(f"invalid annotation: {item['name']}")
        raw_hash = hashlib.sha256(Path(item["image"]).read_bytes()).hexdigest()
        if raw_hash in hashes:
            parser.error(f"duplicate image: {item['name']}")
        hashes.add(raw_hash)
        with Image.open(item["image"]) as image:
            for region in item["truth_regions"]:
                if not (len(region) == 4 and 0 <= region[0] < region[2] <= image.width
                        and 0 <= region[1] < region[3] <= image.height):
                    parser.error(f"out-of-bounds annotation: {item['name']}")
    init_start = time.perf_counter()
    detector = ddddocr.DdddOcr(det=True, show_ad=False)
    std = ddddocr.DdddOcr(show_ad=False)
    beta = ddddocr.DdddOcr(show_ad=False, beta=True)
    init_seconds = time.perf_counter() - init_start
    rows = []
    rng = random.Random(args.seed)
    for repeat in range(1, args.repeat + 1):
        order = list(items)
        if repeat > 1:
            rng.shuffle(order)
        for item in order:
            rows.append(evaluate(item, detector, std, beta, rng, repeat))
        print(json.dumps({"repeat": repeat, **summary([r for r in rows if r["repeat"] == repeat])},
                         ensure_ascii=False), flush=True)
    cohorts = sorted({item["cohort"] for item in items})
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                               text=True).strip(),
        "matcher_source_sha256": hashlib.sha256(Path(gym.__file__).read_bytes()).hexdigest(),
        "python": sys.executable, "python_version": sys.version.split()[0],
        "versions": {name: importlib.metadata.version(name) for name in
                     ("ddddocr", "onnxruntime", "numpy", "Pillow", "psutil")
                     if _installed(name)},
        "unique_images": len(items), "repeat": args.repeat, "seed": args.seed,
        "init_seconds": init_seconds,
        "rss_mb": psutil.Process().memory_info().rss / 2 ** 20 if psutil else None,
        "summary": summary(rows),
        "cohorts": {cohort: {
            "unique_images": sum(item["cohort"] == cohort for item in items),
            **summary([row for row in rows if row["cohort"] == cohort]),
        } for cohort in cohorts},
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "init_seconds": init_seconds,
                      "rss_mb": payload["rss_mb"], "cohorts": payload["cohorts"]},
                     ensure_ascii=False), flush=True)
    return 1 if payload["summary"]["accepted_wrong"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
