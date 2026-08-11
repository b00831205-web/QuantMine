# Research Filter Options by Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the Variant, Test ID, and Sample Scope choices on the research page always come from the currently selected research run.

**Architecture:** Keep one small `ResearchFilterOptions` response shape. The backend accepts an optional `runId`: omitted means newest run, supplied means that run's filter values. The frontend first loads the run list, then refreshes a separate filter-options state whenever the selected run changes, clears stale selections, and finally loads factor rows.

**Tech Stack:** FastAPI, SQLAlchemy Core, PostgreSQL-compatible storage readers, pytest, React, TypeScript, Vitest, Testing Library.

## Global Constraints

- Keep the existing `ResearchFilterOptions` JSON field names: `defaultRunId`, `runs`, `variants`, `testIds`, and `sampleScopes`.
- Keep existing unified FastAPI error handling; an unknown run must be HTTP 404.
- Keep `exactOptionalPropertyTypes` enabled in the frontend; do not explicitly assign `undefined` to an optional property unless its type permits it.
- Use the current `HttpError` / `AsyncState` error conventions.
- Do not add a filters-for-all-runs payload or a new database table.
- Tests are written by the assistant; production logic is implemented by the user.

---

## File structure

- Modify `webapi/app/api/v1/research/results.py`: accept `runId`, select the intended run, and retain the existing response schema.
- Modify `webapi/tests/test_research_results.py`: cover explicit-run and missing-run API behavior through monkeypatched storage readers.
- Modify `frontend/src/api/client/research.ts`: expose optional `runId` and `AbortSignal` arguments for the existing options endpoint.
- Modify `frontend/src/api/client/research.test.ts`: verify query serialization when `runId` is provided and omitted.
- Modify `frontend/src/pages/ResearchPage.tsx`: keep run-list state distinct from filter-options state; refresh and reset filters after run changes.
- Modify `frontend/src/pages/ResearchPage.test.tsx`: verify run switching triggers the correct API call and clears prior selections.

### Task 1: Backend options endpoint chooses a requested run

**Files:**
- Modify: `webapi/app/api/v1/research/results.py`
- Test: `webapi/tests/test_research_results.py`

**Interfaces:**
- Consumes: `fetch_research_runs(engine) -> list[dict]`, `fetch_research_filter_values(engine, run_id) -> dict`, `research_run_exists(engine, run_id) -> bool`.
- Produces: `GET /api/v1/research/options?runId=<int>` returning `ResearchFilterOptions`.

- [ ] **Step 1: Write the failing tests**

```python
def test_research_options_uses_requested_run_for_filter_values(client, monkeypatch):
    monkeypatch.setattr(results, "fetch_research_runs", lambda engine: [
        {"run_id": 42, "run_timestamp": datetime(2026, 7, 30, 10, 0)},
        {"run_id": 41, "run_timestamp": datetime(2026, 7, 29, 10, 0)},
    ])
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: run_id == 41)
    calls: list[int] = []
    monkeypatch.setattr(
        results,
        "fetch_research_filter_values",
        lambda engine, run_id: calls.append(run_id) or {
            "variants": ["orthogonalized"],
            "test_ids": ["newey_orthogonalized"],
            "sample_scopes": ["train"],
        },
    )

    response = client.get("/api/v1/research/options?runId=41")

    assert response.status_code == 200
    assert calls == [41]
    assert response.json()["defaultRunId"] == 42
    assert response.json()["variants"] == ["orthogonalized"]


def test_research_options_returns_404_for_unknown_requested_run(client, monkeypatch):
    monkeypatch.setattr(results, "fetch_research_runs", lambda engine: [
        {"run_id": 42, "run_timestamp": datetime(2026, 7, 30, 10, 0)},
    ])
    monkeypatch.setattr(results, "research_run_exists", lambda engine, run_id: False)

    response = client.get("/api/v1/research/options?runId=999")

    assert response.status_code == 404
```

- [ ] **Step 2: Run the backend test to verify it fails**

Run: `uv run pytest tests/test_research_results.py -q`

Expected: the supplied `runId` is rejected or ignored, so the new assertions fail.

- [ ] **Step 3: Implement the minimal endpoint change**

