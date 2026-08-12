# Operational Reliability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local startup cross-platform, make the Web API image reproducible, connect Docker Airflow to the mounted project and pipeline database, and migrate existing PostgreSQL volumes before the application starts.

**Architecture:** Keep the existing Python launcher, Docker Compose services, SQL migration files, and Airflow BashOperator DAG. Add small command-resolution/process-lifecycle helpers, explicit Compose contracts, and a one-shot tracked SQL migration service. Every confirmed failure receives a focused regression test before its production change.

**Tech Stack:** Python 3.13, pytest, SQLAlchemy, uv, Docker Compose, PostgreSQL 16/pgvector, POSIX shell, Airflow 3.2, Node/Vite.

## Global Constraints

- Support both Windows and Linux/WSL without sharing one platform-specific virtual environment.
- Windows Web API environment path is `webapi/.venv-win`; Linux/WSL path is `webapi/.venv`.
- Docker dependency installation uses `uv sync --locked`; `uv.lock` is generated with `uv add` or `uv lock`, never hand-edited.
- The Docker repository mount remains `/opt/project`; DAG discovery remains `/opt/airflow/dags`.
- Never delete or recreate a user database or Docker volume.
- Do not change factor, IC, backtest, attribution, frontend accessibility, or unrelated lint behavior.
- External-network tests are not part of the deterministic completion gate.

---

## File Structure

- `quantmine/dev.py`: resolve platform-specific commands and own child-process cleanup.
- `test/test_dev.py`: regression coverage for Windows/POSIX resolution and partial-start cleanup.
- `docker/webapi/Dockerfile`: install exactly the locked Web API dependency set.
- `docker-compose.yml`: declare Airflow runtime values, the migration gate, and service ordering.
- `test/test_deployment_contract.py`: parse deployment files and enforce their cross-file contract.
- `docker/postgres/migrate.sh`: apply each pending SQL migration transactionally and record it.
- `scripts/create_user.py`: make existing-user seeding a successful no-op while preserving real failures.
- `test/test_create_user.py`: exercise seeding against a real in-memory SQLAlchemy database.
- `docker/webapi/entrypoint.sh`: stop suppressing unexpected seeding failures.
- `docker/README.md`: document dependency locking, migration startup, and the remaining Airflow CLI limitation.

---

### Task 1: Cross-platform local development launcher

**Files:**
- Create: `test/test_dev.py`
- Modify: `quantmine/dev.py:10-74`

**Interfaces:**
- Produces: `DevCommands(api: list[str], web: list[str])`.
- Produces: `resolve_dev_commands(root: Path = ROOT, platform_name: str | None = None, which: Callable = shutil.which) -> DevCommands`.
- Produces: `_start_processes(commands: DevCommands, env: dict[str, str], popen: Callable = subprocess.Popen) -> list[tuple[str, subprocess.Popen]]`.
- Consumes: existing repository layout and `_load_env()`.

- [ ] **Step 1: Write failing command-resolution tests**

```python
from pathlib import Path

import pytest

from quantmine.dev import resolve_dev_commands


def _make_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_windows_uses_isolated_windows_environment(tmp_path: Path) -> None:
    python = tmp_path / "webapi" / ".venv-win" / "Scripts" / "python.exe"
    _make_file(python)

    commands = resolve_dev_commands(
        tmp_path,
        platform_name="nt",
        which=lambda command: "C:/Program Files/nodejs/npm.cmd" if command == "npm.cmd" else None,
    )

    assert commands.api[0] == str(python)
    assert commands.web == ["C:/Program Files/nodejs/npm.cmd", "run", "dev"]


def test_posix_uses_isolated_posix_environment(tmp_path: Path) -> None:
    python = tmp_path / "webapi" / ".venv" / "bin" / "python"
    _make_file(python)

    commands = resolve_dev_commands(
        tmp_path,
        platform_name="posix",
        which=lambda command: "/usr/bin/npm" if command == "npm" else None,
    )

    assert commands.api[0] == str(python)
    assert commands.web == ["/usr/bin/npm", "run", "dev"]


def test_missing_backend_environment_fails_before_start(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"webapi[/\\]\.venv-win"):
        resolve_dev_commands(
            tmp_path,
            platform_name="nt",
            which=lambda command: "npm.cmd",
        )
```

