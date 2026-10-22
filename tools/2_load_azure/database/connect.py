"""
connect.py — open a connection to the cloud database.

Sign-in is SQL authentication: the login in Config/database.env (SQL_LOGIN) and its password from config.sql_password()
(environment, the repo's git-ignored .env, or Azure Key Vault). The password is never printed: errors show the server
and the login, never the connection string. --entra signs in with your Microsoft account instead, if the server has one
as its Entra admin. The connection is always encrypted, and the server's certificate is checked (no TrustServerCertificate).
"""

from . import config


def _braced(v):
    """A connection-string value that may hold ; or }: wrapped in braces, with } doubled."""
    return "{" + v.replace("}", "}}") + "}"


def connection_string(database=None, interactive=False, entra=False):
    v = config.read()
    base = f"Server=tcp:{config.server_host(v)},1433;Database={database or v['SQL_DATABASE']};Encrypt=yes;TrustServerCertificate=no;ConnectRetryCount=3"
    if entra or interactive:
        return base + f";Authentication={'ActiveDirectoryInteractive' if interactive else 'ActiveDirectoryDefault'}"
    return base + f";Authentication=SqlPassword;UID={_braced(v['SQL_LOGIN'])};PWD={_braced(config.sql_password())}"


def connect(database=None, interactive=False, autocommit=False, entra=False):
    import os
    import mssql_python
    entra = entra or os.getenv("FOURTH_SHEET_SQL_AUTH", "").lower() == "entra"    # FOURTH_SHEET_SQL_AUTH=entra: as you (az login), no password
    try:
        # a paused serverless database takes up to a minute to wake: allow 90 seconds to log in
        conn = mssql_python.connect(connection_string(database, interactive, entra), timeout=90)
    except Exception as e:
        msg = str(e)
        if not (entra or interactive):
            msg = msg.replace(config.sql_password(), "********")      # never show the password, even in an error
        hint = ""
        if "Client with IP address" in msg or "firewall" in msg.lower():
            hint = "\nThis machine isn't on the server's allowed list. Run:  python3 tools/2_load_azure/database/azure_setup.py allow-this-machine"
        elif "login failed" in msg.lower():
            hint = f"\nThe SQL login ({config.read()['SQL_LOGIN']}) or its password ({config.PASSWORD_VAR}) is wrong."
        elif "token" in msg.lower() or "credential" in msg.lower():
            hint = "\nFor Microsoft sign-in (--entra), sign in first:  az login"
        elif "paused" in msg.lower() or "not currently available" in msg.lower():
            hint = "\nThe database was asleep (it pauses when idle to cost nothing). Try again in a minute."
        raise SystemExit(f"Couldn't connect to {config.server_host()}: {msg}{hint}")
    conn.autocommit = autocommit
    return conn


def whoami(conn):
    cur = conn.cursor()
    cur.execute("SELECT SUSER_SNAME(), DB_NAME(), @@VERSION")
    return cur.fetchone()
