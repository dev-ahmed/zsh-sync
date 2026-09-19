"""Command line entry point."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config, track, write_default_config
from .edit import (
    DESCRIPTIONS,
    SENSITIVE,
    AppendError,
    append,
    is_sensitive,
    resolve_target,
    target_table,
)
from .fs import relative_key
from .inspect import aliases, exports, functions
from .organize import organize_scripts
from .sync import (
    SsdNotMounted,
    State,
    backup,
    list_snapshots,
    restore,
    status,
    tracked_paths,
)

app = typer.Typer(add_completion=False, help="Back up and restore zsh dotfiles on the devSSD.")
console = Console()

STATE_STYLE = {
    State.NEW: "green",
    State.CHANGED: "yellow",
    State.UNCHANGED: "dim",
    State.MISSING_LOCALLY: "red",
}


def _fail(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")
    raise typer.Exit(code=1)


@app.command("status")
def status_command(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Include unchanged files."),
) -> None:
    """Show what differs between this machine and the backup."""
    config = load_config()
    try:
        entries = status(config)
    except SsdNotMounted as exc:
        _fail(str(exc))
        return

    table = Table(title=f"zsh-sync · {config.store}", title_justify="left")
    table.add_column("file")
    table.add_column("state")

    shown = 0
    for entry in entries:
        if entry.state is State.UNCHANGED and not verbose:
            continue
        table.add_row(entry.key, f"[{STATE_STYLE[entry.state]}]{entry.state.value}[/]")
        shown += 1

    if shown == 0:
        console.print("[green]✓[/green] everything is backed up and unchanged")
        return

    console.print(table)


@app.command("sync")
def sync_command(
    force: bool = typer.Option(False, "--force", help="Snapshot even when nothing changed."),
) -> None:
    """Copy new and changed files to the SSD."""
    config = load_config()
    try:
        result = backup(config, force=force)
    except SsdNotMounted as exc:
        _fail(str(exc))
        return

    if result.snapshot is None:
        console.print("[green]✓[/green] already up to date, nothing to copy")
        return

    for entry in result.written:
        colour = STATE_STYLE[entry.state]
        console.print(f"  [{colour}]{entry.state.value:<9}[/] {entry.key}")

    console.print(
        f"[green]✓[/green] {len(result.written)} file(s) synced · snapshot "
        f"[cyan]{result.snapshot.name}[/cyan]"
    )


@app.command("snapshots")
def snapshots_command() -> None:
    """List the snapshots held on the SSD, newest first."""
    config = load_config()
    try:
        found = list_snapshots(config)
    except SsdNotMounted as exc:
        _fail(str(exc))
        return

    if not found:
        console.print("no snapshots yet — run [cyan]zs sync[/cyan]")
        return

    for index, path in enumerate(found):
        count = sum(1 for p in path.rglob("*") if p.is_file())
        marker = " [dim](newest)[/dim]" if index == 0 else ""
        console.print(f"  [cyan]{path.name}[/cyan]  {count} file(s){marker}")


@app.command("restore")
def restore_command(
    snapshot: str = typer.Option(None, "--snapshot", "-s", help="Snapshot name; default latest."),
    only: str = typer.Option(None, "--only", "-f", help="Restore a single file by name."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace files that already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Copy files from the SSD back onto this machine."""
    config = load_config()
    try:
        actions = restore(
            config, snapshot=snapshot, only=only, overwrite=overwrite, dry_run=dry_run
        )
    except (SsdNotMounted, FileNotFoundError) as exc:
        _fail(str(exc))
        return

    if not actions:
        console.print("nothing to restore")
        return

    for key, outcome in actions:
        colour = "dim" if outcome.startswith("skipped") else "green"
        console.print(f"  [{colour}]{outcome:<18}[/] {key}")

    if any(o.startswith("skipped") for _, o in actions) and not overwrite:
        console.print("\n[dim]existing files were kept; pass --overwrite to replace them[/dim]")


COMMANDS: tuple[tuple[str, str], ...] = (
    ("zs status", "what differs between this machine and the backup"),
    ("zs sync", "copy new and changed files to the SSD"),
    ("zs append <type> <line>", "add a line to a dotfile, checked, then sync"),
    ("zs track <path>", "start backing up another file or glob"),
    ("zs organize", "extract functions from .scripts.zsh to .scripts/ folder"),
    ("zs list types", "the type names append accepts"),
    ("zs list files", "every file currently tracked"),
    ("zs list aliases", "every alias in .aliases.zsh"),
    ("zs list scripts", "every function in .scripts.zsh"),
    ("zs list env", "exported variable names (never values)"),
    ("zs list all", "aliases, functions and exports together"),
    ("zs list snapshots", "point-in-time copies on the SSD"),
    ("zs restore", "copy files back onto this machine"),
    ("zs init", "write an editable config file"),
    ("zs commands", "this list"),
)


@app.command("commands")
def commands_command() -> None:
    """Show every command at a glance."""
    table = Table(title="zsh-sync", title_justify="left")
    table.add_column("command", style="cyan", no_wrap=True)
    table.add_column("does")

    for name, description in COMMANDS:
        table.add_row(name, description)

    console.print(table)
    console.print("[dim]any command takes --help for its own options[/dim]")


def _print_types() -> None:
    table = Table(title="zs append <type>", title_justify="left")
    table.add_column("type")
    table.add_column("file")
    table.add_column("holds")

    for name, filename, description in target_table():
        style = "red" if filename in SENSITIVE else "cyan"
        table.add_row(f"[{style}]{name}[/]", filename, description)

    console.print(table)
    console.print("[dim]red types are 0600 and hold secrets — append asks before writing[/dim]")


