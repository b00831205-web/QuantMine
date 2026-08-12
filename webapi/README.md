# QUANTMINE Web API

The Web API is a FastAPI application that serves authentication, market data,
research results, backtests, reports, AI workflows, rebalances, data inspection,
Airflow workflow controls, and—when built for service mode—the React application.

## Quick Start

From the repository root:

```bash
cd webapi
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open:

- API documentation: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/api/v1/health>

The API expects the PostgreSQL connection variables created by
`scripts/setup.py`. For the complete frontend/API/Airflow stack, use `uv run quantmine-dev`
from the repository root.

## Environment

Important variables include:

| Variable | Purpose |
|---|---|
| `QUANTMINE_DATABASE_URL` | Web application database connection |
| `QUANT_AIRFLOW_PG_DSN` | Read access to Airflow metadata |
| `QUANT_AUTH_SECRET` | Session-cookie signing secret |
| `QUANT_AIRFLOW_BIN` | Airflow CLI used for workflow mutations |
| `QUANT_AIRFLOW_PYTHON` | Python used for task-level state operations |
| `AIRFLOW_HOME` | Airflow configuration and runtime directory |
| `QUANT_CORS_ORIGINS` | Comma-separated development origins |

Never commit real values. Native setup writes the root `.env`; Docker injects
the same settings from `.env.docker`.

## API Domains

All routes are aggregated in `app/api/__init__.py` under `/api/v1`.

| Domain | Responsibilities |
|---|---|
| health | shallow process health |
| auth | login, logout, current user and password management |
| market | price/volume series and latest-market views |
| research | runs, factor tests, IC, backtests and report data |
| reports | report history and generated artifacts |
| workflows | DAG list, graph, grid, runs, trigger, pause and task actions |
| rebalances | point-in-time portfolio rebalance views |
| data | controlled database inspection |
| ai | providers, conversations, attachments, RAG and analysis |
| services | allowlisted systemd autostart controls |

Authentication routes and `/health` are public. Other product routes share the
`require_user` dependency.

## Structure

```text
webapi/
├── app/
│   ├── ai/                  model providers, attachments and RAG
│   ├── api/v1/              domain routers and query layers
│   ├── reports/             report data, charts and rendering
│   ├── static/              generated frontend bundle in service mode
│   ├── errors.py            trace IDs and normalized errors
│   ├── main.py              FastAPI factory and static serving
│   └── security.py          password hashing and session tokens
├── tests/                   API and storage tests
├── pyproject.toml
└── uv.lock
```

Add a new domain by exposing an `APIRouter` below `app/api/v1/<domain>/` and
including it in `app/api/__init__.py`. Put database access in a small domain
query module instead of embedding SQL in route handlers.

## Airflow Integration

Read operations query the shared Airflow PostgreSQL metadata database. Mutating
operations use the Airflow CLI instead of writing metadata tables directly:

- pause/unpause and trigger use `airflow dags ...`;
- clear/mark-success/mark-failed use a small Airflow ORM helper;
- DAG and task identifiers are validated before execution;
- systemd service names are resolved through a fixed allowlist.

The Docker Web API image includes a separate, lockfile-backed root virtualenv
for the Airflow CLI. The lightweight local Web API virtualenv remains isolated.

## Static Frontend Mode

When `app/static/index.html` exists, FastAPI serves the production frontend and
API from the same origin:

```bash
cd ../frontend
npm ci && npm run build
cd ..
mkdir -p webapi/app/static
cp -r frontend/dist/. webapi/app/static/
```

API paths still return API errors; unmatched non-API paths fall back to the SPA
entry point.

## Testing

```bash
cd webapi
uv run pytest -q
```

The current baseline is 37 passing tests. The canonical contract is
[`../docs/api/openapi.yaml`](../docs/api/openapi.yaml); update the contract,
implementation, client types, and tests together when a response shape changes.
