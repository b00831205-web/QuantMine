# Research Results Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a database-backed research page that defaults to the latest run, filters IC and backtest results, expands one factor, and opens a factor detail route.

**Architecture:** Add a read-only FastAPI `research` domain next to `market`. It reads `research_runs`, `test_results`, and `backtest_metrics`; React owns the selected filters and selected factor and uses the existing HTTP, card, table, and async-state components.

**Tech Stack:** FastAPI, SQLAlchemy Core, PostgreSQL, pytest, React 18, TypeScript, React Router, Vitest, ECharts.

## Global Constraints

- Do not change the DAG, IC calculator, backtest algorithm, or database schema.
- Use `Depends(get_request_engine)`; no database URL may appear in OpenAPI query parameters.
- Default run is the largest `research_runs.run_id`.
- Empty result lists are HTTP 200. Unknown run ids are unified HTTP 404.
- The UI uses camelCase API contracts; SQL column names stay in backend-only code.
- v0.1 displays one run at a time and never compares runs side-by-side.

## File structure

| Path | Purpose |
|---|---|
| `webapi/app/api/v1/research/results.py` | Read-only research routes and focused SQLAlchemy queries. |
| `webapi/app/api/v1/research/__init__.py` | Research router package. |
| `webapi/app/schemas.py` | Pydantic research response models. |
| `webapi/tests/test_research_results.py` | Route contracts and empty/not-found cases. |
| `frontend/src/types/research.ts` | Matching TS contracts. |
| `frontend/src/api/client/research.ts` | Typed calls to research endpoints. |
| `frontend/src/pages/ResearchPage.tsx` | Filters, IC table, single-click selection, vertical sections. |
| `frontend/src/pages/FactorDetailPage.tsx` | Current-run detail route. |
| `frontend/src/router.tsx` | Detail route registration. |

---

### Task 1: Research API contracts and filter options

**Files:**
- Create: `webapi/app/api/v1/research/results.py`
- Create: `webapi/app/api/v1/research/__init__.py`
- Modify: `webapi/app/schemas.py`, `webapi/app/api/__init__.py`
- Test: `webapi/tests/test_research_results.py`

**Produces:** `GET /api/v1/research/options`, returning `defaultRunId`, `runs`, `variants`, `testIds`, `sampleScopes`.

- [ ] **Step 1: Write the failing route test**

```python
def test_research_options_defaults_to_latest_run(client, monkeypatch):
    monkeypatch.setattr(results, "fetch_research_run_options", lambda engine: [
        {"run_id": 7, "run_timestamp": datetime(2026, 7, 29, 10, 0)}
    ])
    body = client.get("/api/v1/research/options").json()
    assert body["defaultRunId"] == 7
    assert body["runs"][0] == {"runId": 7, "createdAt": "2026-07-29T10:00:00"}
```

- [ ] **Step 2: Verify it fails**

Run: `cd webapi && uv run pytest tests/test_research_results.py -q`

Expected: FAIL; research route is absent.

- [ ] **Step 3: Define models and route**

```python
class ResearchRunOption(BaseModel):
    run_id: int = Field(alias="runId")
    created_at: datetime = Field(alias="createdAt")
    model_config = {"populate_by_name": True}

class ResearchFilterOptions(BaseModel):
    default_run_id: int | None = Field(alias="defaultRunId")
    runs: list[ResearchRunOption]
    variants: list[str]
    test_ids: list[str] = Field(alias="testIds")
    sample_scopes: list[str] = Field(alias="sampleScopes")
    model_config = {"populate_by_name": True}
```

In `results.py`, reflect `research_runs`, order by `run_id.desc()`, and query distinct values from `test_results` for the latest run. Register the router in `api/__init__.py`.

- [ ] **Step 4: Verify the route**

Run: `cd webapi && uv run pytest tests/test_research_results.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webapi/app/schemas.py webapi/app/api webapi/tests/test_research_results.py
git commit -m "feat(api): add research filter options"
```

