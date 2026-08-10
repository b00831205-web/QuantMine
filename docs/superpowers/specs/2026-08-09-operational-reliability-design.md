# Operational Reliability Fixes Design

## Goal

Remove the confirmed startup and deployment failures without changing the
quantitative research algorithms. The repaired project must support local
development on Windows and Linux/WSL, build the Web API image from the checked-in
lockfile, execute Airflow tasks from the mounted repository, and apply database
migrations to both fresh and existing PostgreSQL volumes.

## Scope

This change covers four related operational reliability defects:

1. The local `dev` entry point hard-codes a Linux virtual-environment path and
   crashes immediately on Windows.
2. The Web API Dockerfile requests an undefined `webapi` optional dependency.
3. The Airflow container derives the wrong project root and does not receive the
   pipeline database connection.
4. SQL migrations run only during first-time PostgreSQL initialization, so an
   existing volume can start with missing tables or columns.
   *(Resolved 2026-08-10 by commit `c7ba864`, but not as designed below — see
   the note in "Database Migration Lifecycle".)*

Existing frontend accessibility-test failures, repository-wide lint cleanup,
and changes to factor, IC, backtest, or attribution calculations are excluded.

## Chosen Approach

Use targeted fixes within the current architecture. Keep the existing
two-process local developer experience, Docker Compose topology, SQL migration
files, and Airflow BashOperator workflow. Do not consolidate development into
Docker and do not introduce Alembic.

