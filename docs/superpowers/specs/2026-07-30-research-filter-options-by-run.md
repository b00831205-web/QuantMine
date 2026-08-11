# Research filter options by run

## Goal

Ensure the Variant, Test ID, and Sample Scope filters shown on the research
page always belong to the research run currently selected by the user.

## API contract

`GET /api/v1/research/options` accepts an optional `runId` query parameter.

- Without `runId`, the endpoint selects the newest run for its filter values
  and returns that run as `defaultRunId`.
- With `runId`, the endpoint returns the filter values for that specific run.
- Both responses contain the full, newest-first list of selectable runs.
- An unknown `runId` returns HTTP 404 using the existing unified error format.

The response shape remains `ResearchFilterOptions`; no filters-for-all-runs
payload is introduced.

## Frontend flow

1. On first mount, request `/research/options`.
2. Set `activeRunId` from `defaultRunId`.
3. When `activeRunId` changes, request `/research/options?runId=<id>`.
4. Replace the three available filter option lists with that response's values.
5. Clear Variant, Test ID, and Sample Scope selections before requesting the
   new run's factor results, preventing values from the previous run from
   leaking into the next query.

## Error handling

- The initial options request uses the existing `AsyncState` / `HttpError`
  error model.
- A run-specific options failure preserves the current run selection and shows
  no stale filter values.
- Empty filter lists are valid and render an "all" option only.

## Tests

- Backend: options without `runId` selects the newest run; options with a
  supplied run id asks the storage reader for that run; unknown run is 404.
- Frontend client: optional `runId` is serialized only when provided.
- Research page: changing the selected run refreshes its available filters and
  clears prior filter selections.
