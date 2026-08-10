"""DAG step 2: clean the raw increment and merge it into the processed set.

Drops columns whose missing rate exceeds the threshold, forward-fills the rest,
then folds the result into the cumulative processed file. The raw staging file
is removed once merged. Runs the same routine for close, volume, shares, and
market cap.
"""
import pandas as pd
import argparse
import glob
import os


def drop_sparse_columns(
    new_data: pd.DataFrame,
    missing_threshold: float,
) -> tuple[pd.DataFrame, list[str]]:
    """Drop tickers missing more than ``missing_threshold`` of the increment.

    Returns:
        The surviving frame, forward-filled, and the names dropped.
    """
    missing_pct = new_data.isnull().mean()
    usable = missing_pct[missing_pct < missing_threshold].index.tolist()
    dropped = missing_pct[missing_pct >= missing_threshold].index.tolist()
    return new_data[usable].ffill(), dropped


def merge_increment(
    new_data: pd.DataFrame,
    existing: pd.DataFrame | None,
) -> pd.DataFrame:
    """Fold an increment into the cumulative frame at ``(date, ticker)`` grain.

    Args:
        new_data: The cleaned increment.
        existing: The cumulative frame, or None on the first run.

    Returns:
        The merged frame, sorted by date. New values win; where the increment is
        NaN the existing observation survives, so one ticker missing from a
        download cannot erase history that was already collected.

    Notes:
        Cell-level merging is load-bearing, not tidiness. The obvious
        alternative -- ``concat`` then drop duplicate index entries keeping the
        last -- works only while increments cover new dates exclusively. A
        backfill carries a handful of columns over dates the cumulative frame
        already holds; ``concat`` pads the rest of that row with NaN, and
        keeping the last row then silently wipes every other ticker on those
        dates.
    """
    if existing is None or existing.empty:
        return new_data.sort_index()
    return new_data.combine_first(existing).sort_index()


def main() -> None:
    parse = argparse.ArgumentParser(description="clean and merge raw data")
    parse.add_argument("--date", type=str, required=True)
    parse.add_argument("--batch", type=str, required=True)
    parse.add_argument("--missing_threshold", type=float, default=0.3)
    args = parse.parse_args()

    tmp_dir = os.path.join(os.getcwd(), "data/processed")

    # one shared routine so the close/volume handling isn't written twice
    def process(kind, final_name):
        final_path = os.path.join(tmp_dir, final_name)
        # task_1 writes one staging file per download job (jobs cover different
        # date ranges). The bare name is the legacy single-job layout, kept so a
        # run staged by an older task_1 still merges.
        raw_paths = sorted(glob.glob(os.path.join(tmp_dir, f"{kind}.part*.parquet")))
        legacy = os.path.join(tmp_dir, f"{kind}.parquet")
        if os.path.exists(legacy):
            raw_paths.append(legacy)

        if not raw_paths:
            print(f"[{args.batch}] {kind} has no new data, skipping")
            return

        for raw_path in raw_paths:
            # Sparsity is scored per file, against that job's own date range.
            # Pooling the files first would make every incremental ticker look
            # ~100% missing over a backfill's decade-long index and drop them.
            new_data, dropped_cols = drop_sparse_columns(
                pd.read_parquet(raw_path), args.missing_threshold
            )
            if dropped_cols:
                print(
                    f"[{args.batch}] {os.path.basename(raw_path)}: dropping "
                    f"{len(dropped_cols)} columns above the missing-data "
                    f"threshold: {dropped_cols}"
                )
            existing = (
                pd.read_parquet(final_path) if os.path.exists(final_path) else None
            )
            merge_increment(new_data, existing).to_parquet(final_path)
            os.remove(raw_path)
        print(f"[{args.batch}] {final_name} merge complete "
              f"({len(raw_paths)} staging file(s))")

    # process close and volume separately
    process("close", "processed_close.parquet")
    process("volume", "processed_volume.parquet")
    process("shares", "processed_shares.parquet")
    process("market_cap", "processed_market_cap.parquet")


if __name__ == "__main__":
    main()