### Task 2: Filtered factor and backtest endpoints

**Files:**
- Modify: `webapi/app/api/v1/research/results.py`, `webapi/app/schemas.py`
- Modify: `webapi/tests/test_research_results.py`

**Produces:** `GET /api/v1/research/factors` and `GET /api/v1/research/backtest-metrics`.

- [ ] **Step 1: Write a failing factor filter test**

```python
def test_factor_results_returns_camel_case_rows(client, monkeypatch):
    monkeypatch.setattr(results, "fetch_factor_rows", lambda **_: ([
        {"factor_name": "mom", "period": 20, "variant_name": "raw",
         "test_id": "nw", "sample_scope": "train", "ic_mean": 0.04,
         "ic_std": 0.02, "ir": 2.0, "n": 100, "t_stat": 3.1,
         "p_value": 0.01, "significant": True, "bh_significant": True}
    ], 1))
    body = client.get("/api/v1/research/factors", params={"runId": 7}).json()
    assert body["items"][0]["factorName"] == "mom"
    assert body["items"][0]["bhSignificant"] is True
```

- [ ] **Step 2: Verify it fails**

Run: `cd webapi && uv run pytest tests/test_research_results.py::test_factor_results_returns_camel_case_rows -q`

Expected: FAIL with route missing.

- [ ] **Step 3: Implement exact filters**

Define `FactorResultRow` with `factorName, period, variantName, testId, sampleScope, icMean, icStd, ir, n, tStat, pValue, significant, bhSignificant` aliases. Route parameters are `runId` required and `variant, testId, sampleScope, factorName, period, page=1, pageSize=25` optional.

```python
conditions = [table.c.run_id == run_id]
if variant is not None:
    conditions.append(table.c.variant_name == variant)
if test_id is not None:
    conditions.append(table.c.test_id == test_id)
if sample_scope is not None:
    conditions.append(table.c.sample_scope == sample_scope)
statement = (select(table).where(*conditions)
    .order_by(table.c.bh_significant.desc(), table.c.p_value.asc(), table.c.factor_name)
    .limit(page_size).offset((page - 1) * page_size))
```

Use the same run/variant/test/factor/period filters for `backtest_metrics`; return its normalized metric rows without SQL pivoting.

- [ ] **Step 4: Test empty and missing runs**

```python
def test_unknown_run_is_not_found(client, monkeypatch):
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: False)
    assert client.get("/api/v1/research/factors", params={"runId": 999}).status_code == 404
```

Run: `cd webapi && uv run pytest tests/test_research_results.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webapi/app/api/v1/research/results.py webapi/app/schemas.py webapi/tests/test_research_results.py
git commit -m "feat(api): expose filtered research results"
```

### Task 3: Typed frontend client

**Files:**
- Modify: `frontend/src/types/research.ts`, `frontend/src/api/client/index.ts`
- Create: `frontend/src/api/client/research.ts`
- Test: `frontend/src/api/client/research.test.ts`

**Produces:** `fetchResearchOptions`, `fetchFactorResults`, `fetchBacktestMetrics`.

- [ ] **Step 1: Write a failing client test**

```tsx
it('sends the selected scope in camelCase', async () => {
  await fetchFactorResults({ runId: 7, sampleScope: 'train', page: 1, pageSize: 25 });
  expect(requestUrl.searchParams.get('sampleScope')).toBe('train');
});
```

- [ ] **Step 2: Verify it fails**

Run: `cd frontend && npm run test -- research.test.ts`

Expected: FAIL; research client is absent.

- [ ] **Step 3: Implement client signature**

```ts
export interface FactorResultsQuery {
  runId: number;
  variant?: string;
  testId?: string;
  sampleScope?: 'train' | 'test';
  factorName?: string;
  period?: number;
  page: number;
  pageSize: number;
}

export function fetchFactorResults(query: FactorResultsQuery, signal?: AbortSignal) {
  return http<FactorResultsPage>('/api/v1/research/factors', { query, signal });
}
```

