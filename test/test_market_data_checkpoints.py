"""Tests for recoverable market-data batch checkpoint paths."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.contracts import DataBinding, MarketDataBundle
from quantmine.workflows.market_data_checkpoints import (
    load_market_data_batch_checkpoint,
    market_data_batch_checkpoint_dir,
    save_market_data_batch_checkpoint,
)


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("000001", "600000"),
        adjustment="hfq",
    )


def _bundle() -> MarketDataBundle:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame(
                {"000001": [10.0, 11.0], "600000": [20.0, 21.0]},
                index=dates,
            ),
            volume=pd.DataFrame(
                {"000001": [100.0, 110.0], "600000": [200.0, 210.0]},
                index=dates,
            ),
            market_cap=pd.DataFrame(
                {"000001": [1_000.0, 1_100.0], "600000": [2_000.0, 2_100.0]},
                index=dates,
            ),
        ),
        calendar=pd.DatetimeIndex(dates),
        metadata={"provider": "fixture"},
    )


def test_market_data_batch_checkpoint_dir_is_deterministic(
    tmp_path: Path,
) -> None:
    checkpoint_id = "a" * 64

    actual = market_data_batch_checkpoint_dir(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=7,
    )

    assert actual == (
        tmp_path
        / "market_data_refresh"
        / checkpoint_id
        / "batch_000007"
    ).resolve()
    assert actual.is_relative_to(tmp_path.resolve())


def test_market_data_batch_checkpoint_dir_requires_existing_root(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="checkpoint root"):
        market_data_batch_checkpoint_dir(
            missing,
            checkpoint_id="a" * 64,
            batch_number=1,
        )


@pytest.mark.parametrize(
    "checkpoint_id",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "../" + "a" * 64,
        123,
    ],
)
def test_market_data_batch_checkpoint_dir_rejects_invalid_checkpoint_id(
    tmp_path: Path,
    checkpoint_id: object,
) -> None:
    with pytest.raises(ValueError, match="checkpoint_id"):
        market_data_batch_checkpoint_dir(  # type: ignore[arg-type]
            tmp_path,
            checkpoint_id=checkpoint_id,
            batch_number=1,
        )


@pytest.mark.parametrize("batch_number", [0, -1, True, 1.5, "1"])
def test_market_data_batch_checkpoint_dir_rejects_invalid_batch_number(
    tmp_path: Path,
    batch_number: object,
) -> None:
    with pytest.raises(ValueError, match="batch_number"):
        market_data_batch_checkpoint_dir(  # type: ignore[arg-type]
            tmp_path,
            checkpoint_id="a" * 64,
            batch_number=batch_number,
        )


def test_save_market_data_batch_checkpoint_writes_complete_version(
    tmp_path: Path,
) -> None:
    checkpoint_id = "b" * 64

    output_dir = save_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=2,
        binding=_binding(),
        bundle=_bundle(),
    )

    assert output_dir.name == "batch_000002"
    assert {path.name for path in output_dir.iterdir()} == {
        "calendar.parquet",
        "close.parquet",
        "manifest.json",
        "market_cap.parquet",
        "volume.parquet",
    }
    manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest == {
        "batch_number": 2,
        "checkpoint_id": checkpoint_id,
        "fields": ["close", "market_cap", "volume"],
        "has_calendar": True,
        "metadata": {"provider": "fixture"},
        "schema_version": "market_data_batch_checkpoint_v1",
        "tickers": ["000001", "600000"],
    }


def test_save_market_data_batch_checkpoint_never_overwrites(
    tmp_path: Path,
) -> None:
    arguments = {
        "checkpoint_id": "c" * 64,
        "batch_number": 1,
        "binding": _binding(),
        "bundle": _bundle(),
    }
    save_market_data_batch_checkpoint(tmp_path, **arguments)

    with pytest.raises(FileExistsError, match="already exists"):
        save_market_data_batch_checkpoint(tmp_path, **arguments)


def test_save_market_data_batch_checkpoint_rejects_ticker_mismatch(
    tmp_path: Path,
) -> None:
    binding = DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("000001",),
    )

    with pytest.raises(ValueError, match="tickers do not match"):
        save_market_data_batch_checkpoint(
            tmp_path,
            checkpoint_id="d" * 64,
            batch_number=1,
            binding=binding,
            bundle=_bundle(),
        )


def test_save_market_data_batch_checkpoint_cleans_failed_staging_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkpoint_id = "e" * 64

    def fail_write(*args, **kwargs) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_write)

    with pytest.raises(OSError, match="simulated disk failure"):
        save_market_data_batch_checkpoint(
            tmp_path,
            checkpoint_id=checkpoint_id,
            batch_number=1,
            binding=_binding(),
            bundle=_bundle(),
        )

    parent = tmp_path / "market_data_refresh" / checkpoint_id
    assert not (parent / "batch_000001").exists()
    assert list(tmp_path.glob(".market-data-staging-*")) == []


def test_load_market_data_batch_checkpoint_returns_none_when_absent(
    tmp_path: Path,
) -> None:
    assert load_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id="f" * 64,
        batch_number=1,
        binding=_binding(),
    ) is None


def test_load_market_data_batch_checkpoint_restores_complete_bundle(
    tmp_path: Path,
) -> None:
    checkpoint_id = "1" * 64
    expected = _bundle()
    save_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=3,
        binding=_binding(),
        bundle=expected,
    )

    actual = load_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=3,
        binding=_binding(),
    )

    assert actual is not None
    pd.testing.assert_frame_equal(actual.market.close, expected.market.close)
    pd.testing.assert_frame_equal(actual.market.volume, expected.market.volume)
    pd.testing.assert_frame_equal(actual.market.market_cap, expected.market.market_cap)
    assert actual.calendar.equals(expected.calendar)
    assert actual.metadata == expected.metadata


def test_load_market_data_batch_checkpoint_rejects_other_binding(
    tmp_path: Path,
) -> None:
    checkpoint_id = "2" * 64
    save_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=1,
        binding=_binding(),
        bundle=_bundle(),
    )
    other_binding = DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("600000", "000001"),
    )

    with pytest.raises(ValueError, match="invalid tickers"):
        load_market_data_batch_checkpoint(
            tmp_path,
            checkpoint_id=checkpoint_id,
            batch_number=1,
            binding=other_binding,
        )


def test_load_market_data_batch_checkpoint_rejects_corrupt_manifest(
    tmp_path: Path,
) -> None:
    checkpoint_id = "3" * 64
    output_dir = save_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=1,
        binding=_binding(),
        bundle=_bundle(),
    )
    (output_dir / "manifest.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest is invalid"):
        load_market_data_batch_checkpoint(
            tmp_path,
            checkpoint_id=checkpoint_id,
            batch_number=1,
            binding=_binding(),
        )


def test_load_market_data_batch_checkpoint_rejects_missing_field_file(
    tmp_path: Path,
) -> None:
    checkpoint_id = "4" * 64
    output_dir = save_market_data_batch_checkpoint(
        tmp_path,
        checkpoint_id=checkpoint_id,
        batch_number=1,
        binding=_binding(),
        bundle=_bundle(),
    )
    (output_dir / "volume.parquet").unlink()

    with pytest.raises(ValueError, match="missing volume.parquet"):
        load_market_data_batch_checkpoint(
            tmp_path,
            checkpoint_id=checkpoint_id,
            batch_number=1,
            binding=_binding(),
        )
