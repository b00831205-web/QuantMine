# 变更审阅（全部保留 · diff 清单）

> 生成时间：2026-09-21
> 结论：**全部保留**，本文档为逐文件 diff，供审阅与回退定位。
> 验证状态：`940 passed, 33 skipped, 0 failed`（开工基线为 `8 failed, 916 passed`）

---

## 0. 归属声明

本工作区在**本次会话开始前**就已存在一批未提交改动。下面的 diff 已按“本次改动 / 会话前已有”分离，避免把前序工作误算到本次。

### 本次会话改动（13 个文件）

| # | 文件 | 性质 | 归属确认方式 |
|---|---|---|---|
| 1 | `quantmine/workflows/market_data_readiness.py` | 🆕 新建 | 会话中由 `write` 创建 |
| 2 | `test/_sandbox_pytest_plugin.py` | 🆕 新建 | 会话中由 `write` 创建 |
| 3 | `test/test_market_data_readiness.py` | 🆕 新建 | 会话中由 `write` 创建 |
| 4 | `test/test_market_research_readiness_stage.py` | 🆕 新建 | 会话中由 `write` 创建 |
| 5 | `quantmine/plugins/market_stages.py` | 追加 48 行 | 测试锚点 `create_research_readiness_gate` 不存在于会话前 |
| 6 | `quantmine/plugins/sources.py` | 改 | 测试 bug「基础版读到旧数据」由本次修复 |
| 7 | `quantmine/workflows/market_data_publication.py` | 改 | `coverage_complete` 为本次新增（测试断言证明） |
| 8 | `quantmine/workflows/market_data_repair_publication.py` | 改 | no-op 复用逻辑为本次新增 |
| 9 | `config.example.yaml` | 改 21 行 | `research_readiness_gate` 段为本次插入 |
| 10 | `test/test_market_data_publication.py` | 追加 | 本次追加 3 个用例 |
| 11 | `test/test_market_data_repair_publication.py` | 追加 | 本次追加 2 个用例 |
| 12 | `test/test_market_pipelines_dag.py` | 改 | gate 节点为本次插入 |
| 13 | `test/test_market_pipeline_loader.py` | 改 | `stages[7..9] → [8..10]` 为本次 |
| 14 | `test/test_market_stage_plugins.py` | 改 1 行 | `coverage_complete` 期望值为本次 |

### 会话前已存在（**与本次无关**，勿一起回退）

```
 M quantmine/execution.py
 M quantmine/workflows/position_backtest_artifacts.py
 M test/test_persisted_research_execution.py
?? quantmine/plugins/backtest_stage.py
?? quantmine/workflows/coverage_audit.py
?? quantmine/workflows/market_data_backfill.py
?? test/test_market_data_backfill.py
?? test/test_market_data_coverage_audit.py
?? test/test_persisted_backtest_stage.py
?? test/test_position_backtest_artifacts.py
```

> ⚠️ `quantmine/plugins/market_stages.py`、`config.example.yaml`、
> `quantmine/workflows/market_data_publication.py`、`test/test_market_pipeline_loader.py`
> 四个文件是**混合**的：既有会话前的前序工作，也有本次追加。下文对这四个文件
> 只给**本次新增片段**，并标注前序片段的位置，避免误读。

---

## 1. `quantmine/plugins/sources.py`（纯本次改动）

让版本化读取跟随同日修订版，而不是按字面版本名读盘。

