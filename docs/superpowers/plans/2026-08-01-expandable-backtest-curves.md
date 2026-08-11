# Expandable Backtest Net-Value Curves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user expand one backtest summary card on the Research page and inspect its Q1–Qn and Long-Short cumulative net-value curves, while keeping the card values aligned.

**Architecture:** Backtest summary cards continue to come from `backtest_metrics`; chart data comes from date-level returns in `backtest_results`, compounded by a dedicated FastAPI read endpoint. The legacy importer fills `backtest_results` from legacy date-indexed parquet files, while the existing workflow already writes current-run return rows. The React page owns the expanded-card key and the abortable chart request; `BacktestSection` only renders supplied state.

**Tech Stack:** Python 3.13, pandas, SQLAlchemy, PostgreSQL, FastAPI/Pydantic, React, TypeScript, Vitest, React Testing Library, ECharts, CSS Modules.

## Global Constraints

- Do not alter factor selection or backtest calculation logic.
- Keep `backtest_metrics` as the source for summary cards and `backtest_results` as the source for time-series returns.
- Return a successful empty chart payload when a valid card has no stored return rows.
- Preserve the existing unified FastAPI error handling for unknown runs and invalid input.
- Reuse `SeriesChart`; do not add a charting dependency.
- Do not commit or stage files unless the user explicitly asks.

---

## File structure and responsibilities

- `scripts/import_legacy_tmp_backtest_metrics.py`: discover and import legacy date-level backtest returns in addition to summary metrics.
- `test/test_legacy_backtest_import.py`: proves legacy return parquet discovery and conversion.
- `webapi/app/api/v1/research/backtest_series.py`: isolated SQLAlchemy read helper plus the backtest-series route.
- `webapi/app/api/__init__.py`: registers the new research route.
- `webapi/app/schemas.py`: owns the specific nullable-base-date response model.
- `webapi/tests/test_research_results.py`: route-level API contract tests.
- `webapi/tests/test_research_storage.py`: helper-level compounding and empty-result tests.
- `frontend/src/types/research.ts`: request/response types for backtest curves.
- `frontend/src/api/client/research.ts`: typed frontend request client.
- `frontend/src/api/client/research.test.ts`: query serialization test.
- `frontend/src/pages/ResearchPage.tsx`: expanded-card state, abortable curve request, and rendering composition.
- `frontend/src/pages/ResearchPage.module.css`: card alignment and expanded curve styles.
- `frontend/src/pages/ResearchPage.test.tsx`: user-level expansion/collapse/request tests.

### Task 1: Extend the legacy importer to persist date-level return rows

**Files:**
- Modify: `scripts/import_legacy_tmp_backtest_metrics.py`
- Modify: `test/test_legacy_backtest_import.py`

**Consumes:** Legacy files matching `tmp/back_test/backtest_<factor_name>_<period>daysholdingperiod.parquet`, each containing a date index and Q1–Qn/`long_short` return columns.

**Produces:**
- `discover_legacy_backtest_return_cases(backtest_dir: Path) -> list[dict]`
- `build_all_legacy_backtest_result_rows(...) -> pd.DataFrame`
- `main()` saves both metric rows and result rows through `save_backtest_metrics` and `save_backtest_results`.

- [ ] **Step 1: Write a failing discovery test**

  Add a temporary `backtest_Momentum_5daysholdingperiod.parquet` with a date
  index and `Q1`, `Q5`, `long_short` columns. Assert discovery returns one
  case with `factor_name == "Momentum"`, `period == 5`, and its source path.

  ```python
  def test_discover_legacy_backtest_return_cases_reads_factor_and_period(tmp_path):
      frame = pd.DataFrame({"Q1": [0.01], "Q5": [0.02], "long_short": [0.01]},
                           index=pd.to_datetime(["2024-01-02"]))
      path = tmp_path / "backtest_Momentum_5daysholdingperiod.parquet"
      frame.to_parquet(path)

      assert discover_legacy_backtest_return_cases(tmp_path) == [{
          "factor_name": "Momentum", "period": 5, "path": path,
      }]
  ```

- [ ] **Step 2: Run the discovery test and verify it fails**

  Run: `.venv/bin/python -m pytest test/test_legacy_backtest_import.py -q`

  Expected: failure because `discover_legacy_backtest_return_cases` does not
  exist.

