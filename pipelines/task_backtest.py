import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.storage.backtest import save_backtest_workflow_results
from quantmine.storage.database import get_engine
from quantmine.storage.ic import load_ic_variants, load_test_results
from quantmine.storage.runs import find_run_id_by_airflow_batch
from quantmine.workflows.backtest_workflow import run_backtest_workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_backtest_config(config_path: Path) -> dict:
    with config_path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if "backtest" not in config:
        raise KeyError('Missing "backtest" section in config file')

    return config["backtest"]


def main():
    parser = argparse.ArgumentParser(
        description="Run and persist config-driven backtests",
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    engine = get_engine()
    run_id = find_run_id_by_airflow_batch(engine, args.batch)

    close = pd.read_parquet(
        PROJECT_ROOT / "data" / "processed" / "processed_close.parquet"
    )
    # 市值宽表(date×ticker), 与 close 同形; 供 weighting: {name: mcap} 使用。
    # 缺失时传 None, 等权路径不需要它。
    cap_path = PROJECT_ROOT / "data" / "processed" / "processed_market_cap.parquet"
    market_cap = pd.read_parquet(cap_path) if cap_path.exists() else None
    backtest_config = load_backtest_config(PROJECT_ROOT / args.config)

    variants = load_ic_variants(engine, run_id)
    test_results = load_test_results(engine, run_id)

    workflow_results = run_backtest_workflow(
        close=close,
        variants=variants,
        test_results=test_results,
        backtest_config=backtest_config,
        constituents=None,
        market_cap=market_cap,
    )

    safe_batch = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.batch)
    artifact_dir = (
        PROJECT_ROOT
        / "data"
        / "artifacts"
        / "backtest"
        / safe_batch
    )

    saved_counts = save_backtest_workflow_results(
        engine=engine,
        workflow_results=workflow_results,
        run_id=run_id,
        backtest_config=backtest_config,
        artifact_dir=artifact_dir,
    )

    print(
        f"Backtest workflow completed: run_id={run_id}, "
        f"saved={saved_counts}"
    )


if __name__ == "__main__":
    main()