"""Descriptive skill, qualification, employer and location analysis for v2 jobs.

Reads the local merged v2 dataset and its summary only. It emits compact
aggregates and a decision-oriented Markdown note; it never copies full JDs.
"""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
ANALYSIS = ROOT / "analysis"
DATA_PATH = EVIDENCE / "all_jobs_v2.json"
STATS_PATH = ANALYSIS / "统计结果_v2.json"
COMPANY_MIN_N = 5
PAIR_MIN_SUPPORT = 20

MAIN_DIRECTIONS = {
    "application_agent": "AI应用/Agent开发",
    "agent_algorithm": "Agent算法或交叉研究",
    "ai_infra": "AI Infra",
    "posttraining": "后训练",
}
UNCERTAIN_POSTTRAINING = "强化学习阶段待核"

CONTROL_LABELS = {
    "ordinary_development": "普通开发对照",
    "non_ai_algorithm": "算法/研究对照",
    "non_ai_hardware": "硬件/嵌入式对照",
    "nontechnical": "非技术职能对照",
}
NONTECH_FAMILIES = {
    "产品", "销售商务与解决方案", "运营内容与市场", "人力财务法务行政",
    "设计与用户体验", "零售门店与现场业务", "供应链物流与线下", "战略投资与管理",
}

# This is a geographic mention scan over the normalized city/location string.
# A multi-city posting may count in more than one city, so city percentages do
# not sum to 100%.
CITY_ALIASES = {
    "北京": r"北京|Beijing",
    "上海": r"上海|Shanghai",
    "深圳": r"深圳|Shenzhen",
    "杭州": r"杭州|Hangzhou",
    "广州": r"广州|Guangzhou",
    "成都": r"成都|Chengdu",
    "南京": r"南京|Nanjing",
    "苏州": r"苏州|Suzhou",
    "武汉": r"武汉|Wuhan",
    "西安": r"西安|Xi.?an|Xian",
    "合肥": r"合肥|Hefei",
    "无锡": r"无锡|Wuxi",
    "东莞": r"东莞|Dongguan",
    "天津": r"天津|Tianjin",
    "重庆": r"重庆|Chongqing",
    "长沙": r"长沙|Changsha",
    "香港": r"香港|Hong Kong",
}

YEAR_EN = re.compile(r"\b\d+(?:\s*(?:[-–—~]|to)\s*\d+)?\s*\+?\s*(?:years?|yrs?)\b", re.I)
YEAR_ZH = re.compile(r"(?:\d+|[一二三四五六七八九十]+)\s*年(?:\s*(?:及以上|以上|以内|左右|工作经验|相关经验|经验|工作经历))?", re.I)
OPEN_EXP = re.compile(
    r"经验不限|不限经验|无经验(?:要求)?|不要求(?:相关)?经验|应届(?:毕业生|生)?|校招|实习生|"
    r"no\s+(?:prior\s+)?experience(?:\s+required)?|experience\s+not\s+required|"
    r"entry[- ]level|new\s+graduate|recent\s+graduate|campus\s+hire",
    re.I,
)
EXP_WORD = re.compile(r"经验|经历|experience|employment history|work history", re.I)

POSTTRAINING_TEXT_WORD = re.compile(
    r"后训练|post[- ]?train|监督微调|强化学习|RLHF|(?<![a-z])(?:SFT|DPO|GRPO)(?![a-z])",
    re.I,
)
GENERATIVE_CONTEXT = re.compile(
    r"大模型|语言模型|LLM|generative|foundation.model|RLHF|(?<![a-z])SFT(?![a-z])",
    re.I,
)
TECHNICAL_FAMILIES = {
    "开发工程", "算法与研究", "基础设施与系统", "运维与SRE", "测试与质量",
    "数据工程与分析", "硬件嵌入式与通信", "安全与风险", "技术职能待细分",
}


def pct(n: int | float, d: int | float) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def val_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(str(x) for x in value if x is not None)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def req_text(row: dict[str, Any]) -> str:
    value = row.get("requirements_analysis")
    if isinstance(value, str) and value.strip():
        return value
    value = row.get("requirements")
    return value.strip() if isinstance(value, str) else ""


def has_usable_requirements(row: dict[str, Any]) -> bool:
    return bool(row.get("requirements_available")) and bool(req_text(row))


def is_specific_ad(row: dict[str, Any]) -> bool:
    return row.get("record_kind") != "分领域毕业生招聘池"


def explicit_exp_flags(text: str) -> tuple[bool, bool, bool]:
    """Return (numeric duration, open/no-years marker, any experience wording)."""
    numeric = bool(YEAR_EN.search(text) or YEAR_ZH.search(text))
    open_marker = bool(OPEN_EXP.search(text))
    has_exp_word = bool(EXP_WORD.search(text))
    explicit = numeric or open_marker or has_exp_word
    return numeric, open_marker, explicit


def requirement_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in records if has_usable_requirements(r)]
    denom = len(eligible)
    degree_names = ("本科", "硕士", "博士")
    degree_counts = {
        level: sum(level in (r.get("education_mentions") or []) for r in eligible)
        for level in degree_names
    }
    any_degree = sum(bool(r.get("education_mentions")) for r in eligible)
    no_degree_mention = denom - any_degree
    unknown_degree = {"", "未知", "未明示", "未结构化披露", "未提供独立学历字段", "None"}
    structured_degree_known = sum(val_text(r.get("degree_raw")).strip() not in unknown_degree for r in eligible)

    exp_flags = [explicit_exp_flags(req_text(r)) for r in eligible]
    numeric_years = sum(x[0] for x in exp_flags)
    open_markers = sum(x[1] for x in exp_flags)
    any_exp_word = sum(x[2] for x in exp_flags)
    # The normalized field can be sourced from a structured API field or parsed
    # from text. This count is descriptive and is not treated as a required-years
    # estimate.
    unknown_exp = {"", "未知", "未明示", "未结构化披露", "未提供独立年限字段", "None"}
    structured_experience_known = sum(val_text(r.get("experience")).strip() not in unknown_exp for r in eligible)
    exp_distribution = Counter(val_text(r.get("experience") or "未知") for r in eligible)

    return {
        "eligible_requirements_n": denom,
        "eligible_requirements_filter": "requirements_available=true 且 requirements_analysis/requirements 非空；不把 full_combined 中无法分离的要求计入。",
        "education_mentions": {
            "denominator_n": denom,
            "any_degree_mention": {"n": any_degree, "pct": pct(any_degree, denom)},
            "no_degree_mention": {"n": no_degree_mention, "pct": pct(no_degree_mention, denom)},
            "tiers_nonexclusive": {
                level: {"n": n, "denominator_n": denom, "pct": pct(n, denom)}
                for level, n in degree_counts.items()
            },
            "structured_degree_field_known": {"n": structured_degree_known, "denominator_n": denom, "pct": pct(structured_degree_known, denom)},
            "note": "education_mentions 是要求文本中的词级提示，不区分必需与优先，也不表示最高学历门槛；层级可并列，比例不要求合计100%。",
        },
        "experience_explicitness": {
            "denominator_n": denom,
            "numeric_years_mentioned": {"n": numeric_years, "denominator_n": denom, "pct": pct(numeric_years, denom)},
            "open_or_newgrad_marker": {"n": open_markers, "denominator_n": denom, "pct": pct(open_markers, denom)},
            "any_experience_word_or_marker": {"n": any_exp_word, "denominator_n": denom, "pct": pct(any_exp_word, denom)},
            "normalized_experience_field_known": {"n": structured_experience_known, "denominator_n": denom, "pct": pct(structured_experience_known, denom)},
            "normalized_experience_field_top_values": [
                {"value": value, "n": n, "denominator_n": denom, "pct": pct(n, denom)}
                for value, n in exp_distribution.most_common(12)
            ],
            "note": "numeric_years_mentioned 用中英文年限模式扫描资格文本；any_experience_word_or_marker 包含非量化的经验描述。二者均未区分必需/优先，也不等于最低年限的准确解析。",
        },
    }