- [ ] **Step 3: Implement filename discovery**

  Add a separate compiled regular expression. Use `Path.name` and
  `fullmatch`, not string splitting, so factor names containing underscores
  remain intact.

  ```python
  RETURN_FILE_PATTERN = re.compile(
      r"backtest_(?P<factor_name>.+)_(?P<period>\d+)daysholdingperiod\.parquet$"
  )

  def discover_legacy_backtest_return_cases(backtest_dir: Path) -> list[dict]:
      cases = []
      for path in sorted(backtest_dir.glob("backtest_*daysholdingperiod.parquet")):
          match = RETURN_FILE_PATTERN.fullmatch(path.name)
          if match is not None:
              cases.append({"factor_name": match["factor_name"],
                            "period": int(match["period"]), "path": path})
      return cases
  ```

- [ ] **Step 4: Write a failing conversion test**

  Build two discovered frames and assert that
  `build_all_legacy_backtest_result_rows` produces the standard
  `backtest_results` long columns, with Q1 rank 1 and `long_short` rank 0.

  ```python
  assert set(rows["quantile_rank"]) == {0, 1, 5}
  assert set(rows["trade_date"]) == {date(2024, 1, 2)}
  assert rows.loc[rows["quantile_rank"].eq(0), "return_value"].item() == 0.01
  ```

- [ ] **Step 5: Implement conversion through the existing storage boundary**

  Read every discovered parquet into `all_results[(factor_name, period)]`, then
  delegate to `quantmine.storage.backtest.build_backtest_rows`. Do not duplicate
  its melt or quantile-rank logic.

  ```python
  def build_all_legacy_backtest_result_rows(...):
      all_results = {
          (case["factor_name"], case["period"]): pd.read_parquet(case["path"])
          for case in discover_legacy_backtest_return_cases(backtest_dir)
      }
      return build_backtest_rows(all_results, run_id=run_id,
                                 variant_name=variant_name,
                                 backtest_id=backtest_id, test_id=test_id)
  ```

- [ ] **Step 6: Extend the `main()` test before changing `main()`**

  Update the existing main test to monkeypatch both builder functions and
  `save_backtest_results`, then assert it receives the parsed run identity and
  result dataframe once.

- [ ] **Step 7: Save both datasets in `main()`**

  Build the return rows using the same CLI identity fields as metric rows and
  call `save_backtest_results(engine, result_rows)` before saving metrics. Print
  both saved counts so a manual legacy import is auditable.

- [ ] **Step 8: Run importer tests**

  Run: `.venv/bin/python -m pytest test/test_legacy_backtest_import.py -q`

  Expected: all legacy metric and return-import tests pass.

### Task 2: Add a focused backtest-series backend endpoint

**Files:**
- Create: `webapi/app/api/v1/research/backtest_series.py`
- Modify: `webapi/app/api/__init__.py`
- Modify: `webapi/app/schemas.py`
- Modify: `webapi/tests/test_research_results.py`
- Create or modify: `webapi/tests/test_research_storage.py`

**Consumes:** Full card identity: `(run_id, variant, backtest_id, test_id,
factor_name, period)` and `backtest_results.return_value` rows.

**Produces:**
- `BacktestSeriesResponse(baseDate: date | None, series: list[SeriesEntry])`
- `build_backtest_net_value_series(rows: list[dict]) -> dict`
- `GET /api/v1/research/backtest-series`

- [ ] **Step 1: Write a failing compounding-helper test**

  Supply chronological return rows for Q1 and rank 0:

  ```python
  rows = [
      {"trade_date": date(2024, 1, 2), "quantile_rank": 1, "return_value": 0.01},
      {"trade_date": date(2024, 1, 3), "quantile_rank": 1, "return_value": 0.02},
      {"trade_date": date(2024, 1, 2), "quantile_rank": 0, "return_value": -0.01},
  ]
  result = build_backtest_net_value_series(rows)
  assert result["base_date"] == date(2024, 1, 2)
  assert result["series"][0]["symbol"] == "Long-Short"
  assert result["series"][1]["points"][-1]["value"] == pytest.approx(103.02)
  ```

- [ ] **Step 2: Run the helper test and verify it fails**

  Run: `cd webapi && uv run pytest tests/test_research_storage.py -q`

  Expected: import failure for the missing helper module/function.

- [ ] **Step 3: Define the nullable response model**

  In `webapi/app/schemas.py`, add a dedicated model rather than loosening the
  market-series contract:

  ```python
  class BacktestSeriesResponse(BaseModel):
      base_date: date | None = Field(alias="baseDate")
      series: list[SeriesEntry]
      model_config = {"populate_by_name": True}
  ```

- [ ] **Step 4: Implement return-row lookup and compounding**

  In `backtest_series.py`, reflect `backtest_results`, filter on every identity
  field, and order by `trade_date.asc(), quantile_rank.asc()`. Group values by
  rank, skip null returns, compound `value = prior_value * (1 + return_value)`
  beginning from 100. Map rank 0 to `Long-Short` and other ranks to `Q{rank}`.
  Sort output with Long-Short first and numeric Q ranks after it. Empty input
  returns `{base_date: None, series: []}`.

