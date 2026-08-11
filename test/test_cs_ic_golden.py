"""Golden-value regression test: the full chain (factor computation ->
forward_returns -> CS_IC) compared against the legacy CS_IC.parquet.

Final confirmed setup: Pearson method + momentum day=5 reproduces the legacy
values element-wise (differences at the 1e-16 floating-point limit).
"""
import pandas as pd
import pytest

from conftest import (
    requires_real_data, requires_old_cs_ic,
    REAL_CLOSE_PATH, REAL_VOLUME_PATH, OLD_CS_IC_PATH,
)

TOLERANCE = 1e-6  # ICs are correlations, slightly looser than raw factor values
MOMENTUM_DAY = 5

NAME_MAPPING = {
    "daily_return": "DailyReturn",
    "excess_return": "ExcessReturn",
    "TwentyDayVolatility": "TwentyDayVolatility",
    "TwentyDayNegVotality": "TwentyDayNegVolatility",
    "TwentyDayAvgVol": "TwentyDayAvgVol",
    "VolPriceCorr": "VolPriCorr",
    "ShortTermReversal": "ShortTermReversal",
}


def _find_old_column(
    old_ic_df: pd.DataFrame,
    factor_name: str,
    period: int,
) -> str | tuple[str, int] | None:
    multi_index_column = (factor_name, period)
    if multi_index_column in old_ic_df.columns:
        return multi_index_column

    if factor_name == "momentum":
        prefix = f"{MOMENTUM_DAY}DayMomentum"
    else:
        prefix = NAME_MAPPING.get(factor_name)
        if prefix is None:
            return None
    candidate = f"{prefix}_{period}DaysHoldingPeriod"
    return candidate if candidate in old_ic_df.columns else None


@requires_real_data
@requires_old_cs_ic
class TestCSInformationCorrelationGolden:

    @pytest.fixture(scope="class")
    @classmethod
    def new_ic_df(cls, tmp_path_factory):
        import quantmine.factor_mining  # noqa: F401
        from quantmine.factor_register import calculate_all_factors, build_param_pool
        from quantmine.datareader import MarketData
        from quantmine.ic_calculator import forward_return, CS_Information_Correlation

        close = pd.read_parquet(REAL_CLOSE_PATH)
        volume = pd.read_parquet(REAL_VOLUME_PATH)
        market_data = MarketData(close=close, volume=volume)
        param_pool = build_param_pool(market_data, day=MOMENTUM_DAY, halflife=10, period=20)

        failures, factors = calculate_all_factors(param_pool)
        assert not failures

        forward_returns = forward_return(close, periods=[1, 5, 20])

        out_path = str(tmp_path_factory.mktemp("ic") / "ic_test.parquet")
        ic_df, _ = CS_Information_Correlation(
            factors,
            forward_returns,
            output_path=out_path,
        )
        return ic_df

    @pytest.fixture(scope="class")
    @classmethod
    def old_ic_df(cls):
        return pd.read_parquet(OLD_CS_IC_PATH)

    @pytest.mark.parametrize("factor_name", list(NAME_MAPPING.keys()) + ["momentum"])
    @pytest.mark.parametrize("period", [1, 5, 20])
    def test_ic_matches_old_value(self, factor_name, period, new_ic_df, old_ic_df):
        old_col = _find_old_column(old_ic_df, factor_name, period)
        assert old_col is not None, f"no legacy column for {factor_name}, period={period}"

        old_series = old_ic_df[old_col]
        new_series = new_ic_df[(factor_name, period)]
        common_dates = old_series.index.intersection(new_series.index)

        diff = (old_series.loc[common_dates] - new_series.loc[common_dates]).abs()
        max_diff = diff.max()

        assert max_diff < TOLERANCE, f"{factor_name}, period={period} max diff {max_diff} exceeds tolerance"
