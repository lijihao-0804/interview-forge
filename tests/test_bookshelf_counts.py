from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup


def test_public_track_and_category_counts_match_visible_entries():
    shelf = Path(__file__).resolve().parents[1] / "library" / "index.html"
    page = BeautifulSoup(shelf.read_text(encoding="utf-8"), "html.parser")
    cards = page.select("#moduleGrid .module-card")
    tracks = Counter(card["data-track"] for card in cards)
    categories = Counter((card["data-track"], card["data-category"]) for card in cards)

    track_buttons = page.select(".track-card[data-track-filter]:not(#projectNotesTrack)")
    assert {button["data-track-filter"] for button in track_buttons} == set(tracks)
    for button in track_buttons:
        assert int(button.select_one(".track-meta").get_text(strip=True).split()[0]) == tracks[button["data-track-filter"]]

    chips = {
        (group["data-track-group"], chip["data-cat-filter"]): int(chip.select_one(".chip-n").get_text())
        for group in page.select("[data-track-group]")
        for chip in group.select("[data-cat-filter]")
    }
    assert chips == dict(categories)
