"""quantmine: an honest-statistics equity factor research library.

Quick start:
    import quantmine as qm

    data = qm.MarketData(close=close_df, volume=volume_df)

    @qm.factor_registry("my_factor")
    def my_factor(close, tickers):
        return -close[tickers].pct_change(5)

    pool = qm.build_param_pool(data, day=5, halflife=10, period=20)
    failed, factors = qm.calculate_all_factors(pool)

    fwd = qm.forward_return(data.close, periods=[1, 5, 20])
    cs_ic = qm.CS_Information_Correlation(factors, fwd, output_path="cs_ic.parquet")
    report = qm.multiple_testing(qm.newey_west_summary(cs_ic))

Modules:
    datareader          MarketData container, DataSource / ConstituentsSource
                        protocols and their file/yfinance implementations.
    factor_register     Decorator registry and dependency-resolving batch
                        computation of factors.
    factor_mining       Built-in factor implementations (auto-registered).
    ic_calculator       IC testing, Newey-West, multiple-testing control,
                        orthogonalization, train/test workflow.
    back_testing        Point-in-time quantile backtest, turnover costs,
                        sanity tests.
    factor_attribution  Carhart four-factor attribution (daily, HAC).
    config/load_config  Per-step dataclass configs, YAML loader
                        (see config.example.yaml).
"""

__version__ = "0.2.1"

from .datareader import (
    MarketData,
    DataSource,
    ParquetSource,
    CSVSource,
    ExcelSource,
    YFinanceSource,
    ConstituentsSource,
    StaticUniverse,
    MembershipTableSource,
)
from .factor_register import (
    factor_registry,
    build_param_pool,
    calculate_all_factors,
    drop_intermediates,
    FACTOR_REGISTRY,
)
from . import factor_mining  # noqa: F401  importing registers the built-in factors
from .factor_mining import INTERMEDIATE_FACTORS
from .ic_calculator import (
    forward_return,
    data_standarization,
    CS_Information_Correlation,
    TM_Information_correlation,
    summary,
    resample_summary,
    newey_west_summary,
    multiple_testing,
    orthogonal_analysis,
    orthogonalize,
    time_series_stationary_test,
)
from .back_testing import (
    quantile_backtest,
    expand_to_daily_returns,
    expand_all_to_daily_returns,
    calculate_turnover,
    apply_transcation_cost,
    performance_summary,
    monotonicity_test,
    back_test_senity_test,
    back_test_sanity_test
)
from .factor_attribution import load_french_factors, carhart_attribution
from .load_config import load_configs

__all__ = [
    "MarketData", "DataSource", "ParquetSource", "CSVSource", "ExcelSource",
    "YFinanceSource", "ConstituentsSource", "StaticUniverse",
    "MembershipTableSource",
    "factor_registry", "build_param_pool", "calculate_all_factors",
    "drop_intermediates", "INTERMEDIATE_FACTORS",
    "FACTOR_REGISTRY",
    "forward_return", "data_standarization", "CS_Information_Correlation",
    "TM_Information_correlation", "summary", "resample_summary",
    "newey_west_summary", "multiple_testing", "orthogonal_analysis",
    "orthogonalize", "time_series_stationary_test",
    "quantile_backtest", "expand_to_daily_returns",
    "expand_all_to_daily_returns", "calculate_turnover",
    "apply_transcation_cost", "performance_summary", "monotonicity_test",
    "back_test_sanity_test", "back_test_senity_test",
    "load_french_factors", "carhart_attribution",
    "load_configs",
]
