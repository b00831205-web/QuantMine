# Backtest Summary API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render persisted backtest metrics for the selected research run as compact factor-period summary cards.

**Architecture:** The FastAPI route validates a run and delegates long-table aggregation to a storage helper. The frontend client serializes active research filters, while the Research page owns loading, cancellation, and display state.

**Tech Stack:** FastAPI, SQLAlchemy Core, PostgreSQL, Pydantic, React, TypeScript, Vitest.

## Global Constraints

- Preserve `quantmine_web` as a read-only API user for normal application reads.
- Do not read Parquet artifacts or add sensitivity-test behavior in this feature.
- Treat missing stored metrics as absent/null, never as numeric zero.
- User writes production code; assistant supplies tests and user runs them.

---

### Task 1: Backtest summary storage and API response

**Files:**
- Modify: `webapi/app/api/v1/research/results.py`
- Modify: `webapi/app/schemas.py`
- Test: `webapi/tests/test_research_results.py`

**Interfaces:**
- Consumes: `backtest_metrics` long rows keyed by run/variant/backtest/test/factor/period/quantile/metric.
- Produces: `fetch_backtest_summary_rows(engine, *, run_id, variant, test_id, factor_name, period, page, page_size) -> tuple[list[dict], int]` and `GET /research/backtest-summaries`.

- [ ] **Step 1: Write failing API tests**

```python
def test_backtest_summaries_returns_cards_for_a_known_run(client, monkeypatch):
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: True)
    monkeypatch.setattr(
        results,
        "fetch_backtest_summary_rows",
        lambda engine, **kwargs: ([{
            "variant_name": "raw", "backtest_id": "raw_test",
            "test_id": "newey_raw", "factor_name": "toy", "period": 5,
            "quantile_yearly_returns": {"Q1": -0.02, "long_short": 0.10},
            "sharpe": 1.2, "max_drawdown": -0.08, "win_rate": 0.55,
        }], 1),
    )
    response = client.get("/api/v1/research/backtest-summaries?runId=42")
    assert response.status_code == 200
    assert response.json()["items"][0]["quantileYearlyReturns"]["longShort"] == 0.10
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_research_results.py -q`

Expected: route does not exist or summary response model is missing.

- [ ] **Step 3: Add Pydantic response models and route**

```python
@router.get("/research/backtest-summaries", response_model=BacktestSummaryResponse)
async def get_backtest_summaries(
    run_id: int = Query(..., alias="runId"),
    variant: str | None = None,
    test_id: str | None = Query(None, alias="testId"),
    factor_name: str | None = Query(None, alias="factorName"),
    period: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, alias="pageSize", ge=1, le=100),
    engine: Engine = Depends(get_request_engine),
) -> BacktestSummaryResponse:
    ...
```

- [ ] **Step 4: Run the backend tests to verify they pass**

Run: `uv run pytest tests/test_research_results.py tests/test_research_storage.py -q`

Expected: PASS.

### Task 2: Frontend API client and active-run data effect

**Files:**
- Modify: `frontend/src/types/research.ts`
- Modify: `frontend/src/api/client/research.ts`
- Modify: `frontend/src/pages/ResearchPage.tsx`
- Test: `frontend/src/api/client/research.test.ts`
- Test: `frontend/src/pages/ResearchPage.test.tsx`

**Interfaces:**
- Consumes: `BacktestSummaryResponse` from `/api/v1/research/backtest-summaries`.
- Produces: `fetchBacktestSummaries(query, signal?)` and populated `btState` in `ResearchPage`.

- [ ] **Step 1: Write failing client and page tests**

```ts
expect(requestedUrl.searchParams.get('runId')).toBe('42');
expect(requestedUrl.searchParams.get('variant')).toBe('raw');
expect(apiMocks.fetchBacktestSummaries).toHaveBeenCalledWith(
  expect.objectContaining({ runId: 42 }),
  expect.any(AbortSignal),
);
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run: `npm test -- src/api/client/research.test.ts src/pages/ResearchPage.test.tsx`

Expected: `fetchBacktestSummaries` does not exist.

- [ ] **Step 3: Add client function and loading effect**

```ts
useEffect(() => {
  if (activeRunId === null) {
    setBtState({ status: 'success', data: EMPTY_BT });
    return;
  }
  const controller = new AbortController();
  setBtState({ status: 'loading' });
  fetchBacktestSummaries({ runId: activeRunId, ...(variant ? { variant } : {}) }, controller.signal)
    .then((data) => !controller.signal.aborted && setBtState({ status: 'success', data }))
    .catch(/* reuse the existing HttpError and AbortError branches */);
  return () => controller.abort();
}, [activeRunId, variant, testId]);
```

- [ ] **Step 4: Run frontend verification**

Run: `npm test -- src/api/client/research.test.ts src/pages/ResearchPage.test.tsx && npm run typecheck`

Expected: PASS.
