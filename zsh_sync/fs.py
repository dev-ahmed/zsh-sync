"""File helpers: hashing, and copying that preserves permission bits."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mode_of(path: Path) -> int:
    return path.stat().st_mode & 0o777


def copy_preserving_mode(source: Path, target: Path) -> None:
    """Copy source to target, carrying its permission bits across.

    Secrets live at 0600; a copy that widened them would be the whole point of
    this tool undone, so the mode is applied explicitly rather than inherited
    from the destination's umask.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = mode_of(source)

    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            shutil.copyfileobj(src, out)
    except BaseException:
        if target.exists():
            target.unlink(missing_ok=True)
        raise

    os.chmod(target, mode)
    shutil.copystat(source, target, follow_symlinks=True)
    os.chmod(target, mode)


def relative_key(path: Path, home: Path) -> str:
    try:
        return str(path.relative_to(home))
    except ValueError:
        return path.name
