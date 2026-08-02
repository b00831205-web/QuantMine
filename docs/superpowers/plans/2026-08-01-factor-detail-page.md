# Factor Detail Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shareable factor detail page with switchable research context, all-period statistics, selected-period IC history, and factor-specific backtest results.

**Architecture:** The Research table owns drill-down navigation and serializes its current row context into the URL. The detail page derives filter state from URL search parameters, reuses the existing research-statistics and backtest-summary endpoints, and calls a new artifact-backed IC-series endpoint for the selected period. Each request is independently cancellable to prevent stale results rendering after a filter switch.

**Tech Stack:** React 18, TypeScript, React Router, Vitest/Testing Library, FastAPI, Pydantic, SQLAlchemy, pandas/Parquet.

## Global Constraints

- Do not introduce a global state library; URL search parameters are the cross-page state contract.
- Preserve the existing camelCase frontend API contract.
- `testId` is not an input to IC-series because it does not alter raw IC observations.
- Empty IC artifact data is a normal empty response, not a 500 error.
- Each network effect uses an `AbortController` and ignores aborted responses.
- User writes production implementation; assistant supplies tests and reviews the results.

---

### Task 1: Serialize Research-row drill-down context

**Files:**
- Modify: `frontend/src/pages/ResearchPage.tsx`
- Modify: `frontend/src/pages/ResearchPage.test.tsx`

**Interfaces:**
- Consumes: `FactorResultRow` fields `factorName`, `period`, `variantName`, `testId`, `sampleScope` and current `activeRunId`.
- Produces: navigation to `/research/factors/:factorName?runId=...&variant=...&testId=...&sampleScope=...&period=...`.

- [ ] **Step 1: Write the failing navigation test**

```tsx
fireEvent.doubleClick(screen.getByText('TwentyDayAvgVol'));

expect(mockNavigate).toHaveBeenCalledWith(
  '/research/factors/TwentyDayAvgVol?runId=10&variant=legacy_tmp_raw&testId=legacy_tmp_bh&sampleScope=train&period=5',
);
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- src/pages/ResearchPage.test.tsx`

Expected: the navigation assertion fails because the current handler does not
serialize all six identity values.

- [ ] **Step 3: Implement the row double-click handler**

Use `encodeURIComponent(row.factorName)` for the path segment and
`URLSearchParams` for all query values. Do nothing when `activeRunId` is
`null`; otherwise call React Router's `navigate` with the generated path.

```ts
const handleRowDoubleClick = (row: FactorResultRow): void => {
  if (activeRunId === null) return;
  const search = new URLSearchParams({
    runId: String(activeRunId),
    variant: row.variantName,
    testId: row.testId,
    sampleScope: row.sampleScope,
    period: String(row.period),
  });
  navigate(`/research/factors/${encodeURIComponent(row.factorName)}?${search}`);
};
```

- [ ] **Step 4: Attach the handler to table rows**

Extend the existing `PaginatedTable` row API only if it does not already
accept `onRowDoubleClick`. Pass the handler from `ResearchPage` so a double
click, not a single click, changes page.

- [ ] **Step 5: Run the focused test and typecheck**

Run: `npm test -- src/pages/ResearchPage.test.tsx && npm run typecheck`

Expected: PASS; one double-click generates the exact URL above.

### Task 2: Add artifact-backed IC-series backend endpoint

**Files:**
- Create: `webapi/app/api/v1/research/ic_series.py`
- Modify: `webapi/app/schemas.py`
- Modify: `webapi/app/api/__init__.py`
- Create: `webapi/tests/test_ic_series.py`

**Interfaces:**
- Consumes: `runId: int`, `variant: str`, `sampleScope: str`, `factorName: str`, `period: int`.
- Produces: `GET /api/v1/research/ic-series` returning `SeriesResponse`-compatible JSON with `baseDate: date | null` and one `IC` series.

- [ ] **Step 1: Write pure conversion tests**

Test a small IC dataframe converted to the response shape:

