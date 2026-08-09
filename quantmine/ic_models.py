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
    """One factor set with its forward returns, split into train and test.

    A variant is either the raw factors or a processor's output (e.g.
    orthogonalization); ``transforms`` records which processors produced it, so
    a result can be traced back to how its inputs were built. ``train`` and
    ``test`` each hold ``{"factors": ..., "forward_returns": ...}``.
    """
    train: dict
    test: dict
    transforms: list[dict]


@dataclass
class TestResult:
    """Statistical test output for one variant.

    Attributes:
        summary: Per (factor, period) statistics: IC_mean, t_stat, p_value, ...
        multiple_testing: Correction results (e.g. BH); None when not applied.
        test_method: Name of the test that produced the summary.
        sample_scope: ``train`` or ``test``. Selection must consume train
            results, so factor choice never sees the evaluation sample.
    """
    __test__ = False  # stop pytest from collecting this dataclass as a test case
    summary: pd.DataFrame
    multiple_testing: pd.DataFrame | None
    test_method: str
    sample_scope: str


def selected_index_to_pairs(mask: pd.Series) -> list[tuple[str, int]]:
    """Convert a boolean mask over a (factor, period) index into pairs.

    NaN counts as not selected.

    Raises:
        ValueError: If the mask is not indexed by (factor, period).
    """
    selected_index = mask.fillna(False).astype(bool)
    selected_index = selected_index[selected_index].index

    if not isinstance(selected_index, pd.MultiIndex):
        raise ValueError('selector result index must be a MultiIndex of (factor, period)')

    return [(str(factor_name), int(period)) for factor_name, period in selected_index]


class FactorSelector(ABC):
    """Strategy deciding which (factor, period) pairs are worth trading."""
    @abstractmethod
    def select(
        self,
        test_result: TestResult,
        **params,
    ) -> list[tuple[str, int]]:
        """Return the (factor, period) pairs this strategy approves."""
        ...


@register_factor_selector('bh')
class BHselector(FactorSelector):
    """Select pairs surviving Benjamini-Hochberg FDR control.

    The strictest option here: testing many factors makes some look
    significant by chance, and BH controls that false-discovery rate.
    """
    def select(self, test_result: TestResult, **params):
        """Return pairs flagged significant by the BH correction."""
        if test_result.multiple_testing is None:
            raise ValueError('BH selector requires multiple testing result')
        if 'BH_significant' not in test_result.multiple_testing.columns:
            raise ValueError('multiple_testing does not contain BH_significant')

        return selected_index_to_pairs(test_result.multiple_testing['BH_significant'])


@register_factor_selector("p_value")
class PValueSelector(FactorSelector):
    """Select pairs whose p-value falls below ``alpha`` (default 0.05).

    No multiple-testing correction, so with many factors expect some false
    positives; prefer ``bh`` when the factor set is large.
    """
    def select(
        self,
        test_result: TestResult,
        alpha: float = 0.05,
        **params,
    ) -> list[tuple[str, int]]:
        """Return pairs with p-value below ``alpha``."""
        if "p_value" not in test_result.summary.columns:
            raise ValueError("summary does not contain p_value")

        return selected_index_to_pairs(
            test_result.summary["p_value"] < alpha
        )


@register_factor_selector("t_stat")
class TStatSelector(FactorSelector):
    """Select pairs whose |t-stat| exceeds ``threshold`` (default 1.96).

    Equivalent to a two-sided 5% test, but stated as a t threshold.
    """
    def select(
        self,
        test_result: TestResult,
        threshold: float = 1.96,
        **params,
    ) -> list[tuple[str, int]]:
        """Return pairs whose |t-stat| exceeds ``threshold``."""
        if "t_stat" not in test_result.summary.columns:
            raise ValueError("summary does not contain t_stat")

        return selected_index_to_pairs(
            test_result.summary["t_stat"].abs() > threshold
        )


@register_factor_selector("ic_mean")
class ICMeanSelector(FactorSelector):
    """Select pairs whose |mean IC| exceeds ``threshold`` (default 0.02).

    An effect-size filter rather than a significance test: it keeps factors
    that are economically meaningful even if not statistically significant.
    """
    def select(
        self,
        test_result: TestResult,
        threshold: float = 0.02,
        **params,
    ) -> list[tuple[str, int]]:
        """Return pairs whose |mean IC| exceeds ``threshold``."""
        if "IC_mean" not in test_result.summary.columns:
            raise ValueError("summary does not contain IC_mean")

        return selected_index_to_pairs(
            test_result.summary["IC_mean"].abs() > threshold
        )


class CompositeSelector(FactorSelector):
    """Placeholder for combining several selectors. Not implemented."""
    def select(self, test_result, **params):
        """Not implemented."""
        ...
