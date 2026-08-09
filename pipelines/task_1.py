"""Download the market-data increment required by the daily pipeline."""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.data_acquisition import data_acquisition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_START = pd.Timestamp("2015-01-01")


def determine_download_start(
    processed_dir: Path,
    *,
    fallback_start: str | pd.Timestamp,
) -> pd.Timestamp:
    """Return the day after the latest fully cleaned close/volume observation."""
    close_path = processed_dir / "processed_close.parquet"
    volume_path = processed_dir / "processed_volume.parquet"
    if not close_path.exists() or not volume_path.exists():
        return pd.Timestamp(fallback_start)

    close = pd.read_parquet(close_path)
    volume = pd.read_parquet(volume_path)
    if close.empty or volume.empty:
        return pd.Timestamp(fallback_start)

    last_complete_date = min(
        pd.Timestamp(close.index.max()),
        pd.Timestamp(volume.index.max()),
    )
    return last_complete_date.normalize() + pd.Timedelta(days=1)


def load_relevant_tickers(
    membership_path: Path,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> list[str]:
    """Load members whose membership overlaps the requested date window."""
    membership = pd.read_csv(membership_path)
    required = {"ticker", "start_date", "end_date"}
    missing = required.difference(membership.columns)
    if missing:
        raise ValueError(
            f"Membership file is missing columns: {sorted(missing)}"
        )

    membership["start_date"] = pd.to_datetime(
        membership["start_date"],
        errors="coerce",
    )
    membership["end_date"] = pd.to_datetime(
        membership["end_date"],
        errors="coerce",
    )
    overlaps_window = (
        membership["start_date"].fillna(pd.Timestamp.min) <= end_date
    ) & (
        membership["end_date"].isna()
        | (membership["end_date"] >= start_date)
    )
    tickers = {
        str(ticker).replace(".", "-")
        for ticker in membership.loc[overlaps_window, "ticker"].dropna()
    }
    tickers.add("SPY")
    return sorted(tickers)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the next raw market-data increment",
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()

    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    staging_close_path = processed_dir / "close.parquet"
    staging_volume_path = processed_dir / "volume.parquet"
    staging_shares_path = processed_dir / 'shares.parquet'
    staging_cap_path = processed_dir / 'market_cap.parquet'

    requested_date = pd.Timestamp(args.date).normalize()
    start_date = determine_download_start(
        processed_dir,
        fallback_start=ANALYSIS_START,
    )
    if start_date > requested_date:
        print(f"{args.batch} is current; no market-data download is needed")
        return

    default_membership_path = (
        PROJECT_ROOT.parent / "sp500" / "sp500_ticker_start_end.csv"
    )
    membership_path = Path(
        os.environ.get("SP500_MEMBERSHIP_CSV", default_membership_path)
    ).expanduser()
    if not membership_path.exists():
        raise FileNotFoundError(
            "S&P 500 membership file not found. Set SP500_MEMBERSHIP_CSV "
            f"to a valid CSV path (looked for {membership_path})."
        )

    tickers = load_relevant_tickers(
        membership_path,
        start_date=start_date,
        end_date=requested_date,
    )
    print(
        f"Downloading {len(tickers)} tickers from "
        f"{start_date.date()} through {requested_date.date()}"
    )

    # yfinance treats ``end`` as exclusive, so request one day beyond ds.
    exclusive_end = requested_date + pd.Timedelta(days=1)
    close, volume, shares, market_cap = data_acquisition(
        tickers=tickers,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=exclusive_end.strftime("%Y-%m-%d"),
        shares_start_date=ANALYSIS_START.strftime("%Y-%m-%d"),
        batch_size=20,  # 小批次 + 串行下载, 降低触发Yahoo限流的概率
        
    )
    shares.to_parquet(staging_shares_path)
    market_cap.to_parquet(staging_cap_path)
    close.to_parquet(staging_close_path)
    volume.to_parquet(staging_volume_path)
    print(
        f"Downloaded staging data to '{staging_close_path} ', '{staging_volume_path}'"
        f"'{staging_volume_path}' and '{staging_cap_path}'"
    )


if __name__ == "__main__":
    main()
