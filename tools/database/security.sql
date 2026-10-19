-- security.sql — schemas and least-privilege roles inside the database. Safe to run again (every step checks first).
-- Run by: python3 tools/database/azure_setup.py database   (signed in as the server's SQL admin login)
--
-- Schemas
--   dbo     the data (the tables in schema.sql)
--   stage   where each load lands first and is checked; the live tables only change once every check passes
--   ops     the load log: who loaded what, when, from where, how many rows, and whether it passed
--   rpt     reporting views (the website, the report builder and Power BI read these; next step)
--   retail, health, legal   the three synthetic datasets (tools/datasets.py), each in its own schema
--
-- Roles (people and apps are added to a role, never granted rights one by one)
--   report_reader  read-only: SELECT on dbo and rpt. For Power BI, the report builder, the website's API.
--   data_loader    loads data: write to stage, replace rows in dbo, write the load log. Can't change security.
-- Sign-in is SQL authentication. Passwords never go in this file or in git: each comes from an environment variable,
-- the repo's git-ignored .env, or Azure Key Vault, and is typed into the commands below only when they're run.

IF SCHEMA_ID('stage') IS NULL EXEC('CREATE SCHEMA stage');
IF SCHEMA_ID('ops') IS NULL EXEC('CREATE SCHEMA ops');
IF SCHEMA_ID('rpt') IS NULL EXEC('CREATE SCHEMA rpt');
IF SCHEMA_ID('retail') IS NULL EXEC('CREATE SCHEMA retail');
IF SCHEMA_ID('health') IS NULL EXEC('CREATE SCHEMA health');
IF SCHEMA_ID('legal') IS NULL EXEC('CREATE SCHEMA legal');

IF OBJECT_ID('ops.load_run') IS NULL
CREATE TABLE ops.load_run (
    load_id        INT IDENTITY(1,1) PRIMARY KEY,
    started_at     DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at    DATETIME2(0) NULL,
    loaded_by      NVARCHAR(128) NOT NULL DEFAULT SUSER_SNAME(),
    machine        NVARCHAR(128) NULL,
    source         NVARCHAR(400) NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'Running',   -- Running, Loaded, Failed, Checked (dry run)
    tables_loaded  INT NULL,
    rows_loaded    INT NULL,
    message        NVARCHAR(4000) NULL
);

IF OBJECT_ID('ops.load_table') IS NULL
CREATE TABLE ops.load_table (
    load_id        INT NOT NULL REFERENCES ops.load_run(load_id),
    table_name     VARCHAR(128) NOT NULL,
    files          INT NOT NULL,
    csv_rows       INT NOT NULL,
    loaded_rows    INT NOT NULL,
    csv_checksum   DECIMAL(38,6) NULL,     -- sum of the numeric columns in the files
    loaded_checksum DECIMAL(38,6) NULL,    -- the same sum, read back from the database
    PRIMARY KEY (load_id, table_name)
);

IF DATABASE_PRINCIPAL_ID('report_reader') IS NULL CREATE ROLE report_reader;
IF DATABASE_PRINCIPAL_ID('data_loader') IS NULL CREATE ROLE data_loader;

GRANT SELECT ON SCHEMA::dbo TO report_reader;
GRANT SELECT ON SCHEMA::rpt TO report_reader;
GRANT SELECT ON SCHEMA::retail TO report_reader;
GRANT SELECT ON SCHEMA::health TO report_reader;
GRANT SELECT ON SCHEMA::legal TO report_reader;

GRANT SELECT, INSERT, DELETE ON SCHEMA::dbo TO data_loader;
GRANT SELECT, INSERT, DELETE ON SCHEMA::retail TO data_loader;
GRANT SELECT, INSERT, DELETE ON SCHEMA::health TO data_loader;
GRANT SELECT, INSERT, DELETE ON SCHEMA::legal TO data_loader;
GRANT SELECT, INSERT, DELETE, ALTER ON SCHEMA::stage TO data_loader;
GRANT SELECT, INSERT, UPDATE ON SCHEMA::ops TO data_loader;
GRANT CREATE TABLE TO data_loader;

-- People and apps: add each one to a role when it's needed, each with its own SQL user and password (a contained
-- database user, so it only reaches this database). Fill in the name, paste the password from Key Vault or your
-- password manager at the moment you run it, and never save the filled-in command. One at a time, as the admin:
--
--   Someone who reads reports (e.g. in Power BI):
--     CREATE USER [[[READER_NAME]]] WITH PASSWORD = '[[READER_PASSWORD]]';
--     ALTER ROLE report_reader ADD MEMBER [[[READER_NAME]]];
--
--   The report API:
--     CREATE USER [[[REPORT_API_NAME]]] WITH PASSWORD = '[[REPORT_API_PASSWORD]]';
--     ALTER ROLE report_reader ADD MEMBER [[[REPORT_API_NAME]]];
--
--   A scheduled loader:
--     CREATE USER [[[LOADER_NAME]]] WITH PASSWORD = '[[LOADER_PASSWORD]]';
--     ALTER ROLE data_loader ADD MEMBER [[[LOADER_NAME]]];
--
--   To change a password later:  ALTER USER [[[NAME]]] WITH PASSWORD = '[[NEW_PASSWORD]]';
