# The cloud database (Azure SQL)

**Sign-in is a SQL login and password, and the password is never in git or OneDrive's settings.** The tools read it from,
in order: the environment variable `FOURTH_SHEET_SQL_PASSWORD`; a `.env` file at the repo root holding that variable (git
ignores `.env`, and the tools refuse to read one that git tracks); or Azure Key Vault (the secret `sql-password` in the vault
named by `AZURE_KEYVAULT` in `Config/database.env`). Nothing prints it, and errors mask it. Azure management (creating the
server, the firewall) still uses your Microsoft account (`az login`). Only machines you've allowed can reach the server.

### The password, on each machine (once)

Pick one:
- **Environment:** add `export FOURTH_SHEET_SQL_PASSWORD='…'` to your shell profile (Mac), or set it as a user environment
  variable (Windows: System Properties > Environment Variables).
- **.env file:** create `.env` at the repo root with the line `FOURTH_SHEET_SQL_PASSWORD=` followed by the password. Check
  `git status` doesn't list it.
- **Key Vault:** `az keyvault secret set --vault-name <vault> --name sql-password --value '…'`, then set `AZURE_KEYVAULT=<vault>`
  in `Config/database.env`.

Use a long random password (a password manager can make one). To change it: update it where you keep it, then run
`python3 tools/database/azure_setup.py set-password`.

## On any machine (Mac or Windows), once

```
python3 tools/setup_machine.py        # Windows: py tools\setup_machine.py
```

It installs the Python packages and the Azure command line, and switches on the git leak guard. It finds OneDrive and syncs `media/`.
It signs you in to Azure (browser), lets this machine through the database firewall, and tests the connection.
Run it again whenever something seems off, or after your internet address changes (a new network).

## Create the database (once, from either machine)

```
python3 tools/database/azure_setup.py            # the plan: what exists and what would be created (changes nothing)
python3 tools/database/azure_setup.py create     # create it, locked down
python3 tools/database/azure_setup.py status     # security check
```

What it creates: resource group `rg-thefourthsheet`, server `thefourthsheet-sql.database.windows.net`, database `thefourthsheet`
(the names come from `Config/database.env`; `tools/database/config.py` has the defaults).
- **Region:** Australia East.
- **Cost:** the free serverless tier. It pauses when idle, and pauses instead of charging if the free monthly allowance runs out.
- **Sign-in:** SQL login `SQL_LOGIN` (default `tfsadmin`) with the password above; your Microsoft account is also
  set as the server's Entra admin when its ID is known.
- **Encryption:** TLS 1.2 or newer.
- **Firewall:** no Azure-wide access; one rule per machine, at that machine's own address.

Settings (names and IDs only, never secrets) are saved to OneDrive `Config/database.env`, so both machines share them.
The password isn't one of them.

## Load the data

```
python3 tools/database/load.py --check     # stage and check everything; nothing live changes
python3 tools/database/load.py             # load: stage, check, then replace the live tables in one transaction
python3 tools/report.py --compare-sources  # every report from the database = the same report from the CSVs
python3 tools/report.py job-margins --period 2026-06 --source db
```

The load is safe by design:
- **Strict files:** each file's columns must match its table exactly.
- **Staged and checked:** every row lands in `stage` first, and row counts and a checksum of every number are compared with the files.
- **All or nothing:** only then are the live tables replaced, in one transaction. If anything fails, the live data is exactly as it was.
- **Logged:** every run goes in `ops.load_run` / `ops.load_table` (who, which machine, when, rows, result).
- **Parameters only:** values are always sent as parameters, so nothing in a file can run as SQL.

## Inside the database

| Schema | What | Who |
| --- | --- | --- |
| `dbo` | the tables in `schema.sql` (OneDrive, Data documentation) | `data_loader` writes, `report_reader` reads |
| `stage` | each load lands here first | `data_loader` |
| `ops` | load log | `data_loader` |
| `rpt` | reporting views (next: the star schema) | `report_reader` |

Add people and apps to a role, never one by one (`security.sql` has the commands, with placeholders). Each gets its own
contained SQL user and password, typed in when the command is run and kept in Key Vault or a password manager, never in a file.

## The star schema

`Data documentation/Database tables and star schema.md` (OneDrive) has every table: its file, rows, columns, types, keys
and an example. It also gives each table's best-practice place in a star schema, with a ready-to-paste prompt for Claude
through a SQL database MCP. Regenerate it with `python3 tools/database/document.py`.

## If something goes wrong

| Message | Fix |
| --- | --- |
| Client with IP address ... is not allowed | `python3 tools/database/azure_setup.py allow-this-machine` |
| Login failed | the SQL login or its password is wrong: check `FOURTH_SHEET_SQL_PASSWORD` (or Key Vault), or reset it with `azure_setup.py set-password` |
| No SQL password found | set `FOURTH_SHEET_SQL_PASSWORD` (environment or `.env`) or Key Vault, as above |
| Not signed in (Azure management) | `az login` |
| database not currently available | it was paused (free tier); wait a minute and try again |
| COMMIT STOPPED | the leak guard found a secret or personal detail in what you're committing: remove it |