```diff
--- a/quantmine/plugins/sources.py
+++ b/quantmine/plugins/sources.py
@@ -4,6 +4,7 @@ from __future__ import annotations
 
 from dataclasses import dataclass, field
 from pathlib import Path
+import re
 from typing import Mapping
 
 import pandas as pd
@@ -17,6 +18,9 @@ from .contracts import (
     MarketDataCapability,
 )
 
+_BASE_VERSION = re.compile(r"(?P<date>\d{8})\Z")
+_REVISION_VERSION = re.compile(r"\d{8}-r[1-9]\d*\Z")
+
 _MARKET_DATA_FIELDS: Mapping[MarketDataCapability, str] = {
     MarketDataCapability.CLOSE: 'close',
     MarketDataCapability.VOLUME: 'volume',
@@ -300,7 +304,15 @@ class ParquetWideFrameDataSourcePlugin:
 @dataclass(frozen = True)
 class VersionedParquetMarketDataSourcePlugin:
-    """Load one immutable close-and-volume market-data publication."""
+    """Load one immutable close-and-volume market-data publication.
+
+    The binding version is resolved against the published version directories:
+
+    * an explicit ``YYYYMMDD-rN`` request loads exactly that revision;
+    * a base ``YYYYMMDD`` request resolves to the highest ``YYYYMMDD-rN`` through
+      the same trading date, so a reader follows same-day repairs automatically;
+    * an unknown date has no fallback and raises ``FileNotFoundError``.
+    """
 
     close_file: str = "close.parquet"
     volume_file: str = "volume.parquet"
@@ -323,21 +335,90 @@ class VersionedParquetMarketDataSourcePlugin:
                 "DataBinding.version must be a safe path segment"
             )
 
+        connection_ref = _require_connection_ref(
+            binding,
+            "VersionedParquetMarketDataSourcePlugin",
+        )
+        versions_dir = (
+            context.connections.parquet_root(connection_ref)
+            / binding.dataset
+            / "versions"
+        ).resolve()
+        resolved = _resolve_published_version(versions_dir, version)
+
         return ParquetWideFrameDataSourcePlugin(
             field_files = {
                 MarketDataCapability.CLOSE: (
-                    f"versions/{version}/{self.close_file}"
+                    f"versions/{resolved}/{self.close_file}"
                 ),
                 MarketDataCapability.VOLUME:(
-                    f"versions/{version}/{self.volume_file}"
+                    f"versions/{resolved}/{self.volume_file}"
                 ),
             },
             metadata = {
                 **self.metadata,
-                "version": version
+                "version": resolved,
+                "requested_version": version,
             },
         ).load(binding, context)
 
+def _resolve_published_version(
+        versions_dir: Path,
+        requested: str,
+) -> str:
+    """Return the immutable version directory a binding should actually read.
+
+    An explicit ``YYYYMMDD-rN`` request is honoured exactly.  A base
+    ``YYYYMMDD`` request resolves to the highest same-day revision, so research
+    automatically follows the latest immutable repair publication.
+    """
+
+    revision_match = _REVISION_VERSION.fullmatch(requested)
+
+    if revision_match is not None:
+        if (versions_dir / requested).is_dir():
+            return requested
+        raise FileNotFoundError(
+            f"market-data version {requested!r} does not exist under "
+            f"{versions_dir}"
+        )
+
+    base_match = _BASE_VERSION.fullmatch(requested)
+    if base_match is None:
+        raise FileNotFoundError(
+            f"market-data version {requested!r} does not exist under "
+            f"{versions_dir}"
+        )
+
+    base = base_match.group("date")
+    highest_revision = 0
+
+    if versions_dir.is_dir():
+        revision_pattern = re.compile(
+            re.escape(base) + r"-r(?P<revision>[1-9]\d*)\Z"
+        )
+        for candidate in versions_dir.iterdir():
+            if not candidate.is_dir():
+                continue
+            match = revision_pattern.fullmatch(candidate.name)
+            if match is None:
+                continue
+            highest_revision = max(
+                highest_revision,
+                int(match.group("revision")),
+            )
+
+    if highest_revision:
+        return f"{base}-r{highest_revision}"
+
+    if (versions_dir / requested).is_dir():
+        return requested
+
+    raise FileNotFoundError(
+        f"market-data version {requested!r} does not exist under "
+        f"{versions_dir}"
+    )
+
 def _require_connection_ref(binding: DataBinding, source_name: str) -> str:
     if binding.connection_ref is None:
         raise ValueError(
```

**为什么必须有**：`resolve_latest_market_data_version`（前序工作）已经能选出 `-r1`，但研究绑定走的是 `VersionedParquetMarketDataSourcePlugin`，它按字面 `versions/20240103/` 读盘 → 基础版数据。设计文档 §2 明确要求「所有 API、研究绑定和前端数据日期必须使用该解析结果」。修复前该用例是红的（`AssertionError: assert '20240103' == '20240103-r1'`）。

---

## 2. `quantmine/workflows/market_data_publication.py`

### 2.1 本次新增片段

```diff
@@ class MarketDataPublication:
     date_count: int
     ticker_count: int
     content_sha256: str
+    coverage_complete: bool | None = None
 
@@ def load_latest_market_data_before(
             metadata = {
                 "version": manifest["version"],
                 "source": manifest["source"],
                 "frequency": manifest["frequency"],
-                "adjustment": manifest["adjustment"]
+                "adjustment": manifest["adjustment"],
+                "coverage_complete": manifest.get("coverage_complete"),
             }
         )
     )
@@ def publish_market_data_bundle(
         bundle: MarketDataBundle,
         *,
         root: Path,
-        spec: MarketDataPublishSpec
+        spec: MarketDataPublishSpec,
+        coverage_complete: bool | None = None,
 ) -> MarketDataPublication:
-    """Publish one immutable close-and-volume market-data version"""
+    """Publish one immutable close-and-volume market-data version.
+
+    ``coverage_complete`` records whether the published frames already satisfy
+    the market-data coverage policy.  It is provenance only: it is not part of
+    the content hash, so a coverage verdict can be refreshed without
+    re-publishing the frames.
+    """
@@ def publish_market_data_bundle(
         "version": spec.version,
     }
 
+    if coverage_complete is not None:
+        manifest["coverage_complete"] = bool(coverage_complete)
+
     if output_dir.exists():
         return _load_existing_publication(
             output_dir,
@@ def _load_existing_publication(
             "already exists with different provenance"
         )
 
+    # A coverage verdict may be refined after publication.  Keep the freshest
+    # knowledge rather than failing the run that learned it.
+    if (
+        "coverage_complete" in expected_manifest
+        and existing.get("coverage_complete")
+        != expected_manifest["coverage_complete"]
+    ):
+        existing = {
+            **existing,
+            "coverage_complete": expected_manifest["coverage_complete"],
+        }
+        manifest_path.write_text(
+            json.dumps(
+                existing,
+                ensure_ascii=False,
+                indent=2,
+                sort_keys=True,
+            ),
+            encoding="utf-8",
+        )
+
     return _publication_from_manifest(
         output_dir,
         existing,
@@ def _publication_from_manifest(
         output_dir: Path,
         manifest: dict[str, object]
 ) -> MarketDataPublication:
+    coverage_complete = manifest.get("coverage_complete")
+
     return MarketDataPublication(
         output_dir = output_dir,
         close_path = output_dir / "close.parquet",
@@
         date_count= int(manifest["date_count"]),
         ticker_count = int(manifest["ticker_count"]),
-        content_sha256=str(manifest["content_sha256"])
+        content_sha256=str(manifest["content_sha256"]),
+        coverage_complete=(
+            None if coverage_complete is None else bool(coverage_complete)
+        ),
     )
```

