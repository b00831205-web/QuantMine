from pathlib import Path

import pandas as pd

from pipelines.task_1 import determine_download_start


def test_download_start_uses_cleaned_history_not_staging_files(tmp_path):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    index = pd.to_datetime(["2026-07-20", "2026-07-21"])
    pd.DataFrame({"AAPL": [1.0, 2.0]}, index=index).to_parquet(
        processed_dir / "processed_close.parquet"
    )
    pd.DataFrame({"AAPL": [10, 20]}, index=index).to_parquet(
        processed_dir / "processed_volume.parquet"
    )

    assert determine_download_start(
        processed_dir,
        fallback_start="2015-01-01",
    ) == pd.Timestamp("2026-07-22")


def test_download_start_falls_back_when_cleaned_history_is_missing(tmp_path):
    assert determine_download_start(
        Path(tmp_path),
        fallback_start="2015-01-01",
    ) == pd.Timestamp("2015-01-01")
