from unittest.mock import patch

from interview_forge.api.app import app
from interview_forge.api.routers.private_archive import archive_resource
from scripts.check.server_page_links import is_registered_server_page


def test_private_entry_has_a_real_get_handler():
    assert is_registered_server_page('/api/private-archive/index.html')


def test_missing_handler_is_not_hidden_by_static_fallback():
    routes = [route for route in app.router.routes
              if getattr(route, 'endpoint', None) is not archive_resource]
    with patch.object(app.router, 'routes', routes):
        assert not is_registered_server_page('/api/private-archive/index.html')


def test_unknown_api_paths_and_private_members_remain_invalid():
    for path in ['/api/private-archive/typo.html', '/api/private-archive/data/missing.json',
                 '/api/private-archives/index.html', '/api/not-real', '/pages/missing.html']:
        assert not is_registered_server_page(path)