```python
@router.get("/research/options", response_model=ResearchFilterOptions)
async def get_research_options(
    run_id: int | None = Query(None, alias="runId"),
    engine: Engine = Depends(get_request_engine),
) -> ResearchFilterOptions:
    run_rows = fetch_research_runs(engine)
    default_run_id = run_rows[0]["run_id"] if run_rows else None

    if run_id is not None and not research_run_exists(engine, run_id):
        raise HTTPException(status_code=404, detail="Research run not found")

    selected_run_id = run_id if run_id is not None else default_run_id
    filter_values = (
        fetch_research_filter_values(engine, selected_run_id)
        if selected_run_id is not None
        else {"variants": [], "test_ids": [], "sample_scopes": []}
    )
    return ResearchFilterOptions(...)
```

The final constructor must preserve `default_run_id=default_run_id`, the full newest-first `runs` list, and the selected run's three filter lists.

- [ ] **Step 4: Run the backend test to verify it passes**

Run: `uv run pytest tests/test_research_results.py -q`

Expected: PASS.

### Task 2: Frontend API client can request options for one run

**Files:**
- Modify: `frontend/src/api/client/research.ts`
- Test: `frontend/src/api/client/research.test.ts`

**Interfaces:**
- Consumes: `http<T>(path, options)`, `ResearchFilterOptions`.
- Produces: `fetchResearchOptions(runId?: number, signal?: AbortSignal): Promise<ResearchFilterOptions>`.

- [ ] **Step 1: Write the failing tests**

```ts
it('serializes runId when loading filter options for a selected run', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(optionsPayload));

  await fetchResearchOptions(41);

  expect(globalThis.fetch).toHaveBeenCalledWith(
    expect.objectContaining({
      href: expect.stringContaining('/api/v1/research/options?runId=41'),
    }),
    expect.anything(),
  );
});

it('does not serialize runId when loading the default options', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(optionsPayload));

  await fetchResearchOptions();

  expect(globalThis.fetch).toHaveBeenCalledWith(
    expect.objectContaining({
      href: expect.not.stringContaining('runId='),
    }),
    expect.anything(),
  );
});
```

Use the existing test file's response helper and fetch assertion style if they differ.

- [ ] **Step 2: Run the frontend client test to verify it fails**

Run: `npm test -- src/api/client/research.test.ts`

Expected: `fetchResearchOptions` accepts no argument or does not serialize `runId`.

- [ ] **Step 3: Implement the minimal client change**

```ts
export function fetchResearchOptions(
  runId?: number,
  signal?: AbortSignal,
): Promise<ResearchFilterOptions> {
  return http<ResearchFilterOptions>('/api/v1/research/options', {
    query: runId === undefined ? {} : { runId },
    signal,
  });
}
```

An empty query object deliberately produces no query string and satisfies the project’s exact optional-property setting.

- [ ] **Step 4: Run the frontend client test and typecheck**

Run: `npm test -- src/api/client/research.test.ts; npm run typecheck`

Expected: both commands PASS.

### Task 3: Research page refreshes filter choices after run changes

**Files:**
- Modify: `frontend/src/pages/ResearchPage.tsx`
- Test: `frontend/src/pages/ResearchPage.test.tsx`

**Interfaces:**
- Consumes: `fetchResearchOptions(runId?, signal?)`, `fetchFactorResults(query, signal?)`, `ResearchFilterOptions`, `AsyncState<T>`.
- Produces: selected-run-specific `<select>` options and factor requests without stale `variant`, `testId`, or `sampleScope` values.

- [ ] **Step 1: Write the failing page test**

```tsx
it('refreshes filter values and clears stale selections after changing run', async () => {
  apiMocks.fetchResearchOptions
    .mockResolvedValueOnce({
      defaultRunId: 42,
      runs: [
        { runId: 42, createdAt: '2026-07-30T10:00:00' },
        { runId: 41, createdAt: '2026-07-29T10:00:00' },
      ],
      variants: ['raw'], testIds: ['newey_raw'], sampleScopes: ['train'],
    })
    .mockResolvedValueOnce({
      defaultRunId: 42,
      runs: [
        { runId: 42, createdAt: '2026-07-30T10:00:00' },
        { runId: 41, createdAt: '2026-07-29T10:00:00' },
      ],
      variants: ['orthogonalized'], testIds: ['newey_orthogonalized'], sampleScopes: ['test'],
    });

  render(<MemoryRouter><ResearchPage /></MemoryRouter>);
  await user.selectOptions(screen.getByLabelText('Research Run'), '41');

  await waitFor(() => {
    expect(apiMocks.fetchResearchOptions).toHaveBeenCalledWith(41, expect.any(AbortSignal));
  });
  expect(screen.getByLabelText('Variant')).toHaveValue('');
  expect(screen.getByRole('option', { name: 'orthogonalized' })).toBeInTheDocument();
});
```

