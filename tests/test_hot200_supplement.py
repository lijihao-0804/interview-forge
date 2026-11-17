import json
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]


def test_supplement_has_independent_question_ids_links_and_bilingual_solutions():
    library = ROOT / "library"
    rows = json.loads((ROOT / "data/hot200-extra.json").read_bytes())
    catalog = json.loads((library / "manifest.json").read_bytes())
    modules = {module["id"]: module for module in catalog["modules"]}
    hot100 = {int(c["id"].split(":")[1]) for c in modules["hot100"]["chapters"]}
    ids = {row["id"] for row in rows}
    assert len(ids) == len(rows) == 100 and ids.isdisjoint(hot100)
    assert [row["position"] for row in rows] == list(range(101, 201))
    chapters = modules["hot200-extra"]["chapters"]
    assert len(chapters) == len(rows)

    for chapter, row in zip(chapters, rows):
        assert chapter["id"] == f"hot200-extra:{row['id']:04d}"
        assert catalog["routes"]["/library/" + chapter["url"]]["content_id"] == chapter["id"]
        page = library / chapter["url"]
        reader = BeautifulSoup(page.read_text(encoding="utf8"), "html.parser").select_one("main.reader")
        assert reader["data-content-id"] == chapter["id"]
        panels = reader.select("section.language-panel")
        assert [panel["data-lang"] for panel in panels] == ["java", "python"]
        assert all(panel.select_one("pre code") for panel in panels)
        assert reader.find("a", href=f"https://leetcode.cn/problems/{row['slug']}/")
        for link in reader.select('a[href*="/company-solutions/"]'):
            assert (page.parent / unquote(link["href"])).is_file()
