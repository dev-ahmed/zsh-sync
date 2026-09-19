"""Organize zsh files: extract functions to separate files in .scripts/ folder."""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass

SECTION = re.compile(r"^#\s*[─—-]{2,}\s*(?P<title>.*?)\s*[─—-]{2,}\s*$")
FUNCTION = re.compile(
    r"^\s*(?:function\s+(?P<fname>[\w.:-]+)\s*(?:\(\s*\))?|(?P<pname>[\w.:-]+)\s*\(\s*\))\s*\{"
)


@dataclass
class Function:
    name: str
    body: str
    comment: str
    section: str


def extract_functions(path: Path) -> tuple[list[Function], list[str]]:
    """Extract functions from a script file, return functions and remaining lines."""
    if not path.is_file():
        return [], []

    lines = path.read_text(errors="replace").splitlines()
    functions = []
    remaining = []
    section = ""
    i = 0

    while i < len(lines):
        line = lines[i]

        heading = SECTION.match(line)
        if heading:
            title = heading.group("title").strip()
            if title:
                section = title
            remaining.append(line)
            i += 1
            continue

        match = FUNCTION.match(line)
        if not match:
            remaining.append(line)
            i += 1
            continue

        name = match.group("fname") or match.group("pname")
        if not name:
            remaining.append(line)
            i += 1
            continue

        comment = ""
        if i > 0 and lines[i - 1].strip().startswith("#") and not SECTION.match(lines[i - 1]):
            comment = lines[i - 1]
            remaining.pop()

        body_lines = [line]
        brace_count = line.count("{") - line.count("}")
        i += 1

        while i < len(lines) and brace_count > 0:
            body_lines.append(lines[i])
            brace_count += lines[i].count("{") - lines[i].count("}")
            i += 1

        functions.append(Function(name, "\n".join(body_lines), comment, section))

    return functions, remaining


def organize_scripts(home: Path, dry_run: bool = False) -> list[tuple[str, str]]:
    """
    Organize .scripts.zsh by extracting functions to .scripts/ folder.
    Returns list of (action, description) tuples.
    """
    scripts_file = home / ".scripts.zsh"
    scripts_dir = home / ".scripts"

    if not scripts_file.is_file():
        return [("error", f"{scripts_file} does not exist")]

    functions, remaining = extract_functions(scripts_file)

    if not functions:
        return [("no-op", "no functions found in .scripts.zsh")]

    actions = []

    if not dry_run:
        scripts_dir.mkdir(exist_ok=True)

    for func in functions:
        func_file = scripts_dir / f"{func.name}.zsh"
        content = ""
        if func.comment:
            content = func.comment + "\n"
        content += func.body + "\n"

        if not dry_run:
            func_file.write_text(content)

        actions.append(("created", f".scripts/{func.name}.zsh"))

    aggregator = "# Auto-generated: sources all scripts from .scripts/ folder\n\n"
    if any(func.section for func in functions):
        sections = {}
        for func in functions:
            if func.section not in sections:
                sections[func.section] = []
            sections[func.section].append(func.name)

        for section, names in sections.items():
            if section:
                aggregator += f"# ─── {section} ───\n"
            for name in names:
                aggregator += f"source ~/.scripts/{name}.zsh\n"
            aggregator += "\n"
    else:
        for func in functions:
            aggregator += f"source ~/.scripts/{func.name}.zsh\n"

    if remaining:
        aggregator = "\n".join(remaining) + "\n\n" + aggregator

    if not dry_run:
        scripts_file.write_text(aggregator)

    actions.append(("updated", ".scripts.zsh (now sources individual files)"))

    return actions
