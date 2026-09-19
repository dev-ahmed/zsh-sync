"""Which files are tracked, and where they are backed up to."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "zsh-sync" / "config.json"

DEFAULT_SSD = Path("/Volumes/devSSD")
DEFAULT_STORE = "backups/zsh-sync"
DEFAULT_MARKER = ".dev-ssd-marker"

DEFAULT_FILES: tuple[str, ...] = (
    ".zshenv",
    ".zprofile",
    ".zshrc",
    ".aliases.zsh",
    ".scripts.zsh",
    ".environment.zsh",
    ".secrets.zsh",
    ".credentials.zsh",
    ".gitconfig",
)

DEFAULT_GLOBS: tuple[str, ...] = ("bin/*",)

MAX_SNAPSHOTS = 20


@dataclass(frozen=True)
class Config:
    home: Path = field(default_factory=Path.home)
    ssd: Path = DEFAULT_SSD
    store_rel: str = DEFAULT_STORE
    marker: str = DEFAULT_MARKER
    files: tuple[str, ...] = DEFAULT_FILES
    globs: tuple[str, ...] = DEFAULT_GLOBS
    max_snapshots: int = MAX_SNAPSHOTS

    @property
    def store(self) -> Path:
        return self.ssd / self.store_rel

    @property
    def current(self) -> Path:
        return self.store / "current"

    @property
    def snapshots(self) -> Path:
        return self.store / "snapshots"

    @property
    def manifest(self) -> Path:
        return self.store / "manifest.json"

    def ssd_mounted(self) -> bool:
        return (self.ssd / self.marker).exists()


def _from_mapping(data: dict) -> Config:
    base = Config()
    return Config(
        home=Path(data.get("home", base.home)).expanduser(),
        ssd=Path(data.get("ssd", base.ssd)),
        store_rel=data.get("store", base.store_rel),
        marker=data.get("marker", base.marker),
        files=tuple(data.get("files", base.files)),
        globs=tuple(data.get("globs", base.globs)),
        max_snapshots=int(data.get("max_snapshots", base.max_snapshots)),
    )


def load_config(path: Path | None = None) -> Config:
    """Read config from disk, falling back to defaults and then env overrides."""
    target = path or CONFIG_PATH
    config = Config()

    if target.is_file():
        try:
            config = _from_mapping(json.loads(target.read_text()))
        except (json.JSONDecodeError, ValueError, TypeError):
            config = Config()

    env_ssd = os.environ.get("ZSH_SYNC_SSD") or os.environ.get("SSD")
    if env_ssd:
        config = Config(
            home=config.home,
            ssd=Path(env_ssd),
            store_rel=config.store_rel,
            marker=config.marker,
            files=config.files,
            globs=config.globs,
            max_snapshots=config.max_snapshots,
        )

    return config


def save_config(config: Config, path: Path | None = None) -> Path:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "ssd": str(config.ssd),
                "store": config.store_rel,
                "marker": config.marker,
                "files": list(config.files),
                "globs": list(config.globs),
                "max_snapshots": config.max_snapshots,
            },
            indent=2,
        )
        + "\n"
    )
    return target


def track(config: Config, entry: str, path: Path | None = None) -> tuple[Config, bool]:
    """Add a path to the tracked list. Returns the new config and whether it changed."""
    key = entry.strip()
    if key.startswith("~"):
        key = key[1:].lstrip("/")
    candidate = Path(key)
    if candidate.is_absolute():
        try:
            key = str(candidate.relative_to(config.home))
        except ValueError:
            raise ValueError(f"{entry} is outside {config.home}")

    is_glob = any(ch in key for ch in "*?[")
    existing = config.globs if is_glob else config.files
    if key in existing:
        return config, False

    updated = Config(
        home=config.home,
        ssd=config.ssd,
        store_rel=config.store_rel,
        marker=config.marker,
        files=config.files if is_glob else config.files + (key,),
        globs=config.globs + (key,) if is_glob else config.globs,
        max_snapshots=config.max_snapshots,
    )
    save_config(updated, path)
    return updated, True


def write_default_config(path: Path | None = None) -> Path:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    base = Config()
    target.write_text(
        json.dumps(
            {
                "ssd": str(base.ssd),
                "store": base.store_rel,
                "marker": base.marker,
                "files": list(base.files),
                "globs": list(base.globs),
                "max_snapshots": base.max_snapshots,
            },
            indent=2,
        )
        + "\n"
    )
    return target
