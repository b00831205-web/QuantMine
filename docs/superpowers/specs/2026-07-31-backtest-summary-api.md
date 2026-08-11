# Backtest Summary API Design

## Goal

Expose one compact backtest-summary card per `backtest_id`, factor, and holding
period for the active research run, so the Research page can render its
existing backtest section from persisted `backtest_metrics` rows.

## Scope

The first endpoint is `GET /api/v1/research/backtest-summaries`.

- Required query: `runId`
- Optional filters: `variant`, `testId`, `factorName`, `period`
- Response: a paginated list of aggregated backtest cards
- Unknown run: `404`
- No matching metrics: `200` with an empty page

It does not read Parquet artifacts, return daily/net-value series, or expose
sensitivity-test artifacts. Those will be separate endpoints.

## Aggregation contract

`backtest_metrics` is deliberately a long table. The API groups rows by:

`run_id, variant_name, backtest_id, test_id, factor_name, period`

For every group:

- Build `quantileYearlyReturns` from rows whose `metric_name` is
  `yearly_return`. Key `0` becomes `longShort`; keys `1..n` become `Q1..Qn`.
- Read Long-Short (`quantile_rank = 0`) values for `sharp_ratio`,
  `max_drawdown`, and `win_rate`.
- Omit a metric from the object only when it has no stored value; do not use a
  false zero.

The response intentionally mirrors stored metric names rather than guessing a
transaction-turnover value not currently persisted by the workflow.

## Response model

```json
{
  "items": [
    {
      "variantName": "raw",
      "backtestId": "raw_test",
      "testId": "newey_raw",
      "factorName": "TwentyDayVolatility",
      "period": 5,
      "quantileYearlyReturns": {"Q1": -0.08, "Q5": 0.11, "longShort": 0.19},
      "sharpe": 1.42,
      "maxDrawdown": -0.12,
      "winRate": 0.57
    }
  ],
  "total": 1,
  "page": 1,
  "pageSize": 25
}
```

## Error handling and tests

Use the existing `get_request_engine`, `research_run_exists`, SQLAlchemy table
reflection, FastAPI aliases, and the existing unified error middleware. Tests
mock the storage helpers at the API boundary, then frontend tests mock the
client and assert that the active run and filters reach the request.
