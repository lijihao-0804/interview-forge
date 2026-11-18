"""Reviewed documents linked from the published research and practice pages."""

import re
from urllib.parse import urljoin

DOCUMENTS = {
    "/library/ai-employment-research/DATA_SCHEMA.md": "jobs-data-schema",
    "/library/ai-employment-research/INTEGRATION.md": "jobs-integration",
    "/library/ai-employment-research/MAINTENANCE.md": "jobs-maintenance",
    "/library/ai-employment-research/maintenance/PACKAGE_COMMANDS.md": "jobs-package-commands",
    "/library/communications-research/README.md": "communications-overview",
    "/library/communications-research/MAINTENANCE.md": "communications-maintenance",
    "/library/communications-research/reports/专业筛选审阅.md": "communications-selection",
    "/library/communications-research/REBUILD.md": "communications-rebuild",
    "/library/hot200-extra/LICENSE-walkccc.txt": "walkccc-license",
}
READER_ROOT = "/library/document-readers/"
_ANCHOR_HREF = re.compile(rb'(<a\b[^>]*?\shref=)(["\x27])([^"\x27]+)\2', re.IGNORECASE)


def link_readers(page: str, content: bytes) -> bytes:
    def replace(match):
        path = urljoin(page, match[3].decode("utf-8"))
        slug = DOCUMENTS.get(path)
        if slug is None:
            return match[0]
        return match[1] + match[2] + (READER_ROOT + slug + ".html").encode() + match[2]

    return _ANCHOR_HREF.sub(replace, content)
