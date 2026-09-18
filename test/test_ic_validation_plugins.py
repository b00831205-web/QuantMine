"""Contract tests for replaceable IC statistical-validation plugins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quantmine.ic_calculator import ICVariant
from quantmine.plugins import ic_validators as validator_module
from quantmine.plugins.context import SourceContext
from quantmine.plugins.contracts import PluginSpec
from quantmine.plugins.ic_validators import (
    ICValidationComponent,
    ICValidationPlugin,
    ICValidationRequest,
    ICValidationResult,
    PythonICValidationPlugin,
    create_python_ic_validation_engine,
    resolve_ic_validation_component,
    validate_ic_component,
)
from quantmine.storage.connections import ConnectionRegistry


def _variant() -> ICVariant:
    return ICVariant(train={}, test={}, transforms=[])


def _test_spec(**overrides: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "id": "newey_raw",
        "input": "raw",
        "name": "newey_test",
        "params": {},
    }
    spec.update(overrides)
    return spec


def _context(tmp_path: Path) -> SourceContext:
    return SourceContext(
        connections=ConnectionRegistry({}),
        run_id=1001,
        artifact_dir=tmp_path / "artifacts",
    )


class StubValidationPlugin:
    def validate(
        self,
        request: ICValidationRequest,
        context: SourceContext,
    ) -> ICValidationResult:
        del request, context
        return ICValidationResult(
            test_results={"newey_raw": {"summary": object()}},
            metadata={"backend": "stub"},
        )


@pytest.mark.parametrize("tests", [(), (_test_spec(),)])
def test_validation_request_accepts_variants_and_tuple_test_specs(
    tests: tuple[dict[str, Any], ...],
) -> None:
    request = ICValidationRequest(
        variants={"raw": _variant()},
        tests=tests,
    )

    assert tuple(request.variants) == ("raw",)
    assert request.tests == tests


def test_validation_request_rejects_empty_variants() -> None:
    with pytest.raises(ValueError, match="variants must not be empty"):
        ICValidationRequest(variants={}, tests=())


@pytest.mark.parametrize("name", ["", " raw", "raw "])
def test_validation_request_rejects_invalid_variant_names(name: str) -> None:
    with pytest.raises(ValueError, match="variant name"):
        ICValidationRequest(variants={name: _variant()}, tests=())


def test_validation_request_requires_ic_variants() -> None:
    with pytest.raises(TypeError, match="must be an ICVariant"):
        ICValidationRequest(variants={"raw": object()}, tests=())  # type: ignore[dict-item]


def test_validation_request_requires_a_tuple_of_mapping_specs() -> None:
    with pytest.raises(TypeError, match="tests must be a tuple"):
        ICValidationRequest(  # type: ignore[arg-type]
            variants={"raw": _variant()},
            tests=[],
        )

    with pytest.raises(TypeError, match="every test specification"):
        ICValidationRequest(  # type: ignore[arg-type]
            variants={"raw": _variant()},
            tests=(object(),),
        )


def test_validation_request_rejects_duplicate_test_ids() -> None:
    with pytest.raises(ValueError, match="duplicate test id 'newey_raw'"):
        ICValidationRequest(
            variants={"raw": _variant()},
            tests=(_test_spec(), _test_spec()),
        )


def test_validation_request_accepts_two_distinct_tests() -> None:
    request = ICValidationRequest(
        variants={"raw": _variant()},
        tests=(
            _test_spec(),
            _test_spec(id="newey_raw_2"),
        ),
    )

    assert [spec["id"] for spec in request.tests] == [
        "newey_raw",
        "newey_raw_2",
    ]


def test_validation_request_rejects_unknown_input_variant() -> None:
    with pytest.raises(ValueError, match="uses unavailable variant 'missing'"):
        ICValidationRequest(
            variants={"raw": _variant()},
            tests=(_test_spec(input="missing"),),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", " bad", "test id"),
        ("input", " raw", "input"),
        ("name", "", "name"),
    ],
)
def test_validation_request_rejects_invalid_required_test_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ICValidationRequest(
            variants={"raw": _variant()},
            tests=(_test_spec(**{field: value}),),
        )


def test_validation_request_requires_mapping_params() -> None:
    with pytest.raises(TypeError, match="params must be a mapping"):
        ICValidationRequest(
            variants={"raw": _variant()},
            tests=(_test_spec(params=[]),),
        )


def test_validation_result_accepts_empty_results_and_metadata() -> None:
    result = ICValidationResult(
        test_results={},
        metadata={"backend": "python"},
    )

    assert result.test_results == {}
    assert result.metadata == {"backend": "python"}


def test_validation_result_validates_ids_and_payloads() -> None:
    with pytest.raises(ValueError, match="test id"):
        ICValidationResult(test_results={" bad": {}})

    with pytest.raises(TypeError, match="must be a mapping"):
        ICValidationResult(  # type: ignore[arg-type]
            test_results={"newey_raw": object()},
        )


def test_validation_plugin_protocol_and_component_accept_valid_plugin() -> None:
    plugin = StubValidationPlugin()

    assert isinstance(plugin, ICValidationPlugin)
    component = ICValidationComponent(
        id="python_ic_validation",
        plugin=plugin,
        metadata={"backend": "python"},
    )

    assert component.plugin is plugin
    assert component.requires_connection is False


def test_validation_component_rejects_non_plugin() -> None:
    with pytest.raises(TypeError, match="ICValidationPlugin"):
        ICValidationComponent(  # type: ignore[arg-type]
            id="invalid",
            plugin=object(),
        )


def test_validation_component_requires_declared_connection() -> None:
    with pytest.raises(ValueError, match="connection_ref is required"):
        ICValidationComponent(
            id="remote_validation",
            plugin=StubValidationPlugin(),
            requires_connection=True,
        )


def test_validation_component_rejects_invalid_connection_ref() -> None:
    with pytest.raises(ValueError, match="connection_ref"):
        ICValidationComponent(
            id="remote_validation",
            plugin=StubValidationPlugin(),
            connection_ref=" remote",
        )


def test_python_validation_plugin_normalizes_registered_test_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    summary = pd.DataFrame({"t_stat": [2.4], "p_value": [0.02]})
    corrected = pd.DataFrame({"BH_significant": [True]})
    observed: dict[str, object] = {}

    def fake_run_test(**kwargs):
        observed.update(kwargs)
        return ((summary, False), "newey_test"), (corrected, "newey_test")

    monkeypatch.setitem(validator_module.TEST_METHOD, "stub_test", object())
    monkeypatch.setattr(validator_module, "run_test", fake_run_test)
    variant = _variant()
    request = ICValidationRequest(
        variants={"raw": variant},
        tests=(_test_spec(name="stub_test", params={"lag": 2}),),
    )

    result = PythonICValidationPlugin().validate(
        request,
        _context(tmp_path),
    )

    assert result.metadata == {"backend": "python"}
    assert result.test_results["newey_raw"] == {
        "variant_name": "raw",
        "test_method": "stub_test",
        "sample_scope": "train",
        "summary": summary,
        "multiple_testing": corrected,
    }
    assert observed == {
        "variant": variant,
        "test_method": "stub_test",
        "TEST_METHOD": validator_module.TEST_METHOD,
        "test_params": {"lag": 2},
    }


def test_python_validation_plugin_accepts_an_empty_test_plan(
    tmp_path: Path,
) -> None:
    result = PythonICValidationPlugin().validate(
        ICValidationRequest(variants={"raw": _variant()}, tests=()),
        _context(tmp_path),
    )

    assert result.test_results == {}


def test_python_validation_plugin_rejects_unknown_method(
    tmp_path: Path,
) -> None:
    request = ICValidationRequest(
        variants={"raw": _variant()},
        tests=(_test_spec(name="missing_test_method"),),
    )

    with pytest.raises(ValueError, match="unknown IC test method"):
        PythonICValidationPlugin().validate(request, _context(tmp_path))


def test_validation_component_rejects_missing_or_unexpected_results(
    tmp_path: Path,
) -> None:
    class IncompletePlugin:
        def validate(self, request, context):
            del request, context
            return ICValidationResult(test_results={})

    request = ICValidationRequest(
        variants={"raw": _variant()},
        tests=(_test_spec(),),
    )

    with pytest.raises(ValueError, match="missing=.*newey_raw"):
        validate_ic_component(
            ICValidationComponent(id="incomplete", plugin=IncompletePlugin()),
            request,
            _context(tmp_path),
        )


def test_validation_component_rejects_wrong_return_type(
    tmp_path: Path,
) -> None:
    class InvalidPlugin:
        def validate(self, request, context):
            del request, context
            return {}

    request = ICValidationRequest(variants={"raw": _variant()}, tests=())

    with pytest.raises(TypeError, match="expected ICValidationResult"):
        validate_ic_component(
            ICValidationComponent(id="invalid", plugin=InvalidPlugin()),
            request,
            _context(tmp_path),
        )


def test_python_validation_factory_and_allowlisted_resolution() -> None:
    component = create_python_ic_validation_engine()

    assert component.id == "python_ic_validation"
    assert component.requires_connection is False
    assert component.connection_ref is None
    assert component.metadata == {"backend": "python"}
    assert isinstance(component.plugin, PythonICValidationPlugin)

    resolved = resolve_ic_validation_component(
        PluginSpec(
            "quantmine.plugins.ic_validators:"
            "create_python_ic_validation_engine"
        ),
        allowed_module_prefixes=("quantmine",),
    )
    assert resolved.id == "python_ic_validation"


def test_python_validation_factory_rejects_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unsupported.*unexpected"):
        create_python_ic_validation_engine(unexpected=True)
