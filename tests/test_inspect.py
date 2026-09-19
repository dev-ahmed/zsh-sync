from __future__ import annotations

from pathlib import Path

from zsh_sync.inspect import aliases, exports, functions

ALIASES = """\
# ─── Git ────────────────────────────────
alias cgit='cd `git rev-parse --show-toplevel`'     # jump to repo root
alias start='git flow feature start'
# ─── Storage ────────────────────────────
alias py="python3"
alias hash-it='echo "# not a comment"'              # keeps the # inside quotes
not_an_alias=1
"""

SCRIPTS = """\
# ─── markdown → odt ─────────────────────
md2odt() {
  pandoc "$1"
}

# ─── guard ──────────────────────────────
function ssd_mounted {
  [[ -f x ]]
}
ssd_export() {   # export only when mounted
  print hi
}
"""

ENVIRONMENT = """\
# ─── Paths ──────────────────────────────
export WORKSPACE="$HOME/Workspace/Work"
export TOKEN="super-secret-value"          # should never be printed
local NOT_EXPORTED=1
"""


def test_aliases_are_named_and_described(tmp_path: Path) -> None:
    path = tmp_path / ".aliases.zsh"
    path.write_text(ALIASES)

    found = aliases(path)
    names = [item.name for item in found]

    assert names == ["cgit", "start", "py", "hash-it"]
    assert found[0].detail == "jump to repo root"
    assert found[0].section == "Git"


def test_alias_without_a_comment_falls_back_to_its_body(tmp_path: Path) -> None:
    path = tmp_path / ".aliases.zsh"
    path.write_text(ALIASES)

    start = next(item for item in aliases(path) if item.name == "start")
    assert start.detail == "git flow feature start"


def test_hash_inside_quotes_is_not_a_comment(tmp_path: Path) -> None:
    path = tmp_path / ".aliases.zsh"
    path.write_text(ALIASES)

    item = next(i for i in aliases(path) if i.name == "hash-it")
    assert item.detail == "keeps the # inside quotes"


def test_sections_are_tracked(tmp_path: Path) -> None:
    path = tmp_path / ".aliases.zsh"
    path.write_text(ALIASES)

    py = next(item for item in aliases(path) if item.name == "py")
    assert py.section == "Storage"


def test_both_function_styles_are_found(tmp_path: Path) -> None:
    path = tmp_path / ".scripts.zsh"
    path.write_text(SCRIPTS)

    names = [item.name for item in functions(path)]
    assert names == ["md2odt", "ssd_mounted", "ssd_export"]


def test_function_comment_is_captured(tmp_path: Path) -> None:
    path = tmp_path / ".scripts.zsh"
    path.write_text(SCRIPTS)

    item = next(i for i in functions(path) if i.name == "ssd_export")
    assert item.detail == "export only when mounted"


def test_exports_list_names_but_never_values(tmp_path: Path) -> None:
    path = tmp_path / ".environment.zsh"
    path.write_text(ENVIRONMENT)

    found = exports(path)
    names = [item.name for item in found]

    assert names == ["WORKSPACE", "TOKEN"]
    assert all("super-secret-value" not in item.detail for item in found)
    assert all("Workspace" not in item.detail for item in found)


def test_missing_file_is_empty_not_an_error(tmp_path: Path) -> None:
    assert aliases(tmp_path / "nope.zsh") == []
    assert functions(tmp_path / "nope.zsh") == []
    assert exports(tmp_path / "nope.zsh") == []