*(Amended 2026-08-10: "keep the SQL migration files" no longer holds. They were
merged into `quantmine/storage/schema.sql` and deleted — see "Database Migration
Lifecycle". Alembic is still not introduced.)*

This approach has the smallest compatibility surface while preserving the
project's documented commands.

## Local Development Entry Point

`quantmine.dev` will resolve commands before starting either child process.

- On Windows, the backend interpreter is
  `webapi/.venv-win/Scripts/python.exe` and the frontend command is `npm.cmd`.
- On Linux and WSL, the backend interpreter is
  `webapi/.venv/bin/python` and the frontend command is `npm`.
- Missing executables produce an actionable error naming the expected setup
  command and path.
- If the backend starts but the frontend process cannot be created, the backend
  is terminated and reaped before the error is propagated.
- Once both processes exist, the current behavior remains: the launcher exits
  when either child exits and then shuts down the other child.

Command resolution and process cleanup will be separated into small helpers so
they can be tested without starting real servers.

## Web API Image Dependencies

The Web API image will install the project with `uv sync --locked`, using
`webapi/pyproject.toml` and `webapi/uv.lock` as the source of truth. The invalid
`--extra webapi` argument will be removed.

`--locked` is intentional: Docker builds must fail when project metadata and the
lockfile disagree. Developers add dependencies with `uv add`, which updates both
files, or run `uv lock` after editing `pyproject.toml`. The lockfile is generated;
it is never edited by hand.

## Airflow Container Contract

Docker Compose will explicitly give Airflow the following runtime contract:

- `QUANT_PROJECT_ROOT=/opt/project`
- `QUANT_PYTHON_BIN=python`
- `QUANT_CONFIG_PATH=config.yaml`
- `QUANTMINE_PIPELINE_DATABASE_URL` using the `quantmine_pipeline` PostgreSQL
  role and the Compose-provided pipeline password

The repository remains mounted at `/opt/project`, while DAG discovery remains at
`/opt/airflow/dags`. `DAG_pipeline.py` continues to construct commands, but those
commands will change directory to `/opt/project` and execute the mounted
`pipelines/*.py` files. The DAG will continue to promote
`QUANTMINE_PIPELINE_DATABASE_URL` to `QUANTMINE_DATABASE_URL` for database-backed
tasks.

The historical-membership CSV remains user-provided input and is not fabricated
by this change.

## Database Migration Lifecycle

> **SUPERSEDED 2026-08-10 by commit `c7ba864`.** This section is kept for the
> record; it is not what was built. Defect 4 was instead fixed by deleting
> `webapi/migrations/` and making `quantmine/storage/schema.sql` the single DDL
> source: every `CREATE EXTENSION/TABLE/INDEX` carries `IF NOT EXISTS`, so both
> initializers (`docker/postgres/init.sh`, `scripts/setup.py`) replay it
> unconditionally — fresh volumes get every table, existing volumes get whatever
> tables they are missing. No `schema_migrations` table, no `migrate` service.
>
> Rationale: the migration files and `schema.sql` had drifted into defining the
> same tables twice, and `setup.py` skipped `schema.sql` entirely once
> `research_runs` existed, so neither file was a complete description of the
> schema. One replayable file removes the drift at its source.
>
> Known limit of the replacement: `CREATE TABLE IF NOT EXISTS` skips the whole
> statement when the table exists and never compares columns, so `schema.sql`
> cannot deliver a **new column on an existing table** — that needs a manual
> `ALTER TABLE`. When that becomes a recurring chore, revisit the tracking-table
> design below; it is still the right answer for ordered, non-idempotent change.
>
> Verified on 2026-08-10: applying the merged `schema.sql` to a virgin database
> and then replaying it produces 19 tables / 170 columns / 17 foreign keys /
> 33 indexes, identical to the live migrated database.

Add a one-shot Compose `migrate` service based on the PostgreSQL client image.
It starts after the PostgreSQL health check and before the Web API.

The migration runner will:

1. Connect to the `quantmine` database with the Compose PostgreSQL administrator
   credentials.
2. Create a `schema_migrations` table when absent.
3. Enumerate `webapi/migrations/*.sql` in filename order.
4. Skip filenames already recorded in `schema_migrations`.
5. Execute each pending SQL file and its migration-record insert in one
   transaction with stop-on-error enabled.
6. Exit nonzero on the first failure.

This bootstraps existing volumes safely: the current migration files are
idempotent and can be applied once to an untracked installation, after which the
tracking table prevents repeats. Fresh installations remain supported by the
existing base schema initialization and then pass through the same migration
gate.

The Web API will depend on successful completion of `migrate`; it must not start
against a partially upgraded schema.

## Administrator Seeding

User seeding will become genuinely idempotent:

- An existing administrator is a successful no-op.
- A newly created administrator is success.
- Connection, reflection, hashing, or insertion failures remain nonzero.

The Web API entrypoint will no longer suppress every seeding failure with
`|| true`. This prevents a missing `auth_users` table or other schema problem
from being hidden behind an apparently healthy process.

## Error Handling

- Local command validation fails before any child process is started whenever
  possible.
- Partial local startup always cleans up the process that did start.
- A stale dependency lock fails the image build.
- A migration failure blocks Web API startup.
- Airflow task failures retain nonzero exit codes so the scheduler can retry and
  report the failing task accurately.

No operation deletes or recreates user data or Docker volumes.

## Test Strategy

Implementation follows red-green-refactor cycles.

1. Add unit tests for Windows and POSIX command resolution, missing-environment
   messages, and cleanup after a second child fails to start.
2. Add deployment contract tests that inspect the Dockerfile and parsed Compose
   configuration for the locked sync command, Airflow root, database URL, migrate
   service, and Web API dependency ordering.
3. Add tests for administrator-seeding exit semantics.
4. Validate the migration shell script syntax. When Docker execution is
   available, run it against an isolated temporary PostgreSQL instance twice to
   prove first-run application and repeat-run idempotence without touching the
   project's named volume.
5. Run `uv sync --locked` in dry-run mode, `docker compose config`, the core
   non-network pytest suite, the Web API suite when its environment is available,
   and the frontend production build.

Existing external-network tests remain excluded from the deterministic gate.

## Acceptance Criteria

- Windows and Linux/WSL resolve their own backend and npm executables without
  attempting to execute the other platform's virtual environment.
- A partial local startup leaves no child process running.
- The Web API dependency sync accepts the current lockfile and references no
  undefined extra.
- Rendered Compose configuration points Airflow tasks at `/opt/project` and
  includes the pipeline database URL.
- ~~Web API startup waits for successful migrations.~~ *(dropped — no `migrate`
  service exists; `schema.sql` is applied by the PostgreSQL initializer.)*
- Existing PostgreSQL volumes receive every table declared in `schema.sql`.
  *(Met 2026-08-10 via replayable `schema.sql` rather than a tracking table.)*
- Administrator seeding hides only the expected already-exists case.
- Deterministic core tests and the frontend production build remain successful.

