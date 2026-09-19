"""Organize zsh files: extract functions to separate files in .scripts/ folder."""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field

SECTION = re.compile(r"^#\s*[─—-]{2,}\s*(?P<title>.*?)\s*[─—-]{2,}\s*$")
FUNCTION = re.compile(
    r"^\s*(?:function\s+(?P<fname>[\w.:-]+)\s*(?:\(\s*\))?|(?P<pname>[\w.:-]+)\s*\(\s*\))\s*\{"
)
FUNCTION_CALL = re.compile(r"(?:^|\s|;|&&|\|\|)([_a-zA-Z][\w.:-]*)\s*(?:\(|&&|\|\|)")


@dataclass
class Function:
    name: str
    body: str
    comment: str
    section: str
    dependencies: set[str] = field(default_factory=set)


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

    _analyze_dependencies(functions)
    return functions, remaining


def _analyze_dependencies(functions: list[Function]) -> None:
    """Analyze function bodies to find dependencies on other functions."""
    func_names = {f.name for f in functions}

    simple_call = re.compile(r"(?:^|\s|;)([_a-zA-Z][\w.:-]+)(?:\s|$|;|\))")

    for func in functions:
        for match in FUNCTION_CALL.finditer(func.body):
            potential_func = match.group(1)
            if potential_func in func_names and potential_func != func.name:
                func.dependencies.add(potential_func)

        for match in simple_call.finditer(func.body):
            potential_func = match.group(1)
            if potential_func in func_names and potential_func != func.name:
                func.dependencies.add(potential_func)


def _topological_sort(functions: list[Function]) -> list[Function]:
    """Sort functions in dependency order (dependencies first)."""
    sorted_funcs = []
    visited = set()
    temp_mark = set()

    def visit(func: Function) -> None:
        if func.name in temp_mark:
            return
        if func.name in visited:
            return

        temp_mark.add(func.name)

        for dep_name in func.dependencies:
            dep_func = next((f for f in functions if f.name == dep_name), None)
            if dep_func:
                visit(dep_func)

        temp_mark.remove(func.name)
        visited.add(func.name)
        sorted_funcs.append(func)

    for func in functions:
        if func.name not in visited:
            visit(func)

    return sorted_funcs


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

    sorted_funcs = _topological_sort(functions)

    for func in sorted_funcs:
        func_file = scripts_dir / f"{func.name}.zsh"
        content = ""
        if func.comment:
            content = func.comment + "\n"

        if func.dependencies:
            deps_list = ", ".join(sorted(func.dependencies))
            content += f"# Dependencies: {deps_list}\n"

        content += func.body + "\n"

        if not dry_run:
            func_file.write_text(content)

        actions.append(("created", f".scripts/{func.name}.zsh"))

    aggregator = "# Auto-generated: sources all scripts from .scripts/ folder\n"
    aggregator += "# Functions are sourced in dependency order (dependencies first)\n\n"

    if any(func.section for func in sorted_funcs):
        sections = {}
        for func in sorted_funcs:
            if func.section not in sections:
                sections[func.section] = []
            sections[func.section].append(func)

        for section, funcs_in_section in sections.items():
            if section:
                aggregator += f"# ─── {section} ───\n"
            for func in funcs_in_section:
                aggregator += f"source ~/.scripts/{func.name}.zsh\n"
            aggregator += "\n"
    else:
        for func in sorted_funcs:
            aggregator += f"source ~/.scripts/{func.name}.zsh\n"

    if remaining:
        aggregator = "\n".join(remaining) + "\n\n" + aggregator

    if not dry_run:
        scripts_file.write_text(aggregator)

    actions.append(("updated", ".scripts.zsh (now sources individual files)"))

    return actions
