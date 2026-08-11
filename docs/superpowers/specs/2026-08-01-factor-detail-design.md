# Factor Detail Page Design

## Goal

Provide a drill-down page for one factor. A user double-clicks a row in the
Research page and lands on a shareable URL that preserves the selected
research context. The page shows every available holding period for that
factor and highlights the period that was double-clicked.

## Scope

The page contains:

1. A back link and factor title.
2. Selectors for research run, variant, test ID, and sample scope.
3. Holding-period tabs for the selected factor; the URL period is selected by
   default.
4. An IC time-series chart for the selected period.
5. A statistics table for every available period of the factor.
6. Backtest summary cards for that factor, plus the existing expandable net
   value curve affordance.

This page does not add factor calculation, tests, a new global state library,
or report generation.

## Navigation and URL contract

The Research page double-click action navigates to:

```
/research/factor/:factorName?runId=10&variant=raw&testId=newey_raw&sampleScope=test&period=5
```

`factorName` identifies the factor. The query parameters identify the
research-result context and initial selected holding period. The detail page
can therefore be refreshed, bookmarked, or opened directly without relying
on React navigation state.

When a selector changes, the page updates the corresponding query parameter.
Changing the research run first requests run-specific filter options and
clears invalid variant, test ID, and sample scope selections. If the selected
period is unavailable for the new context, the page selects the first returned
period and updates the URL.

## Data flow

Existing endpoints are reused:

| Page need | Endpoint | Query |
| --- | --- | --- |
| Run and filter options | `GET /api/v1/research/options` | optional `runId` |
| Factor statistics, all periods | `GET /api/v1/research/factors` | `runId`, context filters, `factorName`, page size 100 |
| Factor backtest cards | `GET /api/v1/research/backtest-summaries` | `runId`, variant/test filters, `factorName` |
| Expandable backtest net values | existing `GET /api/v1/research/backtest-series` | full card identity |

One endpoint is added:

```
GET /api/v1/research/ic-series
  ?runId=&variant=&sampleScope=&factorName=&period=
```

It loads the selected run/variant/scope's registered IC artifact, extracts
the requested factor and holding-period daily IC series, and returns the
existing frontend `SeriesResponse` shape:

```json
{
  "baseDate": "2021-01-04",
  "series": [{"symbol": "IC", "points": [{"date": "...", "value": 0.03}]}]
}
```

`testId` is intentionally not required by the IC endpoint: test methods
summarize an already computed IC series; they do not change the raw IC
observations.

## Frontend structure

`FactorDetailPage` owns URL-derived filter state and four async states:

- options;
- factor statistics;
- IC series;
- backtest summaries.

Each request uses an `AbortController`. The cleanup function cancels its
previous request, and a successful result only updates state when the request
was not aborted. This prevents stale results from a previously selected run or
period replacing current data.

The statistic response is used twice: to build the holding-period tabs and to
render the all-period table. The selected period filters only the IC chart;
the table remains a comparison view. The selected table row is visually
highlighted.

## Empty and error behavior

- Unknown run: backend returns 404 and the existing error boundary presents
  the normalized API error.
- No rows for a factor/context: show an empty state in the statistics and
  backtest sections.
- No IC artifact or no requested factor/period in an artifact: return a
  normal empty `SeriesResponse`; render “暂无 IC 时序数据”, not a server error.
- Changing a selector clears the selected period/chart until fresh data is
  available.

## Tests

Backend tests cover the IC-series route's identity filtering, artifact-to-
series conversion, unknown run response, and empty result.

Frontend tests cover:

1. Research-page double-click URL construction.
2. Detail-page initial requests from URL parameters.
3. Period tab changes requesting only a different IC series.
4. Run changes replacing filter options and clearing invalid selections.
5. Rendering the selected-period chart and all-period statistics.

## Acceptance criteria

- A Research-page double-click opens a detail page with the correct factor,
  context, and highlighted period.
- The four selectors can be changed and the page does not show stale data.
- A selected period renders its IC curve when the artifact contains data.
- All available periods remain visible for comparison.
- Backtest cards are restricted to the factor and retain their expandable net
  value curves.
