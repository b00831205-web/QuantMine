# QUANTMINE Docker Deployment

The Compose stack provides PostgreSQL/pgvector, FastAPI, the React/Nginx
frontend, and Airflow 3 standalone for local or single-user self-hosting.

## Quick Start

Run from the repository root:

```bash
python scripts/create_docker_env.py
docker compose --env-file .env.docker up -d --build
docker compose --env-file .env.docker ps
```

Open <http://localhost:8090> and use the admin credentials stored in
`.env.docker`. Airflow's native UI is available at <http://localhost:8091>.

The environment generator creates URL-safe database passwords, an application
session secret, an admin password, and a valid Fernet key. Container startup
rejects missing values and the `REPLACE_ME` template placeholder.

## Services

| Service | Role | Host binding |
|---|---|---|
| `frontend` | Nginx static frontend and `/api` reverse proxy | `127.0.0.1:8090` |
| `webapi` | FastAPI and Airflow workflow CLI | internal `8000` |
| `postgres` | PostgreSQL 16 + pgvector; schema and roles on first boot | `127.0.0.1:5432` |
| `airflow` | Airflow scheduler, API server, DAG processor and executor | `127.0.0.1:8091` |

All services use `restart: unless-stopped`. Host port bindings are loopback-only
by default; do not change them to public bindings without authentication, TLS,
and network controls.

## Data and Mounts

- `pgdata` stores PostgreSQL data.
- `airflow-logs` stores Airflow logs.
- `./pipelines` is mounted read-only at `/app/pipelines`.
- `./config.example.yaml` is mounted read-only for the default research config.
- `./data` and `./tmp` preserve market data and checkpoints on the host.

The entire repository is not mounted into any container. Local `.env` files,
credentials, Airflow configuration, virtualenvs, caches, and databases are
excluded from the build context by `.dockerignore`.

## Workflow Execution

The Web API image contains two virtualenvs:

- `/app/webapi/.venv` runs FastAPI;
- `/app/.venv` supplies the Airflow CLI from the committed root `uv.lock`.

Both Web API and Airflow connect to the same Airflow metadata database. The
Workflows page can therefore browse DAGs and perform pause, trigger, clear, and
task-state actions without Docker socket access.

Pipeline tasks run with container Python and write through the
`quantmine_pipeline` database role. The Web API role can read research data and
write only application-state tables.

## Operations

```bash
# Follow application and scheduler logs
docker compose --env-file .env.docker logs -f webapi airflow

# Reset the application admin password
docker compose --env-file .env.docker exec webapi \
  python /app/scripts/reset_password.py admin

# Stop while preserving volumes
docker compose --env-file .env.docker down

# Destructive: stop and delete PostgreSQL/Airflow volumes
docker compose --env-file .env.docker down -v
```

To run the product without Airflow:

```bash
docker compose --env-file .env.docker up -d postgres webapi frontend
```

Login, market, research, report, AI, and data pages remain available, but the
Workflows screen has no active scheduler.

## Verification

```bash
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker ps

curl http://localhost:8090/api/v1/health
curl http://localhost:8091/api/v2/monitor/health
```

A new database is intentionally empty. Sign in to the product, open Workflows,
and trigger `quant_factor_mining` before expecting research/report content.
Yahoo rate limits may reduce historical share coverage; price checkpoints and
the share circuit breaker prevent a full rerun from hanging indefinitely.

This Compose file is a single-machine deployment, not a production Airflow
cluster. Public deployment requires a TLS reverse proxy, secure cookies, proper
secret management, backups, monitoring, and restricted Airflow access.
