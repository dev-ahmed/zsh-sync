# zsh-sync

Keeps your zsh dotfiles mirrored on the devSSD, syncs changes as you make them,
and puts them back if the machine ever loses them.

```bash
zs status      # what differs between this machine and the backup
zs sync        # copy new and changed files to the SSD
zs append      # add a line to a dotfile, safely, then sync
zs track       # start backing up another file
zs snapshots   # list point-in-time copies, newest first
zs restore     # copy files back onto this machine
zs init        # write a config file you can edit
```

## Appending

```bash
zs append aliases "alias gs='git status'"
zs append scripts "myfunc() { print hi }"
zs append env "export EDITOR=nvim"
```

Targets are friendly names — `aliases`, `scripts`, `env`, `zshrc`, `zshenv`,
`zprofile`, `secrets`, `credentials` — or any filename under your home.

This is `>>` with a seatbelt. A stray quote appended to `.aliases.zsh` breaks
every new terminal you open, and the shell won't tell you until you open one.
`zs append` writes the line, runs `zsh -n`, and **puts the file back byte for
byte if the check fails**:

```
$ zs append aliases 'alias oops="unclosed'
✗ syntax check failed, .aliases.zsh reverted:
/Users/ahmed/.aliases.zsh:34: unmatched "
```

It syncs to the SSD on success. Pass `--no-sync` to skip that, or `--no-check`
to bypass the syntax check. Non-zsh files (`.gitconfig`) skip the check
automatically, and file modes are preserved, so appending to `.secrets.zsh`
leaves it at `0600`.

## Tracking more files

```bash
zs track ~/.tmux.conf     # absolute, ~, or relative all work
zs track "bin/*"          # globs go to the glob list
```

Writes to `~/.config/zsh-sync/config.json`. Paths outside your home directory
are rejected rather than silently stored.

## What it tracks

By default, the files that make up the shell:

```
.zshrc  .zshenv  .zprofile  .aliases.zsh  .scripts.zsh
.environment.zsh  .secrets.zsh  .credentials.zsh  .p10k.zsh  .gitconfig
bin/*.sh
```

Anything on that list that doesn't exist is skipped, not an error — so the same
config works across machines that don't all have the same files.

Run `zs init` to write `~/.config/zsh-sync/config.json` and edit the list.

## How the backup is laid out

```
/Volumes/devSSD/backups/zsh-sync/
├── current/                    mirror of the latest sync
├── snapshots/
│   ├── 2026-09-13_143005/      a full copy, per sync that changed something
│   └── 2026-09-12_090112/
└── manifest.json               sha256 + mode per file
```

`current/` is what `restore` reads by default. Snapshots are full copies rather
than deltas — the files are a few KB, so the simplicity is worth more than the
space, and any one of them can be restored without replaying the others. The
newest 20 are kept.

## Permissions

`.secrets.zsh` and `.credentials.zsh` are `0600`, and they stay `0600` on the
SSD and on the way back. A backup that quietly widened them to `0644` would
undo the reason they exist, so the mode is applied explicitly at both ends
rather than left to the umask. A test covers it.

## Restoring

```bash
zs restore                        # from the latest sync; existing files kept
zs restore --overwrite            # replace what's on the machine
zs restore --only .zshrc          # a single file
zs restore -s 2026-09-12_090112   # from a specific snapshot
zs restore --dry-run              # show what would happen
```

Restore never clobbers by default: a file that already exists is reported as
`skipped (exists)` until you pass `--overwrite`. That makes the recovery case —
where the files are simply gone — a safe one-liner, while an accidental restore
over live config takes a deliberate flag.

## When the SSD isn't mounted

Every command checks for `/Volumes/devSSD/.dev-ssd-marker` and exits with a
clear message rather than a traceback — and, importantly, rather than writing
to a `/Volumes/devSSD` directory that macOS would happily create on the
internal disk when the drive is absent.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```
