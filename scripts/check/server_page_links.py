"""Validate the small set of navigable pages served by backend handlers.

Do not accept arbitrary /api/ links: typos must still fail the release check.
Private archive members cannot be shipped to the public repository to satisfy
filesystem checks; their contents and access boundary have separate API tests.
"""
from starlette.routing import Match


def is_registered_server_page(link: str) -> bool:
    if link != "/api/private-archive/index.html":
        return False
    from interview_forge.api.app import app
    from interview_forge.api.routers.private_archive import archive_resource

    scope = {"type": "http", "method": "GET", "path": link, "root_path": ""}
    for route in app.routes:
        match, _ = route.matches(scope)
        if match is Match.FULL:
            # A generic static fallback must not make a missing API route valid.
            return getattr(route, "endpoint", None) is archive_resource
    return False
