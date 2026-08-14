from sqlalchemy import create_engine, text

from app.reports.data import _fetch_attribution

TERMS = ("Alpha", "Mkt-RF", "SMB", "HML", "Mom")


def _engine_with_attribution(rows: list[dict]):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE attribution_results (
                    run_id INTEGER NOT NULL,
                    variant_name TEXT NOT NULL,
                    backtest_id TEXT NOT NULL,
                    test_id TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    period INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    coef FLOAT, std_err FLOAT, t_stat FLOAT, p_value FLOAT,
                    ci_lo FLOAT, ci_hi FLOAT,
                    r2 FLOAT, adj_r2 FLOAT, n INTEGER, alpha_annual FLOAT
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO attribution_results (run_id, variant_name, "
                "backtest_id, test_id, factor_name, period, term, coef, std_err, "
                "t_stat, p_value, ci_lo, ci_hi, r2, adj_r2, n, alpha_annual) "
                "VALUES (:run_id, :variant_name, :backtest_id, :test_id, "
                ":factor_name, :period, :term, :coef, :std_err, :t_stat, "
                ":p_value, :ci_lo, :ci_hi, :r2, :adj_r2, :n, :alpha_annual)"
            ),
            rows,
        )
    return engine


def _terms_for(backtest_id: str, *, alpha_annual: float):
    return [
        {
            "run_id": 1, "variant_name": "orthogonalized", "backtest_id": backtest_id,
            "test_id": "newey_orthogonalized", "factor_name": "TwentyDayAvgVol",
            "period": 5, "term": term,
            "coef": 0.1, "std_err": 0.01, "t_stat": 2.0, "p_value": 0.04,
            "ci_lo": 0.05, "ci_hi": 0.15,
            "r2": 0.3, "adj_r2": 0.29, "n": 500, "alpha_annual": alpha_annual,
        }
        for term in TERMS
    ]


def test_two_jobs_sharing_a_variant_get_their_own_block() -> None:
    """Terms are appended to a block rather than overwritten, so a shared key
    does not lose rows -- it produces one block carrying both regressions'
    terms interleaved, with the model stats of whichever was read first."""
    engine = _engine_with_attribution([
        *_terms_for("orthogonalized_quintile", alpha_annual=0.08),
        *_terms_for("mcap_quintile", alpha_annual=0.02),
    ])

    blocks = _fetch_attribution(engine, 1, None)

    assert len(blocks) == 2
    for block in blocks:
        assert len(block["terms"]) == len(TERMS)
    by_label = {b["variant"]: b for b in blocks}
    assert set(by_label) == {
        "mcap_quintile · orthogonalized · TwentyDayAvgVol · 5d",
        "orthogonalized_quintile · orthogonalized · TwentyDayAvgVol · 5d",
    }
    assert by_label[
        "orthogonalized_quintile · orthogonalized · TwentyDayAvgVol · 5d"
    ]["alpha_annual"] == "8.0%"
    assert by_label[
        "mcap_quintile · orthogonalized · TwentyDayAvgVol · 5d"
    ]["alpha_annual"] == "2.0%"


def test_missing_table_degrades_to_no_section() -> None:
    """A database that predates the attribution table must not break the whole
    report; section 03 keeps its "not stored" note instead."""
    engine = create_engine("sqlite://")

    assert _fetch_attribution(engine, 1, None) == []
