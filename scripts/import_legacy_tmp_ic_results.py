"""Temporarily import legacy IC test files from ``tmp/ic_test`` into one run.

This is a local debugging utility, intentionally kept under the ignored
``scripts/`` directory.  It lets the research-results page be exercised with
real rows without claiming that the imported results were produced by the
selected historical run.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from quantmine.storage.database import get_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_KEY = re.compile(r"^(?P<factor>.+)_(?P<period>\d+)DaysHoldingPeriod$")


def load_root_env() -> None:
    """Load a local root ``.env`` without overwriting shell environment values."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_test_result_records(
    significance_path: Path,
    cs_ic_path: Path,
    *,
    run_id: int,
    variant_name: str,
    test_id: str,
    test_method: str,
    sample_scope: str,
) -> list[dict]:
    """Convert legacy significance and daily IC frames to ``test_results`` rows."""
    significance = pd.read_parquet(significance_path)
    cs_ic = pd.read_parquet(cs_ic_path)
    records: list[dict] = []

    for legacy_key, test_row in significance.iterrows():
        match = RESULT_KEY.fullmatch(str(legacy_key))
        if match is None:
            raise ValueError(f"Cannot parse factor and period from {legacy_key!r}")
        if legacy_key not in cs_ic.columns:
            raise KeyError(f"No IC time series column for {legacy_key!r}")

        ic_values = pd.to_numeric(cs_ic[legacy_key], errors="coerce").dropna()
        n = int(ic_values.size)
        ic_mean = float(ic_values.mean()) if n else None
        ic_std = float(ic_values.std(ddof=1)) if n > 1 else None
        ir = ic_mean / ic_std if ic_std not in (None, 0.0) else None

        records.append(
            {
                "run_id": run_id,
                "factor_name": match.group("factor"),
                "period": int(match.group("period")),
                "variant_name": variant_name,
                "test_id": test_id,
                "test_method": test_method,
                "sample_scope": sample_scope,
                "transforms": [],
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "ir": ir,
                "n": n,
                "t_stat": _optional_float(test_row.get("t")),
                "p_value": _optional_float(test_row.get("p_value")),
                "significant": _optional_bool(test_row.get("significant")),
                "bh_significant": _optional_bool(test_row.get("BH_significant")),
            }
        )
    return records


def _optional_float(value: object) -> float | None:
    return None if pd.isna(value) else float(value)


def _optional_bool(value: object) -> bool | None:
    return None if pd.isna(value) else bool(value)


def import_records(engine, records: list[dict]) -> int:
    """Upsert a single debug result set using the production table constraint."""
    metadata = MetaData()
    runs = Table("research_runs", metadata, autoload_with=engine)
    test_results = Table("test_results", metadata, autoload_with=engine)
    run_id = records[0]["run_id"] if records else None

    with engine.begin() as connection:
        exists = connection.execute(
            select(runs.c.run_id).where(runs.c.run_id == run_id)
        ).scalar_one_or_none()
        if exists is None:
            raise LookupError(f"research_runs has no run_id={run_id}")

        insert_stmt = pg_insert(test_results).values(records)
        key_columns = [
            "run_id",
            "variant_name",
            "test_id",
            "sample_scope",
            "factor_name",
            "period",
        ]
        update_columns = [
            "test_method",
            "transforms",
            "ic_mean",
            "ic_std",
            "ir",
            "n",
            "t_stat",
            "p_value",
            "significant",
            "bh_significant",
        ]
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=key_columns,
            set_={column: getattr(insert_stmt.excluded, column) for column in update_columns},
        )
        connection.execute(upsert_stmt)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--variant-name", default="legacy_tmp_raw")
    parser.add_argument("--test-id", default="legacy_tmp_bh")
    parser.add_argument("--test-method", default="legacy_tmp_ttest")
    parser.add_argument("--sample-scope", choices=("train", "test"), default="train")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = build_test_result_records(
        PROJECT_ROOT / "tmp" / "ic_test" / "significant_test.parquet",
        PROJECT_ROOT / "tmp" / "ic_test" / "CS_IC.parquet",
        run_id=args.run_id,
        variant_name=args.variant_name,
        test_id=args.test_id,
        test_method=args.test_method,
        sample_scope=args.sample_scope,
    )
    print(f"Prepared {len(records)} test_results rows; first row: {records[0] if records else None}")
    if args.dry_run:
        return

    load_root_env()
    written = import_records(get_engine(), records)
    print(
        f"Imported {written} rows into run_id={args.run_id} "
        f"({args.variant_name}/{args.test_id}/{args.sample_scope})."
    )


if __name__ == "__main__":
    main()
