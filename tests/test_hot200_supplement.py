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
        document = BeautifulSoup(page.read_text(encoding="utf8"), "html.parser")
        reader = document.select_one(".site-shell-cols > main.reader-card")
        assert reader["data-content-id"] == chapter["id"]
        assert reader.select_one("#solutionProgress")["data-content-id"] == chapter["id"]
        assert reader.select_one("#selftestToggle")
        assert document.select_one(".sol-rail-left .sol-nav-item.current")["href"] == page.name
        directory = document.select(".sol-rail-right .toc a[href^='#']")
        assert directory and all(document.find(id=unquote(a["href"][1:])) for a in directory)
        panels = reader.select("section.language-panel")
        assert [panel["data-lang"] for panel in panels] == ["java", "python"]
        for panel in panels:
            assert panel.select_one("pre code") and panel.select_one("h4")
            assert panel.select_one(".aside-warn") and panel.select_one(".aside-note")
            assert panel.select_one("table tbody tr")
        iframe = reader.select_one("iframe.reader-visual-frame")
        assert iframe["loading"] == "lazy"
        demo = page.parent / (iframe["src"].split("?")[0])
        payload = json.loads(BeautifulSoup(demo.read_bytes(), "html.parser", from_encoding="utf-8").select_one("#problemExample").string)
        assert payload["no"] == str(row["id"]) and len(payload["frames"]) >= 3
        assert all(f["cells"] and f["why"] for f in payload["frames"])
        assert reader.find("a", href=f"https://leetcode.cn/problems/{row['slug']}/")
        for link in reader.select('a[href*="/company-solutions/"]'):
            assert (page.parent / unquote(link["href"])).is_file()
