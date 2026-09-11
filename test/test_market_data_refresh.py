"""Tests for source-neutral market-data materialization."""

from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path

import pandas as pd
import pytest

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)
from quantmine.storage.connections import (
    ConnectionKind,
    ConnectionRegistry,
    DataConnectionConfig,
)
from quantmine.workflows.market_data_publication import MarketDataPublishSpec
from quantmine.workflows.market_data_refresh import (
    MarketDataRefreshPolicy,
    load_market_data_batches,
    market_data_checkpoint_id,
    merge_market_data_batches,
    partition_data_binding,
    refresh_market_data,
)


class RecordingSource:
    def __init__(self) -> None:
        self.calls: list[tuple[DataBinding, SourceContext]] = []

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        self.calls.append((binding, context))
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {"000001": [10.0, 11.0]},
                    index=dates,
                ),
                volume=pd.DataFrame(
                    {"000001": [1_000, 1_100]},
                    index=dates,
                ),
            )
        )


class BatchSource:
    def __init__(
        self,
        *,
        failing_batch: tuple[str, ...] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failing_batch = failing_batch
        self.failure = failure
        self.failed_once = False

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        del context
        self.calls.append(binding.tickers)
        if (
            binding.tickers == self.failing_batch
            and not self.failed_once
            and self.failure is not None
        ):
            self.failed_once = True
            raise self.failure

        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(
                    {ticker: [10.0, 11.0] for ticker in binding.tickers},
                    index=dates,
                ),
                volume=pd.DataFrame(
                    {ticker: [100.0, 110.0] for ticker in binding.tickers},
                    index=dates,
                ),
            ),
            calendar=pd.DatetimeIndex(dates),
        )


def _component(plugin: RecordingSource) -> DataSourceComponent:
    return DataSourceComponent(
        id="recording_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
            }
        ),
        plugin=plugin,
    )


def _binding() -> DataBinding:
    return DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("000001",),
        adjustment="hfq",
    )


def _spec() -> MarketDataPublishSpec:
    return MarketDataPublishSpec(
        dataset_id="cn_a_share_daily_bars",
        market="CN",
        version="20260909",
        source="fixture",
        frequency="daily",
        adjustment="hfq",
    )


def _context(
    tmp_path: Path,
    *,
    read_only: bool,
) -> SourceContext:
    root = tmp_path / "lake"
    root.mkdir()
    registry = ConnectionRegistry(
        {
            "market_data_output": DataConnectionConfig(
                kind=ConnectionKind.PARQUET,
                root_env="QUANTMINE_TEST_REFRESH_ROOT",
                read_only=read_only,
            )
        }
    )
    return SourceContext(
        connections=registry,
        run_id=101,
        artifact_dir=tmp_path / "artifacts",
    )


def _checkpoint_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    read_only: bool = False,
) -> SourceContext:
    root = tmp_path / "checkpoints"
    root.mkdir(exist_ok=True)
    monkeypatch.setenv("QUANTMINE_TEST_CHECKPOINT_ROOT", str(root))
    return SourceContext(
        connections=ConnectionRegistry(
            {
                "market_checkpoint": DataConnectionConfig(
                    kind=ConnectionKind.PARQUET,
                    root_env="QUANTMINE_TEST_CHECKPOINT_ROOT",
                    read_only=read_only,
                )
            }
        ),
        run_id=102,
        artifact_dir=tmp_path / "artifacts",
    )


def test_market_data_refresh_policy_has_bounded_defaults() -> None:
    policy = MarketDataRefreshPolicy()

    assert policy.batch_size == 50
    assert policy.max_retries == 3
    assert policy.checkpoint_connection_ref is None
    assert policy.resume is True


