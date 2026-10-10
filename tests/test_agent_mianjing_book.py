"""合订本构建脚本的幂等性回归测试。

这个脚本历史上不幂等：它假设 SRC 永远是 PDF 导出的原始形态(没有书名、标题从
一级起)，于是每跑一次就加一层 `# Agent 面经` 并把全书标题再压深一级。SRC 被
人工修订成合订本形态之后，再跑一次就会把书毁掉。这里把两条分支都钉住。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.build import build_agent_mianjing_book as builder

ROOT = Path(__file__).resolve().parents[1]

RAW = """# 1.1 什么是大语言模型

正文一。

```python
# 这是代码注释，不是标题
print("hi")
```

# 1.2 训练范式

正文二。
"""

NESTED = """# Agent 面经

## 1.1 Skill 是什么

````markdown
# PDF Processing

## Quick start

```python
import pdfplumber
```
````

## 1.2 下一节
"""


@pytest.fixture()
def book(tmp_path, monkeypatch):
    """把脚本的 SRC/OUT 指到临时目录，返回 (写入源文件, 读取产物) 两个闭包。"""
    src, out = tmp_path / "src.md", tmp_path / "out.md"
    monkeypatch.setattr(builder, "SRC", src)
    monkeypatch.setattr(builder, "OUT", out)
    monkeypatch.setattr(builder, "ROOT", tmp_path)

    def run(text: str) -> str:
        src.write_text(text, encoding="utf-8")
        builder.main()
        return out.read_text(encoding="utf-8")

    return run


def test_raw_source_gets_title_and_demotion(book):
    result = book(RAW)
    assert result.startswith("# Agent 面经\n\n")
    assert "## 1.1 什么是大语言模型" in result
    assert "## 1.2 训练范式" in result
    # 围栏里的 # 是代码注释，不能当标题降级
    assert '# 这是代码注释，不是标题' in result
    assert '## 这是代码注释' not in result


def test_already_normalized_source_is_left_alone(book):
    once = book(NESTED)
    assert once.count("# Agent 面经") == 1
    assert "## 1.1 Skill 是什么" in once
    assert "### 1.1 Skill 是什么" not in once


def test_repeated_runs_are_idempotent(book, tmp_path):
    """产物再喂回去当源，必须原样输出——这是脚本被误跑两次时的真实场景。"""
    first = book(NESTED)
    second = book(first)
    third = book(second)
    assert first == second == third


def test_nested_fence_headings_survive(book):
    result = book(NESTED)
    # ```` 包着 ```python 的嵌套围栏：内层 ``` 不能被当成收栏，
    # 否则 "## Quick start" 会被误判成正文标题
    assert "## Quick start" in result
    assert "### Quick start" not in result


def test_lora_example_is_a_valid_python_code_block():
    source = (ROOT / "books" / "agent面经" / "agent面经.md").read_text(encoding="utf-8")
    match = re.search(r"代码示例：\s*```python\n(.*?)\n```", source, re.DOTALL)

    assert match is not None
    compile(match.group(1), "agent-mianjing-lora-example", "exec")
    assert "from torch import nn" in match.group(1)
    assert "torch.nnas" not in source
    assert not re.search(r"(?m)^\|\s*\d+(?:\s*<br>.*)?\s*\|", source)


def test_prompt_examples_do_not_contain_pdf_line_number_artifacts():
    source = (ROOT / "books" / "agent面经" / "agent面经.md").read_text(encoding="utf-8")

    assert "```text\n请判断以下文本的情感倾向（正面或负面）：\n文本：这个产品质量非常好，使用体验也很棒。\n```" in source
    assert "```text\n任务：判断文本情感\n\n文本：这个电影非常精彩\n情感：正面" in source
    assert "文本：产品做工很好\n情感：\n```" in source
    assert "```text\n问题：一个盒子里有 3 个红球和 2 个蓝球，总共有多少个球？\n请一步一步思考并给出答案。\n```" in source
    assert not re.search(
        r"(?m)^1\s+(?:请判断|任务：|问题：|请检查|忽略之前|请假装|退款怎么弄|商品退款|如何申请信用卡|如何重置账户|代码块北京|上海现在)",
        source,
    )
    assert not re.search(r"^1\s+[^\n]+\s+2\s+3\s+", source, re.MULTILINE)
