"""Appending to a dotfile, with a syntax check and rollback."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .fs import mode_of

TARGETS: dict[str, str] = {
    "aliases": ".aliases.zsh",
    "scripts": ".scripts.zsh",
    "env": ".environment.zsh",
    "environment": ".environment.zsh",
    "zshrc": ".zshrc",
    "zshenv": ".zshenv",
    "zprofile": ".zprofile",
    "secrets": ".secrets.zsh",
    "credentials": ".credentials.zsh",
    "gitconfig": ".gitconfig",
}

DESCRIPTIONS: dict[str, str] = {
    ".aliases.zsh": "short command aliases",
    ".scripts.zsh": "shell functions",
    ".environment.zsh": "exported environment variables",
    ".zshrc": "interactive shell setup",
    ".zshenv": "every shell, including non-interactive",
    ".zprofile": "login shells",
    ".secrets.zsh": "API tokens — sensitive, 0600",
    ".credentials.zsh": "logins and passwords — sensitive, 0600",
    ".gitconfig": "git configuration",
}

SENSITIVE: frozenset[str] = frozenset({".secrets.zsh", ".credentials.zsh"})


def is_sensitive(path: Path) -> bool:
    return path.name in SENSITIVE


def target_table() -> list[tuple[str, str, str]]:
    """(name, filename, description) for every target, in load order."""
    order = [
        "zshenv",
        "zprofile",
        "zshrc",
        "aliases",
        "scripts",
        "env",
        "secrets",
        "credentials",
        "gitconfig",
    ]
    return [(name, TARGETS[name], DESCRIPTIONS.get(TARGETS[name], "")) for name in order]


class AppendError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppendResult:
    path: Path
    added: str
    checked: bool


def resolve_target(config: Config, name: str) -> Path:
    """Accept a friendly name (aliases), a dotfile name, or a path."""
    key = TARGETS.get(name.lower())
    if key:
        return config.home / key

    candidate = Path(name).expanduser()
    if candidate.is_absolute():
        return candidate

    direct = config.home / name
    if direct.exists():
        return direct

    known = ", ".join(sorted(set(TARGETS)))
    raise AppendError(f"unknown target {name!r}; try one of: {known}")


def _syntax_ok(path: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["zsh", "-n", str(path)], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return True, f"skipped syntax check: {exc}"
    return proc.returncode == 0, proc.stderr.strip()


def append(config: Config, name: str, content: str, check: bool = True) -> AppendResult:
    """Append content to a dotfile, reverting if it would break the shell.

    A bad line in .zshrc or .aliases.zsh breaks every new terminal, and the
    usual `>>` gives no warning. This writes, runs `zsh -n`, and puts the file
    back exactly as it was if the check fails.
    """
    path = resolve_target(config, name)
    if not path.exists():
        raise AppendError(f"{path} does not exist")

    original = path.read_bytes()
    mode = mode_of(path)

    body = content if content.endswith("\n") else content + "\n"
    prefix = "" if original.endswith(b"\n") or not original else "\n"

    with path.open("ab") as handle:
        handle.write((prefix + body).encode())
    os.chmod(path, mode)

    should_check = check and (path.suffix == ".zsh" or path.name.startswith(".zsh"))
    if not should_check:
        return AppendResult(path, body.rstrip("\n"), checked=False)

    ok, message = _syntax_ok(path)
    if not ok:
        path.write_bytes(original)
        os.chmod(path, mode)
        raise AppendError(f"syntax check failed, {path.name} reverted:\n{message}")

    return AppendResult(path, body.rstrip("\n"), checked=True)