@app.command("targets")
def targets_command() -> None:
    """List the names `append` accepts and the file each one writes to."""
    _print_types()


list_app = typer.Typer(help="List types, tracked files, or snapshots.")
app.add_typer(list_app, name="list")


@list_app.command("types")
def list_types() -> None:
    """The type names `append` accepts, and the file each one writes to."""
    _print_types()


@list_app.command("files")
def list_files() -> None:
    """Every file currently tracked for backup."""
    config = load_config()
    table = Table(title="tracked files", title_justify="left")
    table.add_column("file")
    table.add_column("on disk")

    for path in tracked_paths(config):
        table.add_row(relative_key(path, config.home), f"{path.stat().st_size} B")

    missing = [name for name in config.files if not (config.home / name).exists()]
    console.print(table)
    console.print(f"[dim]globs: {', '.join(config.globs) or 'none'}[/dim]")
    if missing:
        console.print(f"[dim]listed but absent: {', '.join(missing)}[/dim]")


@list_app.command("snapshots")
def list_snapshots_sub() -> None:
    """Point-in-time copies held on the SSD, newest first."""
    snapshots_command()


def _print_items(items, title: str, empty: str, name_style: str = "green") -> None:
    if not items:
        console.print(f"[dim]{empty}[/dim]")
        return

    table = Table(title=title, title_justify="left")
    table.add_column("name", style=name_style, no_wrap=True)
    table.add_column("what it does")

    current = None
    for item in items:
        if item.section != current:
            current = item.section
            if current:
                table.add_section()
                table.add_row(f"[bold cyan]{current}[/]", "")
        table.add_row(item.name, item.detail or "[dim]—[/dim]")

    console.print(table)
    console.print(f"[dim]{len(items)} total[/dim]")


@list_app.command("aliases")
def list_aliases() -> None:
    """Every alias defined in .aliases.zsh."""
    config = load_config()
    path = config.home / ".aliases.zsh"
    _print_items(aliases(path), str(path), "no aliases found")


@list_app.command("scripts")
def list_scripts() -> None:
    """Every function defined in .scripts.zsh."""
    config = load_config()
    path = config.home / ".scripts.zsh"
    _print_items(functions(path), str(path), "no functions found")


@list_app.command("env")
def list_env() -> None:
    """Variable names exported from .environment.zsh (names only, never values)."""
    config = load_config()
    path = config.home / ".environment.zsh"
    _print_items(exports(path), str(path), "no exports found", name_style="yellow")


@list_app.command("all")
def list_all() -> None:
    """Aliases, functions and exported variable names together."""
    list_aliases()
    console.print()
    list_scripts()
    console.print()
    list_env()


@app.command("append")
def append_command(
    target: str = typer.Argument(..., help="Run `zs list types` for the full list."),
    content: str = typer.Argument(..., help="The line(s) to add."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Don't back up afterwards."),
    no_check: bool = typer.Option(False, "--no-check", help="Skip the zsh -n syntax check."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the prompt on sensitive files."),
) -> None:
    """Append a line to a dotfile, reverting it if the syntax check fails."""
    config = load_config()

    try:
        path = resolve_target(config, target)
    except AppendError as exc:
        _fail(str(exc))
        return

    if is_sensitive(path) and not yes:
        console.print(f"[yellow]![/yellow] {path.name} holds secrets ({DESCRIPTIONS.get(path.name)})")
        if not typer.confirm(f"append to {path.name}?", default=False):
            console.print("[dim]nothing written[/dim]")
            raise typer.Exit(code=1)

    try:
        result = append(config, target, content, check=not no_check)
    except AppendError as exc:
        _fail(str(exc))
        return

    suffix = "" if result.checked else " [dim](no syntax check for this file type)[/dim]"
    console.print(f"[green]✓[/green] appended to [cyan]{result.path}[/cyan]{suffix}")
    console.print(f"  [dim]{result.added}[/dim]")

    if no_sync:
        return

    try:
        outcome = backup(config)
    except SsdNotMounted as exc:
        console.print(f"[yellow]![/yellow] not backed up: {exc}")
        return

    if outcome.snapshot:
        console.print(f"[green]✓[/green] synced · snapshot [cyan]{outcome.snapshot.name}[/cyan]")


@app.command("track")
def track_command(
    path: str = typer.Argument(..., help="A file or glob under your home directory."),
) -> None:
    """Add a file to the tracked list so it gets backed up from now on."""
    config = load_config()
    try:
        updated, changed = track(config, path)
    except ValueError as exc:
        _fail(str(exc))
        return

    if not changed:
        console.print(f"[dim]already tracked:[/dim] {path}")
        return

    console.print(f"[green]✓[/green] now tracking [cyan]{path}[/cyan]")
    console.print(f"  [dim]{len(updated.files)} file(s), {len(updated.globs)} glob(s)[/dim]")


@app.command("init")
def init_command() -> None:
    """Write a default config you can edit."""
    path = write_default_config()
    console.print(f"[green]✓[/green] wrote {path}")


@app.command("organize")
def organize_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen."),
) -> None:
    """Organize .scripts.zsh by extracting functions to .scripts/ folder."""
    config = load_config()

    actions = organize_scripts(config.home, dry_run=dry_run)

    for action, description in actions:
        if action == "error":
            _fail(description)
            return
        elif action == "no-op":
            console.print(f"[dim]{description}[/dim]")
        elif action == "created":
            console.print(f"  [green]created[/green]   {description}")
        elif action == "updated":
            console.print(f"  [yellow]updated[/yellow]   {description}")

    if not dry_run and actions and actions[0][0] != "no-op":
        console.print(f"\n[green]✓[/green] organized {len([a for a in actions if a[0] == 'created'])} function(s)")


def main() -> None:
    app()