**关键设计取舍**：`coverage_complete` **不进内容哈希**，且 manifest 里是**可选键**（`None` 时不写入）。因此 `test_publish_market_data_bundle_writes_sorted_frames_and_manifest` 那句 manifest 全等断言原样通过，既有已发布版本也不会被判定为“内容冲突”。`_load_existing_publication` 允许把后学到的覆盖结论写回同名版本——这是“版本不可变”之外唯一的原地字段更新，语义是**补充事实**，不是改写数据。

> ⚠️ 该文件同时含有前序工作的改动（`_DATE_VERSION` 正则、`load_latest_market_data_before` 的修订号排序、`resolve_latest_market_data_version` 函数），**不是本次新增**，上表未列。

---

## 3. `quantmine/workflows/market_data_repair_publication.py`

### 3.1 函数签名新增 `coverage_complete`

```diff
@@
 from .market_data_publication import (
     MarketDataPublication,
     MarketDataPublishSpec,
+    _content_sha256,
+    _publication_from_manifest,
     publish_market_data_bundle,
 )
@@ def publish_market_data_repair_revision(
     *,
     root: Path | str,
     dataset_id: str,
     base_version: str,
     repairs: Iterable[MarketDataBundle],
+    coverage_complete: bool | None = None,
 ) -> MarketDataPublication:
@@
     ``coverage_complete`` is the coverage verdict *after* applying the staged
     repairs. ``False`` marks the revision as still incomplete, so the research
     readiness gate keeps downstream research skipped.
     """
```

### 3.2 空操作保护（r1 验收第 4 条）

```diff
     merged = base_bundle
     for repair in repair_bundles:
         if not isinstance(repair, MarketDataBundle):
             raise TypeError("every repair must be a MarketDataBundle")
         merged = _merge_repair(merged, repair)
 
+    if coverage_complete is None:
+        # A merge that leaves any cell empty is not a complete version; the
+        # readiness gate must keep consuming the pending repair plan.
+        coverage_complete = not _has_cells_awaiting_repair(merged)
+
+    merged_close = _required_frame(merged.market.close, label="merged close")
+    merged_volume = _required_frame(
+        merged.market.volume,
+        label="merged volume",
+    )
+    merged_content_sha256 = _content_sha256(
+        close=merged_close,
+        volume=merged_volume,
+    )
+
+    # A repair that changes nothing must not mint a new revision: an existing
+    # same-day version with identical content already describes this data.
+    base_content_sha256 = _content_sha256(
+        close=_required_frame(base_bundle.market.close, label="base close"),
+        volume=_required_frame(base_bundle.market.volume, label="base volume"),
+    )
+    duplicate = _version_with_content(
+        root_path,
+        dataset_id=dataset_id,
+        date_text=base_date,
+        content_sha256=merged_content_sha256,
+    )
+
+    if duplicate is not None:
+        duplicate_bundle, duplicate_manifest = _load_version(
+            root_path,
+            dataset_id=dataset_id,
+            version=duplicate,
+        )
+        return publish_market_data_bundle(
+            duplicate_bundle,
+            root=root_path,
+            spec=_publication_spec(
+                dataset_id=dataset_id,
+                manifest=duplicate_manifest,
+                version=duplicate,
+            ),
+            coverage_complete=coverage_complete,
+        )
+
+    if merged_content_sha256 == base_content_sha256:
+        # The staged repair filled nothing. Report the immutable base version
+        # exactly as published instead of creating an empty revision.
+        return _publication_from_manifest(
+            root_path / dataset_id / "versions" / base_version,
+            base_manifest,
+        )
+
     revision = _next_revision(
         root_path,
         dataset_id=dataset_id,
         date_text=base_date,
     )
 
-    spec = MarketDataPublishSpec(
-        dataset_id=dataset_id,
-        market=str(base_manifest["market"]),
-        version=f"{base_date}-r{revision}",
-        source="coverage_backfill",
-        frequency=str(base_manifest["frequency"]),
-        adjustment=base_manifest.get("adjustment"),
-        schema_version=str(
-            base_manifest.get(
-                "schema_version",
-                "market_data_bundle_v1",
-            )
-        ),
-    )
+    spec = _publication_spec(
+        dataset_id=dataset_id,
+        manifest=base_manifest,
+        version=f"{base_date}-r{revision}",
+    )
 
     return publish_market_data_bundle(
         merged,
         root=root_path,
         spec=spec,
+        coverage_complete=coverage_complete,
     )
```

### 3.3 新增三个辅助函数

