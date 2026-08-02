from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.api.v1.market import series as market_series


def test_latest_market_date_returns_latest_trade_date(
    client: TestClient,
    monkeypatch,
) -> None:
    """The endpoint exposes the latest date using the public camelCase contract."""
    monkeypatch.setattr(
        market_series,
        "fetch_latest_market_trade_date",
        lambda engine: date(2026, 6, 24),
    )

    response = client.get("/api/v1/market/latest-date")

    assert response.status_code == 200
    assert response.json() == {"latestTradeDate": "2026-06-24"}
    assert "x-trace-id" in response.headers


def test_latest_market_date_returns_404_when_no_market_data(
    client: TestClient,
    monkeypatch,
) -> None:
    """An empty market table must be a unified not-found response."""
    monkeypatch.setattr(
        market_series,
        "fetch_latest_market_trade_date",
        lambda engine: None,
    )

    response = client.get("/api/v1/market/latest-date")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["status"] == 404
    assert body["traceId"] == response.headers["x-trace-id"]