Use the identical `http<T>(path, { query, signal })` pattern for options and backtest metrics; do not construct URL strings inside pages.

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run typecheck && npm run test -- research.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/research.ts frontend/src/api/client/research.ts frontend/src/api/client/index.ts frontend/src/api/client/research.test.ts
git commit -m "feat(frontend): add research API client"
```

### Task 4: Build vertical overview, selection, and detail route

**Files:**
- Modify: `frontend/src/pages/ResearchPage.tsx`, `frontend/src/router.tsx`
- Create: `frontend/src/pages/ResearchPage.module.css`, `frontend/src/pages/FactorDetailPage.tsx`, `frontend/src/pages/FactorDetailPage.module.css`
- Test: `frontend/src/pages/ResearchPage.test.tsx`, `frontend/src/pages/FactorDetailPage.test.tsx`

**Produces:** A latest-run default vertical research page; single-click expands a factor; double-click navigates to `/research/factors/:factorName`.

- [ ] **Step 1: Write the failing UI behavior test**

```tsx
it('selects on one click and navigates on double click', async () => {
  render(<MemoryRouter><ResearchPage /></MemoryRouter>);
  const row = await screen.findByText('mom');
  await userEvent.click(row);
  expect(screen.getByText('已选因子：mom / 20')).toBeInTheDocument();
  await userEvent.dblClick(row);
  expect(mockNavigate).toHaveBeenCalledWith(
    '/research/factors/mom?runId=7&variant=raw&testId=nw&sampleScope=train&period=20',
  );
});
```

- [ ] **Step 2: Verify it fails**

Run: `cd frontend && npm run test -- ResearchPage.test.tsx`

Expected: FAIL; page is a static placeholder.

- [ ] **Step 3: Implement UI state and effects**

```tsx
const [runId, setRunId] = useState<number | null>(null);
const [selected, setSelected] = useState<{ factorName: string; period: number } | null>(null);

useEffect(() => {
  fetchResearchOptions().then((options) => setRunId(options.defaultRunId));
}, []);

useEffect(() => {
  if (runId === null) return;
  const controller = new AbortController();
  fetchFactorResults({ runId, variant, testId, sampleScope, page, pageSize: 25 }, controller.signal);
  return () => controller.abort();
}, [runId, variant, testId, sampleScope, page]);
```

Render in this exact vertical order: filter card, IC/significance table, selected-factor expansion card, backtest metric card. Use `AsyncBoundary` around independently loaded data. On double click, use `useNavigate` and preserve `runId, variant, testId, sampleScope, period` in `URLSearchParams`.

- [ ] **Step 4: Implement the detail page**

Add route:

```tsx
{ path: 'research/factors/:factorName', element: <FactorDetailPage /> },
```

`FactorDetailPage` must read `factorName` with `useParams`, `runId` and `period` with `useSearchParams`, reject absent values with an empty state, and request only that factor for that one run. Its run selector reloads the same factor in the newly chosen run; it never renders two runs together.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npm run test && npm run typecheck && npm run build`

Expected: PASS.

```bash
git add frontend/src/pages/ResearchPage.tsx frontend/src/pages/ResearchPage.module.css frontend/src/pages/ResearchPage.test.tsx frontend/src/pages/FactorDetailPage.tsx frontend/src/pages/FactorDetailPage.module.css frontend/src/pages/FactorDetailPage.test.tsx frontend/src/router.tsx
git commit -m "feat(frontend): add research overview and factor detail"
```

## Self-review

- Latest-run default: Task 1.
- Filters and empty/not-found semantics: Tasks 1–2.
- Vertical IC then backtest layout: Task 4.
- Single-click expand and double-click detail: Task 4.
- Current-run-only detail with run switcher: Task 4.
- No schema/DAG/algorithm changes and no cross-run comparison: enforced by global constraints.
