"""DAG step 3: compute all registered factors from the processed data.

Importing ``factor_mining`` is what registers the built-in factors, so the
registry is populated before ``calculate_all_factors`` walks it.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  #locate the repo root when executed as a script

from quantmine.factor_register import calculate_all_factors, build_param_pool
from quantmine.datareader import MarketData
from quantmine import factor_mining  # noqa: F401  importing registers the built-in factors
import pandas as pd
import os
import argparse

if __name__ == "__main__":
    parse = argparse.ArgumentParser(description="calculate quantitative factors")
    parse.add_argument("--date", type= str, required=True)
    parse.add_argument("--batch", type= str, required=True)
    parse.add_argument("--days", type=int, required=False, default = 5)
    parse.add_argument("--halflife", type=int, required=False, default = 10)
    parse.add_argument("--period", type=int, required=False, default =20)
    args = parse.parse_args()


    close_path = os.path.join(os.getcwd(),'data/processed', "processed_close.parquet")
    volume_path = os.path.join(os.getcwd(),'data/processed', "processed_volume.parquet")
    factors_dir = os.path.join(os.getcwd(),'tmp/factors')

    def data_proceeding(close_path: str, volume_path: str, factors_dir: str) -> dict:
        #factor computation needs the full history window, not just the newly appended rows
        if not os.path.exists(close_path) or not os.path.exists(volume_path):
            print("file not found")
            return {}
        close = pd.read_parquet(close_path)
        volume = pd.read_parquet(volume_path)
        data = MarketData(close=close, volume=volume)

        pool = build_param_pool(data, day=args.days, halflife=args.halflife, period=args.period)
        failed, factors = calculate_all_factors(pool)
        if failed:
            print(f"factors failed to compute: {list(failed.keys())}")

        os.makedirs(factors_dir, exist_ok=True)
        for name, df in factors.items():
            if df is not None:
                df.to_parquet(os.path.join(factors_dir, f"{name}.parquet"))
        print("data_proceeding_complete")
        return factors

    data_proceeding(close_path=close_path, volume_path=volume_path, factors_dir=factors_dir)
