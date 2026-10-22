"""
azure_setup.py — create and lock down the Azure SQL database. Every step checks first, so it's safe to re-run.

    python3 tools/2_load_azure/database/azure_setup.py                     show the plan and the current state (changes nothing)
    python3 tools/2_load_azure/database/azure_setup.py create              create whatever is missing, locked down (below)
    python3 tools/2_load_azure/database/azure_setup.py allow-this-machine  let this machine in (run once on each machine,
                                                              and again if your internet address changes)
    python3 tools/2_load_azure/database/azure_setup.py database            schemas, roles and the load log (security.sql); --entra signs in as you
    python3 tools/2_load_azure/database/azure_setup.py status              security check of the server as it is now
    python3 tools/2_load_azure/database/azure_setup.py set-password        give the SQL login the current FOURTH_SHEET_SQL_PASSWORD (rotate it)

What "locked down" means here:
  - SQL sign-in with a login and password. The password is never in git or in OneDrive's settings file: it comes from
    FOURTH_SHEET_SQL_PASSWORD (your environment, or the repo's git-ignored .env) or Azure Key Vault (AZURE_KEYVAULT),
    and these tools never print it. Your Microsoft account can be the server's Entra admin too, for management.
  - Only machines you allow can reach it (one firewall rule per machine, at its own internet address). Nothing
    else in Azure is let in by default.
  - Encrypted connections only, TLS 1.2 or newer.
  - Least privilege inside: readers can only read; the loader can't change security (security.sql).
  - Free tier, serverless: pauses when idle, and pauses rather than charging if the free allowance runs out.

Needs the Azure command line, signed in:  az login   (once per machine; setup_machine.py installs it).
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
import urllib.request
from pathlib import Path

import winutf8; winutf8.ensure()   # noqa: E402  Windows: run in UTF-8 mode

from database import config  # noqa: E402

HERE = Path(__file__).resolve().parent


def az_path():
    for p in (shutil.which("az"), shutil.which("az.cmd"),
              str(Path.home() / ".azure-cli-venv" / "bin" / "az"), str(Path.home() / ".azure-cli-venv" / "Scripts" / "az.exe")):
        if p and Path(p).exists():
            return p
    raise SystemExit("The Azure command line isn't installed. Run:  python3 tools/setup/setup_machine.py")


def az(*args, check=True, quiet=False):
    cmd = [az_path(), *args, "-o", "json"]
    if not quiet:      # never echo a password: the value after --admin-password is masked
        shown = ["********" if i and args[i - 1] == "--admin-password" else a for i, a in enumerate(args)]
        print("  $ az " + " ".join(shown))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        if check:
            raise SystemExit(f"az {' '.join(args[:3])} failed:\n{p.stderr.strip()}")
        return None
    return json.loads(p.stdout) if p.stdout.strip() else {}


def signed_in():
    acct = az("account", "show", check=False, quiet=True)
    if not acct:
        raise SystemExit("Not signed in to Azure on this machine. Run:  az login   (a browser window opens), then run this again.")
    return acct


def machine_rule_name():
    return "machine-" + re.sub(r"[^A-Za-z0-9-]", "-", platform.node().split(".")[0]).strip("-").lower()[:50]


def public_ip():
    import net
    with net.urlopen("https://api.ipify.org", timeout=10) as r:
        ip = r.read().decode().strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip):
        raise SystemExit(f"Couldn't work out this machine's internet address (got {ip!r}).")
    return ip


def fill_settings():
    """Fill the placeholders in OneDrive Config/database.env from the signed-in account (names and IDs only)."""
    acct = signed_in()
    me = az("ad", "signed-in-user", "show", quiet=True)
    v = config.read()
    v["AZURE_SUBSCRIPTION_ID"], v["AZURE_TENANT_ID"] = acct["id"], acct["tenantId"]
    v["SQL_ADMIN_UPN"], v["SQL_ADMIN_OBJECT_ID"] = me["userPrincipalName"], me["id"]
    f = config.write(v)
    print(f"Settings (names and IDs only, no secrets) saved to {f}")
    return v


def plan():
    v = config.read()
    acct = az("account", "show", check=False, quiet=True)
    print(f"Settings file: {config.settings_file()} ({'found' if config.settings_file().exists() else 'not created yet'})")
    for k, val in v.items():
        print(f"  {k:24} {val}")
    print(f"Signed in to Azure: {acct['user']['name'] + ' · subscription ' + acct['name'] if acct else 'NO (run az login)'}")
    if acct:
        rg = az("group", "show", "-n", v["AZURE_RESOURCE_GROUP"], check=False, quiet=True)
        srv = az("sql", "server", "show", "-g", v["AZURE_RESOURCE_GROUP"], "-n", v["SQL_SERVER"], check=False, quiet=True) if rg else None
        db = az("sql", "db", "show", "-g", v["AZURE_RESOURCE_GROUP"], "-s", v["SQL_SERVER"], "-n", v["SQL_DATABASE"], check=False, quiet=True) if srv else None
        print(f"Resource group {v['AZURE_RESOURCE_GROUP']}: {'exists' if rg else 'to create'}")
        print(f"SQL server {v['SQL_SERVER']}: {'exists' if srv else 'to create'}")
        print(f"Database {v['SQL_DATABASE']}: {'exists' if db else 'to create'}")
    print("\nNothing was changed. To create what's missing:  python3 tools/2_load_azure/database/azure_setup.py create")


def create():
    acct = signed_in()
    print(f"Signed in as {acct['user']['name']}, subscription {acct['name']} ({acct['id']}).")
    v = fill_settings()
    rg, loc, srv, db = v["AZURE_RESOURCE_GROUP"], v["AZURE_LOCATION"], v["SQL_SERVER"], v["SQL_DATABASE"]
    tags = ["--tags", "project=thefourthsheet", "owner=" + v["SQL_ADMIN_UPN"]]
    if not az("group", "show", "-n", rg, check=False, quiet=True):
        az("group", "create", "-n", rg, "-l", loc, *tags)
    pw = config.sql_password()                # from the environment, the git-ignored .env or Key Vault; never printed
    if not az("sql", "server", "show", "-g", rg, "-n", srv, check=False, quiet=True):
        az("sql", "server", "create", "-g", rg, "-n", srv, "-l", loc,
           "--admin-user", v["SQL_LOGIN"], "--admin-password", pw,
           "--minimal-tls-version", "1.2", "--enable-public-network", "true")
    else:
        az("sql", "server", "ad-only-auth", "disable", "-g", rg, "-n", srv, check=False)     # SQL logins allowed
        az("sql", "server", "update", "-g", rg, "-n", srv, "--minimal-tls-version", "1.2")
    if not v["SQL_ADMIN_OBJECT_ID"].startswith("[["):                                       # you as Entra admin too, for management
        az("sql", "server", "ad-admin", "create", "-g", rg, "-s", srv, "--display-name", v["SQL_ADMIN_UPN"],
           "--object-id", v["SQL_ADMIN_OBJECT_ID"], check=False)
    # a new server lets nothing in Azure in by default (the "Allow Azure services" rule is 0.0.0.0). An existing server's
    # rules are left as they are: Power BI or Fabric in the cloud may need that rule (status reports it).
    allow_this_machine(v)
    if not az("sql", "db", "show", "-g", rg, "-s", srv, "-n", db, check=False, quiet=True):
        az("sql", "db", "create", "-g", rg, "-s", srv, "-n", db,
           "-e", "GeneralPurpose", "-f", "Gen5", "-c", "2", "--compute-model", "Serverless",
           "--use-free-limit", "--free-limit-exhaustion-behavior", "AutoPause",
           "--backup-storage-redundancy", "Local", *tags)
    database()
    status()


def allow_this_machine(v=None):
    signed_in()
    v = v or config.need("AZURE_RESOURCE_GROUP", "SQL_SERVER")
    rg, srv = v["AZURE_RESOURCE_GROUP"], v["SQL_SERVER"]
    ip, name = public_ip(), machine_rule_name()
    old = az("sql", "server", "firewall-rule", "show", "-g", rg, "-s", srv, "-n", name, check=False, quiet=True)
    if old and old.get("startIpAddress") == ip:
        print(f"This machine ({name}, {ip}) is already allowed.")
        return
    if old:
        az("sql", "server", "firewall-rule", "update", "-g", rg, "-s", srv, "-n", name, "--start-ip-address", ip, "--end-ip-address", ip)
    else:
        az("sql", "server", "firewall-rule", "create", "-g", rg, "-s", srv, "-n", name, "--start-ip-address", ip, "--end-ip-address", ip)
    print(f"Allowed this machine: {name} at {ip} (only this address).")


def database():
    """Schemas, roles and the load log, as the server's admin."""
    from database import connect as dbc
    sql = "\n".join(l for l in (HERE / "security.sql").read_text().splitlines() if not l.strip().startswith("--"))
    conn = dbc.connect(autocommit=True, entra="--entra" in sys.argv)      # --entra: as you (az login), no password
    cur = conn.cursor()
    cur.execute(sql)
    print(f"Database security in place (schemas stage, ops, rpt; roles report_reader, data_loader), signed in as {dbc.whoami(conn)[0]}.")
    conn.close()


