"""Contract tests for ``GET /api/v1/market/series``.

The database read is replaced with a deterministic dataframe.  These tests
exercise the real FastAPI route, frequency conversion, normalisation, and
response schema without requiring PostgreSQL.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.v1.market import series as series_module
from quantmine.storage.database import get_engine


@pytest.fixture
def market_client(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Configure the route to read a caller-supplied in-memory bar table."""

    client.app.dependency_overrides[get_engine] = lambda: object()

    def _with_bars(bars: pd.DataFrame) -> TestClient:
        def _fetch_market_bars(*_args, **_kwargs) -> pd.DataFrame:
            return bars.copy()

        monkeypatch.setattr(series_module, "fetch_market_bars", _fetch_market_bars)
        return client

    yield _with_bars
    client.app.dependency_overrides.clear()


def _request_series(
    client: TestClient,
    *,
    symbols: list[str],
    frequency: str = "D",
    normalize: bool = True,
    start_date: str = "2024-01-02",
    end_date: str = "2024-01-31",
):
    params: list[tuple[str, str]] = [("symbols", symbol) for symbol in symbols]
    params.extend(
        [
            ("startDate", start_date),
            ("endDate", end_date),
            ("frequency", frequency),
            ("normalize", str(normalize).lower()),
        ]
    )
    return client.get("/api/v1/market/series", params=params)


def test_daily_normalized_series_preserves_each_ticker(market_client) -> None:
    """Each requested ticker gets its own price-index series starting at 100."""
    client = market_client(
        pd.DataFrame(
            [
                {"trade_date": date(2024, 1, 2), "ticker": "AAPL", "close": 100.0},
                {"trade_date": date(2024, 1, 3), "ticker": "AAPL", "close": 110.0},
                {"trade_date": date(2024, 1, 2), "ticker": "MSFT", "close": 200.0},
                {"trade_date": date(2024, 1, 3), "ticker": "MSFT", "close": 210.0},
            ]
        )
    )

    response = _request_series(client, symbols=["aapl", "msft"])

    assert response.status_code == 200
    body = response.json()
    assert body["baseDate"] == "2024-01-02"
    by_symbol = {entry["symbol"]: entry["points"] for entry in body["series"]}
    assert set(by_symbol) == {"AAPL", "MSFT"}
    assert [point["date"] for point in by_symbol["AAPL"]] == ["2024-01-02", "2024-01-03"]
    assert [point["value"] for point in by_symbol["AAPL"]] == pytest.approx([100.0, 110.0])
    assert [point["date"] for point in by_symbol["MSFT"]] == ["2024-01-02", "2024-01-03"]
    assert [point["value"] for point in by_symbol["MSFT"]] == pytest.approx([100.0, 105.0])


def test_daily_raw_series_returns_close_values(market_client) -> None:
    """When normalisation is disabled, the route returns unmodified closes."""
    client = market_client(
        pd.DataFrame(
            [
                {"trade_date": date(2024, 1, 2), "ticker": "AAPL", "close": 100.0},
                {"trade_date": date(2024, 1, 3), "ticker": "AAPL", "close": 110.0},
            ]
        )
    )

    response = _request_series(client, symbols=["AAPL"], normalize=False)

    assert response.status_code == 200
    assert response.json()["series"][0]["points"] == [
        {"date": "2024-01-02", "value": 100.0},
        {"date": "2024-01-03", "value": 110.0},
    ]


def test_weekly_series_uses_last_actual_trading_day(market_client) -> None:
    """A Friday holiday keeps Thursday, rather than creating a Friday point."""
    client = market_client(
        pd.DataFrame(
            [
                {"trade_date": date(2024, 1, 1), "ticker": "AAPL", "close": 100.0},
                {"trade_date": date(2024, 1, 2), "ticker": "AAPL", "close": 105.0},
                {"trade_date": date(2024, 1, 4), "ticker": "AAPL", "close": 110.0},
                {"trade_date": date(2024, 1, 8), "ticker": "AAPL", "close": 120.0},
                {"trade_date": date(2024, 1, 11), "ticker": "AAPL", "close": 130.0},
            ]
        )
    )

    response = _request_series(client, symbols=["AAPL"], frequency="W")

    assert response.status_code == 200
    assert response.json()["series"][0]["points"] == [
        {"date": "2024-01-04", "value": 100.0},
        {"date": "2024-01-11", "value": pytest.approx(118.1818181818)},
    ]


def test_monthly_series_uses_last_actual_trading_day(market_client) -> None:
    """Month-end aggregation retains the final available close in each month."""
    client = market_client(
        pd.DataFrame(
            [
                {"trade_date": date(2024, 1, 30), "ticker": "AAPL", "close": 100.0},
                {"trade_date": date(2024, 1, 31), "ticker": "AAPL", "close": 120.0},
                {"trade_date": date(2024, 2, 1), "ticker": "AAPL", "close": 125.0},
                {"trade_date": date(2024, 2, 28), "ticker": "AAPL", "close": 150.0},
            ]
        )
    )

    response = _request_series(
        client,
        symbols=["AAPL"],
        frequency="M",
        start_date="2024-01-30",
        end_date="2024-02-28",
    )

    assert response.status_code == 200
    assert response.json()["series"][0]["points"] == [
        {"date": "2024-01-31", "value": 100.0},
        {"date": "2024-02-28", "value": 125.0},
    ]


def test_date_range_error_uses_validation_error_contract(market_client) -> None:
    """A reversed date range is a 422 validation error, never a 500."""
    client = market_client(pd.DataFrame(columns=["trade_date", "ticker", "close"]))

    response = client.get(
        "/api/v1/market/series",
        params={
            "symbols": "AAPL",
            "startDate": "2024-02-01",
            "endDate": "2024-01-01",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["status"] == 422
