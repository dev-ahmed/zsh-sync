from __future__ import annotations

import os
from pathlib import Path

import pytest

from zsh_sync.config import Config, load_config, track
from zsh_sync.edit import AppendError, append


@pytest.fixture()
def env(tmp_path: Path) -> Config:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".aliases.zsh").write_text("alias a=b\n")
    (home / ".gitconfig").write_text("[user]\n")
    secret = home / ".secrets.zsh"
    secret.write_text("export TOKEN=shh\n")
    os.chmod(secret, 0o600)
    return Config(home=home, ssd=tmp_path / "devSSD", files=(".aliases.zsh",), globs=())


def test_append_adds_a_line(env: Config) -> None:
    append(env, "aliases", "alias c=d")
    assert (env.home / ".aliases.zsh").read_text() == "alias a=b\nalias c=d\n"


def test_append_inserts_missing_trailing_newline(env: Config) -> None:
    (env.home / ".aliases.zsh").write_text("alias a=b")
    append(env, "aliases", "alias c=d")
    assert (env.home / ".aliases.zsh").read_text() == "alias a=b\nalias c=d\n"


def test_broken_syntax_is_reverted(env: Config) -> None:
    original = (env.home / ".aliases.zsh").read_text()

    with pytest.raises(AppendError, match="reverted"):
        append(env, "aliases", 'alias broken="unclosed')

    assert (env.home / ".aliases.zsh").read_text() == original


def test_append_preserves_secret_mode(env: Config) -> None:
    append(env, "secrets", "export OTHER=1")
    assert (env.home / ".secrets.zsh").stat().st_mode & 0o777 == 0o600


def test_non_zsh_file_skips_the_check(env: Config) -> None:
    result = append(env, ".gitconfig", "  name = Ahmed")
    assert result.checked is False
    assert "name = Ahmed" in (env.home / ".gitconfig").read_text()


def test_unknown_target_is_rejected(env: Config) -> None:
    with pytest.raises(AppendError, match="unknown target"):
        append(env, "nope", "x")


def test_missing_file_is_rejected(env: Config) -> None:
    with pytest.raises(AppendError, match="does not exist"):
        append(env, "zshrc", "x")


def test_track_adds_a_file(tmp_path: Path) -> None:
    config = Config(home=tmp_path, files=(".zshrc",), globs=())
    target = tmp_path / "config.json"

    updated, changed = track(config, ".tmux.conf", target)
    assert changed is True
    assert ".tmux.conf" in updated.files
    assert target.is_file()

    again, changed_again = track(updated, ".tmux.conf", target)
    assert changed_again is False
    assert again.files == updated.files


def test_track_accepts_a_glob(tmp_path: Path) -> None:
    config = Config(home=tmp_path, files=(), globs=())
    updated, changed = track(config, "bin/*", tmp_path / "config.json")
    assert changed is True
    assert "bin/*" in updated.globs


def test_track_normalises_absolute_and_tilde_paths(tmp_path: Path) -> None:
    config = Config(home=tmp_path, files=(), globs=())
    target = tmp_path / "config.json"

    updated, _ = track(config, str(tmp_path / ".vimrc"), target)
    assert ".vimrc" in updated.files

    updated2, _ = track(updated, "~/.inputrc", target)
    assert ".inputrc" in updated2.files


def test_track_rejects_paths_outside_home(tmp_path: Path) -> None:
    config = Config(home=tmp_path / "home", files=(), globs=())
    with pytest.raises(ValueError, match="outside"):
        track(config, "/etc/passwd", tmp_path / "config.json")


def test_saved_config_round_trips(tmp_path: Path) -> None:
    config = Config(home=tmp_path, files=(".zshrc",), globs=())
    target = tmp_path / "config.json"
    track(config, ".tmux.conf", target)

    reloaded = load_config(target)
    assert ".tmux.conf" in reloaded.files
