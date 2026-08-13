"""Intermediates are computed, but never presented as findings."""

import pandas as pd

from quantmine.factor_mining import INTERMEDIATE_FACTORS
from quantmine.factor_register import FACTOR_REGISTRY, drop_intermediates


def test_intermediates_stay_registered_because_real_factors_consume_them():
    """Unregistering them would break four genuine factors.

    ``TwentyDayVolatility``, ``TwentyDayNegVotality`` and ``VolPriceCorr`` take
    ``daily_return``; ``ShortTermReversal`` takes ``excess_return``. The registry
    resolves those by parameter name, so the entries have to stay.
    """
    for name in INTERMEDIATE_FACTORS:
        assert name in FACTOR_REGISTRY


def test_drop_intermediates_removes_them_from_the_tested_set():
    computed = {name: pd.DataFrame() for name in FACTOR_REGISTRY}

    kept = drop_intermediates(computed)

    assert set(kept) == set(FACTOR_REGISTRY) - INTERMEDIATE_FACTORS
    # A stock's own daily return is the thing a factor is supposed to predict.
    # Scoring it against forward returns measures autocorrelation, not selection.
    assert "daily_return" not in kept
    # Cross-sectionally identical to daily_return: subtracting one scalar per
    # date from every stock cannot reorder them.
    assert "excess_return" not in kept


def test_short_term_reversal_survives_as_the_real_reversal_factor():
    """The effect is not being suppressed, only its duplicate."""
    kept = drop_intermediates({name: pd.DataFrame() for name in FACTOR_REGISTRY})

    assert "ShortTermReversal" in kept
