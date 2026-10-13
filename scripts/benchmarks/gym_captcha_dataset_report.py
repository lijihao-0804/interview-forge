"""Score the labelled captcha dataset with the production matching route.

Reports, per image, the predicted box for each prompt character under

  * the current probability route (joint one-to-one assignment over the mean of
    the std/beta CTC scores, requiring both models to agree), and
  * the older greedy std+beta vote route, as a reference point.

It also prints the two cheap "confidence" signals we tried and had to reject,
so nobody re-adds them as gates:

  * min(selected_scores) -- 6 of the 13 correct images score below 0.1
    (sample11 scores 0.000 and is still placed correctly); the values are max
    CTC time-step probabilities, not calibrated correctness probabilities.
  * top-1 coverage       -- 6 of the 13 correct images have a prompt character
    that is the argmax of no box at all.

Usage:
    python scripts/benchmarks/gym_captcha_dataset_report.py
    python scripts/benchmarks/gym_captcha_dataset_report.py --json /tmp/a.json
    python scripts/benchmarks/gym_captcha_dataset_report.py --json /tmp/b.json \\
        --diff /tmp/a.json          # e.g. same run under a different venv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import ddddocr
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interview_forge.services import gym_automation as gym  # noqa: E402

MANIFEST = ROOT / ".maintenance" / "ocr-static-20261012" / "manifest.json"


def top1_char(model, crop) -> str:
    """Argmax character of one crop, skipping index 0 (the CTC blank)."""
    result = model.classification(crop, probability=True)
    charset = result["charset"]
    peak = np.asarray(result["probabilities"], dtype=float).reshape((-1, len(charset))).max(axis=0)
    best, char = -1.0, ""
    for index, candidate in enumerate(charset):
        if index == 0 or not candidate:
            continue
        if peak[index] > best:
            best, char = float(peak[index]), candidate
    return char


def box_index(boxes, box) -> int | None:
    for index, candidate in enumerate(boxes):
        if [int(v) for v in candidate] == [int(v) for v in box]:
            return index + 1
    return None


def analyse(img_path, targets, truth, boxes, std, beta) -> dict:
    img = Image.open(img_path).convert("RGB")
    model_scores = np.zeros((2, len(targets), len(boxes)), dtype=float)
    entries = []
    for index, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box)
        crop = img.crop((x1, y1, x2, y2))
        entry = {"box": [x1, y1, x2, y2], "center": ((x1 + x2) / 2, (y1 + y2) / 2),
                 "ds": "", "paddle_chars": ""}
        for model_index, (name, model) in enumerate((("std", std), ("beta", beta))):
            result = model.classification(crop, probability=True)
            charset = result["charset"]
            probs = np.asarray(result["probabilities"], dtype=float).reshape((-1, len(charset)))
            for target_index, target in enumerate(targets):
                if target in charset:
                    model_scores[model_index, target_index, index] = probs[:, charset.index(target)].max()
            entry[name] = result.get("text") or ""
        entries.append(entry)

    assignment, diag = gym.match_click_targets_probability(img, boxes, targets, std, beta)
    predicted = [box_index(boxes, assignment[t]["box"]) for t in targets] if assignment else []
    greedy = gym.assign_targets(entries, targets)
    greedy_ids = [box_index(boxes, greedy[t]["box"]) for t in targets if t in greedy]
    covered = set()
    for index, box in enumerate(boxes):
        crop = img.crop(tuple(box))
        covered.add(top1_char(std, crop))
        covered.add(top1_char(beta, crop))

    selected = diag.get("selected_scores") or []
    return {
        "targets": targets,
        "truth": truth,
        "boxes": [list(map(int, b)) for b in boxes],
        "predicted": predicted,
        "correct": None if truth is None or not predicted else predicted == truth,
        "log_gap": None if diag.get("log_gap") is None else round(diag["log_gap"], 6),
        "model_agreement": diag.get("model_agreement"),
        "reason": diag.get("reason", ""),
        "min_selected_score": min(selected) if selected else None,
        "missing_from_top1": [t for t in targets if t not in covered],
        "greedy": greedy_ids,
        "greedy_correct": None if truth is None or len(greedy_ids) != len(truth) else greedy_ids == truth,
    }


def diff_against(current: dict, other: dict) -> int:
    """Compare two report dumps; returns 0 when every case matches within 1e-5."""
    rows = sorted(set(current["cases"]) | set(other["cases"]))
    worst, worst_case, mismatched = 0.0, None, []
    for name in rows:
        mine, theirs = current["cases"].get(name), other["cases"].get(name)
        if mine is None or theirs is None:
            mismatched.append(name)
            continue
        if mine["predicted"] != theirs["predicted"]:
            mismatched.append(name)
        for key in ("min_selected_score", "log_gap"):
            a, b = mine.get(key), theirs.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(a - b) > worst:
                    worst, worst_case = abs(a - b), name
    print(f"\n对比基线：{current['env']}  vs  {other['env']}")
    print(f"  预测不一致的图：{mismatched or '无'}")
    print(f"  数值最大差：{worst:.3e}（{worst_case}）")
    return 1 if mismatched or worst > 1e-5 else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", default=None, help="把结果写入这个路径")
    parser.add_argument("--diff", default=None, help="与另一份结果 JSON 对比")
    args = parser.parse_args(argv)

    if not MANIFEST.exists():
        print(f"找不到标注清单：{MANIFEST}", file=sys.stderr)
        print("（.maintenance/ 是本机离线实验产物，不入库）", file=sys.stderr)
        return 2

    std = ddddocr.DdddOcr(show_ad=False)
    beta = ddddocr.DdddOcr(show_ad=False, beta=True)
    cases, correct, greedy_correct = {}, 0, 0
    print(f"{'图':12s} {'题面':10s} {'真值':10s} {'预测':10s} {'对':2s} "
          f"{'最低分':>8s} {'top1缺':8s} {'greedy':10s}")
    print("-" * 92)
    for item in json.loads(MANIFEST.read_text(encoding="utf-8")):
        result = analyse(Path(item["image"]), list(item["targets"]), item["truth"],
                         item["boxes"], std, beta)
        cases[item["name"]] = result
        correct += int(bool(result["correct"]))
        greedy_correct += int(bool(result["greedy_correct"]))
        low = result["min_selected_score"]
        print(f"{item['name']:12s} {','.join(item['targets']):10s} "
              f"{str(item['truth']):10s} {str(result['predicted']):10s} "
              f"{'✓' if result['correct'] else '✗':2s} "
              f"{low if low is None else f'{low:.3f}':>8s} "
              f"{','.join(result['missing_from_top1']) or '-':8s} "
              f"{str(result['greedy']):10s} {'✓' if result['greedy_correct'] else '✗'}")

    total = len(cases)
    low_scoring = sum(1 for c in cases.values()
                      if isinstance(c["min_selected_score"], float) and c["min_selected_score"] < 0.1)
    uncovered = sum(1 for c in cases.values() if c["missing_from_top1"])
    print(f"\nprobability 路线位置全对：{correct}/{total}")
    print(f"greedy(std+beta) 参考：{greedy_correct}/{total}")
    print(f"若加 min(selected_scores)>=0.1 门限，会误杀 {low_scoring}/{total} 张位置正确的图")
    print(f"若加 top-1 覆盖门限，会误杀 {uncovered}/{total} 张位置正确的图")

    payload = {"env": {"python": sys.version.split()[0], "numpy": np.__version__,
                       "ddddocr": getattr(ddddocr, "version", "?")},
               "summary": {"correct": correct, "total": total,
                           "greedy_correct": greedy_correct,
                           "killed_by_score_floor": low_scoring,
                           "killed_by_top1_coverage": uncovered},
               "cases": cases}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\n已写入 {args.json}")
    if args.diff:
        return diff_against(payload, json.loads(Path(args.diff).read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
