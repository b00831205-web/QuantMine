"""Data models and factor-selection strategies for the IC research workflow.

Extracted from ``ic_calculator.py`` so the pipeline functions live apart from
the type definitions and the pluggable selector strategies. New selectors are
added here by subclassing ``FactorSelector`` and decorating with
``@register_factor_selector("name")``; ``ic_calculator`` re-exports these names
for backward compatibility, so existing ``from quantmine.ic_calculator import
ICVariant`` imports keep working.
"""
import pandas as pd
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .registry import make_registry

REGISTER_FACTOR_SELECTOR, register_factor_selector = make_registry()


@dataclass
class ICVariant:
    train: dict
    test: dict
    transforms: list[dict]


@dataclass
class TestResult:
    __test__ = False  # stop pytest from collecting this dataclass as a test case
    summary: pd.DataFrame
    multiple_testing: pd.DataFrame | None
    test_method: str
    sample_scope: str


def selected_index_to_pairs(mask: pd.Series) -> list[tuple[str, int]]:
    selected_index = mask.fillna(False).astype(bool)
    selected_index = selected_index[selected_index].index

    if not isinstance(selected_index, pd.MultiIndex):
        raise ValueError('selector result index must be a MultiIndex of (factor, period)')

    return [(str(factor_name), int(period)) for factor_name, period in selected_index]


class FactorSelector(ABC):
    @abstractmethod
    def select(
        self,
        test_result: TestResult,
        **params,
    ) -> list[tuple[str, int]]:
        ...


@register_factor_selector('bh')
class BHselector(FactorSelector):
    def select(self, test_result: TestResult, **params):
        if test_result.multiple_testing is None:
            raise ValueError('BH selector requires multiple testing result')
        if 'BH_significant' not in test_result.multiple_testing.columns:
            raise ValueError('multiple_testing does not contain BH_significant')

        return selected_index_to_pairs(test_result.multiple_testing['BH_significant'])


@register_factor_selector("p_value")
class PValueSelector(FactorSelector):
    def select(
        self,
        test_result: TestResult,
        alpha: float = 0.05,
        **params,
    ) -> list[tuple[str, int]]:
        if "p_value" not in test_result.summary.columns:
            raise ValueError("summary does not contain p_value")

        return selected_index_to_pairs(
            test_result.summary["p_value"] < alpha
        )


@register_factor_selector("t_stat")
class TStatSelector(FactorSelector):
    def select(
        self,
        test_result: TestResult,
        threshold: float = 1.96,
        **params,
    ) -> list[tuple[str, int]]:
        if "t_stat" not in test_result.summary.columns:
            raise ValueError("summary does not contain t_stat")

        return selected_index_to_pairs(
            test_result.summary["t_stat"].abs() > threshold
        )


@register_factor_selector("ic_mean")
class ICMeanSelector(FactorSelector):
    def select(
        self,
        test_result: TestResult,
        threshold: float = 0.02,
        **params,
    ) -> list[tuple[str, int]]:
        if "IC_mean" not in test_result.summary.columns:
            raise ValueError("summary does not contain IC_mean")

        return selected_index_to_pairs(
            test_result.summary["IC_mean"].abs() > threshold
        )


class CompositeSelector(FactorSelector):
    def select(self, test_result, **params):
        ...
