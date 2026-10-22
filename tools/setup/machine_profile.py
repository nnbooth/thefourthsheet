#!/usr/bin/env python3
"""
machine_profile.py — carry your working set-up between the Mac and the PC, through OneDrive.

    python3 tools/setup/machine_profile.py export      on the machine you're leaving (Windows: py tools\\setup\\machine_profile.py export)
    python3 tools/setup/machine_profile.py import      on the machine you're moving to (setup_machine.py runs this for you)
    python3 tools/setup/machine_profile.py status      what's in the profile and when it was saved, and each conversation's name
    python3 tools/setup/machine_profile.py rename "3Sheets website refresh" "4th Sheet buildout"
                                                 rename a conversation (by its current name or id), as /rename does

What travels (to OneDrive: Projects/The Fourth Sheet/Config/Machine profile/):
  - VS Code: the list of extensions (installed on the other machine), and your settings
    (minus machine-specific ones like the Python path)
  - Claude Code: your settings, my memory notes for this project, and this project's conversations,
    so `claude --resume` (or the Claude Code panel's history) can pick up where you left off
What doesn't need to: your Claude plugins, skills and claude.ai connectors come with your Claude account.
What never travels: sign-ins, tokens and keys (~/.claude.json and the keychain stay put: sign in again).

Before anything is overwritten, the existing file is backed up next to it (.bak-<date>). Newer files win.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402,E702  Windows: run in UTF-8 mode
from sync_media import onedrive_root  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
WIN = platform.system() == "Windows"
HOME = Path.home()
MACHINE_ONLY = {"python.defaultInterpreterPath", "python.pythonPath", "terminal.integrated.defaultProfile.osx",
                "terminal.integrated.defaultProfile.windows", "terminal.integrated.shell.osx", "terminal.integrated.shell.windows"}
STAMP = datetime.now().strftime("%Y%m%d-%H%M")


def profile_dir():
    return onedrive_root() / "Config" / "Machine profile"


def vscode_user():
    return Path(os.environ["APPDATA"]) / "Code" / "User" if WIN else HOME / "Library/Application Support/Code/User"


def code_cli():
    cands = [shutil.which("code"), shutil.which("code.cmd"),
             str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/bin/code.cmd"),
             r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
             "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"]
    return next((c for c in cands if c and Path(c).exists()), None)


def claude_project_dir():
    """Claude Code keeps each project's conversations and memory under ~/.claude/projects/<the project path, dashed>."""
    return HOME / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(REPO))


def read_jsonc(path):
    """VS Code's settings.json allows // comments and trailing commas."""
    if not path.exists():
        return {}
    text, out, i, in_str = path.read_text(encoding="utf-8"), [], 0, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1]); i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True; out.append(c)
        elif text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        else:
            out.append(c)
        i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    return json.loads(cleaned) if cleaned.strip() else {}


def backup(path):
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{STAMP}"))


