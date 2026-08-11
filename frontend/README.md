# QUANTMINE Frontend

The QUANTMINE frontend is a React 18 and TypeScript application built with Vite.
It provides market monitoring, factor research, backtest exploration, reports,
AI-assisted analysis, data inspection, and Airflow workflow operations.

## Quick Start

Run the Web API on port 8000 first, then:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. The Vite development server proxies API requests
to the FastAPI service. Port 5173 is strict: if it is occupied, Vite exits
instead of silently switching to 5175 or 5176. The logon/production frontend is
served separately by FastAPI at <http://localhost:8000>.

## Commands

```bash
npm run dev          # Vite development server on 5173
npm test             # Vitest suite
npm run typecheck    # TypeScript project check
npm run lint         # ESLint with zero warnings allowed
npm run build        # production bundle in dist/
npm run preview      # preview the production bundle
```

Use `npm ci`, not `npm install`, for reproducible CI and release builds.

## Structure

```text
frontend/
├── public/                  static public assets and MSW worker
├── src/
│   ├── api/                 HTTP wrapper and typed domain clients
│   ├── components/
│   │   ├── ai/              AI workbench components
│   │   ├── chart/           reusable ECharts visualizations
│   │   ├── common/          loading, error, table and card primitives
│   │   └── layout/          app shell, navigation and top bar
│   ├── i18n/                English/Chinese localization
│   ├── pages/               route-level product screens
│   ├── styles/              tokens and global styles
│   ├── types/               shared TypeScript contracts
│   ├── main.tsx             application entry point
│   └── router.tsx           route definitions
├── package.json
└── vite.config.ts
```

## API and Authentication

All product APIs live under `/api/v1`. Authentication uses an HTTP-only session
cookie; browser requests must keep credentials enabled. Error responses share a
normalized envelope and include `x-trace-id` for diagnostics.

The authoritative API contract and error map are:

- [`../docs/api/openapi.yaml`](../docs/api/openapi.yaml)
- [`../docs/api/ERROR_MAP.md`](../docs/api/ERROR_MAP.md)

The Workflows screen reads DAG metadata through FastAPI and sends pause, trigger,
clear, mark-success, and mark-failed operations through the same API. It never
connects directly to Airflow from the browser.

## Development Conventions

- Keep server state in page/domain hooks rather than global UI components.
- Put endpoint-specific code under `src/api/client/`.
- Reuse common loading and error states through `AsyncBoundary`.
- Add user-facing strings to both locales.
- Add a test for navigation, request mapping, and meaningful UI state changes.
- Do not commit `node_modules/`, `dist/`, coverage, or local environment files.

Earlier design handoff and implementation notes remain under `../docs/frontend/`.
They are historical design references; the running application and tests are the
source of truth when they differ.

## Verification

```bash
npm test
npm run typecheck
npm run build
```

The current baseline is 38 passing frontend tests. Build output includes a known
large-chunk warning; code splitting is a future optimization, not a build error.