- [ ] **Step 2: Run the resolution tests and verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_dev.py -v`

Expected: collection fails because `resolve_dev_commands` and `DevCommands` do not exist.

- [ ] **Step 3: Add a failing partial-start cleanup test**

```python
from quantmine.dev import DevCommands, _start_processes


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.waited = False

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0


def test_frontend_spawn_failure_reaps_backend(tmp_path: Path) -> None:
    backend = FakeProcess()
    calls = 0

    def fake_popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return backend
        raise OSError("frontend unavailable")

    commands = DevCommands(api=["python", "-m", "uvicorn"], web=["npm", "run", "dev"])

    with pytest.raises(OSError, match="frontend unavailable"):
        _start_processes(commands, {}, popen=fake_popen)

    assert backend.terminated is True
    assert backend.waited is True
```

- [ ] **Step 4: Run the cleanup test and verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_dev.py::test_frontend_spawn_failure_reaps_backend -v`

Expected: collection fails because `_start_processes` does not exist.

- [ ] **Step 5: Implement minimal command resolution and cleanup**

Add the following structure to `quantmine/dev.py` and make `main()` consume it:

```python
from collections.abc import Callable
from dataclasses import dataclass
import shutil


@dataclass(frozen=True)
class DevCommands:
    api: list[str]
    web: list[str]


def resolve_dev_commands(
    root: Path = ROOT,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> DevCommands:
    platform_name = platform_name or os.name
    if platform_name == "nt":
        python = root / "webapi" / ".venv-win" / "Scripts" / "python.exe"
        npm_name = "npm.cmd"
        setup = "cd webapi; $env:UV_PROJECT_ENVIRONMENT='.venv-win'; uv sync"
    else:
        python = root / "webapi" / ".venv" / "bin" / "python"
        npm_name = "npm"
        setup = "cd webapi && uv sync"

    if not python.is_file():
        raise RuntimeError(f"Missing Web API environment at {python}. Run: {setup}")
    npm = which(npm_name)
    if npm is None:
        raise RuntimeError(f"Missing {npm_name}; install Node.js and ensure it is on PATH")

    api = [
        str(python), "-m", "uvicorn", "app.main:app", "--reload",
        "--host", "0.0.0.0", "--port", "8000",
    ]
    return DevCommands(api=api, web=[npm, "run", "dev"])


def _start_processes(commands, env, popen=subprocess.Popen):
    api = popen(commands.api, cwd=ROOT / "webapi", env=env)
    try:
        web = popen(commands.web, cwd=ROOT / "frontend", env=env)
    except BaseException:
        api.terminate()
        api.wait(timeout=5)
        raise
    return [("api", api), ("web", web)]
```

Keep the existing monitor loop, but use `terminate()` for portable shutdown and
kill only after a five-second timeout.

- [ ] **Step 6: Run Task 1 tests and the deterministic core suite**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_dev.py -v`

Expected: all `test_dev.py` tests pass.

Run: `.\.venv-win\Scripts\python.exe -m pytest test -q -m "not network"`

Expected: existing deterministic tests plus the new launcher tests pass.

- [ ] **Step 7: Commit Task 1**

```bash
git add quantmine/dev.py test/test_dev.py
git commit -m "fix: make dev launcher cross-platform"
```

---

### Task 2: Locked Web API build and Airflow runtime contract

**Files:**
- Create: `test/test_deployment_contract.py`
- Modify: `docker/webapi/Dockerfile:19-22`
- Modify: `docker-compose.yml:57-71`

**Interfaces:**
- Consumes: `webapi/uv.lock`, `/opt/project` repository mount, Compose password variables.
- Produces: an Airflow environment that lets `DAG_pipeline.task_command()` execute mounted scripts and connect as `quantmine_pipeline`.

- [ ] **Step 1: Write failing deployment contract tests**

```python
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_webapi_dockerfile_uses_checked_lockfile() -> None:
    dockerfile = (ROOT / "docker" / "webapi" / "Dockerfile").read_text(encoding="utf-8")
    assert "RUN uv sync --locked" in dockerfile
    assert "--extra webapi" not in dockerfile