- [ ] **Step 5: Run helper tests**

  Run: `cd webapi && uv run pytest tests/test_research_storage.py -q`

  Expected: compounding, rank naming, and empty-input tests pass.

- [ ] **Step 6: Write failing route tests**

  Monkeypatch `research_run_exists` and the row lookup helper. Verify:

  ```python
  response = client.get("/api/v1/research/backtest-series", params={
      "runId": 42, "variant": "raw", "backtestId": "raw_test",
      "testId": "newey_raw", "factorName": "momentum_20d", "period": 5,
  })
  assert response.status_code == 200
  assert response.json()["series"][0]["symbol"] == "Long-Short"
  ```

  Add tests for unknown run (`404`) and known run with no rows (`200`, null
  `baseDate`, empty `series`).

- [ ] **Step 7: Implement and register the route**

  Use `Query(..., alias=...)` for camel-case fields and
  `Depends(get_request_engine)` for the database engine. Import its router in
  `webapi/app/api/__init__.py` under the same `/api/v1` router composition used
  by the existing research results router.

- [ ] **Step 8: Run backend research tests**

  Run: `cd webapi && uv run pytest tests/test_research_results.py tests/test_research_storage.py -q`

  Expected: existing options/factors/summary tests and new curve tests pass.

### Task 3: Add frontend curve API types and client contract

**Files:**
- Modify: `frontend/src/types/research.ts`
- Modify: `frontend/src/api/client/research.ts`
- Modify: `frontend/src/api/client/index.ts`
- Modify: `frontend/src/api/client/research.test.ts`

**Consumes:** `GET /api/v1/research/backtest-series` contract from Task 2.

**Produces:**
- `BacktestSeriesQuery`
- `BacktestSeriesResponse`
- `fetchBacktestSeries(query, signal?)`

- [ ] **Step 1: Write a failing client serialization test**

  Assert the client requests the exact endpoint and includes every identity
  query parameter:

  ```ts
  await fetchBacktestSeries({
    runId: 42, variant: 'raw', backtestId: 'raw_test', testId: 'newey_raw',
    factorName: 'momentum_20d', period: 5,
  });
  expect(requestedUrl.searchParams.get('backtestId')).toBe('raw_test');
  expect(requestedUrl.searchParams.get('period')).toBe('5');
  ```

- [ ] **Step 2: Run the client test and verify it fails**

  Run: `cd frontend && npm test -- src/api/client/research.test.ts`

  Expected: `fetchBacktestSeries is not a function`.

- [ ] **Step 3: Define types and client call**

  Reuse the existing market `SeriesEntry` shape or define its structurally
  identical local response shape. Keep the nullable base date explicit:

  ```ts
  export interface BacktestSeriesResponse {
    baseDate: string | null;
    series: Array<{ symbol: string; points: Array<{ date: string; value: number }> }>;
  }

  export function fetchBacktestSeries(query: BacktestSeriesQuery, signal?: AbortSignal) {
    return http<BacktestSeriesResponse>('/api/v1/research/backtest-series', { query, signal });
  }
  ```

- [ ] **Step 4: Export and verify**

  Re-export from `frontend/src/api/client/index.ts`, then run:

  `cd frontend && npm test -- src/api/client/research.test.ts && npm run typecheck`

  Expected: client test and TypeScript check pass.

### Task 4: Add expandable card state and curve rendering

**Files:**
- Modify: `frontend/src/pages/ResearchPage.tsx`
- Modify: `frontend/src/pages/ResearchPage.test.tsx`

**Consumes:** `BacktestSummaryCard`, `fetchBacktestSeries`, `SeriesChart`, and
the existing `AsyncBoundary` component.

**Produces:** One-card-at-a-time curve expansion that is reset on relevant
filter changes and safely cancels stale requests.

- [ ] **Step 1: Write a failing page interaction test**

  Mock one summary card and a resolved curve response. Render the page, click
  the visible `查看净值曲线` button, and assert the client receives its full
  identity and the chart legend contains `Long-Short`. Click the button again
  and assert the chart panel disappears.

- [ ] **Step 2: Run the page test and verify it fails**

  Run: `cd frontend && npm test -- src/pages/ResearchPage.test.tsx`

  Expected: button is not found.

- [ ] **Step 3: Add local key and async state**

  Add a typed key that includes all required route identity fields, plus:

  ```ts
  const [expandedBacktest, setExpandedBacktest] = useState<BacktestSeriesQuery | null>(null);
  const [curveState, setCurveState] = useState<AsyncState<BacktestSeriesResponse>>({ status: 'idle' });
  ```

  The card key must include `backtestId` and `testId`, not only factor and
  period, because those values can differ inside one run.

