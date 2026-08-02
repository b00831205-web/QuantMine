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

    engine = get_engine()
    run_id = find_run_id_by_airflow_batch(engine, args.batch)

    result = save_daily_market_data(engine, close, volume, run_id)
    print(
        f"market bars updated complete: run_id={run_id}, date={args.date}, "
        f"bars={result['bars_written']}, "
        f"snapshots={result['snapshots_written']}"
    )
if __name__ == '__main__':
    main()