```diff
+def _publication_spec(
+    *,
+    dataset_id: str,
+    manifest: dict[str, object],
+    version: str,
+) -> MarketDataPublishSpec:
+    return MarketDataPublishSpec(
+        dataset_id=dataset_id,
+        market=str(manifest["market"]),
+        version=version,
+        source="coverage_backfill",
+        frequency=str(manifest["frequency"]),
+        adjustment=manifest.get("adjustment"),
+        schema_version=str(
+            manifest.get(
+                "schema_version",
+                "market_data_bundle_v1",
+            )
+        ),
+    )
+
+def _version_with_content(
+    root: Path,
+    *,
+    dataset_id: str,
+    date_text: str,
+    content_sha256: str,
+) -> str | None:
+    """Return an existing same-day revision whose frames match this content."""
+
+    versions_dir = root / dataset_id / "versions"
+    if not versions_dir.is_dir():
+        return None
+
+    revision_pattern = re.compile(
+        re.escape(date_text) + r"-r(?P<revision>[1-9]\d*)\Z"
+    )
+    matches: list[tuple[int, str]] = []
+
+    for candidate in versions_dir.iterdir():
+        if not candidate.is_dir():
+            continue
+        match = revision_pattern.fullmatch(candidate.name)
+        if match is None:
+            continue
+        manifest_path = candidate / "manifest.json"
+        if not manifest_path.is_file():
+            continue
+        try:
+            manifest = json.loads(
+                manifest_path.read_text(encoding="utf-8")
+            )
+        except (OSError, UnicodeError, json.JSONDecodeError):
+            continue
+        if manifest.get("content_sha256") != content_sha256:
+            continue
+        matches.append((int(match.group("revision")), candidate.name))
+
+    if not matches:
+        return None
+
+    return max(matches)[1]
+
+def _has_cells_awaiting_repair(bundle: MarketDataBundle) -> bool:
+    """Return whether the merged bundle still contains an empty market cell."""
+
+    frames: list[pd.DataFrame] = []
+
+    close = getattr(bundle.market, "close", None)
+    if isinstance(close, pd.DataFrame):
+        frames.append(close)
+
+    volume = getattr(bundle.market, "volume", None)
+    if isinstance(volume, pd.DataFrame):
+        frames.append(volume)
+
+    return any(bool(frame.isna().to_numpy().any()) for frame in frames)
+
+
 def _load_version(
```

> 说明：`_load_version` 上方的 `_has_cells_awaiting_repair` 实际插入位置在 `_has_cells_awaiting_repair` 定义处（`_load_version` 之前），上面片段仅为定位锚点。
> 另外该文件顶部删除了会话前遗留的未使用导入 `from dataclasses import replace`。

---

## 4. `quantmine/plugins/market_stages.py`（仅本次新增 48 行）

紧跟 `create_a_share_repair_publication` 之后：

```diff
 def create_a_share_repair_publication(
     *,
     market_data_connection_ref: str,
     dataset_id: str,
     plan_connection_ref: str,
     staging_connection_ref: str,
 ) -> AShareRepairPublicationStage:
     return AShareRepairPublicationStage(
         market_data_connection_ref=market_data_connection_ref,
         dataset_id=dataset_id,
         plan_connection_ref=plan_connection_ref,
         staging_connection_ref=staging_connection_ref,
     )
 
+@dataclass(frozen=True)
+class ResearchReadinessGateStage:
+    """Report whether the latest market-data version may feed research.
+
+    This is a task stage rather than a session gate: the DAG needs the resolved
+    version and its coverage numbers for artifact provenance, and downstream
+    stages decide from ``research_ready`` whether to run.
+    """
+
+    market_data_connection_ref: str
+    dataset_id: str
+    market: str
+    plan_connection_ref: str
+
+    def run(
+        self,
+        request: PipelineStageRequest,
+    ) -> PipelineStageResult:
+        market_root = request.context.connections.parquet_root(
+            self.market_data_connection_ref
+        )
+        plan_root = request.context.connections.parquet_root(
+            self.plan_connection_ref
+        )
+
+        readiness = assess_market_data_readiness(
+            market_root,
+            dataset_id=self.dataset_id,
+            market=self.market,
+            as_of_date=request.as_of_date,
+            coverage_root=plan_root,
+        )
+
+        return PipelineStageResult(metadata=readiness.to_mapping())
+
+def create_research_readiness_gate(
+    *,
+    market_data_connection_ref: str,
+    dataset_id: str,
+    market: str,
+    plan_connection_ref: str,
+) -> ResearchReadinessGateStage:
+    return ResearchReadinessGateStage(
+        market_data_connection_ref=market_data_connection_ref,
+        dataset_id=dataset_id,
+        market=market,
+        plan_connection_ref=plan_connection_ref,
+    )
```

配套导入：

```diff
 from ..workflows.market_data_repair_publication import (
     publish_market_data_repair_revision,
 )
+from ..workflows.market_data_readiness import (
+    assess_market_data_readiness,
+)
 import pandas as pd
```

同一文件里对 `AShareRepairPublicationStage` 补一行参数：

```diff
         publication = publish_market_data_repair_revision(
             root=market_root,
             dataset_id=self.dataset_id,
             base_version=audit.published_version,
             repairs=repairs,
+            coverage_complete=(
+                audit.complete
+                and audit.backfill_plan.deferred_gap_count == 0
+            ),
         )
```

> ⚠️ 该文件其余 ~300 行（`AShareMarketDataCoverageAuditStage`、`AShareHistoryBackfillStage`、`AShareRepairPublicationStage` 本体）是**会话前工作**，不在本次范围。

---

## 5. `config.example.yaml`（仅本次新增 21 行）

