"""Contracts for replaceable Python, C++, or CUDA IC calculation engines."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantmine.ic_calculator import calculate_ic
from quantmine.plugins.bundles import ResearchBundle
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import DataBinding, PluginSpec
from quantmine.plugins.ic_engines import (
    ICCalculationComponent,
    ICCalculationRequest,
    ICCalculationResult,
    ICScopeInput,
    PythonICCalculationPlugin,
    calculate_ic_component,
    create_python_ic_calculation_engine,
    resolve_ic_calculation_component,
)
from quantmine.plugins.ic_validators import (
    create_python_ic_validation_engine,
)
from quantmine.research_config import ResearchRunConfig
from quantmine.storage.connections import ConnectionRegistry
from quantmine.workflows import ic as ic_workflow_module
from quantmine.workflows.ic import (
    run_ic_workflow,
    run_persisted_ic_workflow,
)


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=1001,
        artifact_dir=tmp_path / "artifacts",
    )


def _request() -> ICCalculationRequest:
    dates = pd.date_range("2024-01-02", periods=3, freq="B")
    columns = ["A", "B", "C"]
    factor = pd.DataFrame(
        [[1.0, 2.0, 3.0], [3.0, 2.0, 1.0], [1.0, 3.0, 2.0]],
        index=dates,
        columns=columns,
    )
    forward = pd.DataFrame(
        [[0.01, 0.02, 0.03], [0.03, 0.02, 0.01], [0.01, 0.03, 0.02]],
        index=dates,
        columns=columns,
    )
    return ICCalculationRequest(
        scopes={
            "train": ICScopeInput(
                factors={"momentum": factor},
                forward_returns={1: forward},
            ),
            "test": ICScopeInput(
                factors={"momentum": factor.iloc[:2]},
                forward_returns={1: forward.iloc[:2]},
            ),
        },
        method="pearson",
    )


def test_python_ic_plugin_returns_one_normalized_frame_per_scope(
    tmp_path: Path,
) -> None:
    result = PythonICCalculationPlugin().calculate(
        _request(),
        _context(tmp_path),
    )

    assert isinstance(result, ICCalculationResult)
    assert set(result.scopes) == {"train", "test"}
    assert list(result.scopes["train"].columns) == [("momentum", 1)]
    assert result.scopes["train"].columns.names == ["factor", "period"]
    np.testing.assert_allclose(
        result.scopes["train"][("momentum", 1)].to_numpy(),
        np.ones(3),
    )
    assert result.metadata == {
        "backend": "python",
        "method": "pearson",
    }


def test_python_ic_component_factory_exposes_backend_without_connections() -> None:
    component = create_python_ic_calculation_engine()

    assert component.id == "python_cross_sectional_ic"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert component.metadata["backend"] == "python"
    assert isinstance(component.plugin, PythonICCalculationPlugin)


def test_ic_component_resolves_from_an_allowlisted_persistent_spec() -> None:
    component = resolve_ic_calculation_component(
        PluginSpec(
            "quantmine.plugins.ic_engines:"
            "create_python_ic_calculation_engine"
        ),
        allowed_module_prefixes=("quantmine",),
    )

    assert component.id == "python_cross_sectional_ic"
    assert isinstance(component.plugin, PythonICCalculationPlugin)


def test_ic_request_rejects_unsupported_method() -> None:
    request = _request()

    with pytest.raises(ValueError, match="method"):
        ICCalculationRequest(scopes=request.scopes, method="kendall")


def test_ic_scope_rejects_misaligned_factor_and_return_tickers() -> None:
    request = _request()
    train = request.scopes["train"]
    bad_return = train.forward_returns[1].rename(columns={"C": "D"})

    with pytest.raises(ValueError, match="ticker|columns"):
        ICScopeInput(
            factors=train.factors,
            forward_returns={1: bad_return},
        )


def test_ic_result_rejects_missing_requested_scope() -> None:
    request = _request()

    class IncompletePlugin:
        def calculate(self, request, context):
            del request, context
            return ICCalculationResult(
                scopes={"train": pd.DataFrame()},
                metadata={"backend": "incomplete"},
            )

    with pytest.raises(ValueError, match="scope"):
        calculate_ic_component(
            ICCalculationComponent(
                id="incomplete",
                plugin=IncompletePlugin(),
            ),
            request,
            _context(Path("artifacts")),
        )


def test_legacy_calculate_ic_accepts_an_injected_component_without_changing_output(
    tmp_path: Path,
) -> None:
    request = _request()
    expected = {
        scope_name: pd.DataFrame(
            {("custom", 1): [0.25]},
            index=pd.DatetimeIndex(["2024-01-02"]),
        )
        for scope_name in request.scopes
    }
    for frame in expected.values():
        frame.columns = pd.MultiIndex.from_tuples(
            frame.columns,
            names=["factor", "period"],
        )

    class RecordingPlugin:
        received_request = None
        received_context = None

        def calculate(self, calculation_request, context):
            self.received_request = calculation_request
            self.received_context = context
            return ICCalculationResult(
                scopes=expected,
                metadata={"backend": "recording"},
            )

    plugin = RecordingPlugin()
    component = ICCalculationComponent(id="recording", plugin=plugin)
    context = _context(tmp_path)
    output_path = tmp_path / "cs_ic.parquet"
    prepared_input = {
        "factors": {
            name: scope.factors for name, scope in request.scopes.items()
        },
        "forward_returns": {
            name: scope.forward_returns
            for name, scope in request.scopes.items()
        },
    }

    result = calculate_ic(
        prepared_input,
        output_path=output_path,
        component=component,
        context=context,
    )

    assert set(result) == set(expected)
    for scope_name, expected_frame in expected.items():
        pd.testing.assert_frame_equal(result[scope_name], expected_frame)
    assert plugin.received_context is context
    assert set(plugin.received_request.scopes) == {"train", "test"}
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "cs_ic_train.parquet"),
        expected["train"],
    )
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "cs_ic_test.parquet"),
        expected["test"],
    )


def test_ic_workflow_forwards_the_injected_engine_and_context(
    tmp_path: Path,
) -> None:
    dates = pd.date_range("2024-01-02", periods=20, freq="B")
    close = pd.DataFrame(
        {
            "A": np.arange(20, dtype=float) + 100,
            "B": np.arange(20, dtype=float) ** 2 + 100,
            "C": np.arange(20, dtype=float) ** 3 + 100,
        },
        index=dates,
    )
    factors = {"momentum": close.pct_change()}

    class RecordingPythonPlugin:
        def __init__(self) -> None:
            self.calls: list[
                tuple[ICCalculationRequest, SourceContext]
            ] = []

        def calculate(self, request, context):
            self.calls.append((request, context))
            return PythonICCalculationPlugin().calculate(request, context)

    plugin = RecordingPythonPlugin()
    component = ICCalculationComponent(id="recording_python", plugin=plugin)
    context = _context(tmp_path)

    variants, test_results = run_ic_workflow(
        close,
        factors,
        {
            "train_end": str(dates[9].date()),
            "test_start": str(dates[10].date()),
            "periods": [1],
            "processors": [
                {
                    "id": "orthogonalized",
                    "name": "orthogonalize",
                    "input": "raw",
                    "params": {"periods": [1]},
                }
            ],
            "tests": [],
        },
        ic_component=component,
        context=context,
    )

    assert set(variants) == {"raw", "orthogonalized"}
    assert test_results == {}
    assert len(plugin.calls) == 2
    assert all(call_context is context for _, call_context in plugin.calls)


def test_persisted_ic_workflow_resolves_the_snapshotted_engine_with_allowlist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dates = pd.date_range("2024-01-02", periods=20, freq="B")
    close = pd.DataFrame(
        {
            "A": np.arange(20, dtype=float) + 100,
            "B": np.arange(20, dtype=float) ** 2 + 100,
            "C": np.arange(20, dtype=float) ** 3 + 100,
        },
        index=dates,
    )
    factors = {"momentum": close.pct_change()}
    engine_spec = PluginSpec("vendor_ic:create_cuda_engine")
    validation_spec = PluginSpec(
        "vendor_validation:create_bootstrap_validator"
    )
    run_config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="fixture",
            display_name="Fixture",
            data_source=PluginSpec("fixture:create_source"),
            universe=None,
            factor_packs=(PluginSpec("fixture:create_factors"),),
        ),
        data_binding=DataBinding(
            connection_ref=None,
            dataset="fixture_prices",
        ),
        factor_parameters={},
        ic_engine=engine_spec,
        validation_engine=validation_spec,
        ic_research={
            "train_end": str(dates[9].date()),
            "test_start": str(dates[10].date()),
            "periods": [1],
            "processors": [],
            "tests": [],
        },
    )
    observed = {}
    ic_component = create_python_ic_calculation_engine()
    validation_component = create_python_ic_validation_engine()

    def fake_resolve_ic(spec, *, allowed_module_prefixes):
        observed["ic_spec"] = spec
        observed["ic_allowed_module_prefixes"] = allowed_module_prefixes
        return ic_component

    def fake_resolve_validation(spec, *, allowed_module_prefixes):
        observed["validation_spec"] = spec
        observed["validation_allowed_module_prefixes"] = (
            allowed_module_prefixes
        )
        return validation_component

    monkeypatch.setattr(
        ic_workflow_module,
        "resolve_ic_calculation_component",
        fake_resolve_ic,
        raising=False,
    )
    monkeypatch.setattr(
        ic_workflow_module,
        "resolve_ic_validation_component",
        fake_resolve_validation,
    )
    context = _context(tmp_path)

    variants, test_results = run_persisted_ic_workflow(
        config=run_config,
        close=close,
        factors=factors,
        context=context,
        allowed_module_prefixes=(
            "quantmine",
            "vendor_ic",
            "vendor_validation",
        ),
    )

    assert observed == {
        "ic_spec": engine_spec,
        "ic_allowed_module_prefixes": (
            "quantmine",
            "vendor_ic",
            "vendor_validation",
        ),
        "validation_spec": validation_spec,
        "validation_allowed_module_prefixes": (
            "quantmine",
            "vendor_ic",
            "vendor_validation",
        ),
    }
    assert set(variants) == {"raw"}
    assert test_results == {}


def test_persisted_ic_workflow_reuses_pre_resolved_components(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = ResearchRunConfig(
        bundle=ResearchBundle(
            id="fixture",
            display_name="Fixture",
            data_source=PluginSpec("fixture:create_source"),
            universe=None,
            factor_packs=(PluginSpec("fixture:create_factors"),),
        ),
        data_binding=DataBinding(
            connection_ref=None,
            dataset="fixture_prices",
        ),
        factor_parameters={},
        ic_research={"periods": [1]},
    )
    ic_component = create_python_ic_calculation_engine()
    validation_component = create_python_ic_validation_engine()
    observed: dict[str, object] = {}

    def fail_resolve(*args, **kwargs):
        del args, kwargs
        raise AssertionError("pre-resolved component was resolved again")

    def fake_run_ic_workflow(*args, **kwargs):
        del args
        observed.update(kwargs)
        return {}, {}

    monkeypatch.setattr(
        ic_workflow_module,
        "resolve_ic_calculation_component",
        fail_resolve,
    )
    monkeypatch.setattr(
        ic_workflow_module,
        "resolve_ic_validation_component",
        fail_resolve,
    )
    monkeypatch.setattr(
        ic_workflow_module,
        "run_ic_workflow",
        fake_run_ic_workflow,
    )

    result = run_persisted_ic_workflow(
        config=config,
        close=object(),
        factors={},
        context=_context(tmp_path),
        ic_component=ic_component,
        validation_component=validation_component,
    )

    assert result == ({}, {})
    assert observed["ic_component"] is ic_component
    assert observed["validation_component"] is validation_component
