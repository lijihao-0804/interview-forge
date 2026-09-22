"""合订本构建脚本的幂等性回归测试。

这个脚本历史上不幂等：它假设 SRC 永远是 PDF 导出的原始形态(没有书名、标题从
一级起)，于是每跑一次就加一层 `# Agent 面经` 并把全书标题再压深一级。SRC 被
人工修订成合订本形态之后，再跑一次就会把书毁掉。这里把两条分支都钉住。
"""
from __future__ import annotations

import pytest

from scripts.build import build_agent_mianjing_book as builder

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