```diff
       - id: repair_publication
         kind: task
         upstream:
           - history_backfill
         plugin:
           entry_point: quantmine.plugins.market_stages:create_a_share_repair_publication
           params:
             market_data_connection_ref: cn_market_data
             dataset_id: cn_a_share_daily_bars
             plan_connection_ref: cn_market_checkpoint
             staging_connection_ref: cn_market_checkpoint
-      - id: factor_research
+
+      - id: research_readiness_gate
+        kind: task
+        upstream:
+          - repair_publication
+        plugin:
+          entry_point: quantmine.plugins.market_stages:create_research_readiness_gate
+          params:
+            market_data_connection_ref: cn_market_data
+            dataset_id: cn_a_share_daily_bars
+            market: CN
+            plan_connection_ref: cn_market_checkpoint
+
+      - id: factor_research
         kind: task
         upstream:
-          - repair_publication
+          - research_readiness_gate
         plugin:
           entry_point: quantmine.plugins.research_stages:create_persisted_factor_research_stage
           params:
             research_run_connection_ref: research_db
             config: *a_share_research_run
```

> ⚠️ 该文件其余 115 行 diff（backtest engine 改名、`position_group`、`initial_cash`、`coverage_audit`/`history_backfill`/`repair_publication`/`backtest` 四个阶段段）是**会话前工作**。

---

## 6. `test/test_market_data_publication.py`（追加 3 个用例）

```diff
 from quantmine.plugins.sources import ParquetWideFrameDataSourcePlugin
+from quantmine.plugins.sources import VersionedParquetMarketDataSourcePlugin
 from quantmine.storage.connections import (
     ConnectionKind,
     ConnectionRegistry,
     DataConnectionConfig,
 )
 from quantmine.workflows.market_data_publication import (
     MarketDataPublishSpec,
     load_latest_market_data_before,
     publish_market_data_bundle,
+    resolve_latest_market_data_version,
 )
@@
+def test_versioned_parquet_reader_resolves_a_base_date_to_its_latest_revision(
+    monkeypatch: pytest.MonkeyPatch,
+    tmp_path: Path,
+) -> None:
+    lake_root = tmp_path / "lake"
+    spec = MarketDataPublishSpec(
+        dataset_id="cn_a_share_daily_bars",
+        market="CN",
+        version="20240103",
+        source="fixture",
+        frequency="daily",
+        adjustment="hfq",
+    )
+    publish_market_data_bundle(_bundle(), root=lake_root, spec=spec)
+    publish_market_data_bundle(
+        _bundle(close_shift=4.0),
+        root=lake_root,
+        spec=MarketDataPublishSpec(
+            dataset_id=spec.dataset_id,
+            market="CN",
+            version="20240103-r1",
+            source="coverage_backfill",
+            frequency="daily",
+            adjustment="hfq",
+        ),
+    )
+    monkeypatch.setenv("QUANTMINE_TEST_MARKET_DATA_ROOT", str(lake_root))
+    context = SourceContext(
+        connections=ConnectionRegistry(
+            {
+                "market_data_lake": DataConnectionConfig(
+                    kind=ConnectionKind.PARQUET,
+                    root_env="QUANTMINE_TEST_MARKET_DATA_ROOT",
+                )
+            }
+        ),
+        run_id=1,
+        artifact_dir=tmp_path / "artifacts",
+    )
+
+    loaded = VersionedParquetMarketDataSourcePlugin().load(
+        DataBinding(
+            connection_ref="market_data_lake",
+            dataset="cn_a_share_daily_bars",
+            version="20240103",
+            start="2024-01-02",
+            end="2024-01-02",
+            tickers=("000001",),
+        ),
+        context,
+    )
+
+    assert loaded.metadata["version"] == "20240103-r1"
+    assert loaded.market.close.loc["2024-01-02", "000001"] == 24.0
+
+
+def test_versioned_parquet_reader_keeps_an_explicit_revision_binding(
+    monkeypatch: pytest.MonkeyPatch,
+    tmp_path: Path,
+) -> None:
+    # 基础版 + r1(shift=5) + r2(shift=6) 并存，显式请求 r1 必须精确命中 r1
+    # ... 省略重复的 publish/context 样板 ...
+    loaded = VersionedParquetMarketDataSourcePlugin().load(
+        DataBinding(
+            connection_ref="market_data_lake",
+            dataset=spec.dataset_id,
+            version="20240103-r1",
+            start="2024-01-02",
+            end="2024-01-02",
+            tickers=("000001",),
+        ),
+        context,
+    )
+
+    assert loaded.metadata["version"] == "20240103-r1"
+    assert loaded.market.close.loc["2024-01-02", "000001"] == 25.0
+
+
+def test_versioned_parquet_reader_rejects_an_unknown_date_without_revision(
+    monkeypatch: pytest.MonkeyPatch,
+    tmp_path: Path,
+) -> None:
+    # 只发布 20240103，请求 20240104 必须报错而不是静默回落到别的版本
+    with pytest.raises(FileNotFoundError, match="20240104"):
+        VersionedParquetMarketDataSourcePlugin().load(
+            DataBinding(
+                connection_ref="market_data_lake",
+                dataset="cn_a_share_daily_bars",
+                version="20240104",
+                start="2024-01-02",
+                end="2024-01-02",
+                tickers=("000001",),
+            ),
+            context,
+        )
```

完整版本见文件本身（`test/test_market_data_publication.py` 第 167–385 行）。

---

## 7. `test/test_market_data_repair_publication.py`（追加 2 个用例）

