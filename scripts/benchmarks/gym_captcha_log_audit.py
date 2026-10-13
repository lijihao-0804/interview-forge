"""Audit every captcha attempt recorded in the local booking logs.

The captcha screenshots used to be written under fixed file names and were
overwritten by the next run, so the logs are the only unbiased record of what
the site actually served. This script pairs each prompt with the per-box OCR
output of that attempt and reports how often the model never even saw a prompt
character -- the failure no assignment rule can recover from.

Standard library only, no OCR dependencies.

Usage:
    python scripts/benchmarks/gym_captcha_log_audit.py
    python scripts/benchmarks/gym_captcha_log_audit.py --logs /path/to/logs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOGS = ROOT / "data" / "logs" / "gym"

PROMPT = re.compile(r"点选验证码第 (\d+) 次：依次点击 \[(.+?)\]")
PERBOX = re.compile(r"逐框识别：(\[.*?\])\s*$")
SCORES = re.compile(r"候选分数匹配：(\{.*\})\s*$")
BOXES = re.compile(r"检测到 (\d+) 个字框")


def parse_attempts(log_path: Path) -> list[dict]:
    attempts, current = [], None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = PROMPT.search(line)
        if match:
            if current:
                attempts.append(current)
            current = {"file": log_path.name, "attempt": int(match.group(1)),
                       "targets": [t.strip().strip("'\"") for t in match.group(2).split(",")],
                       "perbox": None, "scores": None, "boxes": None}
            continue
        if current is None:
            continue
        for pattern, key, loader in ((BOXES, "boxes", int), (PERBOX, "perbox", json.loads),
                                     (SCORES, "scores", json.loads)):
            match = pattern.search(line)
            if match:
                try:
                    current[key] = loader(match.group(1))
                except (json.JSONDecodeError, ValueError):
                    current[key] = None
                break
    if current:
        attempts.append(current)
    return attempts


def perbox_verdict(attempt: dict) -> tuple[str, list[str]]:
    """Which prompt characters never appear as any box's std/beta reading."""
    entries = attempt["perbox"]
    if not isinstance(entries, list):
        return "", []
    targets = attempt["targets"]
    seen = set()
    for entry in entries:
        for key in ("std", "beta"):
            text = entry.get(key) or ""
            if text in targets:
                seen.add(text)
    missing = [t for t in targets if t not in seen]
    return ("/".join(f"{e.get('std', '')}/{e.get('beta', '')}" for e in entries), missing)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--logs", default=str(DEFAULT_LOGS), help="日志目录")
    args = parser.parse_args(argv)

    log_dir = Path(args.logs)
    logs = sorted(log_dir.glob("booking-*.log"))
    if not logs:
        print(f"{log_dir} 下没有 booking-*.log", file=sys.stderr)
        return 2

    print(f"{'日志':32s} {'次':2s} {'题面':12s} {'框':2s} 识别情况")
    print("-" * 108)
    attempts = passed = 0
    blind = partial = full = 0
    days: dict[str, list[int]] = {}
    for log in logs:
        tries = parse_attempts(log)
        if not tries:
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        ok = len(re.findall(r"点选验证码通过", text))
        attempts += len(tries)
        passed += ok
        day = log.name[8:16]
        days.setdefault(day, [0, 0])
        days[day][0] += len(tries)
        days[day][1] += ok
        for attempt in tries:
            detail, missing = perbox_verdict(attempt)
            if attempt["perbox"] is None:
                scores = (attempt["scores"] or {}).get("selected_scores") or []
                note = (f"selected_scores={[round(s, 3) for s in scores]}"
                        if scores else "（无识别输出）")
            elif not missing:
                full += 1
                note = f"字符齐全  [{detail[:56]}]"
            elif len(missing) == len(attempt["targets"]):
                blind += 1
                note = f"全部缺失 {missing}"
            else:
                partial += 1
                note = f"缺 {','.join(missing)}  [{detail[:48]}]"
            print(f"{log.name[8:24]:32s} {attempt['attempt']:2d} "
                  f"{','.join(attempt['targets']):12s} {str(attempt['boxes']):2s} {note}")

    print(f"\n单次尝试通过率：{passed}/{attempts}"
          + (f"（{passed / attempts:.0%}）" if attempts else ""))
    for day, (t, o) in sorted(days.items()):
        print(f"  {day}：尝试 {t}，通过 {o}")
    print(f"\n有逐框文本的尝试：字符齐全 {full} 次，部分缺失 {partial} 次，全部缺失 {blind} 次")
    print("注：另见 scripts/benchmarks/gym_captcha_dataset_report.py —— 人工整理的 13 张\n"
          "    标注图是 13/13 全对，与这里的真实分布有明显差距（样本选择偏差）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