def test_market_data_refresh_policy_accepts_explicit_values() -> None:
    policy = MarketDataRefreshPolicy(
        batch_size=25,
        max_retries=0,
        checkpoint_connection_ref="market_data_checkpoint",
        resume=False,
    )

    assert policy.batch_size == 25
    assert policy.max_retries == 0
    assert policy.checkpoint_connection_ref == "market_data_checkpoint"
    assert policy.resume is False


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_market_data_refresh_policy_rejects_invalid_batch_size(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        MarketDataRefreshPolicy(batch_size=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_market_data_refresh_policy_rejects_invalid_max_retries(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="max_retries"):
        MarketDataRefreshPolicy(max_retries=value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["", " checkpoint", "checkpoint ", 123])
def test_market_data_refresh_policy_rejects_invalid_checkpoint_reference(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="checkpoint_connection_ref"):
        MarketDataRefreshPolicy(  # type: ignore[arg-type]
            checkpoint_connection_ref=value,
        )


def test_market_data_refresh_policy_rejects_non_boolean_resume() -> None:
    with pytest.raises(TypeError, match="resume"):
        MarketDataRefreshPolicy(resume=1)  # type: ignore[arg-type]


def test_partition_data_binding_preserves_request_and_tail_batch() -> None:
    binding = DataBinding(
        connection_ref="provider_api",
        dataset="daily_history",
        version="source_v3",
        start="2024-01-02",
        end="2024-01-31",
        tickers=("000001", "000002", "600000", "600001", "830001"),
        adjustment="hfq",
        metadata={"market": "CN"},
    )

    batches = partition_data_binding(binding, batch_size=2)

    assert tuple(batch.tickers for batch in batches) == (
        ("000001", "000002"),
        ("600000", "600001"),
        ("830001",),
    )
    for batch in batches:
        assert batch.connection_ref == binding.connection_ref
        assert batch.dataset == binding.dataset
        assert batch.version == binding.version
        assert batch.start == binding.start
        assert batch.end == binding.end
        assert batch.adjustment == binding.adjustment
        assert batch.metadata == binding.metadata


def test_partition_data_binding_rejects_empty_ticker_request() -> None:
    binding = DataBinding(
        connection_ref=None,
        dataset="daily_history",
        start="2024-01-02",
        end="2024-01-31",
    )

    with pytest.raises(ValueError, match="tickers must not be empty"):
        partition_data_binding(binding, batch_size=50)


@pytest.mark.parametrize("batch_size", [0, -1, True, 1.5])
def test_partition_data_binding_rejects_invalid_batch_size(
    batch_size: object,
) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        partition_data_binding(  # type: ignore[arg-type]
            _binding(),
            batch_size=batch_size,
        )


def _market_batch(
    ticker: str,
    dates: list[str],
    *,
    include_volume: bool = True,
) -> MarketDataBundle:
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    values = list(range(1, len(index) + 1))
    return MarketDataBundle(
        market=MarketData(
            close=pd.DataFrame({ticker: values}, index=index),
            volume=(
                pd.DataFrame({ticker: values}, index=index)
                if include_volume
                else None
            ),
            market_cap=pd.DataFrame(
                {ticker: [value * 100 for value in values]},
                index=index,
            ),
        ),
        calendar=index,
        metadata={"provider": "fixture"},
    )


def test_merge_market_data_batches_merges_fields_and_calendar() -> None:
    merged = merge_market_data_batches(
        (
            _market_batch("000001", ["2024-01-02", "2024-01-03"]),
            _market_batch("600000", ["2024-01-03", "2024-01-04"]),
        )
    )

    expected_dates = pd.DatetimeIndex(
        pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    )
    assert merged.market.close.columns.tolist() == ["000001", "600000"]
    assert merged.market.volume.columns.tolist() == ["000001", "600000"]
    assert merged.market.market_cap.columns.tolist() == ["000001", "600000"]
    assert merged.market.close.index.equals(expected_dates)
    assert merged.calendar.equals(expected_dates)
    assert merged.metadata == {"provider": "fixture"}


def test_merge_market_data_batches_rejects_inconsistent_optional_field() -> None:
    with pytest.raises(ValueError, match="inconsistent volume"):
        merge_market_data_batches(
            (
                _market_batch("000001", ["2024-01-02"]),
                _market_batch(
                    "600000",
                    ["2024-01-02"],
                    include_volume=False,
                ),
            )
        )


def test_merge_market_data_batches_rejects_duplicate_tickers() -> None:
    with pytest.raises(ValueError, match="duplicate close tickers"):
        merge_market_data_batches(
            (
                _market_batch("000001", ["2024-01-02"]),
                _market_batch("000001", ["2024-01-03"]),
            )
        )


def test_merge_market_data_batches_rejects_non_market_bundle() -> None:
    with pytest.raises(TypeError, match="every batch"):
        merge_market_data_batches((_market_batch("000001", ["2024-01-02"]), object()))  # type: ignore[arg-type]


def test_merge_market_data_batches_rejects_universe_and_benchmark() -> None:
    base = _market_batch("000001", ["2024-01-02"])
    with_universe = MarketDataBundle(
        market=base.market,
        universe=object(),  # type: ignore[arg-type]
    )
    with_benchmark = MarketDataBundle(
        market=base.market,
        benchmark=pd.Series([1.0], index=base.calendar),
    )

    with pytest.raises(ValueError, match="universe"):
        merge_market_data_batches((with_universe,))
    with pytest.raises(ValueError, match="benchmark"):
        merge_market_data_batches((with_benchmark,))


def _batch_component(
    plugin: BatchSource,
    *,
    retry_classifier=None,
) -> DataSourceComponent:
    return DataSourceComponent(
        id="batch_source",
        capabilities=frozenset(
            {
                MarketDataCapability.CLOSE,
                MarketDataCapability.VOLUME,
                MarketDataCapability.CALENDAR,
            }
        ),
        plugin=plugin,
        retry_classifier=retry_classifier,
    )


def _multi_ticker_binding() -> DataBinding:
    return DataBinding(
        connection_ref=None,
        dataset="provider_request",
        start="2024-01-02",
        end="2024-01-03",
        tickers=("000001", "000002", "600000", "600001", "830001"),
        adjustment="hfq",
    )


def test_load_market_data_batches_loads_in_order_and_merges_result(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = BatchSource()
    caplog.set_level(
        logging.INFO,
        logger="quantmine.workflows.market_data_refresh",
    )

    result = load_market_data_batches(
        _context(tmp_path, read_only=False),
        source_component=_batch_component(source),
        binding=_multi_ticker_binding(),
        policy=MarketDataRefreshPolicy(batch_size=2),
        sleeper=lambda _: None,
    )

    assert source.calls == [
        ("000001", "000002"),
        ("600000", "600001"),
        ("830001",),
    ]
    assert result.market.close.columns.tolist() == [
        "000001",
        "000002",
        "600000",
        "600001",
        "830001",
    ]
    assert "market-data refresh started: source=batch_source" in caplog.text
    assert "tickers=5 batches=3 batch_size=2 resume=True" in caplog.text
    assert "market-data batch 1/3 started: tickers=2" in caplog.text
    assert "market-data batch 3/3 completed" in caplog.text
    assert "market-data refresh completed: source=batch_source batches=3" in caplog.text


def test_load_market_data_batches_retries_only_classified_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    failing_batch = ("600000", "600001")
    source = BatchSource(
        failing_batch=failing_batch,
        failure=TimeoutError("temporary provider timeout"),
    )
    delays: list[float] = []

    load_market_data_batches(
        _context(tmp_path, read_only=False),
        source_component=_batch_component(
            source,
            retry_classifier=lambda error: isinstance(error, TimeoutError),
        ),
        binding=_multi_ticker_binding(),
        policy=MarketDataRefreshPolicy(batch_size=2, max_retries=2),
        sleeper=delays.append,
    )

    assert source.calls.count(failing_batch) == 2
    assert delays == [1.0]
    assert (
        "market-data batch 2/3 failed with TimeoutError on attempt 1/3; "
        "retrying in 1.0s"
    ) in caplog.text


def test_load_market_data_batches_does_not_retry_unclassified_failure(
    tmp_path: Path,
) -> None:
    failing_batch = ("000001", "000002")
    source = BatchSource(
        failing_batch=failing_batch,
        failure=ValueError("invalid provider frame"),
    )
    delays: list[float] = []

    with pytest.raises(ValueError, match="invalid provider frame"):
        load_market_data_batches(
            _context(tmp_path, read_only=False),
            source_component=_batch_component(
                source,
                retry_classifier=lambda error: isinstance(error, TimeoutError),
            ),
            binding=_multi_ticker_binding(),
            policy=MarketDataRefreshPolicy(batch_size=2, max_retries=3),
            sleeper=delays.append,
        )

    assert source.calls == [failing_batch]
    assert delays == []


def test_load_market_data_batches_zero_retries_disables_classifier(
    tmp_path: Path,
) -> None:
    failing_batch = ("000001", "000002")
    source = BatchSource(
        failing_batch=failing_batch,
        failure=TimeoutError("temporary provider timeout"),
    )

    with pytest.raises(TimeoutError):
        load_market_data_batches(
            _context(tmp_path, read_only=False),
            source_component=_batch_component(
                source,
                retry_classifier=lambda error: isinstance(error, TimeoutError),
            ),
            binding=_multi_ticker_binding(),
            policy=MarketDataRefreshPolicy(batch_size=2, max_retries=0),
            sleeper=lambda _: None,
        )

    assert source.calls == [failing_batch]


def test_load_market_data_batches_resumes_without_calling_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = _checkpoint_context(monkeypatch, tmp_path)
    policy = MarketDataRefreshPolicy(
        batch_size=2,
        checkpoint_connection_ref="market_checkpoint",
        resume=True,
    )
    first_source = BatchSource()
    first = load_market_data_batches(
        context,
        source_component=_batch_component(first_source),
        binding=_multi_ticker_binding(),
        policy=policy,
        publish_spec=_spec(),
        sleeper=lambda _: None,
    )
    caplog.clear()
    caplog.set_level(
        logging.INFO,
        logger="quantmine.workflows.market_data_refresh",
    )
    second_source = BatchSource()
    second = load_market_data_batches(
        context,
        source_component=_batch_component(second_source),
        binding=_multi_ticker_binding(),
        policy=policy,
        publish_spec=_spec(),
        sleeper=lambda _: None,
    )

    assert first_source.calls == [
        ("000001", "000002"),
        ("600000", "600001"),
        ("830001",),
    ]
    assert second_source.calls == []
    assert caplog.text.count("restored from checkpoint") == 3
    assert "market-data batch 1/3 restored from checkpoint" in caplog.text
    assert "market-data batch 3/3 restored from checkpoint" in caplog.text
    pd.testing.assert_frame_equal(second.market.close, first.market.close)
    pd.testing.assert_frame_equal(second.market.volume, first.market.volume)


def test_load_market_data_batches_requires_publish_spec_for_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _checkpoint_context(monkeypatch, tmp_path)
    source = BatchSource()

    with pytest.raises(ValueError, match="publish_spec is required"):
        load_market_data_batches(
            context,
            source_component=_batch_component(source),
            binding=_multi_ticker_binding(),
            policy=MarketDataRefreshPolicy(
                batch_size=2,
                checkpoint_connection_ref="market_checkpoint",
            ),
            sleeper=lambda _: None,
        )

    assert source.calls == []


def test_load_market_data_batches_rejects_read_only_checkpoint_before_loading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context = _checkpoint_context(
        monkeypatch,
        tmp_path,
        read_only=True,
    )
    source = BatchSource()

    with pytest.raises(PermissionError, match="market_checkpoint.*read-only"):
        load_market_data_batches(
            context,
            source_component=_batch_component(source),
            binding=_multi_ticker_binding(),
            policy=MarketDataRefreshPolicy(
                batch_size=2,
                checkpoint_connection_ref="market_checkpoint",
            ),
            publish_spec=_spec(),
            sleeper=lambda _: None,
        )

    assert source.calls == []


def test_market_data_checkpoint_id_is_stable_for_same_request() -> None:
    source = BatchSource()
    component = _batch_component(source)
    binding = _multi_ticker_binding()
    policy = MarketDataRefreshPolicy(batch_size=2)

    first = market_data_checkpoint_id(
        source_component=component,
        binding=binding,
        publish_spec=_spec(),
        policy=policy,
    )
    second = market_data_checkpoint_id(
        source_component=component,
        binding=binding,
        publish_spec=_spec(),
        policy=policy,
    )

    assert first == second
    assert len(first) == 64


def test_market_data_checkpoint_id_changes_with_content_identity() -> None:
    component = _batch_component(BatchSource())
    binding = _multi_ticker_binding()
    spec = _spec()
    policy = MarketDataRefreshPolicy(batch_size=2)

    baseline = market_data_checkpoint_id(
        source_component=component,
        binding=binding,
        publish_spec=spec,
        policy=policy,
    )
    variants = (
        (component, replace(binding, tickers=tuple(reversed(binding.tickers))), spec, policy),
        (component, replace(binding, start="2024-01-03"), spec, policy),
        (component, binding, replace(spec, version="20260910"), policy),
        (component, binding, replace(spec, frequency="weekly"), policy),
        (component, binding, spec, replace(policy, batch_size=3)),
        (
            DataSourceComponent(
                id="other_source",
                capabilities=component.capabilities,
                plugin=BatchSource(),
            ),
            binding,
            spec,
            policy,
        ),
    )

    for variant_component, variant_binding, variant_spec, variant_policy in variants:
        assert market_data_checkpoint_id(
            source_component=variant_component,
            binding=variant_binding,
            publish_spec=variant_spec,
            policy=variant_policy,
        ) != baseline


def test_market_data_checkpoint_id_ignores_execution_only_policy() -> None:
    component = _batch_component(BatchSource())
    binding = _multi_ticker_binding()
    spec = _spec()

    first = market_data_checkpoint_id(
        source_component=component,
        binding=binding,
        publish_spec=spec,
        policy=MarketDataRefreshPolicy(
            batch_size=2,
            max_retries=0,
            resume=False,
        ),
    )
    second = market_data_checkpoint_id(
        source_component=component,
        binding=binding,
        publish_spec=spec,
        policy=MarketDataRefreshPolicy(
            batch_size=2,
            max_retries=9,
            resume=True,
        ),
    )

    assert first == second


def test_market_data_checkpoint_id_rejects_non_json_metadata() -> None:
    binding = replace(
        _multi_ticker_binding(),
        metadata={"invalid": object()},
    )

    with pytest.raises(TypeError, match="JSON serializable"):
        market_data_checkpoint_id(
            source_component=_batch_component(BatchSource()),
            binding=binding,
            publish_spec=_spec(),
            policy=MarketDataRefreshPolicy(batch_size=2),
        )

def test_refresh_market_data_loads_component_and_publishes_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    monkeypatch.setenv("QUANTMINE_TEST_REFRESH_ROOT", str(root))
    context = _context(tmp_path, read_only=False)
    source = RecordingSource()
    binding = _binding()

    publication = refresh_market_data(
        context,
        source_component=_component(source),
        binding=binding,
        output_connection_ref="market_data_output",
        publish_spec=_spec(),
    )

    assert source.calls == [(binding, context)]
    assert publication.output_dir == (
        root
        / "cn_a_share_daily_bars"
        / "versions"
        / "20260909"
    )
    assert publication.date_count == 2
    assert publication.ticker_count == 1


def test_refresh_market_data_uses_optional_batch_policy_before_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    monkeypatch.setenv("QUANTMINE_TEST_REFRESH_ROOT", str(root))
    context = _context(tmp_path, read_only=False)
    source = BatchSource()

    publication = refresh_market_data(
        context,
        source_component=_batch_component(source),
        binding=_multi_ticker_binding(),
        output_connection_ref="market_data_output",
        publish_spec=_spec(),
        policy=MarketDataRefreshPolicy(
            batch_size=2,
            max_retries=0,
        ),
    )

    assert source.calls == [
        ("000001", "000002"),
        ("600000", "600001"),
        ("830001",),
    ]
    assert publication.date_count == 2
    assert publication.ticker_count == 5
    stored_close = pd.read_parquet(publication.close_path)
    assert stored_close.columns.tolist() == [
        "000001",
        "000002",
        "600000",
        "600001",
        "830001",
    ]


def test_refresh_market_data_rejects_read_only_output_before_loading_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "lake"
    monkeypatch.setenv("QUANTMINE_TEST_REFRESH_ROOT", str(root))
    context = _context(tmp_path, read_only=True)
    source = RecordingSource()

    with pytest.raises(
        PermissionError,
        match="market_data_output.*read-only",
    ):
        refresh_market_data(
            context,
            source_component=_component(source),
            binding=_binding(),
            output_connection_ref="market_data_output",
            publish_spec=_spec(),
        )

    assert source.calls == []
