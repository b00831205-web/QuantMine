from dataclasses import dataclass, field


@dataclass
class BaseCheckpointConfig:
    checkpoint_dir: str = 'tmp/checkpoint'

@dataclass
class DataAcquisitionConfig(BaseCheckpointConfig):
    max_retries: int = 3
    wait: int = 60
    def __post_init__(self):
        if not (0 < self.max_retries < 100):
            raise ValueError(f'max retries only support retreies below 100 times, currently{self.max_retries}')

@dataclass
class RetryBatchesConfig(BaseCheckpointConfig):
    wait: int = 60

'''
factor_mining
'''

@dataclass
class MomentumConfig:
    day: int = 5
    def __post_init__(self):
        if self.day< 1:
            raise ValueError(f"momentum days greater than one, current{self.day}")

'''
ic_calculator
'''

@dataclass
class ForwardReturnConfig:
    periods: list[int]|int = field(default_factory=  lambda: [1,5,20])
    def __post_init__(self):
        if isinstance(self.periods, int): #the annotation accepts int; without normalization the for-loop below would fail iterating an int
            self.periods = [self.periods]
        for period in self.periods:
            if not isinstance(period, int):
                raise TypeError('periods should be integers')
            if period < 1:
                raise ValueError(f'periods should greater than 1, current{self.periods}')

@dataclass
class NeweyWestSummaryConfig:
    lag_multiplier: int = 2
    def __post_init__(self):
        if self.lag_multiplier< 1:
            raise ValueError(f"lag multiplier should greater than one, current{self.lag_multiplier}")

@dataclass
class OrthogonalizeConfig:
    threshold: float = 0.03
    min_period : int = 60
    def __post_init__(self):
        if not (0 < self.threshold < 1):
            raise ValueError(f"threshold should be between 0, 1, current: {self.threshold}")
        if self.min_period< 1:
            raise ValueError(f"min period should greater than one, current{self.min_period}")

@dataclass
class TimeSeriesStationaryTestConfig:
    rolling_period: int = 126
    periods: list = field(default_factory=lambda: [1, 5, 20])
    def __post_init__(self):
        if self.rolling_period < 2:
            raise ValueError(f"rolling period should greater than one, current{self.rolling_period}")
        for period in self.periods:
            if not isinstance(period, int) or period < 1:
                raise ValueError(f'periods should be positive integers, current{self.periods}')

@dataclass
class BackTestingConfig:
    part: int = 5
    jobs: list[dict] = field(default_factory=list)
    def __post_init__(self):
        if self.part < 2:
            raise ValueError(f"part should greater than two, current{self.part}")
        if not isinstance(self.jobs, list):
            raise TypeError("backtest jobs must be a list")

@dataclass
class TranscationCostConfig:
    cost_per_trade: float = 0.001
    def __post_init__(self):
        if not (0 < self.cost_per_trade < 1):
            raise ValueError(f"cost per trade should in (0,1), current{self.cost_per_trade}")

'''
factor attribution
'''

@dataclass
class CarhartAttributionConfig:
    maxlags: int = 20
    def __post_init__(self):
        if self.maxlags < 1:
            raise ValueError(f"max lags should greater than one, current{self.maxlags}")

CONFIG_REGISTRY = {
    'checkpoint': BaseCheckpointConfig,
    'data_acquisition': DataAcquisitionConfig,
    'retry_batches': RetryBatchesConfig,

    'momentum': MomentumConfig,
    'forward_return': ForwardReturnConfig,
    'newey_west': NeweyWestSummaryConfig,
    'orthogonalize': OrthogonalizeConfig,
    'time_series_stationary_test': TimeSeriesStationaryTestConfig,

    'backtest': BackTestingConfig,
    'transaction_cost': TranscationCostConfig,

    'carhart_attribution': CarhartAttributionConfig,
}
