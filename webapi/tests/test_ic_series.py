"""Tests for converting stored cross-sectional IC values into chart series."""

from datetime import date

import pandas as pd

from app.api.v1.research import ic_series
from app.api.v1.research.ic_series import build_ic_series
from quantmine.ic_calculator import ICVariant


def test_build_ic_series_returns_selected_factor_period_in_date_order() -> None:
    """The selected IC column becomes one chart series without rescaling."""
    frame = pd.DataFrame(
        {
            ("momentum", 5): [0.01, -0.02],
            ("momentum", 20): [0.03, 0.04],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    base_date, series = build_ic_series(
        frame,
        factor_name="momentum",
        period=5,
    )

    assert base_date == date(2024, 1, 2)
    assert series == [
        {
            "symbol": "IC",
            "points": [
                {"date": date(2024, 1, 2), "value": 0.01},
                {"date": date(2024, 1, 3), "value": -0.02},
            ],
        }
    ]


def test_build_ic_series_returns_empty_for_an_absent_factor_period() -> None:
    """A valid artifact without the requested period is an empty chart."""
    frame = pd.DataFrame(
        {("momentum", 5): [0.01]},
        index=pd.to_datetime(["2024-01-02"]),
    )

    assert build_ic_series(frame, factor_name="momentum", period=20) == (None, [])


def test_ic_series_route_loads_the_requested_variant_scope(client, monkeypatch) -> None:
    """The chart endpoint reads the selected artifact scope and returns JSON points."""
    frame = pd.DataFrame(
        {("momentum", 5): [0.01, -0.02]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    variants = {
        "raw": ICVariant(
            train={"cs_ic": frame},
            test={"cs_ic": frame * 2},
            transforms=[],
        )
    }
    monkeypatch.setattr(ic_series, "research_run_exists", lambda engine, run_id: run_id == 42)
    monkeypatch.setattr(ic_series, "load_ic_variants", lambda engine, run_id: variants)

    response = client.get(
        "/api/v1/research/ic-series",
        params={
            "runId": 42,
            "variant": "raw",
            "sampleScope": "test",
            "factorName": "momentum",
            "period": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "baseDate": "2024-01-02",
        "series": [
            {
                "symbol": "IC",
                "points": [
                    {"date": "2024-01-02", "value": 0.02},
                    {"date": "2024-01-03", "value": -0.04},
                ],
            }
        ],
    }
