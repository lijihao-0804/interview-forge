"""Safely install an extracted private teaching site into a new release directory.
Usage: python -m scripts.install_private_archive /private/site.zip /private/releases/v2/site
Never overwrite an existing release. Point the server's PRIVATE_ARCHIVE_DIR at
this destination only after validation; keep the previous release for rollback.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from interview_forge.services.private_archive_store import MAX_MEMBER_BYTES, member_type, private_directory

MAX_TOTAL_BYTES = 256 * 1024 * 1024
_DIRECTORIES = {'site/', 'site/assets/', 'site/assets/media/', 'site/data/',
                'site/data/chapters/', 'site/data/originals/', 'site/data/sources/'}


def install(source: Path, destination: Path) -> None:
    destination = private_directory(str(destination))
    # Do not traverse existing symlinks, including an operator-provided parent.
    for parent in (destination, *destination.parents):
        if parent.is_symlink():
            raise ValueError('Symlink destinations are forbidden')
    if destination.exists():
        raise FileExistsError('Choose a new release directory; existing releases are never overwritten')
    if not destination.parent.is_dir():
        raise ValueError('Create a private parent directory before installation')
    with zipfile.ZipFile(source) as package:
        members = package.infolist()
        if len(members) > 5000 or sum(i.file_size for i in members) > MAX_TOTAL_BYTES:
            raise ValueError('Archive exceeds installation limits')
        seen = set()
        for info in members:
            name = info.filename
            mode = stat.S_IFMT(info.external_attr >> 16)
            if name in seen or mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Duplicate or non-regular archive member')
            seen.add(name)
            if info.is_dir():
                if name not in _DIRECTORIES:
                    raise ValueError('Unexpected archive directory')
            elif not name.startswith('site/') or member_type(name[5:]) is None or info.file_size > MAX_MEMBER_BYTES:
                raise ValueError('Unexpected or oversized archive member')
        if not {'site/index.html', 'site/assets/app.js', 'site/data/manifest.json'} <= seen:
            raise ValueError('Incomplete teaching site')
        staging = Path(tempfile.mkdtemp(prefix='.teaching-install-', dir=destination.parent))
        try:
            for info in members:
                if info.is_dir():
                    continue
                target = staging / info.filename[5:]
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with package.open(info) as src, target.open('xb') as out:
                    shutil.copyfileobj(src, out)
                if target.stat().st_size != info.file_size:
                    raise ValueError('Archive member size mismatch')
                target.chmod(0o600)
            # The parent is operator-owned; no untrusted writer may rename it.
            # Recheck before an atomic same-filesystem publish of this new release.
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('Destination appeared during installation')
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    install(args.source, args.destination)
    print('Private teaching site extracted. Configure INTERVIEW_FORGE_PRIVATE_ARCHIVE_DIR after verification.')