def skill_metrics(records: list[dict[str, Any]], skill_universe: list[str]) -> tuple[dict[str, Any], dict[str, int]]:
    eligible = [r for r in records if has_usable_requirements(r)]
    denom = len(eligible)
    total_counts: Counter[str] = Counter()
    per_company_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_company_n: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()

    for row in eligible:
        company = val_text(row.get("company")) or "未知"
        skills = sorted(set(s for s in (row.get("skills_in_requirement") or []) if isinstance(s, str) and s))
        per_company_n[company] += 1
        total_counts.update(skills)
        per_company_counts[company].update(skills)
        pair_counts.update(itertools.combinations(skills, 2))

    skill_rows = []
    for skill in skill_universe:
        weighted_n = total_counts.get(skill, 0)
        rates = [per_company_counts[c].get(skill, 0) / n * 100.0
                 for c, n in per_company_n.items() if n >= COMPANY_MIN_N]
        skill_rows.append({
            "skill": skill,
            "job_weighted": {"n": weighted_n, "denominator_n": denom, "pct": pct(weighted_n, denom)},
            "company_equal": {
                "mean_pct": round(statistics.mean(rates), 2) if rates else None,
                "denominator_companies_n": len(rates),
                "minimum_requirements_per_company": COMPANY_MIN_N,
            },
            "company_equal_minus_job_weighted_pp": round(statistics.mean(rates) - (pct(weighted_n, denom) or 0), 2) if rates else None,
        })
    skill_rows.sort(key=lambda x: (-(x["job_weighted"]["n"]), x["skill"]))

    pairs = []
    for (skill_a, skill_b), n_ab in pair_counts.items():
        if n_ab < PAIR_MIN_SUPPORT:
            continue
        n_a = total_counts[skill_a]
        n_b = total_counts[skill_b]
        lift = (n_ab * denom / (n_a * n_b)) if denom and n_a and n_b else None
        pairs.append({
            "skill_a": skill_a,
            "skill_b": skill_b,
            "n_both": n_ab,
            "denominator_n": denom,
            "support_pct": pct(n_ab, denom),
            "n_a": n_a,
            "n_b": n_b,
            "expected_n_if_independent": round(n_a * n_b / denom, 2) if denom else None,
            "lift": round(lift, 3) if lift is not None else None,
        })
    pairs.sort(key=lambda x: (-x["lift"], -x["n_both"], x["skill_a"], x["skill_b"]))

    return {
        "denominator_n": denom,
        "skill_table": skill_rows,
        "top_skills": skill_rows[:15],
        "company_equal_method": f"每家公司先计算 n_skill/n_requirements，再对 requirements 数至少 {COMPANY_MIN_N} 的公司做简单平均；各公司等权。",
        "company_equal_companies_n": sum(n >= COMPANY_MIN_N for n in per_company_n.values()),
        "cooccurrence": {
            "min_support_n": PAIR_MIN_SUPPORT,
            "denominator_n": denom,
            "qualifying_pairs_n": len(pairs),
            "lift_definition": "lift(A,B)=(n_both/denominator)/[(n_A/denominator)*(n_B/denominator)]=n_both*denominator/(n_A*n_B)。lift>1 表示在本样本同一条资格文本中共同出现频率高于按边际频率独立时的期望，不代表因果。",
            "pairs": pairs,
        },
    }, dict(total_counts)


def concentration(records: list[dict[str, Any]], denominator_type: str) -> dict[str, Any]:
    counts = Counter(val_text(r.get("company")) or "未知" for r in records)
    denom = len(records)
    top = counts.most_common(10)
    return {
        "denominator_type": denominator_type,
        "denominator_n": denom,
        "companies_n": len(counts),
        "top_company": ({"company": top[0][0], "n": top[0][1], "denominator_n": denom, "pct": pct(top[0][1], denom)} if top else None),
        "top_three_share": {"n": sum(n for _, n in top[:3]), "denominator_n": denom, "pct": pct(sum(n for _, n in top[:3]), denom)},
        "top_companies": [{"company": c, "n": n, "denominator_n": denom, "pct": pct(n, denom)} for c, n in top],
    }


def geography_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    denom = len(records)
    geo_counts = Counter(val_text(r.get("geography") or "地域待核或其他地区") for r in records)
    city_counts: Counter[str] = Counter()
    for row in records:
        loc = val_text(row.get("city"))
        for city, pattern in CITY_ALIASES.items():
            if re.search(pattern, loc, re.I):
                city_counts[city] += 1
    return {
        "denominator_n": denom,
        "geography_field_distribution": [{"value": k, "n": n, "denominator_n": denom, "pct": pct(n, denom)} for k, n in geo_counts.most_common()],
        "major_city_mentions": [{"city": c, "n": n, "denominator_n": denom, "pct": pct(n, denom)} for c, n in city_counts.most_common(12)],
        "city_method": "在标准化 city/location 文本中扫描固定城市中英文别名；多城市职位会在每个提及城市计一次，因此城市百分比可合计超过100%。未匹配的城市不计入 major_city_mentions。",
    }


