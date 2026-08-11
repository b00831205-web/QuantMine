"""Golden-value regression tests: the 8 factors computed by the new
architecture must match the legacy factors.parquet (composite column names)
within floating-point tolerance.

This file freezes a verification that was originally run by hand. Any future
change to factor_mining.py or factor_register.py can be checked for
correctness regressions by running this file alone.
"""
import re
import pandas as pd
import pytest

from conftest import (
    requires_real_data, requires_old_factors,
    REAL_CLOSE_PATH, REAL_VOLUME_PATH, OLD_FACTORS_PATH,
)

# registry name -> legacy column-name prefix (mapping confirmed one by one)
NAME_MAPPING = {
    "daily_return": "DailyReturn",
    "excess_return": "ExcessReturn",
    "TwentyDayVolatility": "TwentyDayVolatility",
    "TwentyDayNegVotality": "TwentyDayNegVolatility",  # new code misses an 'l'; not renamed yet
    "TwentyDayAvgVol": "TwentyDayAvgVol",
    "VolPriceCorr": "VolPriCorr",
    "ShortTermReversal": "ShortTermReversal",
}
MOMENTUM_DAY = 5  # the legacy data used a 5-day momentum window; must match param_pool['day']
TOLERANCE = 1e-8


def _extract_old_factor(old_factors: pd.DataFrame, prefix: str) -> pd.DataFrame:
    matching_cols = [c for c in old_factors.columns if c.rsplit("_", 1)[0] == prefix]
    if not matching_cols:
        return pd.DataFrame()
    df = old_factors[matching_cols].copy()
    df.columns = [c.rsplit("_", 1)[1] for c in matching_cols]
    return df


def _extract_old_momentum(old_factors: pd.DataFrame, day: int) -> pd.DataFrame:
    pattern = rf"^{day}DayMomentum_"
    matching_cols = [c for c in old_factors.columns if re.match(pattern, c)]
    if not matching_cols:
        return pd.DataFrame()
    df = old_factors[matching_cols].copy()
    df.columns = [c.rsplit("_", 1)[1] for c in matching_cols]
    return df


def _max_abs_diff(old_df: pd.DataFrame, new_df: pd.DataFrame) -> float:
    common_tickers = list(set(old_df.columns) & set(new_df.columns))
    common_dates = old_df.index.intersection(new_df.index)
    old_aligned = old_df.loc[common_dates, common_tickers]
    new_aligned = new_df.loc[common_dates, common_tickers]
    return (old_aligned - new_aligned).abs().max().max()


@requires_real_data
@requires_old_factors
class TestFactorsGoldenValues:
    """One test case per factor so a failure points straight at the culprit."""

    @pytest.fixture(scope="class")
    @classmethod
    def computed_factors(cls):
        import quantmine.factor_mining  # noqa: F401  importing triggers decorator registration
        from quantmine.factor_register import calculate_all_factors, build_param_pool
        from quantmine.datareader import MarketData

        close = pd.read_parquet(REAL_CLOSE_PATH)
        volume = pd.read_parquet(REAL_VOLUME_PATH)
        market_data = MarketData(close=close, volume=volume)
        param_pool = build_param_pool(market_data, day=MOMENTUM_DAY, halflife=10, period=20)

        failures, factors = calculate_all_factors(param_pool)
        assert not failures, f"no factor should fail to compute, but got: {failures}"
        return factors

    @pytest.fixture(scope="class")
    @classmethod
    def old_factors(cls):
        return pd.read_parquet(OLD_FACTORS_PATH)

    @pytest.mark.parametrize("factor_name", list(NAME_MAPPING.keys()))
    def test_factor_matches_old_value(self, factor_name, computed_factors, old_factors):
        old_prefix = NAME_MAPPING[factor_name]
        old_df = _extract_old_factor(old_factors, old_prefix)
        assert not old_df.empty, f"no columns found for {old_prefix} in the legacy data"

        new_df = computed_factors[factor_name]
        max_diff = _max_abs_diff(old_df, new_df)
        assert max_diff < TOLERANCE, f"{factor_name} max diff {max_diff} exceeds tolerance"

    def test_momentum_matches_old_value(self, computed_factors, old_factors):
        old_df = _extract_old_momentum(old_factors, MOMENTUM_DAY)
        assert not old_df.empty, "no momentum columns found in the legacy data"

        new_df = computed_factors["momentum"]
        max_diff = _max_abs_diff(old_df, new_df)
        assert max_diff < TOLERANCE, f"momentum max diff {max_diff} exceeds tolerance"
