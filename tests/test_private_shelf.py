from pathlib import Path
from bs4 import BeautifulSoup
from scripts.build.build_library import private_shelf_entry

ROOT = Path(__file__).resolve().parents[1]


def test_public_shelf_has_empty_mount_and_no_private_metadata():
    page = (ROOT / 'library/index.html').read_text()
    soup = BeautifulSoup(page, 'html.parser')
    host = soup.select_one('#privateTeachingShelf')
    assert host is not None and host.has_attr('hidden') and not host.contents
    assert soup.select_one('script[src="../assets/private-archive-entry.js?v=5"]')
    assert not soup.select('#moduleGrid #privateTeachingShelf')
    assert 'AgentHub 教学档案' not in page
    assert '/api/private-archive/index.html' not in page
    generated = private_shelf_entry('<main class="module-grid" id="moduleGrid"></main>')
    assert str(BeautifulSoup(generated, 'html.parser').select_one('#privateTeachingShelf')) == str(host)


def test_old_admin_entry_removed_and_return_points_to_shelf():
    admin = (ROOT / 'pages/admin.html').read_text()
    assert 'privateArchiveEntry' not in admin
    assert 'private-archive-entry.js' not in admin
    script = (ROOT / 'assets/private-archive-shell.js').read_text()
    assert "back.href = '/library/index.html'" in script
    assert "back.href = '/pages/admin.html'" not in script


def test_private_metadata_is_not_in_public_display_script():
    script = (ROOT / 'assets/private-archive-entry.js').read_text()
    assert 'AgentHub' not in script
    assert 'localStorage' not in script and 'sessionStorage' not in script
