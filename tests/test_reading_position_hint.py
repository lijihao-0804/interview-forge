"""阅读位置恢复提示：最多展示 10 秒，点击或明显滚动后立即收起。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_builder_and_generated_pages_share_new_hint_timing():
    builder = (ROOT / "scripts/build/build_library.py").read_text(encoding="utf-8")
    page = (ROOT / "library/java-core/chapter-01.html").read_text(encoding="utf-8")
    for name, text in (("builder", builder), ("page", page)):
        assert "hintHideTimer=setTimeout" in text, name
        assert "10000" in text, name
        assert "hintHideNow" in text, name
        assert "Math.abs(window.scrollY-hintStartY)>80" in text, name
        assert "},4200);" not in text, name