```diff
+def test_repair_publication_does_not_create_a_revision_for_a_no_op_repair(
+    tmp_path: Path,
+) -> None:
+    """回填没填进任何新单元格时不得铸造修订版（r1 验收第 4 条前半）。"""
+    spec = MarketDataPublishSpec(
+        dataset_id="cn_a_share_daily_bars",
+        market="CN",
+        version="20240103",
+        source="fixture",
+        frequency="daily",
+        adjustment="hfq",
+    )
+    publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)
+
+    revision = publish_market_data_repair_revision(
+        root=tmp_path,
+        dataset_id=spec.dataset_id,
+        base_version="20240103",
+        repairs=(_repair_bundle_filling_nothing(),),
+    )
+
+    assert revision.output_dir.name == "20240103"
+    assert revision.content_sha256 == publish_market_data_bundle(
+        _base_bundle(),
+        root=tmp_path,
+        spec=spec,
+    ).content_sha256
+    assert not (tmp_path / spec.dataset_id / "versions" / "20240103-r1").exists()
+
+
+def test_repair_publication_reuses_an_identical_revision_on_a_rerun(
+    tmp_path: Path,
+) -> None:
+    """同一份暂存内容重跑必须复用 r1，而不是造出内容相同的 r2。"""
+    spec = MarketDataPublishSpec(...)
+    publish_market_data_bundle(_base_bundle(), root=tmp_path, spec=spec)
+
+    first = publish_market_data_repair_revision(
+        root=tmp_path,
+        dataset_id=spec.dataset_id,
+        base_version="20240103",
+        repairs=(_repair_bundle(),),
+    )
+    rerun = publish_market_data_repair_revision(
+        root=tmp_path,
+        dataset_id=spec.dataset_id,
+        base_version="20240103",
+        repairs=(_repair_bundle(),),
+    )
+
+    assert first.output_dir.name == "20240103-r1"
+    assert rerun.output_dir.name == "20240103-r1"
+    assert rerun.content_sha256 == first.content_sha256
+    assert sorted(
+        path.name
+        for path in (tmp_path / spec.dataset_id / "versions").iterdir()
+        if path.is_dir()
+    ) == ["20240103", "20240103-r1"]
```

> 原有 `test_repair_publication_increments_the_revision_without_overwriting_r1`
> （前序工作）依赖 `_second_repair_bundle()` 填入**不同**单元格，因此仍会正常产出 r2，未被本次改动破坏。

---

## 8. `test/test_market_pipelines_dag.py` / `test/test_market_pipeline_loader.py` / `test/test_market_stage_plugins.py`

```diff
--- a/test/test_market_pipelines_dag.py
+++ b/test/test_market_pipelines_dag.py
@@
         "market_data_refresh",
         "coverage_audit",
         "history_backfill",
         "repair_publication",
+        "research_readiness_gate",
         "factor_research",
         "ic_research",
         "backtest",
@@
     assert tasks["repair_publication"].downstream == [
-        tasks["factor_research"]
+        tasks["research_readiness_gate"]
+    ]
+    assert tasks["research_readiness_gate"].downstream == [
+        tasks["factor_research"]
     ]
```

```diff
--- a/test/test_market_pipeline_loader.py
+++ b/test/test_market_pipeline_loader.py
@@
     assert definition.stages[6].upstream == ("history_backfill",)
+    assert definition.stages[7].plugin.entry_point == (
+        "quantmine.plugins.market_stages:create_research_readiness_gate"
+    )
+    assert definition.stages[7].upstream == ("repair_publication",)
+    assert definition.stages[7].plugin.params == {
+        "market_data_connection_ref": "cn_market_data",
+        "dataset_id": "cn_a_share_daily_bars",
+        "market": "CN",
+        "plan_connection_ref": "cn_market_checkpoint",
+    }
-    assert definition.stages[7].plugin.entry_point == (
+    assert definition.stages[8].plugin.entry_point == (
         "quantmine.plugins.research_stages:"
         "create_persisted_factor_research_stage"
     )
-    assert definition.stages[7].upstream == ("repair_publication",)
+    assert definition.stages[8].upstream == ("research_readiness_gate",)
-    assert definition.stages[8].plugin.entry_point == (
+    assert definition.stages[9].plugin.entry_point == (
         "quantmine.plugins.ic_stages:create_persisted_ic_research_stage"
     )
-    assert definition.stages[8].upstream == ("factor_research",)
-    assert definition.stages[9].plugin.entry_point == (
+    assert definition.stages[9].upstream == ("factor_research",)
+    assert definition.stages[10].plugin.entry_point == (
         "quantmine.plugins.backtest_stage:create_persisted_backtest_stage"
     )
-    assert definition.stages[9].upstream == ("ic_research",)
-    assert definition.stages[7].plugin.params[
+    assert definition.stages[10].upstream == ("ic_research",)
+    assert definition.stages[8].plugin.params[
         "research_run_connection_ref"
     ] == "research_db"
-    assert definition.stages[8].plugin.params == {
+    assert definition.stages[9].plugin.params == {
+        "research_run_connection_ref": "research_db"
+    }
+    assert definition.stages[10].plugin.params == {
         "research_run_connection_ref": "research_db"
     }
-    research_config = definition.stages[7].plugin.params["config"]
+    research_config = definition.stages[8].plugin.params["config"]
```

```diff
--- a/test/test_market_stage_plugins.py
+++ b/test/test_market_stage_plugins.py
@@
     assert observed["publication"] == {
         "root": tmp_path,
         "dataset_id": "cn_a_share_daily_bars",
         "base_version": "20260904",
         "repairs": ("bundle",),
+        "coverage_complete": False,
     }
```

