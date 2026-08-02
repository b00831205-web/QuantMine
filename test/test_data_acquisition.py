import json

import pandas as pd

from quantmine import data_acquisition as acquisition


def test_save_blacklist_preserves_existing_tickers(tmp_path):
    blacklist_path = tmp_path / "blacklist.json"
    blacklist_path.write_text(json.dumps(["OLD"]), encoding="utf-8")

    acquisition.save_blacklist(["NEW"], str(tmp_path))

    assert acquisition.load_blacklist(str(tmp_path)) == {"OLD", "NEW"}


def test_data_acquisition_uses_stable_ticker_batches(monkeypatch, tmp_path):
    calls = []
    dates = pd.to_datetime(["2026-07-23"])

    def fake_download(tickers, **kwargs):
        calls.append(list(tickers))
        columns = pd.MultiIndex.from_product(
            [["Close", "Volume"], tickers],
        )
        return pd.DataFrame([[1.0] * len(columns)], index=dates, columns=columns)

    monkeypatch.setattr(acquisition.yf, "download", fake_download)
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: None)

    acquisition.data_acquisition(
        tickers=["MSFT", "AAPL", "MSFT", "GOOG"],
        start_date="2026-07-23",
        end_date="2026-07-24",
        batch_size=2,
        max_retries=1,
        wait=0,
        checkpoint_dir=str(tmp_path),
    )

    assert calls == [["AAPL", "GOOG"], ["MSFT"]]
