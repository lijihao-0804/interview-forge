"""Private teaching-site member policy and symlink-safe directory reads."""
from contextlib import ExitStack
import os
from pathlib import Path
import re
import stat

from interview_forge.core.paths import ROOT

MAX_MEMBER_BYTES = 32 * 1024 * 1024
_TYPES = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript',
          '.json':'application/json', '.webp':'image/webp', '.png':'image/png',
          '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.woff2':'font/woff2'}
_DATA = {'manifest.json', 'diagrams.json', 'history-data.json', 'history-sample.json',
         'history-templates.json', 'notes.json', 'search-index.json', 'visuals.json'}


def member_type(member: str) -> str | None:
    if not member or any(c in member for c in ('\\', '%', ':', '\0')):
        return None
    parts = member.split('/')
    if any(not p or p.startswith('.') or p != p.rstrip(' .') for p in parts):
        return None
    allowed = member == 'index.html'
    allowed |= member in {'assets/app.css', 'assets/app.js', 'assets/hljs.js'}
    allowed |= len(parts) == 2 and parts[0] == 'data' and parts[1] in _DATA
    allowed |= len(parts) == 3 and parts[:2] == ['assets', 'media'] and Path(parts[2]).suffix.lower() in {'.webp','.png','.jpg','.svg'}
    if len(parts) == 3 and parts[0] == 'data':
        patterns = {'chapters':r'[a-z0-9][a-z0-9-]*\.json', 'originals':r'doc-\d+\.json', 'sources':r'b_\d+\.json'}
        allowed |= bool(re.fullmatch(patterns.get(parts[1], r'(?!)'), parts[2]))
    return _TYPES.get(Path(member).suffix.lower()) if allowed else None


def private_directory(value: str) -> Path:
    path = Path(value)
    if not value or not path.is_absolute() or '..' in path.parts:
        raise ValueError('Private directory must be absolute')
    if path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Private directory must be outside the repository')
    return path


def read_directory_member(root: Path, member: str) -> bytes:
    """Open every path component without following links, including ancestors.

    dir_fd keeps traversal anchored even if an operator renames a directory.
    Fail closed on platforms without the required secure-open primitives.
    """
    private_directory(str(root))
    if member_type(member) is None:
        raise FileNotFoundError(member)
    if os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW'):
        raise OSError('Secure directory serving requires POSIX openat/O_NOFOLLOW')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as stack:
        fd = os.open(root.anchor, directory_flags)
        stack.callback(os.close, fd)
        for part in (*root.parts[1:], *member.split('/')[:-1]):
            fd = os.open(part, directory_flags, dir_fd=fd)
            stack.callback(os.close, fd)
        leaf = os.open(member.split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        stream = stack.enter_context(os.fdopen(leaf, 'rb'))
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_MEMBER_BYTES:
            raise FileNotFoundError(member)
        body = stream.read(MAX_MEMBER_BYTES + 1)
        if len(body) > MAX_MEMBER_BYTES:
            raise FileNotFoundError(member)
        return body