def group_record_metrics(records: list[dict[str, Any]], label: str, skill_universe: list[str]) -> dict[str, Any]:
    requirements = [r for r in records if has_usable_requirements(r)]
    skills, _ = skill_metrics(requirements, skill_universe)
    eligible_company = concentration(requirements, "requirements_available=true 且资格文本非空的职位")
    positions_company = concentration(records, "具体职位广告记录")
    return {
        "label": label,
        "positions_n": len(records),
        "positions_denominator_n": None,
        "requirements_eligible_n": len(requirements),
        "requirements_eligible_pct_of_positions": pct(len(requirements), len(records)),
        "company_concentration_positions": positions_company,
        "company_concentration_requirements_eligible": eligible_company,
        "geography": geography_metrics(records),
        "qualification_metrics": requirement_metrics(requirements),
        "skills": skills,
    }


def control_predicates() -> dict[str, Any]:
    def ordinary_dev(r: dict[str, Any]) -> bool:
        return r.get("job_family") == "开发工程" and r.get("title_direction") == "其他技术或标题未分方向"

    def non_ai_algorithm(r: dict[str, Any]) -> bool:
        return r.get("job_family") == "算法与研究" and r.get("title_direction") == "其他技术或标题未分方向"

    def non_ai_hardware(r: dict[str, Any]) -> bool:
        return r.get("job_family") == "硬件嵌入式与通信" and r.get("title_direction") in {"硬件或嵌入式", "其他技术或标题未分方向"}

    def nontechnical(r: dict[str, Any]) -> bool:
        return r.get("job_family") in NONTECH_FAMILIES

    return {
        "ordinary_development": ordinary_dev,
        "non_ai_algorithm": non_ai_algorithm,
        "non_ai_hardware": non_ai_hardware,
        "nontechnical": nontechnical,
    }