def test_airflow_container_points_at_mounted_project_and_pipeline_database() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    airflow = compose["services"]["airflow"]
    environment = airflow["environment"]

    assert environment["QUANT_PROJECT_ROOT"] == "/opt/project"
    assert environment["QUANT_PYTHON_BIN"] == "python"
    assert environment["QUANT_CONFIG_PATH"] == "config.yaml"
    assert environment["QUANTMINE_PIPELINE_DATABASE_URL"] == (
        "postgresql+psycopg2://quantmine_pipeline:"
        "${QUANTMINE_PIPELINE_PASSWORD}@postgres:5432/quantmine"
    )
    assert "./:/opt/project" in airflow["volumes"]
```

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_deployment_contract.py -v`

Expected: the Dockerfile assertion and Airflow environment assertions fail.

- [ ] **Step 3: Apply the minimal Dockerfile and Compose changes**

Change the Dockerfile install line to:

```dockerfile
RUN uv sync --locked
```

Add these Airflow environment entries:

```yaml
      QUANT_PROJECT_ROOT: /opt/project
      QUANT_PYTHON_BIN: python
      QUANT_CONFIG_PATH: config.yaml
      QUANTMINE_PIPELINE_DATABASE_URL: postgresql+psycopg2://quantmine_pipeline:${QUANTMINE_PIPELINE_PASSWORD}@postgres:5432/quantmine
```

