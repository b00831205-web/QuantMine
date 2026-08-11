import pandas as pd
from glob import glob
import re
from pathlib import Path
from quantmine.storage.database import get_engine
from quantmine.storage.backtest import save_backtest_metrics, save_backtest_results, build_backtest_rows
import argparse

FILE_PATTERN = re.compile(
    r'(?P<period>\d+)DaysHoldingPeriod_'
    r'(?P<factor_name>.+)_summary_after_cost\.parquet$'
)
RETURN_FILE_PATTERN = re.compile(r'backtest_(?P<factor_name>.+)_(?P<period>\d+)daysholdingperiod\.parquet$')

def build_legacy_backtest_metric_rows(
        *,
        summary: pd.DataFrame,
        monotonicity: pd.DataFrame | None,
        run_id: int,
        variant_name: str,
        backtest_id: str,
        test_id: str,
        factor_name: str,
        period : int
) -> pd.DataFrame:
    rows = []
    for quantile, summary_values in summary.iterrows():
        if quantile == 'long_short':
            quantile_rank = 0
        else:
            quantile_rank = int(str(quantile).removeprefix('Q'))
        for metric_name, metric_value in summary_values.items():
            rows.append(
                {'run_id': run_id,
                 'variant_name': variant_name,
                 'backtest_id': backtest_id,
                 'test_id': test_id,
                 'factor_name': factor_name,
                 'period': period,
                 'quantile_rank': quantile_rank,
                 'metric_name': metric_name,
                 'metric_value': None if pd.isna(metric_value) else float(metric_value),
                 'metric_metadata': {},
                 }
            )
    if monotonicity is not None:

        mono_values = monotonicity.iloc[0]
        for metric_name, metric_value in mono_values.items():
            rows.append({
                'run_id':run_id,
                'variant_name': variant_name,
                'backtest_id': backtest_id,
                'test_id': test_id,
                'factor_name': factor_name,
                'period': period,
                'quantile_rank': 0,
                'metric_name': f'monotonicity_{metric_name}',
                'metric_value': None if pd.isna(metric_value) else float(metric_value),
                'metric_metadata': {}
            }
        )
    return pd.DataFrame(rows)

def discover_legacy_backtest_cases(backtest_dir: Path):
    result = []
    for summary_path in backtest_dir.glob("*_summary_after_cost.parquet"):
        match = FILE_PATTERN.fullmatch(summary_path.name)
        if match is None:
            continue
        period = int(match['period'])
        factor_name = match['factor_name']
        mono_path = backtest_dir/ f'{period}DaysHoldingPeriod_{factor_name}_mono.parquet'
        if not mono_path.exists():
            mono_path = None
        result.append({
            'period':period,
            'factor_name':factor_name,
            'summary_path':summary_path,
            'monotonicity_path': mono_path,
        })
    return result

def build_all_legacy_backtest_metric_rows(backtest_dir: Path,
                                          run_id : int,
                                          variant_name: str,
                                          backtest_id: str,
                                          test_id: str
                                          ):
    frames = []
    for case in discover_legacy_backtest_cases(backtest_dir):
        summary = pd.read_parquet(case['summary_path'])
        mono_path = case['monotonicity_path']
        monotonicity = (None if mono_path is None
                        else pd.read_parquet(mono_path))
        rows = build_legacy_backtest_metric_rows(
            summary = summary,
            monotonicity = monotonicity,
            run_id = run_id,
            variant_name= variant_name,
            backtest_id = backtest_id,
            test_id = test_id,
            factor_name = case['factor_name'],
            period = case['period']
        )
        frames.append(rows)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index= True)

def discover_legacy_backtest_return_cases(backtest_dir: Path) -> list[dict]:
    result = []
    for path in backtest_dir.glob("backtest_*daysholdingperiod.parquet"):
        match = RETURN_FILE_PATTERN.fullmatch(path.name)
        if match is None:
            continue
        result.append({
            'factor_name':match['factor_name'],
            'period': int(match['period']),
            'path': path,
        })
    return result

def build_all_legacy_backtest_return_rows(
        *,
        backtest_dir: Path,
        run_id: int,
        variant_name: str,
        backtest_id: str,
        test_id: str
) -> pd.DataFrame:
    all_returns = {}

    for case in discover_legacy_backtest_return_cases(backtest_dir):
        daily_returns = pd.read_parquet(case['path'])
        all_returns[(case['factor_name'], case['period'])] = daily_returns

    if not all_returns:
        return pd.DataFrame()

    return build_backtest_rows(
        all_returns,
        run_id = run_id,
        variant_name= variant_name,
        backtest_id = backtest_id,
        test_id=test_id
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--backtest-dir",
        type=Path,
        default=Path("tmp/back_test"),
    )
    parser.add_argument("--variant-name", default="legacy_tmp_raw")
    parser.add_argument("--backtest-id", default="legacy_tmp_after_cost")
    parser.add_argument("--test-id", default="legacy_tmp_bh")
    args = parser.parse_args()

    metric_rows = build_all_legacy_backtest_metric_rows(
    backtest_dir=args.backtest_dir,
    run_id=args.run_id,
    variant_name=args.variant_name,
    backtest_id=args.backtest_id,
    test_id=args.test_id,
)
    return_rows = build_all_legacy_backtest_return_rows(
        backtest_dir = Path(args.backtest_dir),
        run_id = args.run_id,
        variant_name = args.variant_name,
        backtest_id = args.backtest_id,
        test_id = args.test_id
    )

    engine = get_engine()

    saved_count = save_backtest_metrics(engine, metric_rows)
    saved_return_count = save_backtest_results(engine, return_rows)

    print(f"Imported {saved_count} legacy backtest metric rows."
          f'{saved_return_count} daily return rows for run {args.run_id}')

if __name__ == "__main__":
    main()