Use the labels and test utilities already present in this file. If the test needs to put a non-empty old variant into the UI first, do so before selecting run 41.

- [ ] **Step 2: Run the page test to verify it fails**

Run: `npm test -- src/pages/ResearchPage.test.tsx`

Expected: the second options request is never made, or the old filter value remains.

- [ ] **Step 3: Add separate filter-options state and the refresh effect**

```ts
const [filterOptionsState, setFilterOptionsState] =
  useState<AsyncState<ResearchFilterOptions>>({ status: 'idle' });

// In the initial request success handler:
setOptionsState({ status: 'success', data });
setFilterOptionsState({ status: 'success', data });
setActiveRunId(data.defaultRunId);

useEffect(() => {
  if (activeRunId === null) return;

  const controller = new AbortController();
  setVariant('');
  setTestId('');
  setSampleScope('');
  setFilterOptionsState({ status: 'loading' });

  fetchResearchOptions(activeRunId, controller.signal)
    .then((data) => {
      if (!controller.signal.aborted) {
        setFilterOptionsState({ status: 'success', data });
      }
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      if (error instanceof HttpError) {
        setFilterOptionsState({ status: 'error', error: error.apiError });
        return;
      }
      setFilterOptionsState({ status: 'error', error: NETWORK_ERROR });
    });

  return () => controller.abort();
}, [activeRunId]);
```

Define `NETWORK_ERROR` as the same `ApiError` object already used in the page, or keep the existing inline object; do not return an object from `catch`.

- [ ] **Step 4: Replace free-text filters with selected-run option lists**

```tsx
const filterOptions = filterOptionsState.status === 'success'
  ? filterOptionsState.data
  : null;

<select value={variant} onChange={(e) => setVariant(e.target.value)}>
  <option value="">全部</option>
  {filterOptions?.variants.map((value) => (
    <option key={value} value={value}>{value}</option>
  ))}
</select>
```

Apply the identical pattern to `testIds` and `sampleScopes`. Use the existing label elements so the page test can locate them. On loading, show only the `全部` option; on error, also show only `全部` rather than stale values.

- [ ] **Step 5: Run page, client, and type checks**

Run: `npm test -- src/pages/ResearchPage.test.tsx src/api/client/research.test.ts; npm run typecheck`

Expected: both tests and typecheck PASS.

### Task 4: Verify the complete boundary

**Files:**
- Verify only: `webapi/tests/test_research_results.py`, `frontend/src/api/client/research.test.ts`, `frontend/src/pages/ResearchPage.test.tsx`

**Interfaces:**
- Consumes: completed Tasks 1–3.
- Produces: evidence that API selection, query serialization, and UI refresh agree.

- [ ] **Step 1: Run backend regression tests**

Run: `uv run pytest tests/test_research_results.py tests/test_research_storage.py -q`

Expected: PASS.

- [ ] **Step 2: Run frontend regression tests and static verification**

Run: `npm test -- src/api/client/research.test.ts src/pages/ResearchPage.test.tsx; npm run typecheck`

Expected: PASS.

- [ ] **Step 3: Manually verify in the browser**

1. Open the research page with the backend and frontend running.
2. Select a run which has different Variant/Test ID/Sample Scope values from the latest run.
3. Confirm the three dropdown lists change to that run's values.
4. Confirm each selection is reset to `全部` immediately after changing run.
5. Confirm the Network panel has `GET /api/v1/research/options?runId=<selected id>` before the factor query.

## Plan self-review

- **Spec coverage:** Task 1 covers newest default, explicit run values, full run list, and unknown-run 404. Task 2 covers frontend query serialization. Task 3 covers refresh, reset, no stale values, loading/error behavior, and option rendering. Task 4 covers end-to-end verification.
- **Placeholder scan:** No unfinished implementation placeholders remain; code snippets name every required function, parameter, and response field.
- **Type consistency:** The backend uses `runId` in the FastAPI alias and the client query. `ResearchFilterOptions` remains unchanged. The client returns the same promise type used by `ResearchPage`.
