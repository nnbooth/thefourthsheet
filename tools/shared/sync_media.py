#!/usr/bin/env python3
"""
sync_media.py — keep everything under media/ identical between this machine and OneDrive.

The Excel downloads (and anything else git ignores) only live on the machine that built them,
so they're mirrored to OneDrive (Projects/The Fourth Sheet/Media/site media/), both ways:
whichever copy is newer wins, and files missing on one side are copied over. On a fresh
machine, running this pulls everything down.

Except the downloads (media/exports/): the build makes those, so the build's copy is the only truth. They're copied
one way, up to OneDrive, and a download the build no longer makes is deleted from OneDrive too (never copied back).

Runs at the end of tools/1_build_data/sample_data.py, render_mockups.py and record_demo.py.
Run it yourself any time:   python3 tools/shared/sync_media.py
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import os
import shutil
from pathlib import Path
import winutf8; winutf8.ensure()   # Windows: run in UTF-8 mode (the tools write characters like ¢ and ▲)

REPO = Path(__file__).resolve().parent.parent.parent
LOCAL = REPO / "media"

# Files that have been retired: deleted on BOTH sides before syncing (otherwise "newer wins" would copy a
# deleted file straight back). Patterns are relative to media/.
GENERATED = ("exports",)      # top-level folders under media/ that only the build writes: mirrored one way, up

RETIRED = [
    "exports/reports/*.xlsx", "exports/reports/*.pdf", "exports/reports/*.pptx",   # replaced by exports/reports/<period>/ (6 Oct 2026)
]


PROJECT = "Projects/The Fourth Sheet"                      # the project's OneDrive folder (renamed from "The 4th Sheet", 10 Oct 2026)
OLD_PROJECTS = ("Projects/The 4th Sheet",)                  # earlier names: a machine pinned to one is moved to PROJECT


def onedrive_candidates():
    """Every place OneDrive can live, personal or business, on a Mac or a Windows PC. The one that holds
    'Projects/The Fourth Sheet' wins, so moving the project to OneDrive for Business needs no code change."""
    home = Path.home()
    bases = [os.getenv("OneDriveConsumer"), os.getenv("OneDriveCommercial"), os.getenv("OneDrive"),
             home / "Library/CloudStorage/OneDrive-Personal", *sorted((home / "Library/CloudStorage").glob("OneDrive-*")),
             home / "OneDrive", *sorted(home.glob("OneDrive - *"))]
    return [Path(b) for b in bases if b]


PIN = Path.home() / ".fourthsheet" / "onedrive_root.txt"   # this machine's pinned project folder (not in git or OneDrive)


def pinned():
    return Path(PIN.read_text(encoding="utf-8").strip()).expanduser() if PIN.exists() and PIN.read_text(encoding="utf-8").strip() else None


def pin(path):
    """Pin this machine to one project folder: every tool then reads it, and stops (rather than looking elsewhere) if it's missing."""
    path = Path(path).expanduser()
    if not (path / "Data").is_dir():
        raise SystemExit(f"Not pinned: {path} doesn't have a Data folder. Is it the 'The Fourth Sheet' folder, and has OneDrive synced it?")
    PIN.parent.mkdir(parents=True, exist_ok=True)
    PIN.write_text(str(path), encoding="utf-8")
    return path


def onedrive_root():
    """The project folder in OneDrive ('Projects/The Fourth Sheet'). Order: FOURTH_SHEET_DATA (its parent), then this
    machine's pin (~/.fourthsheet/onedrive_root.txt), then a search of the usual OneDrive places (only if not pinned).
    A pin to the folder's old name ('The 4th Sheet') is moved to the new name once OneDrive has it."""
    if os.getenv("FOURTH_SHEET_DATA"):
        return Path(os.getenv("FOURTH_SHEET_DATA")).expanduser().parent
    p = pinned()
    if p and not (p / "Data").is_dir():
        for old in OLD_PROJECTS:
            name = Path(old).name
            if p.name == name and (p.parent / Path(PROJECT).name / "Data").is_dir():
                p = pin(p.parent / Path(PROJECT).name)          # the folder was renamed: follow it
                print(f"OneDrive project folder renamed: now pinned to {p}")
                break
    if p:
        if not (p / "Data").is_dir():
            raise SystemExit(f"The pinned project folder isn't available: {p}\n"
                             "OneDrive may still be syncing or remapping. Wait for it to finish, or pin the new place with:\n"
                             "  python3 tools/setup/setup_machine.py --onedrive \"<the 'The Fourth Sheet' folder>\"   (Windows: py ...)")
        return p
    for base in onedrive_candidates():
        if (base / PROJECT).exists():
            return base / PROJECT
    raise SystemExit(f"Can't find the OneDrive folder '{PROJECT}' (personal or business). "
                     "Sign in to OneDrive and let it sync, or pin it: python3 tools/setup/setup_machine.py --onedrive \"<folder>\"")


def sync(quiet=False):
    remote = onedrive_root() / "Media" / "site media"
    gone = 0
    for pat in RETIRED:
        for side in (LOCAL, remote):
            for f in side.glob(pat):
                f.unlink()
                gone += 1
    up = down = 0
    names = {p.relative_to(LOCAL) for p in LOCAL.rglob("*") if p.is_file()} | \
            ({p.relative_to(remote) for p in remote.rglob("*") if p.is_file()} if remote.exists() else set())
    for rel in sorted(names):
        if rel.name == ".DS_Store":
            continue
        a, b = LOCAL / rel, remote / rel
        if rel.parts[0] in GENERATED:                      # downloads: the build's copy wins, always
            if not a.exists():
                b.unlink()
                gone += 1
            elif not b.exists() or a.stat().st_size != b.stat().st_size or a.read_bytes() != b.read_bytes():
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(a, b)
                up += 1
            continue
        if a.exists() and b.exists() and a.stat().st_size == b.stat().st_size and abs(a.stat().st_mtime - b.stat().st_mtime) > 1 \
                and a.read_bytes() == b.read_bytes():
            t = min(a.stat().st_mtime, b.stat().st_mtime)      # same file, different dates (e.g. a fresh git clone):
            os.utime(a, (t, t)); os.utime(b, (t, t))           # line the dates up instead of copying
            continue
        if a.exists() and (not b.exists() or a.stat().st_mtime > b.stat().st_mtime + 1):
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(a, b)
            up += 1
        elif b.exists() and (not a.exists() or b.stat().st_mtime > a.stat().st_mtime + 1):
            a.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(b, a)
            down += 1
    if not quiet:
        print(f"media/ and OneDrive in step: {up} copied up, {down} copied down" + (f", {gone} removed (retired, or downloads the build no longer makes)" if gone else "") + f" ({remote})")
    return up, down


if __name__ == "__main__":
    sync()
