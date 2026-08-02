# Expandable Backtest Net-Value Curves

## Goal

Extend the Research page's existing backtest summary cards so that a user can
open one card and inspect the corresponding Q1–Qn and Long-Short cumulative
net-value curves. At the same time, make the card metric layout align reliably
on desktop screens.

## Scope

This feature has three bounded parts:

1. Align each summary card's annual-return and statistic fields with a fixed
   desktop grid.
2. Persist or import the per-factor/per-period daily return series into the
   existing normalized `backtest_results` table. The existing long-form
   `backtest_metrics` table remains the source for summary cards only.
3. Add a read-only research API and an on-demand chart area under the card
   row. Only the selected card's curve is loaded and displayed.

It does not change the factor-selection or backtest calculations, add
cross-run comparisons, or create a new standalone backtest page.

## User interaction

- Every backtest summary card has a `查看净值曲线` control.
- Clicking it expands a full-width chart directly below the card grid. The
  chart belongs to that exact `(variant, backtestId, testId, factorName,
  period)` combination.
- At most one card is expanded at a time. Clicking the selected card's control
  again closes the chart.
- Choosing another research run, variant, or test ID closes the chart. This
  prevents a curve from a prior filter context being shown under new cards.
- The chart contains Q1–Qn and Long-Short series, indexed to 100 at their
  first usable observation, with the existing ECharts tooltip and zoom/brush
  behaviour.
- A card can still render when no curve artifact was saved. Expanding it shows
  a neutral empty state: `该回测未保存净值曲线` rather than treating it as a page
  error.

## Data contract

The curve data is not derivable from the existing annualized metrics. It is
derived from the persisted daily returns in `backtest_results` for each factor
and holding period, by cumulatively compounding each quantile return stream.

The API is:

`GET /api/v1/research/backtest-series`

Required query fields:

- `runId`
- `variant`
- `backtestId`
- `testId`
- `factorName`
- `period`

Successful responses use the same frontend-friendly series shape as the market
chart:

```json
{
  "baseDate": "2024-01-02",
  "series": [
    {"symbol": "Q1", "points": [{"date": "2024-01-02", "value": 100.0}]},
    {"symbol": "long_short", "points": [{"date": "2024-01-02", "value": 100.0}]}
  ]
}
```

The storage helper filters `backtest_results` by the full card identity,
orders rows by date and quantile rank, pivots them into a date-by-portfolio
return frame, and cumulatively compounds each column before converting it to
chart series. It does not query `backtest_metrics` for time-series values.
If no matching daily-return rows exist, it returns a successful empty `series`
array so the frontend can render its empty state.

The current workflow already writes daily returns to `backtest_results`. The
legacy importer will additionally discover matching `tmp/back_test/backtest_*`
parquet files and import their date-indexed Q1–Qn/Long-Short returns into the
same table for the legacy run. Summary and monotonicity files are not treated
as curve data.

## Frontend structure

`ResearchPage` owns:

- `expandedBacktestKey`, either `null` or the selected card identity;
- a separate async state for the selected curve;
- an abortable effect that requests a curve only while a key is expanded.

`BacktestSection` remains a presentation component. It receives cards, the
selected key, and a toggle callback, then renders the chart panel beneath the
card grid. Existing `SeriesChart` and its normalization utility are reused;
the chart component does not contain database or request logic.

For desktop alignment, the annual-return row uses six equal columns
(Long-Short, Q1–Q5) and the statistic row uses four equal columns
(Sharpe, maximum drawdown, win rate, holding period). A responsive breakpoint
may reduce the column count on narrow screens, but the desktop layout must not
wrap Q5 onto a second row.

## Error handling

- Unknown research run or malformed query: existing API error convention.
- Existing run with no artifact: `200` plus empty series; shown as a local
  curve empty state.
- Network/server failure while a curve is open: local chart error state with
  retry, while cards remain visible.
- Filter changes abort the prior curve request and clear the expanded key.

## Verification

- Python: legacy daily-return importer tests; storage conversion tests; route
  tests for populated and absent return rows.
- TypeScript: API client serializes all curve identity fields.
- React: clicking one card requests and displays its curve; clicking a second
  swaps the selection; changing filters collapses it; empty series shows the
  curve-specific empty state.
- Visual check: Q5 remains aligned with the other annual-return values on the
  desktop card layout.