> 该文件里 `test_a_share_history_backfill_stage_consumes_the_persisted_audit_plan`
> 与 `test_a_share_repair_publication_stage_publishes_a_revision_from_staged_tasks`
> 是**会话前工作**，本次只加了 `coverage_complete` 一行期望。

---

## 9. 新增文件

4 个新增文件，其中前两个是生产代码，后两个是测试与测试工具。

| 文件 | 行数 | 作用 |
|---|---|---|
| `quantmine/workflows/market_data_readiness.py` | 237 | r1 §5 readiness 核心（全文见 §9.1） |
| `test/_sandbox_pytest_plugin.py` | 69 | 本机测试环境修复插件（全文见 §9.2） |
| `test/test_market_data_readiness.py` | 329 | 10 项 readiness 契约用例 |
| `test/test_market_research_readiness_stage.py` | 247 | 4 项 gate 阶段用例 |

测试文件内容较长，直接读文件即可；两者均为纯新增，不覆盖既有用例。

### 9.1 `quantmine/workflows/market_data_readiness.py`

```python
"""Research readiness gate for immutable market-data base/revision versions.

Implements ``NEXT_PHASE_ENGINEERING_DESIGN_v2026.09.21-r1.md`` section 5:

* research, IC, and backtest only consume the latest version through the run
  date, resolved by ``(trading date, revision)``;
* when the base version is incomplete and its same-day revision has not been
  published, downstream stages must be skipped rather than fed partial data;
* the resolved version exposes its coverage ratio, gap count, and revision so
  an API or front end can display them without re-deriving the version name.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from .coverage_audit import (
    CoverageAudit,
    load_coverage_audit,
)
from .market_data_publication import (
    load_latest_market_data_before,
    resolve_latest_market_data_version,
)


_VERSION = re.compile(r"(?P<date>\d{8})(?:-r(?P<revision>[1-9]\d*))?\Z")

READY = "ready"
NO_VERSION = "no_published_version"
AUDIT_MISSING = "coverage_audit_missing"
AUDIT_INVALID = "coverage_audit_invalid"
COVERAGE_INCOMPLETE = "coverage_incomplete"
COVERAGE_PENDING = "coverage_pending"


@dataclass(frozen=True)
class MarketDataReadiness:
    """Resolved market-data version and its fitness for a research run."""

    market: str
    dataset_id: str
    as_of_date: pd.Timestamp
    resolved_version: str | None
    base_version: str | None
    revision: int
    ready: bool
    reason: str
    coverage_ratio: float | None = None
    gap_count: int | None = None
    deferred_gap_count: int | None = None
    audit_path: Path | None = None

    def to_mapping(self) -> dict[str, object]:
        """Return a JSON-safe summary for a pipeline stage result."""

        return {
            "market": self.market,
            "dataset_id": self.dataset_id,
            "as_of_date": self.as_of_date.date().isoformat(),
            "market_data_version": self.resolved_version,
            "base_market_data_version": self.base_version,
            "revision": self.revision,
            "research_ready": self.ready,
            "reason": self.reason,
            "coverage_ratio": self.coverage_ratio,
            "gap_count": self.gap_count,
            "deferred_gap_count": self.deferred_gap_count,
            "coverage_audit_path": (
                None if self.audit_path is None else str(self.audit_path)
            ),
        }


def readiness_audit_path(
    root: Path | str,
    *,
    market: str,
    version: str,
) -> Path:
    """Return the coverage-audit file belonging to one market-data version."""

    for label, value in (("market", market), ("version", version)):
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(f"{label} must be a non-empty trimmed string")
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError(f"{label} must be a safe path segment")

    return (
        Path(root)
        / f"market={market}"
        / f"version={version}"
        / "coverage_audit.json"
    )


def split_market_data_version(version: str) -> tuple[str, int]:
    """Split ``YYYYMMDD`` or ``YYYYMMDD-rN`` into its date and revision."""

    match = _VERSION.fullmatch(version or "")
    if match is None:
        raise ValueError(
            "market-data version must use YYYYMMDD or YYYYMMDD-rN"
        )

    return match.group("date"), int(match.group("revision") or 0)


def assess_market_data_readiness(
    root: Path | str,
    *,
    dataset_id: str,
    market: str,
    as_of_date: pd.Timestamp | str,
    coverage_root: Path | str | None = None,
) -> MarketDataReadiness:
    """Decide whether research may consume the latest version through a date.

    ``root`` is the market-data lake root holding ``<dataset_id>/versions/``.
    ``coverage_root`` is the directory holding ``market=<M>/version=<V>/``
    coverage audits and defaults to the lake root.
    """

    date = pd.Timestamp(as_of_date)
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")
    date = date.normalize()

    if not market or market.strip() != market:
        raise ValueError("market must be a non-empty trimmed string")

    lake_root = Path(root)
    audit_root = (
        lake_root if coverage_root is None else Path(coverage_root)
    )

    resolved = resolve_latest_market_data_version(
        lake_root,
        dataset_id=dataset_id,
        as_of_date=date,
    )

    if resolved is None:
        return MarketDataReadiness(
            market=market,
            dataset_id=dataset_id,
            as_of_date=date,
            resolved_version=None,
            base_version=None,
            revision=0,
            ready=False,
            reason=NO_VERSION,
        )

    base_version, revision = split_market_data_version(resolved)
    audit_path = readiness_audit_path(
        audit_root,
        market=market,
        version=resolved,
    )

    loaded = load_latest_market_data_before(
        lake_root,
        dataset_id=dataset_id,
        as_of_date=date + pd.Timedelta(days=1),
    )
    coverage_complete: bool | None = None
    if loaded is not None:
        coverage_complete = loaded[0].coverage_complete

    audit: CoverageAudit | None = None
    invalid_reason: str | None = None
    if audit_path.is_file():
        try:
            audit = load_coverage_audit(audit_path)
        except ValueError:
            invalid_reason = AUDIT_INVALID

    common = {
        "market": market,
        "dataset_id": dataset_id,
        "as_of_date": date,
        "resolved_version": resolved,
        "base_version": base_version,
        "revision": revision,
        "audit_path": audit_path,
    }

    if coverage_complete is False:
        # The publication itself declares that a repair revision is pending.
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=COVERAGE_PENDING,
            coverage_ratio=None if audit is None else audit.coverage_ratio,
            gap_count=None if audit is None else audit.gap_count,
            deferred_gap_count=(
                None if audit is None else audit.backfill_plan.deferred_gap_count
            ),
        )

    if invalid_reason is not None:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=invalid_reason,
        )

    if audit is None:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=AUDIT_MISSING,
        )

    if not audit.complete:
        return MarketDataReadiness(
            **common,
            ready=False,
            reason=COVERAGE_INCOMPLETE,
            coverage_ratio=audit.coverage_ratio,
            gap_count=audit.gap_count,
            deferred_gap_count=audit.backfill_plan.deferred_gap_count,
        )

    return MarketDataReadiness(
        **common,
        ready=True,
        reason=READY,
        coverage_ratio=audit.coverage_ratio,
        gap_count=audit.gap_count,
        deferred_gap_count=audit.backfill_plan.deferred_gap_count,
    )
```

