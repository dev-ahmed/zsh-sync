"""Read the tracked dotfiles and report what they define."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SECTION = re.compile(r"^#\s*[─—-]{2,}\s*(?P<title>.*?)\s*[─—-]{2,}\s*$")
ALIAS = re.compile(r"^\s*alias\s+(?P<name>[\w.-]+)=(?P<body>.*)$")
FUNCTION = re.compile(
    r"^\s*(?:function\s+(?P<fname>[\w.:-]+)\s*(?:\(\s*\))?|(?P<pname>[\w.:-]+)\s*\(\s*\))\s*\{"
)
EXPORT = re.compile(r"^\s*export\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)=")


@dataclass(frozen=True)
class Item:
    name: str
    detail: str
    section: str


def _trailing_comment(line: str) -> str:
    """The `# description` after a definition, if the # isn't inside quotes."""
    in_single = in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double and index > 0:
            return line[index + 1 :].strip()
    return ""


def _strip_quotes(value: str) -> str:
    value = value.strip()
    comment = _trailing_comment(value)
    if comment:
        value = value[: value.rfind("#")].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value.strip()


def _scan(path: Path, pattern: re.Pattern[str], key: str, detail_of) -> list[Item]:
    if not path.is_file():
        return []

    items: list[Item] = []
    section = ""

    for line in path.read_text(errors="replace").splitlines():
        heading = SECTION.match(line)
        if heading:
            title = heading.group("title").strip()
            if title:
                section = title
            continue

        match = pattern.match(line)
        if not match:
            continue

        name = match.group(key) if key in match.groupdict() else None
        if name is None:
            name = match.group("fname") or match.group("pname")
        if not name:
            continue

        items.append(Item(name, detail_of(line, match), section))

    return items


def aliases(path: Path) -> list[Item]:
    def detail(line: str, match: re.Match[str]) -> str:
        described = _trailing_comment(line)
        return described or _strip_quotes(match.group("body"))

    return _scan(path, ALIAS, "name", detail)


def functions(path: Path) -> list[Item]:
    def detail(line: str, _match: re.Match[str]) -> str:
        return _trailing_comment(line)

    return _scan(path, FUNCTION, "__either__", detail)


def exports(path: Path) -> list[Item]:
    """Variable names only — the values are frequently secrets."""

    def detail(line: str, _match: re.Match[str]) -> str:
        return _trailing_comment(line)

    return _scan(path, EXPORT, "name", detail)
