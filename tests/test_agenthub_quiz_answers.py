"""Keep the reviewed answer attached to its meaning when lab options are reordered."""
import json
from pathlib import Path


CORRECT_OPTIONS = {
    "atomic-claim": ("可信的外部执行回执", "共享数据库原子 CAS", "按已有状态退出"),
    "gateway-visible": ("是否已向 Runtime yield", "MODEL_STREAM_INTERRUPTED", "两档各尝试最多 2 次"),
    "approval-twin": ("execution_status=NOT_STARTED", "外部服务可能已处理成功", "Run.created_by"),
    "version-freeze": ("在创建 Run 时动态解析并固化", "选择已发布的 V1", "严格使用 S3"),
    "evidence-journey": ("准入后的模型输入", "整条跳过", "按题等权"),
    "wiki-lineage": ("子字符串引用", "WIKI_PUBLICATION_REVOKED", "重新绑定"),
    "memory-stages": ("保持原有的 ACTIVE", "通过了分类预算准入", "冻结的 effective_memory_snapshot"),
    "experiment-freeze": ("20 道独立题目，60 次用例尝试", "阻断 Materialize", "task_success 指标"),
}


def test_answer_keys_match_reviewed_options():
    path = Path(__file__).resolve().parents[1] / "library/agenthub/data/visuals.json"
    labs = json.loads(path.read_text(encoding="utf-8"))
    assert {lab["id"] for lab in labs} == CORRECT_OPTIONS.keys()
    for lab in labs:
        for question, phrase in zip(lab["questions"], CORRECT_OPTIONS[lab["id"]], strict=True):
            matches = [index for index, option in enumerate(question["options"]) if phrase in option]
            assert matches == [question["answer"]], (lab["id"], question["q"], matches)
