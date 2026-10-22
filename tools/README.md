# tools/: what runs, in what order

Everything here is Python (plus `mockups/` pictures and the git hook). The programs are sorted by **job**, in the order the work happens:

```
 1_build_data/        MAKE the raw data       invented numbers -> CSV files + schema.sql in OneDrive (Data/, Data documentation/)
        |
        v  (the CSVs)
 2_load_azure/        LOAD it into Azure      CSVs -> Azure SQL tables (staged, all-or-nothing)           [only when the database needs refreshing]
        |
        v  (the data: CSVs today, Azure with --source db)
 3_publish_site/      PUBLISH to the website  data -> page data (data/*.js), report pages, Excel/PDF/PowerPoint downloads (media/exports/)
```

Run the lot: `python3 tools/run_pipeline.py` (add `--azure` to include stage 2). Or one stage at a time:

| Stage | Command | Reads | Writes |
|---|---|---|---|
| 1 | `python3 tools/1_build_data/sample_data.py` | nothing (the model is in code) | OneDrive `Data/**.csv`, `Data documentation/schema.sql` and `README.md` |
| 2 | `python3 tools/2_load_azure/database/load.py` | OneDrive `Data/` | Azure SQL |
| 3 | `python3 tools/3_publish_site/build_site.py` | OneDrive `Data/` (or Azure) | `data/*.js`, `report-*.html`, `media/exports/*`, OneDrive Power BI prompts |

Then, in the cloud: `.github/workflows/pages.yml` runs `3_publish_site/tests/exports_match.py`, builds with Jekyll, and runs `3_publish_site/publish_site.py`.

## The other folders

| Folder | What it is |
|---|---|
| `shared/` | Small helpers more than one stage needs: `winutf8` (Windows UTF-8), `sync_media` (finds OneDrive, mirrors `media/`), `net` (downloads), `data_status` (when months lock), `readable_json`. |
| `setup/` | Run once per machine: `setup_machine.py` (packages, Azure sign-in, git guard), `machine_profile.py` (carry settings between Mac and PC). `setup_pc.cmd/.ps1` (in `tools/`) start it on Windows. |
| `archive/` | One-off programs nothing depends on (QR code, share image, game demo video, mock-up pictures). Kept in case you need to re-make those files. |
| `githooks/` | The pre-commit guard (stops a commit containing a password or data file). Switched on by `setup/setup_machine.py`. |
| `newsletter/` | The weekly newsletter builder. Separate from the site data pipeline. |
| `mockups/` | The mock-up pictures' source pages. Stage 1 checks its key figures still appear in them. |

## Who may import whom (the rule that keeps the stages apart)

- `shared/` imports nothing from the stages.
- **Stage 1** imports only `shared/`. (One deliberate exception: the last step of `sample_data.py` writes the 13-week cash-forecast table, which is worked out by the report engine in stage 3, so it calls `fourthsheet`.)
- **Stage 2** imports `shared/` only.
- **Stage 3** imports `shared/`; the model in stage 1 (`financial_model`, `model_tables`, `tax_payroll`, `deliveries`: the home dashboard and the reports are calculated from it); and, for `--source db`, the connection code in stage 2 (`database/connect.py`, `schema.py`).

Every program can be run straight from its own folder because it starts with a 3-line block that puts all the stage folders on Python's import path. That is why `import financial_model` works from anywhere under `tools/`.

## Where things were split (22 Oct 2026)

- `deliveries.py` (stage 1, data) and `3_publish_site/deliveries_site.py` (the website file and downloads) used to be one file.
- `model_tables.py` (stage 1) took the CSV rows out of `publish_dashboard.py` (stage 3).
- `sample_data.py` no longer builds the website; `3_publish_site/build_site.py` does.
