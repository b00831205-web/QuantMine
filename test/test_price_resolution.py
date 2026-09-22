"""Tests for replaceable backtest price-resolution policies."""

from __future__ import annotations

import pandas as pd
import pytest

from quantmine.workflows.price_resolution import (
    LastObservationPricePolicy,
    PriceResolutionPolicy,
    PriceResolutionRequest,
    ResolvedPrices,
)


def _series(values: list[float]) -> pd.Series:
    return pd.Series(
        values,
        index=pd.Index(["AAA", "BBB"], name="ticker"),
        dtype=float,
    )


def _request(
    *,
    raw_prices: pd.Series | None = None,
    last_prices: pd.Series | None = None,
    positions: pd.Series | None = None,
) -> PriceResolutionRequest:
    return PriceResolutionRequest(
        trade_date=pd.Timestamp("2026-09-18"),
        raw_prices=(
            raw_prices
            if raw_prices is not None
            else _series([10.0, 20.0])
        ),
        last_prices=(
            last_prices
            if last_prices is not None
            else _series([9.0, 19.0])
        ),
        positions=(
            positions
            if positions is not None
            else _series([100.0, 0.0])
        ),
    )


def test_last_observation_policy_implements_protocol() -> None:
    assert isinstance(LastObservationPricePolicy(), PriceResolutionPolicy)


def test_price_policy_uses_observed_prices_for_valuation_and_trading() -> None:
    result = LastObservationPricePolicy().resolve(_request())

    assert result.valuation_prices.tolist() == [10.0, 20.0]
    assert result.tradable.tolist() == [True, True]
    assert result.sources.tolist() == ["observed", "observed"]


def test_price_policy_uses_last_price_for_valuation_only() -> None:
    result = LastObservationPricePolicy().resolve(
        _request(
            raw_prices=_series([float("nan"), 20.0]),
            last_prices=_series([9.5, 19.0]),
            positions=_series([100.0, 0.0]),
        )
    )

    assert result.valuation_prices.tolist() == [9.5, 20.0]
    assert result.tradable.tolist() == [False, True]
    assert result.sources.tolist() == ["last_observation", "observed"]


def test_price_policy_uses_placeholder_only_for_flat_unpriced_security() -> None:
    result = LastObservationPricePolicy(
        flat_position_fallback=2.5
    ).resolve(
        _request(
            raw_prices=_series([10.0, float("nan")]),
            last_prices=_series([9.0, float("nan")]),
            positions=_series([100.0, 0.0]),
        )
    )

    assert result.valuation_prices.tolist() == [10.0, 2.5]
    assert result.tradable.tolist() == [True, False]
    assert result.sources.tolist() == ["observed", "unavailable_flat"]


def test_price_policy_rejects_unpriced_held_position() -> None:
    with pytest.raises(ValueError, match="held positions.*AAA"):
        LastObservationPricePolicy().resolve(
            _request(
                raw_prices=_series([float("nan"), 20.0]),
                last_prices=_series([float("nan"), 19.0]),
                positions=_series([100.0, 0.0]),
            )
        )


@pytest.mark.parametrize("field", ["raw_prices", "last_prices"])
def test_price_request_rejects_non_positive_known_prices(
    field: str,
) -> None:
    values = {field: _series([0.0, 20.0])}

    with pytest.raises(ValueError, match="positive non-missing"):
        _request(**values)


def test_price_request_rejects_misaligned_inputs() -> None:
    last_prices = pd.Series(
        [9.0, 19.0],
        index=pd.Index(["BBB", "AAA"], name="ticker"),
    )

    with pytest.raises(ValueError, match="last_prices.*raw_prices"):
        _request(last_prices=last_prices)


@pytest.mark.parametrize("trade_date", ["2026-09-18", pd.NaT])
def test_price_request_rejects_invalid_trade_date(
    trade_date: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="trade_date"):
        PriceResolutionRequest(
            trade_date=trade_date,  # type: ignore[arg-type]
            raw_prices=_series([10.0, 20.0]),
            last_prices=_series([9.0, 19.0]),
            positions=_series([0.0, 0.0]),
        )


@pytest.mark.parametrize("fallback", [True, 0.0, -1.0, float("nan")])
def test_last_observation_policy_rejects_invalid_fallback(
    fallback: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="fallback"):
        LastObservationPricePolicy(
            flat_position_fallback=fallback  # type: ignore[arg-type]
        )


def test_resolved_prices_requires_boolean_tradability() -> None:
    with pytest.raises(TypeError, match="boolean"):
        ResolvedPrices(
            valuation_prices=_series([10.0, 20.0]),
            tradable=_series([1.0, 0.0]),
            sources=pd.Series(
                ["observed", "last_observation"],
                index=_series([0.0, 0.0]).index,
            ),
        )
