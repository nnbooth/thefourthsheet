"""
config.py — where the database is, and how to get its password without it ever being in git.

Settings (names only, never secrets) are read from, in order:
  1. environment variables (e.g. FOURTH_SHEET_SQL_SERVER), handy for a one-off;
  2. OneDrive: Projects/The Fourth Sheet/Config/database.env, so the Mac and the PC share one copy;
  3. the defaults below.
A value still showing [[PLACEHOLDER]] stops anything that needs it, with a message saying what to fill in.

The SQL password (sql_password) comes from, in order:
  1. the environment variable FOURTH_SHEET_SQL_PASSWORD;
  2. a .env file at the repo root (git ignores it; this refuses to read one that git tracks), holding a line with
     FOURTH_SHEET_SQL_PASSWORD, an equals sign and the password;
  3. Azure Key Vault, if AZURE_KEYVAULT names a vault: the secret "sql-password", read with the Azure command line.
It is never printed, logged or written anywhere by these tools.
"""
import sys, pathlib  # noqa: E401  (next 2 lines: make every stage folder importable; see tools/README.md)
_T = next(p for p in pathlib.Path(__file__).resolve().parents if p.name == "tools")
sys.path[:0] = [d for d in (str(x) for x in sorted(_T.iterdir()) if x.is_dir() and (x.name[0].isdigit() or x.name in ("shared", "setup"))) if d not in sys.path]

import os
import sys
from pathlib import Path


DEFAULTS = {
    "AZURE_SUBSCRIPTION_ID": "[[AZURE_SUBSCRIPTION_ID]]",   # az account show --query id   (filled in by azure_setup.py)
    "AZURE_TENANT_ID": "[[AZURE_TENANT_ID]]",               # az account show --query tenantId
    "AZURE_RESOURCE_GROUP": "rg-thefourthsheet",
    "AZURE_LOCATION": "australiaeast",
    "SQL_SERVER": "thefourthsheet-sql",                      # becomes thefourthsheet-sql.database.windows.net (created 9 Oct 2026)
    "SQL_DATABASE": "thefourthsheet",
    "SQL_LOGIN": "tfsadmin",                                 # the SQL admin login (a name, not a secret)
    "AZURE_KEYVAULT": "",                                    # optional: a Key Vault holding the secret "sql-password"
    "SQL_ADMIN_UPN": "[[SQL_ADMIN_UPN]]",                   # your Microsoft sign-in (Azure management; optional server admin too)
    "SQL_ADMIN_OBJECT_ID": "[[SQL_ADMIN_OBJECT_ID]]",       # az ad signed-in-user show --query id
}
PASSWORD_VAR = "FOURTH_SHEET_SQL_PASSWORD"
REPO = Path(__file__).resolve().parents[3]
FILE_HEADER = """# The Fourth Sheet: where the cloud database is. Shared by every machine through OneDrive.
# NAMES ONLY. Never put a password, key, secret or connection string with a password in this file:
# the SQL password lives in FOURTH_SHEET_SQL_PASSWORD (environment or the repo's git-ignored .env) or Azure Key Vault.
"""


def onedrive_project():
    from sync_media import onedrive_root
    return onedrive_root()


def settings_file():
    return onedrive_project() / "Config" / "database.env"


def read():
    vals = dict(DEFAULTS)
    f = settings_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    for k in vals:
        if os.getenv("FOURTH_SHEET_" + k):
            vals[k] = os.getenv("FOURTH_SHEET_" + k)
    return vals


def write(vals):
    f = settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(FILE_HEADER + "".join(f"{k}={vals[k]}\n" for k in DEFAULTS), encoding="utf-8")
    return f


def need(*keys):
    vals = read()
    missing = [k for k in keys if vals[k].startswith("[[")]
    if missing:
        raise SystemExit(f"Fill in {', '.join(missing)} in {settings_file()} (or run: python3 tools/2_load_azure/database/azure_setup.py)")
    return vals


def server_host(vals=None):
    return f"{(vals or read())['SQL_SERVER']}.database.windows.net"


def _dotenv_password():
    f = REPO / ".env"
    if not f.exists():
        return None
    import subprocess
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", ".env"], capture_output=True).returncode == 0
    if tracked:
        raise SystemExit(".env is tracked by git, so it would be public. Remove it from git (git rm --cached .env) before using it.")
    for line in f.read_text(encoding="utf-8").splitlines():
        k, _, v = line.strip().partition("=")
        if k.strip() == PASSWORD_VAR and v.strip():
            return v.strip().strip('"').strip("'")
    return None


def _keyvault_password(vault):
    import subprocess
    from database.azure_setup import az_path
    p = subprocess.run([az_path(), "keyvault", "secret", "show", "--vault-name", vault, "--name", "sql-password", "--query", "value", "-o", "tsv"],
                       capture_output=True, text=True)
    return p.stdout.strip() or None if p.returncode == 0 else None


def sql_password():
    """The SQL login's password: environment, then the git-ignored .env, then Key Vault. Never printed or stored by these tools."""
    pw = os.getenv(PASSWORD_VAR) or _dotenv_password()
    if not pw and read().get("AZURE_KEYVAULT"):
        pw = _keyvault_password(read()["AZURE_KEYVAULT"])
    if not pw:
        raise SystemExit(f"No SQL password found. Set {PASSWORD_VAR} in your environment, or in a .env file at the repo root "
                         f"(git ignores it), or put it in Azure Key Vault as \"sql-password\" and set AZURE_KEYVAULT in {settings_file()}.")
    return pw
