"""Backup, status and restore over the tracked zsh files."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from .config import Config
from .fs import copy_preserving_mode, mode_of, relative_key, sha256


class SsdNotMounted(RuntimeError):
    pass


class State(str, Enum):
    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    MISSING_LOCALLY = "missing-locally"


@dataclass(frozen=True)
class Entry:
    key: str
    state: State
    local: Path | None
    backed_up: Path | None


@dataclass(frozen=True)
class BackupResult:
    entries: tuple[Entry, ...]
    snapshot: Path | None

    @property
    def written(self) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.state in (State.NEW, State.CHANGED))


def require_ssd(config: Config) -> None:
    if not config.ssd.exists():
        raise SsdNotMounted(f"{config.ssd} is not mounted")
    if not config.ssd_mounted():
        raise SsdNotMounted(f"{config.ssd} is mounted but has no {config.marker}")


def tracked_paths(config: Config) -> list[Path]:
    """Every tracked file that currently exists, de-duplicated, in stable order."""
    found: list[Path] = []
    seen: set[Path] = set()

    candidates = [config.home / name for name in config.files]
    for pattern in config.globs:
        candidates.extend(sorted(config.home.glob(pattern)))

    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        found.append(path)

    return found


def read_manifest(config: Config) -> dict:
    if not config.manifest.is_file():
        return {}
    try:
        return json.loads(config.manifest.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _manifest_entry(path: Path) -> dict:
    return {
        "sha256": sha256(path),
        "mode": oct(mode_of(path)),
        "size": path.stat().st_size,
    }


def status(config: Config) -> tuple[Entry, ...]:
    """Compare the machine against the backup without writing anything."""
    require_ssd(config)
    manifest = read_manifest(config)
    entries: list[Entry] = []

    for path in tracked_paths(config):
        key = relative_key(path, config.home)
        mirror = config.current / key
        recorded = manifest.get(key, {}).get("sha256")

        if not mirror.exists() or recorded is None:
            state = State.NEW
        elif sha256(path) != recorded:
            state = State.CHANGED
        else:
            state = State.UNCHANGED

        entries.append(Entry(key, state, path, mirror if mirror.exists() else None))

    local_keys = {e.key for e in entries}
    for key in sorted(manifest):
        if key in local_keys:
            continue
        mirror = config.current / key
        entries.append(Entry(key, State.MISSING_LOCALLY, None, mirror if mirror.exists() else None))

    return tuple(entries)


def _new_snapshot_dir(config: Config) -> Path:
    """A fresh snapshot directory, suffixed if one already exists this second."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    candidate = config.snapshots / stamp

    suffix = 2
    while candidate.exists():
        candidate = config.snapshots / f"{stamp}-{suffix}"
        suffix += 1

    candidate.mkdir(parents=True)
    return candidate


def _prune_snapshots(config: Config) -> None:
    if not config.snapshots.is_dir():
        return
    existing = sorted((p for p in config.snapshots.iterdir() if p.is_dir()), reverse=True)
    for stale in existing[config.max_snapshots :]:
        shutil.rmtree(stale, ignore_errors=True)


def backup(config: Config, force: bool = False) -> BackupResult:
    """Mirror changed files to the SSD, snapshotting only when something moved."""
    require_ssd(config)
    entries = status(config)
    changed = [e for e in entries if e.state in (State.NEW, State.CHANGED)]

    if not changed and not force:
        return BackupResult(entries, None)

    config.current.mkdir(parents=True, exist_ok=True)
    snapshot = _new_snapshot_dir(config)

    manifest = read_manifest(config)
    for path in tracked_paths(config):
        key = relative_key(path, config.home)
        copy_preserving_mode(path, config.current / key)
        copy_preserving_mode(path, snapshot / key)
        manifest[key] = _manifest_entry(path)

    config.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _prune_snapshots(config)

    return BackupResult(entries, snapshot)


def list_snapshots(config: Config) -> tuple[Path, ...]:
    require_ssd(config)
    if not config.snapshots.is_dir():
        return ()
    return tuple(sorted((p for p in config.snapshots.iterdir() if p.is_dir()), reverse=True))


def resolve_source(config: Config, snapshot: str | None) -> Path:
    if snapshot is None:
        return config.current
    candidate = config.snapshots / snapshot
    if not candidate.is_dir():
        raise FileNotFoundError(f"no snapshot named {snapshot}")
    return candidate


def restorable(config: Config, source: Path) -> list[tuple[str, Path]]:
    if not source.is_dir():
        return []
    return [
        (str(p.relative_to(source)), p) for p in sorted(source.rglob("*")) if p.is_file()
    ]


def restore(
    config: Config,
    snapshot: str | None = None,
    only: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Copy files back onto the machine. Skips files that already exist unless overwrite."""
    require_ssd(config)
    source = resolve_source(config, snapshot)
    actions: list[tuple[str, str]] = []

    for key, backed_up in restorable(config, source):
        if only and key != only and Path(key).name != only:
            continue

        target = config.home / key
        if target.exists() and not overwrite:
            actions.append((key, "skipped (exists)"))
            continue

        if not dry_run:
            copy_preserving_mode(backed_up, target)
        actions.append((key, "would restore" if dry_run else "restored"))

    return actions
