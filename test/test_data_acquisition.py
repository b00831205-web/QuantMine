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
        with_market_cap=False,  # 只测价格批次逻辑, 不触发 get_shares_full/mcap 下载
    )

    assert calls == [["AAPL", "GOOG"], ["MSFT"]]


def test_empty_batch_is_not_retried_once_a_batch_has_returned_rows(monkeypatch, tmp_path):
    """A healthy session turns an empty frame into an answer, not a rate-limit guess.

    Yahoo reports throttling as an empty frame too, so an isolated empty
    response is genuinely ambiguous. But once another batch in the same run has
    returned rows, throttling is ruled out -- and sleeping 60s twice to re-ask
    about a long-delisted name is pure dead time.
    """
    sleeps = []
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: sleeps.append(seconds))

    attempts = []

    def fake_download(tickers, **kwargs):
        attempts.append(list(tickers))
        return pd.DataFrame()

    monkeypatch.setattr(acquisition.yf, "download", fake_download)

    acquisition.download_batch_with_retry(
        batch=["DEAD"],
        start_date="2015-01-01",
        end_date="2015-03-13",
        batch_index=1,
        task_checkpoint_dir=str(tmp_path),
        session_healthy=True,
    )

    assert len(attempts) == 1, "a healthy session must not re-ask for an empty batch"
    assert sleeps == [], "no backoff should be paid for a known-empty response"


def test_empty_batch_still_retries_while_the_session_is_unproven(monkeypatch, tmp_path):
    """With nothing downloaded yet, an empty frame may still be throttling.

    Dropping the retry here would let a rate-limited first batch look like a
    delisted one, silently shrinking the universe -- the survivorship bias the
    point-in-time membership work exists to avoid.
    """
    sleeps = []
    monkeypatch.setattr(acquisition.time, "sleep", lambda seconds: sleeps.append(seconds))

    attempts = []

    def fake_download(tickers, **kwargs):
        attempts.append(list(tickers))
        return pd.DataFrame()

    monkeypatch.setattr(acquisition.yf, "download", fake_download)

    acquisition.download_batch_with_retry(
        batch=["MAYBE"],
        start_date="2015-01-01",
        end_date="2015-03-13",
        batch_index=1,
        task_checkpoint_dir=str(tmp_path),
        max_retries=3,
        wait=60,
        session_healthy=False,
    )

    assert len(attempts) == 3, "an unproven session must still exhaust its retries"
    assert sleeps == [60, 60]