```py
frame = pd.DataFrame(
    {('momentum', 5): [0.01, -0.02]},
    index=pd.to_datetime(['2024-01-02', '2024-01-03']),
)
assert build_ic_series(frame, factor_name='momentum', period=5) == (
    date(2024, 1, 2),
    [{'symbol': 'IC', 'points': [
        {'date': date(2024, 1, 2), 'value': 0.01},
        {'date': date(2024, 1, 3), 'value': -0.02},
    ]}],
)
```

Also test missing factor/period returns `(None, [])`.

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest webapi/tests/test_ic_series.py -q`

Expected: collection error because `ic_series.py` and `build_ic_series` do not
yet exist.

- [ ] **Step 3: Implement artifact lookup and pure conversion**

Read the registered `ic_artifacts` manifest for `(run_id, variant_name,
sample_scope)`, load the `cs_ic` entry through the existing IC artifact loader
helpers, then implement `build_ic_series`. Accept either a MultiIndex
`(factor, period)` column or the project’s current IC dataframe representation;
normalize the selected observations to date/value points without changing their
numeric values.

- [ ] **Step 4: Add the route and response schema**

Use these query declarations:

```py
run_id: int = Query(..., alias='runId')
variant: str = Query(...)
sample_scope: str = Query(..., alias='sampleScope')
factor_name: str = Query(..., alias='factorName')
period: int = Query(..., ge=1)
engine: Engine = Depends(get_request_engine)
```

Check `research_run_exists`; return `404` for an unknown run and an empty
`SeriesResponse(baseDate=None, series=[])` for absent artifact data.

- [ ] **Step 5: Add route tests**

Mock the artifact reader and assert the route maps camelCase query fields,
returns 200 with the IC points, returns 404 for an unknown run, and returns
`{"baseDate": null, "series": []}` for no matching period.

- [ ] **Step 6: Run backend verification**

Run: `uv run pytest webapi/tests/test_ic_series.py webapi/tests/test_research_results.py -q`

Expected: PASS.

### Task 3: Add typed frontend IC-series client

**Files:**
- Modify: `frontend/src/types/research.ts`
- Modify: `frontend/src/api/client/research.ts`
- Modify: `frontend/src/api/client/index.ts`
- Modify: `frontend/src/api/client/research.test.ts`

**Interfaces:**
- Produces:

```ts
export interface IcSeriesQuery {
  runId: number;
  variant: string;
  sampleScope: 'train' | 'test';
  factorName: string;
  period: number;
}

export function fetchIcSeries(
  query: IcSeriesQuery,
  signal?: AbortSignal,
): Promise<SeriesResponse>;
```

- [ ] **Step 1: Write a client serialization test**

```ts
await fetchIcSeries({
  runId: 10, variant: 'raw', sampleScope: 'train',
  factorName: 'momentum_20d', period: 5,
});
expect(requestedUrl.pathname).toBe('/api/v1/research/ic-series');
expect(requestedUrl.searchParams.get('sampleScope')).toBe('train');
expect(requestedUrl.searchParams.get('period')).toBe('5');
```

- [ ] **Step 2: Run it and verify it fails**

Run: `npm test -- src/api/client/research.test.ts`

Expected: `fetchIcSeries is not a function`.

- [ ] **Step 3: Add types, client wrapper, and barrel export**

Call `http<SeriesResponse>('/api/v1/research/ic-series', { query: {...}, signal })`.
Keep optional properties out of this query: every IC identity field is required.

- [ ] **Step 4: Run client verification**

Run: `npm test -- src/api/client/research.test.ts && npm run typecheck`

Expected: PASS.

### Task 4: Replace the FactorDetailPage placeholder with URL-driven data

**Files:**
- Modify: `frontend/src/pages/FactorDetailPage.tsx`
- Modify: `frontend/src/pages/FactorDetailPage.module.css`
- Create: `frontend/src/pages/FactorDetailPage.test.tsx`

**Interfaces:**
- Consumes: `fetchResearchOptions`, `fetchFactorResults`, `fetchBacktestSummaries`, `fetchIcSeries`, `SeriesChart`, and URL parameters from Task 1.
- Produces: a working `/research/factors/:factorName` page.

- [ ] **Step 1: Write the initial-load page test**

Mock all four clients. Render:

```tsx
<MemoryRouter initialEntries={[
  '/research/factors/momentum_20d?runId=10&variant=raw&testId=newey_raw&sampleScope=train&period=5',
]}>
  <Routes><Route path='/research/factors/:factorName' element={<FactorDetailPage />} /></Routes>