- [ ] **Step 4: Implement the abortable curve effect**

  When no card is expanded, set the curve state back to idle and do not make a
  request. Otherwise create an `AbortController`, set loading, request the
  selected curve, ignore `AbortError`, map `HttpError` to the existing API
  error state, and abort in the effect cleanup.

- [ ] **Step 5: Reset on context changes**

  In the effects or change handlers already responsible for new run/variant/test
  data, set `expandedBacktest` to `null`. This must happen when changing run,
  variant, or test ID so no old curve remains expanded below new cards.

- [ ] **Step 6: Refactor `BacktestSection` into a presentational surface**

  Pass it `items`, `expandedBacktest`, `curveState`, and `onToggleCurve`.
  `BtMetricCard` receives an `isExpanded` boolean and button callback. Render
  a full-width panel *after* the metric-card grid only when expanded, using
  `AsyncBoundary` around `SeriesChart`.

  ```tsx
  <button type="button" onClick={() => onToggleCurve(key)}>
    {isExpanded ? '收起净值曲线' : '查看净值曲线'}
  </button>
  ```

  For a successful empty response, pass an `isEmpty` predicate checking
  `data.series.length === 0` and use the copy `该回测未保存净值曲线`.

- [ ] **Step 7: Extend page tests**

  Add assertions that opening a second card replaces the first request/panel,
  and that changing a variant or test ID collapses the current curve. Mock
  `fetchBacktestSeries` so tests remain independent of a live server.

- [ ] **Step 8: Run frontend page verification**

  Run: `cd frontend && npm test -- src/pages/ResearchPage.test.tsx && npm run typecheck`

  Expected: all page tests and the TypeScript check pass.

### Task 5: Align cards and style the expanded chart

**Files:**
- Modify: `frontend/src/pages/ResearchPage.module.css`
- Modify: `frontend/src/pages/ResearchPage.test.tsx` only if accessibility labels are added.

**Consumes:** Existing card class names plus new curve-control and chart-panel
class names from Task 4.

**Produces:** Desktop card layout with no wrapped Q5 metric and a clear,
full-width selected curve area.

- [ ] **Step 1: Make the desktop metric rows deterministic**

  Replace the flex-wrapped return row and auto-fit stat grid with fixed grids:

  ```css
  .btQuantileRow { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .btStatGrid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .btQuantile { min-width: 0; }
  ```

- [ ] **Step 2: Add responsive fallback**

  At a narrow-screen breakpoint, reduce the quantile grid to three columns and
  the statistics grid to two columns. Do not use horizontal overflow for
  summary values.

- [ ] **Step 3: Style control and expanded panel**

  Give the card control a visible outline/focus state. Put the selected curve
  panel below `.btMetricsRow`, add a subtle top border and label, and preserve
  the dashboard's existing dark colour tokens. Keep chart height at 300–360px.

- [ ] **Step 4: Run checks and visually inspect**

  Run: `cd frontend && npm run typecheck && npm test -- src/pages/ResearchPage.test.tsx`

  Then open the Research page at desktop width; verify Q5 remains on the first
  row and opening/collapsing a card does not shift other cards unpredictably.

### Task 6: End-to-end local verification and legacy data backfill

**Files:**
- No source change required unless prior checks reveal a defect.

**Consumes:** Completed Tasks 1–5 and existing local database configuration.

**Produces:** A manually verifiable Run 10 with summary cards and a curve.

- [ ] **Step 1: Run focused Python tests**

  Run:

  ```bash
  .venv/bin/python -m pytest test/test_legacy_backtest_import.py -q
  cd webapi && uv run pytest tests/test_research_results.py tests/test_research_storage.py -q
  ```

  Expected: all focused backend/import tests pass.

- [ ] **Step 2: Run focused frontend tests**

  Run:

  ```bash
  cd frontend
  npm test -- src/api/client/research.test.ts src/pages/ResearchPage.test.tsx
  npm run typecheck
  ```

  Expected: all tests pass and TypeScript reports no errors.

- [ ] **Step 3: Import legacy Run 10 return rows**

  Run the extended importer with the existing Run 10 identity. Confirm its
  output reports a nonzero `result_rows` count and that re-running it is safe
  because `save_backtest_results` upserts its unique key.

- [ ] **Step 4: Verify the live page**

  Start the API and frontend with the project’s existing development commands.
  On Research Run 10, select `legacy_tmp_raw` / `legacy_tmp_bh`, click the
  TwentyDayAvgVol 5-day card's curve control, and confirm Q1–Q5 and Long-Short
  lines render. Switch variant or run and confirm the chart closes.