def pct_text(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def frac(n: int, d: int) -> str:
    return f"{n:,}/{d:,} ({pct_text(pct(n, d))})"


def build_insights(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    groups = analysis["directions"]
    insights: list[dict[str, Any]] = []

    core_n = sum(groups[k]["positions_n"] for k in MAIN_DIRECTIONS)
    eligible_n = sum(groups[k]["requirements_eligible_n"] for k in MAIN_DIRECTIONS)
    total = analysis["data_overview"]["specific_job_ads_n"]
    insights.append({
        "id": "scope_and_coverage",
        "title": "四个目标方向在样本中有不同的正文可分析覆盖率",
        "evidence": [f"四方向具体职位记录合计 {core_n:,}/{total:,} 条；其中资格文本可分析 {eligible_n:,}/{core_n:,} 条。", "方向为标题规则分类，岗位记录来源范围和企业截面并不一致。"],
        "interpretation": "后续技能、学历、经验百分比只代表可分析的资格文本，不应按全部岗位记录作分母。",
        "action": "先按方向和资格可用标记筛选，再比较技术栈；对未拆出资格文本的岗位回看原始正文。",
        "limitation": "方向由标题规则推断；样本不覆盖统一雇主集合，也不是全国招聘市场份额。",
    })

    concentration_rows = []
    for key in MAIN_DIRECTIONS:
        g = groups[key]
        c = g["company_concentration_positions"]
        top = c.get("top_company")
        if top:
            concentration_rows.append((key, top["company"], top["n"], top["denominator_n"], top["pct"], c["top_three_share"]["pct"]))
    highest = max(concentration_rows, key=lambda x: x[4]) if concentration_rows else None
    if highest:
        insights.append({
            "id": "employer_concentration",
            "title": "职位加权结果受头部雇主集中度影响",
            "evidence": [f"{groups[highest[0]]['label']}方向中，{highest[1]}占 {highest[2]:,}/{highest[3]:,} 条 ({highest[4]:.1f}%)，该方向前三雇主合计占 {highest[5]:.1f}%。"],
            "interpretation": "职位加权率回答的是‘本次收集到的职位文本中有多少提到某技能’，不是典型公司的要求；单一雇主模板会显著影响比例。",
            "action": "阅读方向技能时同时查看 company_equal 率；求职者可用目标公司组内的要求做准备清单。",
            "limitation": "每家公司的职位数反映本次公开列表与采集范围，不等于HC或公司招聘强度。",
        })

    app = groups["application_agent"]
    app_skill = {x["skill"]: x for x in app["skill_metrics"]["skill_table"]}
    app_n = app["requirements_eligible_n"]
    app_parts = []
    for name in ("Agent", "RAG", "Python", "Java", "工具调用", "评测"):
        item = app_skill.get(name)
        if item:
            app_parts.append(f"{name} {frac(item['job_weighted']['n'], app_n)}")
    insights.append({
        "id": "app_agent_stack",
        "title": "应用/Agent岗位常同时要求后端工程基础与检索、智能体能力",
        "evidence": app_parts,
        "interpretation": "该方向的文本信号不是单一框架栈；Agent/RAG与Python、Java等通用工程语言并行出现。",
        "action": "准备可演示的Agent端到端项目，同时覆盖服务端、数据接入、工具调用与评测；简历按项目交付拆解。",
        "limitation": "技能词由词典匹配；提及不等于必需熟练，也不反映真实工作占比。",
    })

    agent_alg = groups["agent_algorithm"]
    algo_skills = {x["skill"]: x for x in agent_alg["skill_metrics"]["skill_table"]}
    algo_n = agent_alg["requirements_eligible_n"]
    compare_names = ("PyTorch", "RL/对齐", "评测", "Python", "C++", "GPU")
    compare = []
    for name in compare_names:
        a = algo_skills.get(name)
        b = app_skill.get(name)
        if a and b:
            compare.append(f"{name}: Agent算法 {frac(a['job_weighted']['n'], algo_n)}；应用/Agent {frac(b['job_weighted']['n'], app_n)}")
    insights.append({
        "id": "agent_algorithm_vs_application",
        "title": "Agent算法岗位更偏模型实验，应用岗位更偏系统落地",
        "evidence": compare,
        "interpretation": "两个方向有技术交集，但资格文本的重心不同；算法/研究方向更适合用模型训练、实验与论文/复现实绩说明能力，应用方向更适合强调可运行系统和业务链路。",
        "action": "求职材料分两版组织：算法版展示实验设计、对照与结果；应用版展示服务、数据/工具编排、上线质量和用户任务完成。",
        "limitation": "标题分组存在交叉；文本词项不能替代具体团队岗位说明。",
    })

    infra = groups["ai_infra"]
    infra_skills = {x["skill"]: x for x in infra["skill_metrics"]["skill_table"]}
    infra_n = infra["requirements_eligible_n"]
    infra_parts = []
    for name in ("GPU", "CUDA/Triton", "分布式系统", "性能优化", "NCCL/RDMA", "TVM/MLIR/XLA/LLVM", "vLLM/SGLang/TensorRT"):
        item = infra_skills.get(name)
        if item:
            infra_parts.append(f"{name} {frac(item['job_weighted']['n'], infra_n)}")
    insights.append({
        "id": "infra_profile",
        "title": "AI Infra职位的区分点集中在计算栈与系统性能",
        "evidence": infra_parts,
        "interpretation": "相比应用工程，GPU、通信/分布式和编译/内核工具在Infra资格文本里更常见；这支持按系统层级而非‘会不会某个大模型’来准备。",
        "action": "将个人项目分成推理/训练框架、GPU算子/编译、集群通信/调度、性能基准四类，并量化吞吐、时延、显存或稳定性结果。",
        "limitation": "同一方向含平台开发、性能工程、集群系统等不同职能；聚合比例会掩盖岗位差异。",
    })

    post = groups["posttraining"]
    post_skills = {x["skill"]: x for x in post["skill_metrics"]["skill_table"]}
    post_n = post["requirements_eligible_n"]
    post_parts = []
    for name in ("RL/对齐", "PyTorch", "SFT/微调", "DeepSpeed/Megatron/FSDP", "分布式系统"):
        item = post_skills.get(name)
        if item:
            post_parts.append(f"{name} {frac(item['job_weighted']['n'], post_n)}")
    unc = analysis["uncertain_posttraining_sensitivity"]
    post_text = analysis["posttraining_text_signal_sensitivity"]
    insights.append({
        "id": "posttraining_small_n",
        "title": "后训练标题组较小，但正文训练线索范围更广",
        "evidence": [
            f"严格标题主分类为 {post['positions_n']}/{analysis['data_overview']['specific_job_ads_n']} 条具体职位，覆盖 {post['company_concentration_positions']['companies_n']} 家公司。",
            f"生成式语境扫描池 {post_text['scan_universe_n']:,} 条中，职责词线索 {post_text['duty_text_cue']['n']:,}/{post_text['duty_text_cue']['denominator_n']:,}；资格词线索 {post_text['qualification_text_cue']['n']:,}/{post_text['qualification_text_cue']['denominator_n']:,}。",
            f"职责/资格文本纯并集 {post_text['duty_or_qualification_cue_union']['n']:,}/{post_text['duty_or_qualification_cue_union']['denominator_n']:,}；v2候选并集计入严格标题行后为 {post_text['report_candidate_union_including_strict_title']['n']:,}/{post_text['report_candidate_union_including_strict_title']['denominator_n']:,}，其中 {post_text['report_candidate_union_including_strict_title']['title_only_without_body_cue_n']} 条只由严格标题入列。",
            f"职责线索中有 {post_text['duty_cues_outside_strict_posttraining_title_n']:,} 条不在严格‘后训练’标题组；另把 {unc['uncertain_positions_n']} 条‘强化学习阶段待核’标题并入时，标题敏感性样本为 {unc['combined_positions_n']} 条职位、资格可分析 {unc['combined_requirements_eligible_n']} 条。",
            *post_parts,
        ],
        "interpretation": "37条是严格标题主分类，不是后训练工作线索的完整边界；职责与要求命中说明训练相关内容分散在算法、Agent或Infra职位文本中。",
        "action": "筛选岗位时用职责描述确认具体环节，再准备SFT/偏好优化/RL、评测与训练数据工程证据；标题和正文线索分开核验。",
        "limitation": post_text["interpretation_limit"] + " 词项命中依赖固定正则；生成式语境筛选和严格标题分类也会漏掉未出现这些词的岗位。",
    })

    edu = []
    for key in MAIN_DIRECTIONS:
        g = groups[key]
        e = g["qualification_metrics"]["education_mentions"]
        master = e["tiers_nonexclusive"]["硕士"]
        phd = e["tiers_nonexclusive"]["博士"]
        edu.append(f"{g['label']}: 硕士提及 {frac(master['n'], master['denominator_n'])}；博士提及 {frac(phd['n'], phd['denominator_n'])}")
    insights.append({
        "id": "education_mentions",
        "title": "学历词提及率可区分研究型与工程型文本，但不等于硬门槛",
        "evidence": edu,
        "interpretation": "不同方向的学历表达习惯不同；研究型描述更可能出现硕博词，工程方向经常依赖经验与系统能力。",
        "action": "如果目标组的硕博提及率较高，准备研究/实验/论文材料；如果文本常以经验技能表达，则优先补交付证据并逐岗核对学历要求。",
        "limitation": "education_mentions 是要求文本词级提及；不能区分最低学历、可替代学位或优先条件。",
    })

    exp_rows = []
    for key in MAIN_DIRECTIONS:
        g = groups[key]
        x = g["qualification_metrics"]["experience_explicitness"]
        exp_rows.append(f"{g['label']}: 年限词 {frac(x['numeric_years_mentioned']['n'], x['denominator_n'])}；明确不限/应届 {frac(x['open_or_newgrad_marker']['n'], x['denominator_n'])}；规范经验字段非未知 {frac(x['normalized_experience_field_known']['n'], x['denominator_n'])}")
    insights.append({
        "id": "experience_clarity",
        "title": "经验年限明确性需要与结构化字段覆盖分开读",
        "evidence": exp_rows,
        "interpretation": "年限词扫描与结构化经验字段是两种信息通道；不同方向中一方的覆盖率可高可低，二者不能互相替代，也不能据此推断缺少经验要求。",
        "action": "针对目标方向准备能对应年限门槛的项目年限/责任范围证明；面对未量化岗位，突出能力证据而非自行推断年限。",
        "limitation": "规则扫描会漏掉隐含经验表述，也会把必需与优先年限一并计入；不是最低年限解析器。",
    })

    balance_rows = []
    candidate_skills = ("Python", "Agent", "RAG", "PyTorch", "C++", "GPU", "CUDA/Triton", "RL/对齐")
    for key in MAIN_DIRECTIONS:
        g = groups[key]
        t = {x["skill"]: x for x in g["skill_metrics"]["skill_table"]}
        diff = [(abs(t[s]["company_equal_minus_job_weighted_pp"] or 0), s, t[s]) for s in candidate_skills if s in t and t[s]["company_equal"]["denominator_companies_n"]]
        if diff:
            _, name, item = max(diff)
            balance_rows.append(f"{g['label']} {name}: 职位加权 {frac(item['job_weighted']['n'], item['job_weighted']['denominator_n'])}；公司均权 {pct_text(item['company_equal']['mean_pct'])}（{item['company_equal']['denominator_companies_n']}家公司，每家资格样本至少{COMPANY_MIN_N}条）")
    insights.append({
        "id": "equal_company_vs_position_weight",
        "title": "职位加权与公司均权会给出不同的典型技能图景",
        "evidence": balance_rows,
        "interpretation": "职位加权按每条公开职位贡献一次；公司均权将符合门槛的每家公司贡献设为相同，弱化头部企业重复/大量发布的影响。",
        "action": "制定个人学习优先级时，把两种口径都列入；若技能只在职位加权率高，先核对是否由少数公司驱动。",
        "limitation": f"公司均权仅纳入每个方向有至少{COMPANY_MIN_N}条可分析要求的公司；不代表按员工数、业务规模或真实HC加权。",
    })

    city_parts = []
    for key in MAIN_DIRECTIONS:
        g = groups[key]
        cities = g["geography"]["major_city_mentions"]
        if cities:
            top = cities[0]
            city_parts.append(f"{g['label']}: {top['city']} {frac(top['n'], top['denominator_n'])}")
    insights.append({
        "id": "geographic_concentration",
        "title": "大城市职位集中明显，且地理字段仍有待核比例",
        "evidence": city_parts,
        "interpretation": "地点提及显示本次公开职位文本更多落在头部城市；多地点岗位会重复计入城市扫描，地域待核字段则留在独立类别。",
        "action": "先按可接受城市/远程条件筛选目标岗位，再比较方向技能；多城市岗位逐条确认团队实际办公地点。",
        "limitation": "城市别名扫描不覆盖全部城市/远程语义；多地点百分比不互斥，地理分类来自源字段解析。",
    })

    pair_parts = []
    for key in MAIN_DIRECTIONS:
        pairs = groups[key]["skill_metrics"]["cooccurrence"]["pairs"]
        if pairs:
            p = pairs[0]
            pair_parts.append(f"{groups[key]['label']}: {p['skill_a']} + {p['skill_b']} 共现 {p['n_both']}/{p['denominator_n']} ({pct_text(p['support_pct'])})，lift={p['lift']:.2f}")
    insights.append({
        "id": "skill_cooccurrence",
        "title": "高共现表示同帖关联，不等于必须成套掌握",
        "evidence": pair_parts,
        "interpretation": "同一资格文本里的共提只说明文本关联；技能可能是并列、至少掌握一种或优先条件，lift衡量相对独立频率的共现增强程度。",
        "action": "先核对完整JD中的并列、任选、优先等逻辑，再决定是否把技能组合成项目；共现不能推出必需的成套组合或学习先后顺序。",
        "limitation": f"仅保留同方向support≥{PAIR_MIN_SUPPORT}的技能对；模板复用、词典覆盖和职位重叠会影响共现，不能推断因果、强制组合或技术先后关系。",
    })

    controls = analysis["control_groups"]
    compare_names = ("Python", "Java", "C++", "PyTorch", "GPU", "SQL", "CUDA/Triton", "SoC/ASIC/RISC-V")
    control_evidence = []
    for key in ("ordinary_development", "non_ai_algorithm", "non_ai_hardware", "nontechnical"):
        c = controls[key]
        if not c["top_skills"]:
            continue
        lookup = {x["skill"]: x for x in c["top_skills"]}
        chosen = [f"{s} {frac(lookup[s]['job_weighted']['n'], lookup[s]['job_weighted']['denominator_n'])}" for s in compare_names if s in lookup][:3]
        control_evidence.append(f"{c['label']} ({c['requirements_eligible_n']:,}条资格文本): " + "；".join(chosen))
    insights.append({
        "id": "control_group_comparison",
        "title": "普通开发、算法与硬件对照能避免把所有技术要求混成一类",
        "evidence": control_evidence,
        "interpretation": "对照组说明基础工程语言与模型/硬件专门技能的出现背景不同；求职者可以基于目标岗位族组合，而非只按AI标签准备。",
        "action": "普通开发强调系统设计、语言与数据服务；算法/研究强调实验与模型框架；硬件岗位强调芯片/嵌入式验证与软硬协同。",
        "limitation": "对照组按job_family与title_direction规则筛选，存在分类错误；非技术组由预设职能集合构成。",
    })

    return insights


def posttraining_text_signal_metrics(specific: list[dict[str, Any]]) -> dict[str, Any]:
    """Reproduce the v2 report's broad posttraining cue scan, not a role label."""
    scan_universe = []
    for row in specific:
        if val_text(row.get("job_family")) not in TECHNICAL_FAMILIES:
            continue
        if not val_text(row.get("full_text")):
            continue
        context_text = "\n".join(
            val_text(row.get(field))
            for field in ("title", "description", "requirements_analysis")
        )
        if not GENERATIVE_CONTEXT.search(context_text) and row.get("title_direction") != "后训练":
            continue
        scan_universe.append(row)

    duty_rows = [r for r in scan_universe if POSTTRAINING_TEXT_WORD.search(val_text(r.get("description")))]
    qualification_rows = [r for r in scan_universe if POSTTRAINING_TEXT_WORD.search(val_text(r.get("requirements_analysis")))]
    cue_union = {
        val_text(r.get("id") or r.get("source_job_id"))
        for r in scan_universe
        if POSTTRAINING_TEXT_WORD.search(val_text(r.get("description")))
        or POSTTRAINING_TEXT_WORD.search(val_text(r.get("requirements_analysis")))
    }
    title_post = {
        val_text(r.get("id") or r.get("source_job_id"))
        for r in scan_universe if r.get("title_direction") == "后训练"
    }
    report_candidate_union = cue_union | title_post
    denominator = len(scan_universe)
    return {
        "scan_universe_n": denominator,
        "scan_universe_definition": (
            "具体职位中，job_family属于技术类集合、full_text非空，且title/description/requirements_analysis"
            "命中生成式模型语境词，或title_direction=后训练。"
        ),
        "posttraining_cue_regex": POSTTRAINING_TEXT_WORD.pattern,
        "generative_context_regex": GENERATIVE_CONTEXT.pattern,
        "duty_text_cue": {
            "n": len(duty_rows), "denominator_n": denominator,
            "pct": pct(len(duty_rows), denominator),
        },
        "qualification_text_cue": {
            "n": len(qualification_rows), "denominator_n": denominator,
            "pct": pct(len(qualification_rows), denominator),
        },
        "duty_or_qualification_cue_union": {
            "n": len(cue_union), "denominator_n": denominator,
            "pct": pct(len(cue_union), denominator),
        },
        "strict_title_posttraining_n": len(title_post),
        "report_candidate_union_including_strict_title": {
            "n": len(report_candidate_union), "denominator_n": denominator,
            "pct": pct(len(report_candidate_union), denominator),
            "title_only_without_body_cue_n": len(title_post - cue_union),
        },
        "duty_cues_outside_strict_posttraining_title_n": sum(
            r.get("title_direction") != "后训练" and bool(POSTTRAINING_TEXT_WORD.search(val_text(r.get("description"))))
            for r in scan_universe
        ),
        "interpretation_limit": (
            "职责/资格词命中只表示文本线索；可指Infra训练平台支持、Agent算法交叉或优先经验，"
            "不能直接认定职位主责为后训练，也不能当作HC。"
        ),
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
    elif path.suffix.lower() in {".ndjson", ".jsonl"}:
        with path.open("r", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
    else:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError("输入JSON必须是对象数组，或使用NDJSON/NDJSON.GZ。")
        rows = loaded
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("输入中的每条记录都必须是JSON对象。")
    return rows


def make_report(data_path: Path = DATA_PATH, stats_path: Path | None = STATS_PATH) -> dict[str, Any]:
    rows = load_rows(data_path)
    baseline = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path and stats_path.exists() else None
    record_kinds = Counter(val_text(r.get("record_kind") or "未标注") for r in rows)
    pools = [r for r in rows if r.get("record_kind") == "分领域毕业生招聘池"]
    specific = [r for r in rows if is_specific_ad(r)]
    if baseline and len(rows) != baseline.get("records"):
        raise ValueError(f"输入行数{len(rows)}与统计结果记录数{baseline.get('records')}不一致")

    all_skills = sorted({
        s for row in specific if has_usable_requirements(row)
        for s in (row.get("skills_in_requirement") or []) if isinstance(s, str) and s
    })
    by_direction: dict[str, list[dict[str, Any]]] = {
        key: [r for r in specific if r.get("title_direction") == label]
        for key, label in MAIN_DIRECTIONS.items()
    }
    directions = {}
    for key, label in MAIN_DIRECTIONS.items():
        g = group_record_metrics(by_direction[key], label, all_skills)
        g["positions_denominator_n"] = len(specific)
        g["positions_share_of_specific_ads_pct"] = pct(g["positions_n"], len(specific))
        directions[key] = g

    # Keep the uncertain RL-stage title bucket separate in the main view, then
    # add an explicit sensitivity view to show the denominator change.
    uncertain = [r for r in specific if r.get("title_direction") == UNCERTAIN_POSTTRAINING]
    post_core = by_direction["posttraining"]
    post_combined = post_core + uncertain
    uncertain_post = group_record_metrics(uncertain, UNCERTAIN_POSTTRAINING, all_skills)
    combined_post_metrics = requirement_metrics(post_combined)
    uncertain_sensitivity = {
        "uncertain_title_direction": UNCERTAIN_POSTTRAINING,
        "uncertain_positions_n": len(uncertain),
        "uncertain_requirements_eligible_n": sum(has_usable_requirements(r) for r in uncertain),
        "core_posttraining_positions_n": len(post_core),
        "combined_positions_n": len(post_combined),
        "combined_requirements_eligible_n": combined_post_metrics["eligible_requirements_n"],
        "combined_qualification_metrics": combined_post_metrics,
        "uncertain_group_top_skills": uncertain_post["skills"]["top_skills"],
        "note": "‘强化学习阶段待核’不并入核心后训练结论；此处仅展示若合并时分母及资格词指标变化。",
    }
    posttraining_text_sensitivity = posttraining_text_signal_metrics(specific)

    predicates = control_predicates()
    controls = {}
    for key, predicate in predicates.items():
        records = [r for r in specific if predicate(r)]
        item = group_record_metrics(records, CONTROL_LABELS[key], all_skills)
        item["positions_denominator_n"] = len(specific)
        item["positions_share_of_specific_ads_pct"] = pct(len(records), len(specific))
        # Control group skill lists can be large; keep full top skills and the
        # qualification aggregate, but omit every skill row not in the top 15.
        controls[key] = item

    company_balance = {}
    for key, records in by_direction.items():
        req_rows = [r for r in records if has_usable_requirements(r)]
        all_company_n = Counter(val_text(r.get("company")) or "未知" for r in records)
        req_company_n = Counter(val_text(r.get("company")) or "未知" for r in req_rows)
        company_balance[key] = {
            "label": MAIN_DIRECTIONS[key],
            "position_company_n": len(all_company_n),
            "requirement_company_n": len(req_company_n),
            "company_min_requirements_for_equal_weight": COMPANY_MIN_N,
            "equal_weight_included_companies": sorted(c for c, n in req_company_n.items() if n >= COMPANY_MIN_N),
            "position_weighted_top_companies": concentration(records, "具体职位广告") ["top_companies"],
            "requirements_position_weighted_top_companies": concentration(req_rows, "资格可分析职位") ["top_companies"],
            "equal_company_denominator_n": sum(n >= COMPANY_MIN_N for n in req_company_n.values()),
        }

    summary_direction_counts = Counter(val_text(r.get("title_direction") or "未分方向") for r in specific)
    all_req_eligible = [r for r in specific if has_usable_requirements(r)]
    overview = {
        "input_records_n": len(rows),
        "input_stats_records_n": baseline.get("records") if baseline else None,
        "record_kind_counts": {k: v for k, v in record_kinds.most_common()},
        "specific_job_ads_n": len(specific),
        "aggregated_graduate_pools_excluded_from_role_level_analysis_n": len(pools),
        "requirements_eligible_specific_ads_n": len(all_req_eligible),
        "requirements_eligible_filter": "requirements_available=true 且 requirements_analysis/requirements 非空",
        "all_specific_ads_body_archived_n": sum(bool(r.get("full_text")) for r in specific),
        "specific_ads_direction_counts": dict(summary_direction_counts.most_common()),
        "source_scope_note": baseline.get("scope_note") if baseline else None,
        "input_stats_snapshot": {k: baseline.get(k) for k in ("body_archived", "separate_requirements", "legacy_without_body", "duplicate_id_updates", "title_directions", "job_families")} if baseline else {},
    }

    # Four direction profile, deliberately retaining the public list count and
    # requirements-eligible count as separate denominators.
    profiles = {}
    for key, data in directions.items():
        profiles[key] = {
            "label": data["label"],
            "positions_n": data["positions_n"],
            "positions_denominator_n": data["positions_denominator_n"],
            "positions_share_of_specific_ads_pct": data["positions_share_of_specific_ads_pct"],
            "requirements_eligible_n": data["requirements_eligible_n"],
            "requirements_eligible_pct_of_positions": data["requirements_eligible_pct_of_positions"],
            "company_concentration_positions": data["company_concentration_positions"],
            "company_concentration_requirements_eligible": data["company_concentration_requirements_eligible"],
            "geography": data["geography"],
            "qualification_metrics": data["qualification_metrics"],
            "skill_metrics": data["skills"],
        }
    control_profiles = {}
    for key, data in controls.items():
        control_profiles[key] = {
            "label": data["label"],
            "positions_n": data["positions_n"],
            "positions_denominator_n": data["positions_denominator_n"],
            "positions_share_of_specific_ads_pct": data["positions_share_of_specific_ads_pct"],
            "requirements_eligible_n": data["requirements_eligible_n"],
            "requirements_eligible_pct_of_positions": data["requirements_eligible_pct_of_positions"],
            "qualification_metrics": data["qualification_metrics"],
            "top_skills": data["skills"]["top_skills"],
            "company_concentration_positions": data["company_concentration_positions"],
            "geography": data["geography"],
        }

    result = {
        "schema_version": "3.0",
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "source": {
            "jobs_file": data_path.name,
            "stats_file": stats_path.name if baseline and stats_path else None,
            "records_loaded": len(rows),
            "analysis_is_descriptive": True,
        },
        "metric_definitions": {
            "specific_position": "record_kind != 分领域毕业生招聘池；输入中的两条NVIDIA新毕业生聚合招聘池从具体职位层分析排除，并在record_kind计数中保留。",
            "direction_groups": "严格按title_direction四个核心标签分组；‘强化学习阶段待核’单独列出，不自动并入后训练。",
            "requirements_eligible": "requirements_available=true 且 requirements_analysis/requirements 非空。技能、学历、经验指标均仅使用该集合。",
            "skill_job_weighted": "提及该skill的资格文本职位数 / 该方向全部可分析资格文本职位数。",
            "skill_company_equal": f"先计算公司内提及职位数 / 公司内可分析资格文本职位数，再对每方向可分析资格数≥{COMPANY_MIN_N}的公司取简单均值；不是职位加权。",
            "education": "使用education_mentions词级字段；本科/硕士/博士提及率分别以可分析资格文本数为分母，多个层级可同时出现。",
            "experience": "使用requirements_analysis/requirements文本扫描年限和不限/应届信号；同时报告归一化experience字段非未知率。未区分必需条件与优先条件。",
            "geography": "geography类别与具体职位记录数为分母；城市为city字段别名命中职位数/组内职位数，多地点可重复命中。",
            "skill_cooccurrence": f"同一条可分析资格文本同时提及两个技能的记录数；仅保留support n≥{PAIR_MIN_SUPPORT}。lift=(n_both/N)/[(n_a/N)(n_b/N)]。",
            "posttraining_text_signal_sensitivity": "严格复现v2正文线索筛选：技术职能且full_text非空的具体职位中，title/description/requirements_analysis命中生成式模型语境词，或title_direction=后训练；再分别扫描description与requirements_analysis中的后训练/SFT/RLHF等词。此为文本线索敏感性，不是岗位主责判定。",
            "no_causal_inference": "共现、比例、集中度均为该批本地公开职位文本的描述性关联，不代表因果关系、招聘名额、技能门槛强度或录用概率。",
        },
        "data_overview": overview,
        "directions": profiles,
        "uncertain_posttraining_sensitivity": uncertain_sensitivity,
        "posttraining_text_signal_sensitivity": posttraining_text_sensitivity,
        "control_groups": control_profiles,
        "company_balance": company_balance,
    }
    result["insights"] = build_insights(result)
    return result


def render_markdown(data: dict[str, Any]) -> str:
    overview = data["data_overview"]
    directions = data["directions"]
    insights = data["insights"]
    lines = [
        "# 高级分析与结论 v3",
        "",
        f"生成时间：{data['generated_at']}。数据来源：本地 v2 合并集及其统计汇总。",
        "",
        "## 范围与口径",
        "",
        f"- 输入 {overview['input_records_n']:,} 条；职位层分析纳入 {overview['specific_job_ads_n']:,} 条具体职位，排除 {overview['aggregated_graduate_pools_excluded_from_role_level_analysis_n']} 条分领域毕业生招聘池。",
        f"- 资格文本可分析 {overview['requirements_eligible_specific_ads_n']:,} 条；条件为 `requirements_available=true` 且资格文本非空。职位总数和资格分母分开报告。",
        "- 四方向按 `title_direction` 标签严格分组。19条“强化学习阶段待核”保留为敏感性口径，不自动并入核心后训练。",
        "- 技能频率使用 `skills_in_requirement`；学历使用 `education_mentions`；经验明确度用资格文本扫描年限/应届/不限标记，并另列规范经验字段覆盖。",
        "- 职位加权让每条职位等权；公司均权先计算公司内比例，再对每方向至少有5条可分析资格的公司取简单平均。",
        "- 城市采用固定中英文别名命中 `city`；多城市职位可命中多个城市。技能对仅报告同一资格文本共现至少20条的组合，lift按独立边际期望定义，不作因果解释。",
        "",
        "本数据是多个雇主公开列表与存档记录的并集，收集范围、页面筛选和公司覆盖并不一致。因此下列比例只描述本地职位文本，不能当作全国市场份额、HC缺口或录用概率。",
        "",
        "## 四方向概览",
        "",
        "| 方向 | 具体职位 n / 全集 | 资格可分析 n / 职位 | 公司数 | 头部雇主（职位加权） | 前三雇主份额 |",
        "|---|---:|---:|---|---|---:|",
    ]
    for key, direction_data in directions.items():
        c = direction_data["company_concentration_positions"]
        top = c["top_company"]
        lines.append(
            f"| {direction_data['label']} | {direction_data['positions_n']:,}/{direction_data['positions_denominator_n']:,} ({pct_text(direction_data['positions_share_of_specific_ads_pct'])}) | "
            f"{direction_data['requirements_eligible_n']:,}/{direction_data['positions_n']:,} ({pct_text(direction_data['requirements_eligible_pct_of_positions'])}) | "
            f"{c['companies_n']} | {top['company']} {top['n']:,}/{top['denominator_n']:,} ({pct_text(top['pct'])}) | "
            f"{pct_text(c['top_three_share']['pct'])} |"
        )
    post_text = data["posttraining_text_signal_sensitivity"]
    lines += [
        "", "## 后训练正文信号敏感性", "",
        f"生成式语境扫描池为 {post_text['scan_universe_n']:,} 条具体职位；职责词线索 {post_text['duty_text_cue']['n']:,}/{post_text['duty_text_cue']['denominator_n']:,} ({pct_text(post_text['duty_text_cue']['pct'])})，资格词线索 {post_text['qualification_text_cue']['n']:,}/{post_text['qualification_text_cue']['denominator_n']:,} ({pct_text(post_text['qualification_text_cue']['pct'])})。职责/资格文本的纯并集为 {post_text['duty_or_qualification_cue_union']['n']:,}/{post_text['duty_or_qualification_cue_union']['denominator_n']:,} ({pct_text(post_text['duty_or_qualification_cue_union']['pct'])})。",
        f"按v2正文候选清单口径，再纳入严格标题为后训练的职位后共 {post_text['report_candidate_union_including_strict_title']['n']:,}/{post_text['report_candidate_union_including_strict_title']['denominator_n']:,} ({pct_text(post_text['report_candidate_union_including_strict_title']['pct'])})；其中 {post_text['report_candidate_union_including_strict_title']['title_only_without_body_cue_n']} 条仅因标题入列。职责线索有 {post_text['duty_cues_outside_strict_posttraining_title_n']:,} 条落在严格后训练标题组之外。",
        "这些词线索不代表职位主责，也不能相加为招聘名额；它们可能来自Infra训练平台支持、Agent算法交叉职责或优先经历。",
        "", "## 职位加权与公司均权技能对照", ""
    ]
    comparison_skills = ("Agent", "RAG", "Python", "Java", "PyTorch", "RL/对齐", "GPU", "CUDA/Triton", "分布式系统", "NCCL/RDMA", "SFT/微调", "评测")
    lines += ["| 方向 | 技能 | 职位加权 n/分母 | 职位加权率 | 公司均权率 | 纳入公司数 |", "|---|---|---:|---:|---:|---:|"]
    for key, direction_data in directions.items():
        lookup = {x["skill"]: x for x in direction_data["skill_metrics"]["skill_table"]}
        for skill in comparison_skills:
            item = lookup.get(skill)
            if not item or (item["job_weighted"]["n"] == 0 and item["company_equal"]["mean_pct"] is None):
                continue
            lines.append(f"| {direction_data['label']} | {skill} | {item['job_weighted']['n']:,}/{item['job_weighted']['denominator_n']:,} | {pct_text(item['job_weighted']['pct'])} | {pct_text(item['company_equal']['mean_pct'])} | {item['company_equal']['denominator_companies_n']} |")
    lines += ["", "公司均权率仅在该方向可分析资格数≥5的公司之间取平均；表中公司数就是均权分母。", "", "## 学历、经验与地域对比", "", "| 方向 | 资格分母 | 本科提及 | 硕士提及 | 博士提及 | 年限词 | 不限/应届 | 规范经验字段非未知 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key, direction_data in directions.items():
        q = direction_data["qualification_metrics"]
        edu = q["education_mentions"]
        exp = q["experience_explicitness"]
        d = q["eligible_requirements_n"]
        lines.append(
            f"| {direction_data['label']} | {d:,} | {frac(edu['tiers_nonexclusive']['本科']['n'],d)} | {frac(edu['tiers_nonexclusive']['硕士']['n'],d)} | {frac(edu['tiers_nonexclusive']['博士']['n'],d)} | "
            f"{frac(exp['numeric_years_mentioned']['n'],d)} | {frac(exp['open_or_newgrad_marker']['n'],d)} | {frac(exp['normalized_experience_field_known']['n'],d)} |"
        )
    lines += ["", "学历词层级可重叠；年限/应届标记扫描不等于必需条件解析。", "", "## 技能共现", ""]
    for key, direction_data in directions.items():
        pairs = direction_data["skill_metrics"]["cooccurrence"]["pairs"][:8]
        lines += [f"### {direction_data['label']}", ""]
        if not pairs:
            lines += ["没有组合达到 support ≥20。", ""]
        else:
            lines += ["| 组合 | 共现 n/分母 | Support | 边际 nA/nB | Lift |", "|---|---:|---:|---:|---:|"]
            for p in pairs:
                lines.append(f"| {p['skill_a']} + {p['skill_b']} | {p['n_both']:,}/{p['denominator_n']:,} | {pct_text(p['support_pct'])} | {p['n_a']:,}/{p['n_b']:,} | {p['lift']:.2f} |")
            lines.append("")
    lines += ["Lift = (同帖共现率)/(两个技能边际率乘积)。高于1表示在样本资格文本中比独立边际期望更常一起出现；共享模板或技术类别会产生关联，不能推出技能之间的因果关系。", "", "## 对照组", "", "| 对照组 | 具体职位 | 资格可分析 | 高频技能（n/资格分母） |", "|---|---:|---:|---|"]
    for key, item in data["control_groups"].items():
        tops = "；".join(f"{x['skill']} {x['job_weighted']['n']:,}/{x['job_weighted']['denominator_n']:,} ({pct_text(x['job_weighted']['pct'])})" for x in item["top_skills"][:5])
        lines.append(f"| {item['label']} | {item['positions_n']:,} | {item['requirements_eligible_n']:,} | {tops} |")
    lines += ["", "对照组用于展示文本差异，不与四方向的职位权重混合。普通开发、算法和硬件对照排除了相应AI方向标签；非技术组按职能族定义。", "", "## 可核查结论与行动建议", ""]
    for i, insight in enumerate(insights, 1):
        lines += [f"### {i}. {insight['title']}", "", "**证据**"]
        for ev in insight["evidence"]:
            lines.append(f"- {ev}")
        lines += ["", f"**解释：** {insight['interpretation']}", "", f"**行动：** {insight['action']}", "", f"**局限：** {insight['limitation']}", ""]
    lines += ["## 数据使用边界", "", "- 本分析没有重新联网，使用本地已归档职位文本。公开招聘条目不证明仍有实际HC、预算、用人优先级或HR确认。", "- 技能提及、教育词、年限词和共现依赖归档文本及词典/标题规则；通用招聘模板、免责声明和分类错误可能影响命中。", "- 不把收集样本解释为全国岗位总量、市场份额、技能因果关系或个人录用概率。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute descriptive job-text analysis from a JSON array or NDJSON.GZ dataset.")
    parser.add_argument("--input", type=Path, help="Input JSON array, .ndjson, .jsonl, or .ndjson.gz file; defaults to the project's evidence/all_jobs_v2.json.")
    parser.add_argument("--stats", type=Path, help="Optional matching analysis/统计结果_v2.json snapshot for count validation and metadata.")
    parser.add_argument("--output-dir", type=Path, help="Output folder; defaults to the project's analysis folder.")
    args = parser.parse_args()
    input_path = args.input or (Path(__file__).resolve().parents[1] / 'data/corpus.ndjson.gz')
    stats_path = args.stats if args.stats else (STATS_PATH if input_path.resolve() == DATA_PATH.resolve() else None)
    output_dir = args.output_dir or (Path(__file__).resolve().parents[1] / 'reports/recomputed')
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / "advanced_analysis_v3.json"
    out_md = output_dir / "高级分析与结论_v3.md"
    result = make_report(data_path=input_path, stats_path=stats_path)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({
        "json": str(out_json),
        "markdown": str(out_md),
        "input": str(input_path),
        "stats": str(stats_path) if stats_path else None,
        "records": result["data_overview"]["input_records_n"],
        "specific_ads": result["data_overview"]["specific_job_ads_n"],
        "requirements_eligible": result["data_overview"]["requirements_eligible_specific_ads_n"],
        "directions": {k: {"positions": v["positions_n"], "requirements": v["requirements_eligible_n"]} for k, v in result["directions"].items()},
        "insights": len(result["insights"]),
        "pairs_by_direction": {k: v["skill_metrics"]["cooccurrence"]["qualifying_pairs_n"] for k, v in result["directions"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