</MemoryRouter>
```

Assert that factor results receive `factorName: 'momentum_20d'`, IC series
receives period `5`, every returned period tab appears, and `5天` is selected.

- [ ] **Step 2: Run it and verify it fails**

Run: `npm test -- src/pages/FactorDetailPage.test.tsx`

Expected: FAIL because the current page uses placeholder state and no clients.

- [ ] **Step 3: Replace legacy types and placeholder states**

Use the current `FactorResultRow` and `BacktestSummaryCard` types rather than
the obsolete `ResearchRun`, `TestSummary`, and `BacktestSummary` definitions.
Use `useSearchParams` to read/write `runId`, `variant`, `testId`,
`sampleScope`, and `period`.

- [ ] **Step 4: Implement the options effect**

On initial render and run changes, call `fetchResearchOptions(runId)`. If a
new run is selected, clear `variant`, `testId`, and `sampleScope` before
applying its returned options. If no run exists, render empty states rather
than attempting factor or IC requests.

- [ ] **Step 5: Implement factor, backtest, and IC effects**

When all required identity values exist:

1. fetch factor rows for the selected context with page size 100;
2. fetch factor-specific backtest cards;
3. fetch selected-period IC points.

Each effect creates an `AbortController`, sets `loading`, ignores an aborted
success response, normalizes non-HTTP failures to the project `ApiError`
shape, and returns `() => controller.abort()`.

- [ ] **Step 6: Render selectors, period tabs, comparison table, and chart**

Render the four selectors from run-specific options. Derive sorted unique
periods from factor rows. A period tab updates only `period` in search params.
Use `SeriesChart` inside `AsyncBoundary` for the IC result; use the exact
empty copy `暂无 IC 时序数据` for empty series. Render all factor rows in the
comparison table and apply a selected-row CSS class where `row.period ===
selectedPeriod`.

- [ ] **Step 7: Render factor-specific backtest cards**

Reuse the card metric presentation from `ResearchPage` but query with
`factorName`; retain its net-value curve button and full identity. Do not use
the stale `turnover` or `netReturn` fields from the old skeleton.

- [ ] **Step 8: Add state-transition tests**

Add tests for selecting a different period (only IC query period changes) and
selecting a different run (run-specific options replace old options and
variant/test/scope controls reset).

- [ ] **Step 9: Run frontend verification**

Run: `npm test -- src/pages/FactorDetailPage.test.tsx src/pages/ResearchPage.test.tsx && npm run typecheck`

Expected: PASS.

### Task 5: End-to-end manual verification

**Files:**
- No source changes required unless a defect is found.

**Interfaces:**
- Consumes: Tasks 1–4 and a database run containing IC artifacts and backtest data.
- Produces: manual confirmation of the drill-down workflow.

- [ ] **Step 1: Start backend and frontend development servers**

Run the existing web API on port 8000 and Vite frontend on port 5173 using the
project’s established `.env` database configuration.

- [ ] **Step 2: Verify navigation and initial context**

Open Research, choose a populated run, double-click a factor row, and confirm
the URL carries the selected `runId`, `variant`, `testId`, `sampleScope`, and
`period`.

- [ ] **Step 3: Verify dynamic controls**

Switch period and confirm a new `ic-series` request has only the period
changed. Switch research run and confirm stale selector values clear before
the new run’s options render.

- [ ] **Step 4: Verify empty behavior**

Choose a context without an IC artifact and confirm the page reads `暂无 IC
时序数据`, not an internal-server error or endless spinner.

- [ ] **Step 5: Run the affected full suites**

Run:

```bash
cd webapi
uv run pytest tests/test_research_results.py tests/test_ic_series.py -q

cd ../frontend
npm test -- src/api/client/research.test.ts src/pages/ResearchPage.test.tsx src/pages/FactorDetailPage.test.tsx
npm run typecheck
```

Expected: all tests and type checking pass.
