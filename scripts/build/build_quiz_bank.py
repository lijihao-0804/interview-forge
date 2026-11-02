"""从 glossary 生成选择题题库 → assets/quiz.json。

每题：题干「以下哪项是对「TERM」的正确描述？」，1 个正确 definition + 3 个同分类干扰项，
附答案索引与解析。front-end 读此 JSON 做题、本地判分。
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from interview_forge.data.glossary import GLOSSARY  # noqa: E402

OUT = ROOT / "assets" / "quiz.json"
random.seed(42)  # 固定，构建产物稳定

entries = [g for g in GLOSSARY if g.get("definition") and len(g["definition"]) >= 12]
by_cat = {}
for g in entries:
    by_cat.setdefault(g.get("category") or "其他", []).append(g)

bank = []
for g in entries:
    cat = g.get("category") or "其他"
    pool = [x for x in by_cat.get(cat, []) if x["definition"] != g["definition"]]
    if len(pool) < 3:
        pool = [x for x in entries if x["definition"] != g["definition"]]
    distractors = random.sample(pool, 3)
    options = [{"text": g["definition"], "correct": True}] + \
              [{"text": d["definition"], "correct": False} for d in distractors]
    random.shuffle(options)
    answer = next(i for i, o in enumerate(options) if o["correct"])
    abbr = ("（" + str(g["abbr"]) + "）") if g.get("abbr") else ""
    bank.append({
        "key": g["term"],
        "category": cat,
        "stem": "以下哪项是对「" + g["term"] + "」" + abbr + "的正确描述？",
        "options": [o["text"] for o in options],
        "answer": answer,
        "explain": g["term"] + abbr + "：" + (g.get("detail") or g["definition"]),
    })

OUT.write_text(json.dumps({"total": len(bank), "questions": bank}, ensure_ascii=False, indent=1), encoding="utf-8")
cats = {}
for q in bank:
    cats[q["category"]] = cats.get(q["category"], 0) + 1
print("生成", len(bank), "道选择题 | 分类", len(cats), "个 →", OUT.relative_to(ROOT))