def copy_newer(src, dst):
    if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime + 1:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def title(jsonl):
    """A conversation's name: the latest /rename (custom title), else Claude's own (ai title)."""
    custom = ai = None
    with open(jsonl, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"custom-title"' in line or '"ai-title"' in line:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                custom = d.get("customTitle", custom)
                ai = d.get("aiTitle", ai)
    return custom or ai or jsonl.stem


def rename(old, new):
    """Rename a conversation in this machine's project folder (the name travels with it on export)."""
    hits = [f for f in claude_project_dir().glob("*.jsonl") if old in (f.stem, title(f))]
    if len(hits) != 1:
        sys.exit(f"Found {len(hits)} conversations called {old!r}. Names: " + ", ".join(repr(title(f)) for f in claude_project_dir().glob('*.jsonl')))
    f = hits[0]
    with open(f, "a", encoding="utf-8") as out:
        out.write(json.dumps({"type": "custom-title", "customTitle": new, "sessionId": f.stem}, separators=(",", ":")) + "\n")
    print(f"Renamed {old!r} to {new!r} ({f.stem}).")


# ------------------------------------------------------------------------- export

def export():
    out = profile_dir()
    out.mkdir(parents=True, exist_ok=True)
    prof = {"exported_from": platform.node(), "platform": platform.system(), "exported_at": datetime.now().isoformat(timespec="minutes")}
    code = code_cli()
    if code:
        prof["vscode_extensions"] = subprocess.run([code, "--list-extensions"], capture_output=True, text=True).stdout.split()
    settings = read_jsonc(vscode_user() / "settings.json")
    prof["vscode_settings"] = {k: v for k, v in settings.items() if k not in MACHINE_ONLY}
    kb = vscode_user() / "keybindings.json"
    prof["vscode_keybindings"] = read_jsonc(kb) if kb.exists() else []
    cs = HOME / ".claude" / "settings.json"
    prof["claude_settings"] = json.loads(cs.read_text(encoding="utf-8")) if cs.exists() else {}
    (out / "profile.json").write_text(json.dumps(prof, indent=1), encoding="utf-8")
    # memory notes and this project's conversations (each with its folder of tool results)
    src = claude_project_dir()
    n_mem = n_ses = 0
    if src.exists():
        for f in (src / "memory").glob("*.md"):
            n_mem += copy_newer(f, out / "claude" / "memory" / f.name)
        for f in src.glob("*.jsonl"):
            n_ses += copy_newer(f, out / "claude" / "sessions" / f.name)
            folder = src / f.stem
            if folder.is_dir():
                for g in folder.rglob("*"):
                    if g.is_file():
                        copy_newer(g, out / "claude" / "sessions" / f.stem / g.relative_to(folder))
    print(f"Saved this machine's set-up to {out}")
    for f in sorted(src.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        print(f"  conversation: {title(f)}  ({f.stat().st_size // 1_000_000} MB, last used {datetime.fromtimestamp(f.stat().st_mtime):%d %b %H:%M})")
    print(f"  VS Code: {len(prof.get('vscode_extensions', []))} extensions, {len(prof['vscode_settings'])} settings · "
          f"Claude: settings, {n_mem} memory notes and {n_ses} conversations updated")


# ------------------------------------------------------------------------- import

def import_profile(quiet=False):
    src = profile_dir()
    pf = src / "profile.json"
    if not pf.exists():
        print("  !! no machine profile in OneDrive yet (run 'machine_profile.py export' on the other machine)")
        return
    prof = json.loads(pf.read_text(encoding="utf-8"))
    print(f"  from {prof['exported_from']} ({prof['platform']}), saved {prof['exported_at']}")
    # VS Code extensions
    code = code_cli()
    if code and prof.get("vscode_extensions"):
        have = set(subprocess.run([code, "--list-extensions"], capture_output=True, text=True).stdout.lower().split())
        missing = [e for e in prof["vscode_extensions"] if e.lower() not in have]
        for e in missing:
            r = subprocess.run([code, "--install-extension", e], capture_output=True, text=True)
            print(f"  {'ok' if r.returncode == 0 else '!!'} VS Code extension {e}")
        if not missing:
            print(f"  ok VS Code: all {len(prof['vscode_extensions'])} extensions already installed")
    elif prof.get("vscode_extensions"):
        print("  !! VS Code isn't installed yet: install it, then run this again")
    # VS Code settings and keybindings (merged; existing file backed up)
    user = vscode_user()
    if prof.get("vscode_settings"):
        cur = read_jsonc(user / "settings.json")
        merged = {**cur, **prof["vscode_settings"]}
        if merged != cur:
            user.mkdir(parents=True, exist_ok=True)
            backup(user / "settings.json")
            (user / "settings.json").write_text(json.dumps(merged, indent=4), encoding="utf-8")
            print(f"  ok VS Code settings merged ({len(prof['vscode_settings'])} carried over)")
    if prof.get("vscode_keybindings"):
        backup(user / "keybindings.json")
        (user / "keybindings.json").write_text(json.dumps(prof["vscode_keybindings"], indent=4), encoding="utf-8")
        print("  ok VS Code keyboard shortcuts")
    # Claude Code settings
    if prof.get("claude_settings"):
        cs = HOME / ".claude" / "settings.json"
        cur = json.loads(cs.read_text(encoding="utf-8")) if cs.exists() else {}
        merged = {**cur, **prof["claude_settings"]}
        if merged != cur:
            cs.parent.mkdir(parents=True, exist_ok=True)
            backup(cs)
            cs.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        print("  ok Claude Code settings")
    # memory notes and conversations, into this machine's folder for this project
    dst = claude_project_dir()
    n_mem = sum(copy_newer(f, dst / "memory" / f.name) for f in (src / "claude" / "memory").glob("*.md"))
    n_ses = 0
    for f in (src / "claude" / "sessions").glob("*.jsonl"):
        n_ses += copy_newer(f, dst / f.name)
        folder = src / "claude" / "sessions" / f.stem
        if folder.is_dir():
            for g in folder.rglob("*"):
                if g.is_file():
                    copy_newer(g, dst / f.stem / g.relative_to(folder))
    for f in sorted((src / "claude" / "sessions").glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        print(f"     conversation: {title(f)}")
    print(f"  ok Claude: {n_mem} memory notes and {n_ses} conversations brought over "
          f"({dst}). In the project folder run 'claude --resume' (or open the Claude Code panel's history) to carry on.")


def status():
    pf = profile_dir() / "profile.json"
    if not pf.exists():
        print("No machine profile saved yet.")
        return
    p = json.loads(pf.read_text(encoding="utf-8"))
    ses = sorted((profile_dir() / "claude" / "sessions").glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True)
    print(f"Saved from {p['exported_from']} ({p['platform']}) at {p['exported_at']}: {len(p.get('vscode_extensions', []))} VS Code extensions, "
          f"{len(p.get('vscode_settings', {}))} settings, {len(list((profile_dir() / 'claude' / 'memory').glob('*.md')))} memory notes, {len(ses)} conversations:")
    for f in ses:
        print(f"  {title(f)}  (last used {datetime.fromtimestamp(f.stat().st_mtime):%d %b %H:%M})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "rename" and len(sys.argv) == 4:
        rename(sys.argv[2], sys.argv[3])
    else:
        {"export": export, "import": import_profile, "status": status}.get(cmd, lambda: sys.exit('Use: export, import, status, or rename "old name" "new name"'))()
