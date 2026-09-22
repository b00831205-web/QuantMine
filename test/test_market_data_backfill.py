"""Plan-driven, resumable staging of historical market-data repairs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantmine.datareader import MarketData
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import (
    DataBinding,
    DataSourceComponent,
    MarketDataBundle,
    MarketDataCapability,
)
from quantmine.workflows.coverage_audit import BackfillTask
from quantmine.workflows.market_data_backfill import (
    load_staged_market_data_backfill,
    stage_market_data_backfill,
)
from quantmine.workflows.market_data_refresh import MarketDataRefreshPolicy


class _Connections:
    def __init__(self, root: Path) -> None:
        self.root = root

    def writable_parquet_root(self, connection_ref: str) -> Path:
        assert connection_ref == "backfill_staging"
        return self.root


class _Source:
    def __init__(self) -> None:
        self.bindings: list[DataBinding] = []

    def load(
        self,
        binding: DataBinding,
        context: SourceContext,
    ) -> MarketDataBundle:
        self.bindings.append(binding)
        index = pd.date_range(binding.start, binding.end, freq="B")
        columns = list(binding.tickers)
        return MarketDataBundle(
            market=MarketData(
                close=pd.DataFrame(10.0, index=index, columns=columns),
                volume=pd.DataFrame(100.0, index=index, columns=columns),
            )
        )


def test_backfill_worker_uses_the_persisted_task_scope_and_reuses_its_checkpoint(
    tmp_path: Path,
) -> None:
    source = _Source()
    component = DataSourceComponent(
        id="fixture_source",
        capabilities=frozenset({
            MarketDataCapability.CLOSE,
            MarketDataCapability.VOLUME,
        }),
        plugin=source,
    )
    context = SourceContext(
        connections=_Connections(tmp_path),
        run_id=0,
        artifact_dir=tmp_path / "artifacts",
    )
    task = BackfillTask(
        start=pd.Timestamp("2024-01-03"),
        end=pd.Timestamp("2024-01-04"),
        symbols=("000001.SZ", "600000.SH"),
        fields=("close", "volume"),
        reason="coverage_gap",
        checkpoint_key="repair-001",
    )

    result = stage_market_data_backfill(
        context,
        source_component=component,
        binding_template=DataBinding(
            connection_ref=None,
            dataset="akshare_a_share_history",
            adjustment="hfq",
        ),
        policy=MarketDataRefreshPolicy(
            batch_size=50,
            max_retries=0,
        ),
        plan_id="plan-001",
        task=task,
        staging_connection_ref="backfill_staging",
    )

    assert len(source.bindings) == 1
    binding = source.bindings[0]
    assert binding.start == "2024-01-03"
    assert binding.end == "2024-01-04"
    assert binding.tickers == task.symbols
    assert result.plan_id == "plan-001"
    assert result.checkpoint_key == task.checkpoint_key
    assert result.output_dir.is_dir()

    restored = load_staged_market_data_backfill(
        context,
        plan_id="plan-001",
        task=task,
        staging_connection_ref="backfill_staging",
    )
    assert restored.market.close.loc[:, list(task.symbols)].notna().all().all()
    assert restored.market.volume.loc[:, list(task.symbols)].notna().all().all()

    second = stage_market_data_backfill(
        context,
        source_component=component,
        binding_template=DataBinding(
            connection_ref=None,
            dataset="akshare_a_share_history",
            adjustment="hfq",
        ),
        policy=MarketDataRefreshPolicy(
            batch_size=50,
            max_retries=0,
        ),
        plan_id="plan-001",
        task=task,
        staging_connection_ref="backfill_staging",
    )

    assert len(source.bindings) == 1
    assert second.output_dir == result.output_dir