- [ ] **Step 4: Verify the contract and rendered Compose model**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_deployment_contract.py -v`

Expected: both tests pass.

Run: `docker compose --env-file .env.docker.example config --quiet`

Expected: exit 0 with no undefined-variable warnings.

Run from `webapi/`: `uv sync --locked --dry-run`

Expected: exit 0 and no undefined-extra or stale-lock error.

- [ ] **Step 5: Commit Task 2**

```bash
git add docker/webapi/Dockerfile docker-compose.yml test/test_deployment_contract.py
git commit -m "fix: repair container dependency and airflow contracts"
```

---

### ~~Task 3: Tracked migration gate for existing PostgreSQL volumes~~ — OBSOLETE

> **Do not implement.** Superseded 2026-08-10 by commit `c7ba864`, which fixed
> the same defect (existing volumes missing tables) by making
> `quantmine/storage/schema.sql` the single, replayable DDL source and deleting
> `webapi/migrations/`. There is no `migrations/` directory left to enumerate,
> so every step below refers to files that no longer exist.
>
> `docker/postgres/migrate.sh` was never created; `docker-compose.yml` has no
> `migrate` service and no longer mounts `./webapi/migrations`. The invariants
> are locked by `test/test_schema_contract.py` instead.
>
> Reopen this task only if `schema.sql` starts needing **column** changes on
> existing tables — `CREATE TABLE IF NOT EXISTS` cannot express those. The
> design here (a `schema_migrations` bookkeeping table) is still the right
> approach for that case. See the superseded-section note in
> `docs/superpowers/specs/2026-08-09-operational-reliability-design.md`.

**Files:**
- Create: `docker/postgres/migrate.sh`
- Modify: `docker-compose.yml:32-47`
- Modify: `test/test_deployment_contract.py`

**Interfaces:**
- Consumes: `/migrations/*.sql`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and the `postgres` service.
- Produces: `schema_migrations(filename text primary key, applied_at timestamptz)` in `quantmine`.
- Produces: one-shot Compose service `migrate` whose successful completion gates `webapi`.

- [ ] **Step 1: Add failing migration-service contract tests**

```python
def test_webapi_waits_for_tracked_migrations() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    migrate = services["migrate"]

    assert migrate["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "./webapi/migrations:/migrations:ro" in migrate["volumes"]
    assert "./docker/postgres/migrate.sh:/migrate.sh:ro" in migrate["volumes"]
    assert services["webapi"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )


def test_migration_runner_tracks_files_and_uses_transactions() -> None:
    script = (ROOT / "docker" / "postgres" / "migrate.sh").read_text(encoding="utf-8")
    assert "schema_migrations" in script
    assert "--single-transaction" in script
    assert "ON_ERROR_STOP=1" in script
    assert 'for file in /migrations/*.sql' in script
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_deployment_contract.py -v`

Expected: failure because the `migrate` service and script do not exist.

- [ ] **Step 3: Implement the migration runner**

Create `docker/postgres/migrate.sh` with this behavior:

```sh
#!/bin/sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

export PGHOST="${POSTGRES_HOST:-postgres}"
export PGPORT="${POSTGRES_PORT:-5432}"
export PGUSER="$POSTGRES_USER"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGDATABASE="quantmine"

psql -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL

for file in /migrations/*.sql; do
    [ -f "$file" ] || continue
    name=$(basename "$file")
    case "$name" in
        *[!A-Za-z0-9_.-]*)
            echo "[migrate] unsafe migration filename: $name" >&2
            exit 2
            ;;
    esac
    applied=$(psql -v ON_ERROR_STOP=1 -tA \
        -c "SELECT 1 FROM schema_migrations WHERE filename = '$name'")
    if [ "$applied" = "1" ]; then
        echo "[migrate] already applied: $name"
        continue
    fi
    echo "[migrate] applying: $name"
    {
        cat "$file"
        printf "\nINSERT INTO schema_migrations(filename) VALUES ('%s');\n" "$name"
    } | psql -v ON_ERROR_STOP=1 --single-transaction
done
```

- [ ] **Step 4: Add the one-shot Compose service and gate Web API startup**

Add:

```yaml
  migrate:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_HOST: postgres
    volumes:
      - ./docker/postgres/migrate.sh:/migrate.sh:ro
      - ./webapi/migrations:/migrations:ro
    entrypoint: ["/bin/sh", "/migrate.sh"]
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"
```

Replace the Web API's direct PostgreSQL dependency with:

```yaml
    depends_on:
      migrate:
        condition: service_completed_successfully
```

- [ ] **Step 5: Verify tests, shell syntax, and Compose ordering**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_deployment_contract.py -v`

Expected: all deployment contract tests pass.

Run when a POSIX shell is available: `sh -n docker/postgres/migrate.sh`

Expected: exit 0.

Run: `docker compose --env-file .env.docker.example config --quiet`

Expected: exit 0.

- [ ] **Step 6: Run isolated migration integration when Docker is available**

Use a unique Compose project name and the example environment so no existing
named volume is touched:

```bash
docker compose --project-name quantmine-migration-audit --env-file .env.docker.example up --build --abort-on-container-exit migrate
docker compose --project-name quantmine-migration-audit --env-file .env.docker.example run --rm migrate
docker compose --project-name quantmine-migration-audit --env-file .env.docker.example down -v
```

Expected: first run applies migrations, second run reports every migration as
already applied, and cleanup removes only `quantmine-migration-audit` resources.

- [ ] **Step 7: Commit Task 3**

```bash
git add docker/postgres/migrate.sh docker-compose.yml test/test_deployment_contract.py
git commit -m "fix: gate web startup on tracked migrations"
```

---

### Task 4: Stop hiding administrator-seeding failures

**Files:**
- Create: `test/test_create_user.py`
- Modify: `scripts/create_user.py:20-49`
- Modify: `docker/webapi/entrypoint.sh:14-18`

**Interfaces:**
- Produces: `main(argv: list[str], engine: Engine | None = None) -> int`.
- Behavior: existing and newly created users return 0; unexpected database errors propagate.

- [ ] **Step 1: Write failing real-database tests**

```python
import pytest
from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.exc import NoSuchTableError

from scripts.create_user import main


def _auth_engine():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    Table(
        "auth_users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String, nullable=False, unique=True),
        Column("password_hash", String, nullable=False),
        Column("display_name", String),
        Column("is_active", Boolean, nullable=False, default=True),
    )
    metadata.create_all(engine)
    return engine


def test_existing_user_is_successful_no_op() -> None:
    engine = _auth_engine()
    assert main(["create_user.py", "admin", "first"], engine=engine) == 0
    assert main(["create_user.py", "admin", "second"], engine=engine) == 0

    users = Table("auth_users", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        assert len(connection.execute(select(users)).all()) == 1


def test_missing_auth_table_is_not_hidden() -> None:
    engine = create_engine("sqlite://")
    with pytest.raises(NoSuchTableError):
        main(["create_user.py", "admin", "secret"], engine=engine)
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_create_user.py -v`

Expected: failure because `main()` does not accept `engine`, and the existing-user path currently returns 1.

- [ ] **Step 3: Implement idempotent seeding**

Change the function signature and engine initialization:

```python
from sqlalchemy.engine import Engine


def main(argv: list[str], engine: Engine | None = None) -> int:
    # argument validation remains unchanged
    engine = engine or get_engine()
```

Change the existing-user path to:

```python
    if exists:
        print(f"用户已存在：{username}", file=sys.stderr)
        return 0
```

Do not catch reflection or insert exceptions.

- [ ] **Step 4: Make the entrypoint fail on genuine seed errors**

Change:

```sh
python /app/scripts/create_user.py "$QUANTMINE_ADMIN_USER" "$QUANTMINE_ADMIN_PASSWORD" 管理员 || true
```

to:

```sh
python /app/scripts/create_user.py "$QUANTMINE_ADMIN_USER" "$QUANTMINE_ADMIN_PASSWORD" 管理员
```

- [ ] **Step 5: Verify seeding and deterministic core tests**

Run: `.\.venv-win\Scripts\python.exe -m pytest test/test_create_user.py -v`

Expected: both tests pass.

Run: `.\.venv-win\Scripts\python.exe -m pytest test -q -m "not network"`

Expected: all deterministic core and operational tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/create_user.py docker/webapi/entrypoint.sh test/test_create_user.py
git commit -m "fix: surface administrator seed failures"
```

---

### Task 5: Documentation and full verification

**Files:**
- Modify: `docker/README.md:6-47`
- Modify: `README.md:20-32`

**Interfaces:**
- Documents: platform-specific Web API environment setup, lockfile workflow, migration gate, and the existing Airflow CLI write-action limitation.

- [ ] **Step 1: Update local-development instructions**

Document these commands without changing the existing library installation
instructions:

```powershell
# Windows
cd webapi
$env:UV_PROJECT_ENVIRONMENT='.venv-win'
uv sync
cd ..
uv run quantmine-dev
```

```bash
# Linux / WSL
cd webapi
uv sync
cd ..
uv run quantmine-dev
```

- [ ] **Step 2: Update Docker dependency and migration documentation**

State explicitly:

- dependencies are added with `uv add` or reconciled with `uv lock`;
- Docker uses `uv sync --locked` and rejects a stale lockfile;
- `migrate` runs before `webapi` on every Compose startup and does not recreate the database;
- Workflows write buttons still require an Airflow CLI/REST integration and remain outside this fix.

- [ ] **Step 3: Run fresh verification gates**

Run: `.\.venv-win\Scripts\python.exe -m pytest test -q -m "not network"`

Expected: zero failures.

Run: `.\.venv-win\Scripts\python.exe -m ruff check quantmine/dev.py scripts/create_user.py test/test_dev.py test/test_create_user.py test/test_deployment_contract.py --select F,E9`

Expected: zero findings in changed Python files.

Run: `npm.cmd run build` from `frontend/`.

Expected: TypeScript and Vite build successfully; the existing chunk-size warning is allowed.

Run: `docker compose --env-file .env.docker.example config --quiet`.

Expected: exit 0.

Run from `webapi/`: `uv sync --locked --dry-run`.

Expected: exit 0.

Run the Web API suite in `webapi/.venv` or `webapi/.venv-win` when that environment is executable.

Expected: zero failures. If the host WSL distribution remains read-only, report the environment blocker instead of claiming the suite passed.

- [ ] **Step 4: Verify the original failures are gone**

On Windows with `webapi/.venv-win` present, run:

```powershell
.\.venv-win\Scripts\python.exe -c "from quantmine.dev import resolve_dev_commands; print(resolve_dev_commands())"
```

Expected: the API command begins with `webapi\.venv-win\Scripts\python.exe` and the web command begins with `npm.cmd`.

Run:

```powershell
Select-String -Path docker/webapi/Dockerfile -Pattern 'uv sync --locked'
```

Expected: one matching install line and no `--extra webapi` occurrence.

- [ ] **Step 5: Review the final diff for scope and safety**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short`

Expected: only the planned operational, test, and documentation files are modified.

- [ ] **Step 6: Commit Task 5**

```bash
git add README.md docker/README.md
git commit -m "docs: explain reliable local and docker startup"
```

