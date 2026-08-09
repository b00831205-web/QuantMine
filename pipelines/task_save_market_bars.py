import sys
from pathlib import Path
import pandas as pd
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.storage.database import get_engine
from quantmine.storage.runs import find_run_id_by_airflow_batch
from quantmine.workflows.market import save_daily_market_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(
        description= 'store the raw close and volume data, and get the snap shot'
    )
    parser.add_argument('--date', required = True)
    parser.add_argument('--batch', required = True)
    args= parser.parse_args()
    close = pd.read_parquet(
        PROJECT_ROOT/'data'/'processed'/'processed_close.parquet'
    )
    volume = pd.read_parquet(
        PROJECT_ROOT/'data'/'processed'/'processed_volume.parquet'
    )

    # shares/market_cap 可能缺失(某次全抓不到时 task_2 不产出); build_market_bars 会按 None 优雅补 NA
    shares_path = PROJECT_ROOT / 'data' / 'processed' / 'processed_shares.parquet'
    cap_path = PROJECT_ROOT / 'data' / 'processed' / 'processed_market_cap.parquet'
    shares = pd.read_parquet(shares_path) if shares_path.exists() else None
    market_cap = pd.read_parquet(cap_path) if cap_path.exists() else None

    engine = get_engine()
    run_id = find_run_id_by_airflow_batch(engine, args.batch)

    result = save_daily_market_data(engine, close, volume, run_id, shares = shares, market_cap = market_cap)
    print(
        f"market bars updated complete: run_id={run_id}, date={args.date}, "
        f"bars={result['bars_written']}, "
        f"snapshots={result['snapshots_written']}"
    )
if __name__ == '__main__':
    main()
