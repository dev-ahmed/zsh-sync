from __future__ import annotations

import os
from pathlib import Path

import pytest

from zsh_sync.config import Config
from zsh_sync.sync import (
    SsdNotMounted,
    State,
    backup,
    list_snapshots,
    restore,
    status,
)


@pytest.fixture()
def env(tmp_path: Path) -> Config:
    home = tmp_path / "home"
    ssd = tmp_path / "devSSD"
    (home / "bin").mkdir(parents=True)
    ssd.mkdir()
    (ssd / ".dev-ssd-marker").touch()

    (home / ".zshrc").write_text("alias a=b\n")
    secret = home / ".secrets.zsh"
    secret.write_text("export TOKEN=shh\n")
    os.chmod(secret, 0o600)
    (home / "bin" / "tool.sh").write_text("#!/bin/sh\necho hi\n")

    return Config(
        home=home,
        ssd=ssd,
        files=(".zshrc", ".secrets.zsh", ".missing.zsh"),
        globs=("bin/*.sh",),
        max_snapshots=3,
    )


def test_requires_mounted_ssd(env: Config) -> None:
    (env.ssd / ".dev-ssd-marker").unlink()
    with pytest.raises(SsdNotMounted):
        status(env)


def test_first_sync_reports_everything_new(env: Config) -> None:
    result = backup(env)
    assert {e.key for e in result.written} == {".zshrc", ".secrets.zsh", "bin/tool.sh"}
    assert result.snapshot is not None


def test_absent_files_are_skipped_not_errors(env: Config) -> None:
    backup(env)
    assert ".missing.zsh" not in {e.key for e in status(env)}


def test_second_sync_is_a_noop(env: Config) -> None:
    backup(env)
    result = backup(env)
    assert result.written == ()
    assert result.snapshot is None


def test_edit_is_detected_and_resynced(env: Config) -> None:
    backup(env)
    (env.home / ".zshrc").write_text("alias a=c\n")

    changed = [e for e in status(env) if e.state is State.CHANGED]
    assert [e.key for e in changed] == [".zshrc"]

    result = backup(env)
    assert [e.key for e in result.written] == [".zshrc"]
    assert (env.current / ".zshrc").read_text() == "alias a=c\n"


def test_secret_mode_survives_backup_and_restore(env: Config) -> None:
    backup(env)
    assert (env.current / ".secrets.zsh").stat().st_mode & 0o777 == 0o600

    (env.home / ".secrets.zsh").unlink()
    restore(env)
    assert (env.home / ".secrets.zsh").stat().st_mode & 0o777 == 0o600


def test_restore_keeps_existing_files_unless_overwrite(env: Config) -> None:
    backup(env)
    (env.home / ".zshrc").write_text("local edit\n")

    restore(env)
    assert (env.home / ".zshrc").read_text() == "local edit\n"

    restore(env, overwrite=True)
    assert (env.home / ".zshrc").read_text() == "alias a=b\n"


def test_restore_after_total_loss(env: Config) -> None:
    backup(env)
    for path in (env.home / ".zshrc", env.home / ".secrets.zsh", env.home / "bin" / "tool.sh"):
        path.unlink()

    actions = restore(env)
    assert all(outcome == "restored" for _, outcome in actions)
    assert (env.home / ".zshrc").exists()
    assert (env.home / "bin" / "tool.sh").exists()


def test_dry_run_writes_nothing(env: Config) -> None:
    backup(env)
    (env.home / ".zshrc").unlink()

    actions = restore(env, dry_run=True)
    assert (".zshrc", "would restore") in actions
    assert not (env.home / ".zshrc").exists()


def test_restore_single_file(env: Config) -> None:
    backup(env)
    (env.home / ".zshrc").unlink()
    (env.home / ".secrets.zsh").unlink()

    restore(env, only=".zshrc")
    assert (env.home / ".zshrc").exists()
    assert not (env.home / ".secrets.zsh").exists()


def test_missing_locally_is_flagged(env: Config) -> None:
    backup(env)
    (env.home / ".zshrc").unlink()

    entry = next(e for e in status(env) if e.key == ".zshrc")
    assert entry.state is State.MISSING_LOCALLY


def test_snapshots_are_pruned_to_the_limit(env: Config) -> None:
    for index in range(5):
        (env.home / ".zshrc").write_text(f"version {index}\n")
        backup(env)

    assert len(list_snapshots(env)) == env.max_snapshots


def test_restore_from_a_named_snapshot(env: Config) -> None:
    (env.home / ".zshrc").write_text("first\n")
    first = backup(env).snapshot
    assert first is not None

    (env.home / ".zshrc").write_text("second\n")
    backup(env)

    restore(env, snapshot=first.name, overwrite=True)
    assert (env.home / ".zshrc").read_text() == "first\n"