### 9.2 `test/_sandbox_pytest_plugin.py`

```python
"""Sandbox-only pytest plugin: make pytest's temp directories usable again.

Why this exists
---------------
pytest creates its session temp directories with ``mode=0o700``::

    rootdir.mkdir(mode=0o700, exist_ok=True)      # _pytest/tmpdir.py (getbasetemp)
    new_path.mkdir(mode=mode)                     # _pytest/pathlib.py (make_numbered_dir)

On Windows CPython maps the POSIX ``mode`` onto ``SetFileAttributesW``: the
read-only attribute follows the *write* bit, and ``0o700`` -- which has no
group/other bits -- marks the newly created directory read-only.  On an
ordinary account that is harmless; inside the DSH file sandbox, opening a
read-only directory handle is denied, so every later scandir/iteration over the
directory fails::

    PermissionError: [WinError 5] ...\\pytest-of-<user>

That makes every fixture-backed test error during setup, even though the code
under test is fine.  ``--basetemp`` does not help because pytest cleans up the
given directory with ``Path.iterdir()`` at session finish.

What it does
------------
Normalises the mode of pytest-owned temp directories to ``0o777``, and extends
the session temp root cleanup so it survives the same sandbox restriction.
Nothing in the quantmine test suite depends on the access bits of ``tmp_path``.

Usage (the plugin is not auto-loaded)::

    $env:PYTHONPATH = "test"
    .venv-win\\Scripts\\python.exe -m pytest -p _sandbox_pytest_plugin -q
"""

from __future__ import annotations

import pathlib

_ORIGINAL_MKDIR = pathlib.Path.mkdir


def _mkdir(self: pathlib.Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False):
    """Create a directory, but never as read-only."""

    if mode & 0o200 == 0 or mode in (0o700, 0o755):
        mode = 0o777
    return _ORIGINAL_MKDIR(self, mode=mode, parents=parents, exist_ok=exist_ok)


def pytest_configure(config) -> None:
    pathlib.Path.mkdir = _mkdir  # type: ignore[method-assign]

    import _pytest.pathlib
    import _pytest.tmpdir

    def _cleanup_dead_symlinks(root: pathlib.Path) -> None:
        try:
            entries = list(root.iterdir())
        except OSError:
            return
        for left_dir in entries:
            try:
                if left_dir.is_symlink() and not left_dir.resolve().exists():
                    left_dir.unlink()
            except OSError:
                continue

    _pytest.pathlib.cleanup_dead_symlinks = _cleanup_dead_symlinks
    _pytest.tmpdir.cleanup_dead_symlinks = _cleanup_dead_symlinks
```

---

## 10. 验证命令与结果

```powershell
New-Item -ItemType Directory -Force -Path "pt" | Out-Null
$env:PYTHONPATH="test"; $env:TMPDIR="pt"; $env:TEMP="pt"; $env:TMP="pt"
.\.venv-win\Scripts\python.exe -m pytest -p _sandbox_pytest_plugin -q
# => 940 passed, 33 skipped, 2 deselected
```

回归定位：本次改动前，`test_versioned_parquet_reader_resolves_a_base_date_to_its_latest_revision`
是唯一真实失败（`'20240103' != '20240103-r1'`）。

## 11. 已知未完成

1. `config.yaml`（gitignored 的实际部署配置）**仍无** `coverage_audit` /
   `history_backfill` / `repair_publication` / `research_readiness_gate` 四段，
   生产 DAG 不会真正执行 r1 流程。
2. r1 验收第 5 条（API / 前端显示解析后的最新修订版本、覆盖率与回填状态）未开工，
   `webapi/` 与 `frontend/` 未改动。
3. 遗留只读目录 `tmp_pytest/`、`pytest-of-18410/` 无法用当前账户删除，需手工清理。