def set_password():
    """Give the SQL login the password in FOURTH_SHEET_SQL_PASSWORD (or Key Vault): how to rotate it."""
    v = config.need("AZURE_RESOURCE_GROUP", "SQL_SERVER")
    signed_in()
    az("sql", "server", "update", "-g", v["AZURE_RESOURCE_GROUP"], "-n", v["SQL_SERVER"], "--admin-password", config.sql_password())
    print(f"The SQL login {v['SQL_LOGIN']} now has the password from {config.PASSWORD_VAR} (not shown).")


def status():
    v = config.need("AZURE_RESOURCE_GROUP", "SQL_SERVER")
    signed_in()
    rg, srv = v["AZURE_RESOURCE_GROUP"], v["SQL_SERVER"]
    s = az("sql", "server", "show", "-g", rg, "-n", srv, quiet=True)
    ad_only = az("sql", "server", "ad-only-auth", "get", "-g", rg, "-n", srv, quiet=True)
    rules = az("sql", "server", "firewall-rule", "list", "-g", rg, "-s", srv, quiet=True)
    checks = [
        (f"SQL sign-in on, login {s.get('administratorLogin')} (password from the environment or Key Vault, never in git)",
         not (ad_only and ad_only.get("azureAdOnlyAuthentication")) and bool(s.get("administratorLogin"))),
        ("TLS 1.2 or newer only", s.get("minimalTlsVersion") in ("1.2", "1.3")),
        ("No wide-open address ranges", all(r["startIpAddress"] == r["endIpAddress"] for r in rules)),
    ]
    azure_wide = any(r["startIpAddress"] == "0.0.0.0" for r in rules)
    print(f"\nServer {s['fullyQualifiedDomainName']} ({s['location']})")
    for label, ok in checks:
        print(f"  [{'ok' if ok else '!!'}] {label}")
    print("  Allowed machines: " + (", ".join(f"{r['name']} ({r['startIpAddress']})" for r in rules if r["startIpAddress"] != "0.0.0.0") or "none"))
    print("  [info] " + ("\"Allow Azure services\" is ON: any service in Azure can try to connect (still needs the login). Needed for Power BI or Fabric "
                         "refreshing from the cloud; turn it off in the portal (SQL server > Networking) if you don't use those." if azure_wide else
                         "\"Allow Azure services\" is off: only the machines above can connect."))
    if not all(ok for _, ok in checks):
        raise SystemExit("Some security checks failed: run  python3 tools/2_load_azure/database/azure_setup.py create  to fix them.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    {"plan": plan, "create": create, "allow-this-machine": allow_this_machine, "database": database, "status": status,
     "set-password": set_password}.get(
        cmd, lambda: sys.exit(f"Unknown command {cmd!r}. Use: plan, create, allow-this-machine, database, status, set-password"))()
