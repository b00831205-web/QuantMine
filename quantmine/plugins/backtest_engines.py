"""Replaceable portfolio-backtest engine contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from ..ic_calculator import ICVariant, TestResult
from ..workflows.backtest_workflow import run_backtest_workflow, run_backtest_job
from ..workflows.portfolio_targets import build_quantile_target_weights
from ..workflows.position_backtest import run_position_backtest
from .context import SourceContext
from .contracts import MarketDataBundle, PluginSpec
from .loader import resolve_plugin
from .market_rules import MarketRulesComponent, MarketStateProvider


@dataclass(frozen=True)
class BacktestRequest:
    """Stable input shared by legacy and position-based backtest engines."""

    close: pd.DataFrame
    variants: Mapping[str, ICVariant]
    test_results: Mapping[str, Mapping[str, object]]
    config: Mapping[str, Any]
    constituents: object | None = None
    market_cap: pd.DataFrame | None = None
    market_data: MarketDataBundle | None = None
    market_rules: MarketRulesComponent | None = None
    market_state_provider: MarketStateProvider | None = None 

    def __post_init__(self) -> None:
        if not isinstance(self.close, pd.DataFrame):
            raise TypeError("close must be a pandas DataFrame")

        if self.close.empty: 
            raise ValueError("close must not be empty")

        if not isinstance(self.variants, Mapping):
            raise TypeError("variants must be a mapping")

        if not self.variants:
            raise ValueError("variants must not be empty")

        for variant_id, variant in self.variants.items():
            if not isinstance(variant_id, str) or not variant_id or variant_id.strip() != variant_id:
                raise ValueError("variant id must be a non-empty trimmed string")

            if not isinstance(variant, ICVariant):
                raise TypeError(f"variant '{variant_id}' must be an ICVariant")

        if not isinstance(self.test_results, Mapping):
            raise TypeError("test_results must be a mapping")

        if not isinstance(self.config, Mapping):
            raise TypeError("config must be a mapping")

        jobs= self.config.get("jobs")
        if not isinstance(jobs, list):
            raise TypeError("backtest config jobs must be a list")

        if self.market_cap is not None and not isinstance(self.market_cap, pd.DataFrame):
            raise TypeError("market_cap must be a pandas DataFrame")

        if self.market_data is not None and not isinstance(self.market_data, MarketDataBundle):
            raise TypeError("market_data must be a MarketDataBundle")

        if self.market_rules is not None and not isinstance(self.market_rules, MarketRulesComponent):
            raise TypeError("market_rules must be a MarketRulesComponent")

        if self.market_state_provider is not None and not isinstance(self.market_state_provider, MarketStateProvider):
            raise TypeError(
                "market_state_provider must implement MarketStateProvider"
            )

        seen_job_ids: set[str] = set()
        for job in jobs:
            if not isinstance(job, Mapping):
                raise TypeError("every backtest job must be a mapping")

            job_id = job.get("id")
            variant_id = job.get("variant")
            selection_test = job.get("selection_test")

            if not isinstance(job_id, str) or not job_id or job_id.strip() != job_id:
                raise ValueError("backtest job id must be a non-empty trimmed string")

            if job_id in seen_job_ids:
                raise ValueError(f"duplicate backtest job id '{job_id}'")

            seen_job_ids.add(job_id)

            if not isinstance(variant_id, str) or variant_id not in self.variants:
                raise ValueError(f"backtest job '{job_id}' uses unavailable variant '{variant_id}'")

            if not isinstance(selection_test, str) or selection_test not in self.test_results:
                raise ValueError(f"backtest job '{job_id}' uses unavailable selection test '{selection_test}'")

@dataclass(frozen=True)
class BacktestResult:
    job_results: Mapping[str, Mapping[str, object]]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.job_results, Mapping):
            raise TypeError("job_results must be a mapping")

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

        for job_id, result in self.job_results.items():
            if not isinstance(job_id, str) or not job_id or job_id.strip() != job_id:
                raise ValueError("job id must be a non-empty trimmed string")

            if not isinstance(result, Mapping):
                raise TypeError(f"backtest result '{job_id}' must be a mapping")


@runtime_checkable
class BacktestPlugin(Protocol):
    def run(self, request: BacktestRequest, context: SourceContext) -> BacktestResult: ...


@dataclass(frozen=True)
class BacktestComponent:
    id: str
    plugin: BacktestPlugin
    connection_ref: str | None = None
    requires_connection: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or self.id.strip() != self.id:
            raise ValueError("backtest component id must be non-empty trimmed string")

        if not isinstance(self.plugin, BacktestPlugin):
            raise TypeError("plugin must implement BacktestPlugin")

        if self.connection_ref is not None and (
            not isinstance(self.connection_ref, str) or not self.connection_ref or self.connection_ref.strip() != self.connection_ref
        ):
            raise ValueError("connection_ref must be a non-empty trimmed string")

        if self.requires_connection and self.connection_ref is None:
            raise ValueError(
                "connection_ref is required when requires_connection is true"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

def run_backtest_component(component: BacktestComponent, request: BacktestRequest, context: SourceContext) -> BacktestResult:
    result = component.plugin.run(request, context)

    if not isinstance(result, BacktestResult):
        raise TypeError(f"backtest component '{component.id}' returned {type(result).__name__}, expected BacktestResult")

    requested_ids = {job["id"] for job in request.config["jobs"]}
    returned_ids = set(result.job_results)

    if returned_ids != requested_ids:
        missing = sorted(requested_ids - returned_ids)
        unexpected = sorted(returned_ids - requested_ids)
        raise ValueError(
            f"backtest component '{component.id}' returned invalid job ids: missing={missing}, unexpected={unexpected}"
        )

    return result


@dataclass(frozen=True)
class PythonQuantileBacktestPlugin:
    """Adapter around the existing vectorized quantile backtest."""

    def run(
            self,
            request: BacktestRequest,
            context: SourceContext,
    ) -> BacktestResult:
        del context

        job_results = run_backtest_workflow(
            close = request.close,
            variants=dict(request.variants),
            test_results=dict(request.test_results),
            backtest_config=dict(request.config),
            constituents=request.constituents,
            market_cap=request.market_cap
        )

        return BacktestResult(
            job_results= job_results,
            metadata={
                "backend": "python",
                "model": "vectorized_quantile"
            }
        )

@dataclass(frozen=True)
class PythonPositionBacktestPlugin:
    """Position-based engine using replaceable market execution rules."""

    def run(self, request: BacktestRequest, context: SourceContext) -> BacktestResult:
        if request.market_rules is None:
            raise ValueError("position backtest requires a market-rules component")

        job_results: dict[str, Mapping[str, object]] = {}

        for job in request.config["jobs"]:
            job_id = job["id"]
            variant = request.variants[job["variant"]]
            test_output = request.test_results[job["selection_test"]]

            test_result = TestResult(
                summary= test_output["summary"],
                multiple_testing= test_output["multiple_testing"],
                test_method= test_output["test_method"],
                sample_scope = test_output["sample_scope"]
            )

            membership_job = run_backtest_job(
                close= request.close,
                variant = variant,
                test_result= test_result,
                job_config = dict(job),
                constituents= request.constituents,
                market_cap= request.market_cap,
            )

            if membership_job["status"] == "no_significant_factor":
                job_results[job_id] = {
                    "status": "no_significant_factor",
                    "selected_factor_periods": [],
                    "group": None,
                    "portfolio_results": {},
                    "ticker_history": {},
                }
                continue

            part = job["part"]
            group = job.get("position_group", f"Q{part}")
            gross_exposure = job.get("gross_exposure", request.config.get("gross_exposure", 1.0))
            initial_cash = job.get("initial_cash", request.config.get("initial_cash", 1_000_000.0))
            portfolio_results: dict[tuple[str, int], object] = {}

            for factor_period, ticker_history in (membership_job["ticker_history"]).items():
                factor_name, _ = factor_period
                factor_frame = variant.test["factors"][factor_name]
                test_dates = factor_frame.index.intersection(request.close.index)
                test_close = request.close.loc[test_dates]
                target_weights = build_quantile_target_weights(
                    ticker_history,
                    tickers = test_close.columns,
                    group = group,
                    gross_exposure = gross_exposure,
                )

                portfolio_results[factor_period] = (
                    run_position_backtest(
                        close=test_close,
                        target_weights= target_weights,
                        initial_cash= initial_cash,
                        component = request.market_rules,
                        context = context,
                        market_state_provider= request.market_state_provider
                    )
                )

            job_results[job_id] = {
                "status": "ok",
                "selected_factor_periods": membership_job["selected_factor_periods"],
                "group": group,
                "gross_exposure": gross_exposure,
                "initial_cash": initial_cash,
                "portfolio_results": portfolio_results,
                "ticker_history": membership_job["ticker_history"]
            }

        return BacktestResult(
            job_results= job_results,
            metadata= {
                "backend": "python",
                "model": "position_based",
                "market_rules": request.market_rules.id
            }
        )
def create_python_backtest_engine(**params: Any) -> BacktestComponent:
    if params:
        unexpected = ", ".join(sorted(params))
        raise ValueError(
            f"unsupported Python backtest parameters: {unexpected}"
        )

    return BacktestComponent(
        id = "python_quantile_backtest",
        plugin=PythonQuantileBacktestPlugin(),
        requires_connection=False,
        metadata={
            "backend": "python",
            "model": "vectorized_quantile"
        }
    )

def resolve_backtest_component(
        spec: PluginSpec,
        *,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> BacktestComponent:
    component = resolve_plugin(spec, allowed_module_prefixes= allowed_module_prefixes)

    if not isinstance(component, BacktestComponent):
        raise TypeError(f"backtest factory {spec.entry_point!r} returned {type(component).__name__}, expected BacktestComponent")

    return component

def create_python_position_backtest_engine(**params: Any) -> BacktestComponent:
    """Create the Python position-based backtest engine."""

    if params:
        unexpected = ", ".join(sorted(params))
        raise ValueError(
            f"unsupported Python position-backtest parameters: {unexpected}"
        )

    return BacktestComponent(
        id = "python_position_backtest",
        plugin = PythonPositionBacktestPlugin(),
        requires_connection= False,
        metadata= {
            "backend": "python",
            "model": "position_based"
        }
    )