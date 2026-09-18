"""Replaceable IC statistical-validation contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..ic_calculator import TEST_METHOD, ICVariant, run_test
from .context import SourceContext
from .contracts import PluginSpec
from .loader import resolve_plugin


@dataclass(frozen = True)
class ICValidationRequest:
    variants: Mapping[str, ICVariant]
    tests: tuple[Mapping[str, Any], ...]
    

    def __post_init__(self) -> None:
        if not isinstance(self.variants, Mapping):
            raise TypeError("variants must be a mapping")

        if not self.variants:
            raise ValueError("variants must not be empty")
        for name, variant in self.variants.items():
            if not isinstance(name, str) or not name or name.strip() != name:
                raise ValueError(
                    "variant name must be a non-empty trimmed string"
                )

            if not isinstance(variant, ICVariant):
                raise TypeError(
                    f"variant '{name}' must be an ICVariant"
                )

        if not isinstance(self.tests, tuple):
            raise TypeError("tests must be a tuple")
        seen_test_ids: set[str] = set()
        for test_spec in self.tests:
            if not isinstance(test_spec, Mapping):
                raise TypeError("every test specification must be a mapping")
            test_id = test_spec.get("id")
            variant_name = test_spec.get("input")
            method_name = test_spec.get("name")
            params = test_spec.get("params", {})

            if not isinstance(test_id, str) or not test_id or test_id.strip() != test_id:
                raise ValueError("test id must be a non-empty trimmed string")

            if test_id in seen_test_ids:
                raise ValueError(f"duplicate test id '{test_id}'")

            seen_test_ids.add(test_id)

            if not isinstance(variant_name, str) or not variant_name or variant_name.strip() != variant_name:
                raise ValueError(f"test '{test_id}' input must be a non-empty trimmed string")

            if variant_name not in self.variants:
                raise ValueError(f"test '{test_id}' uses unavailable variant '{variant_name}'")

            if not isinstance(method_name, str) or not method_name or method_name.strip() != method_name:
                raise ValueError(f"test '{test_id}' name must be a non-empty trimmed string")

            if not isinstance(params, Mapping):
                raise TypeError(f"test '{test_id}' params must be a mapping")



@dataclass(frozen = True)
class ICValidationResult:
    test_results: Mapping[str, Mapping[str, object]]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.test_results, Mapping):
            raise TypeError("test_results must be a mapping")

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

        for test_id, result in self.test_results.items():
            if not isinstance(test_id, str) or not test_id or test_id.strip() != test_id:
                raise ValueError("test id must be a non-empty trimmed string")

            if not isinstance(result, Mapping):
                raise TypeError(
                    f"test result '{test_id}' must be a mapping"
                )

@runtime_checkable
class ICValidationPlugin(Protocol):
    def validate(
            self,
            request: ICValidationRequest,
            context: SourceContext
    ) -> ICValidationResult:
        ...

@dataclass(frozen=True)
class ICValidationComponent:
    id: str
    plugin: ICValidationPlugin
    connection_ref: str | None = None
    requires_connection: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError("IC validation component id must be a non-empty trimmed string")

        if not isinstance(self.plugin, ICValidationPlugin):
            raise TypeError("plugin must implement ICValidationPlugin")

        if self.connection_ref is not None and (not self.connection_ref or self.connection_ref.strip() != self.connection_ref):
            raise ValueError("connection_ref must be a non-empty trimmed string")

        if self.requires_connection and self.connection_ref is None:
            raise ValueError(
                "connection_ref is required when requires_connection is true"
            )

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

def validate_ic_component(component: ICValidationComponent, request: ICValidationRequest, context: SourceContext) -> ICValidationResult:
    """Run one validation component and verify its output contract."""

    result = component.plugin.validate(request, context)

    if not isinstance(result, ICValidationResult):
        raise TypeError(
            f"IC validation component '{component.id}' returned {type(result).__name__}, expected ICValidationResult"
        )

    requested_ids = {test_spec["id"] for test_spec in request.tests}
    returned_ids = set(result.test_results)

    if returned_ids != requested_ids:
        missing = sorted(requested_ids - returned_ids)
        unexpected = sorted(returned_ids - requested_ids)
        raise ValueError(
            f"IC validation component '{component.id}' returned "
            f"invalid test ids: missing={missing}, unexpected={unexpected}"
        )

    return result

@dataclass(frozen=True)
class PythonICValidationPlugin:
    """Built-in validation backend using registered Python test methods."""

    def validate(self, request: ICValidationRequest, context: SourceContext) -> ICValidationResult:
        del context

        test_results: dict[str, dict[str, object]] = {}

        for test_spec in request.tests:
            test_id = test_spec["id"]
            variant_name = test_spec["input"]
            test_method = test_spec["name"]

            if test_method not in TEST_METHOD:
                raise ValueError(
                    f"unknown IC test method '{test_method}'"
                )

            test_output, corrected_output = run_test(
                variant = request.variants[variant_name],
                test_method= test_method,
                TEST_METHOD= TEST_METHOD,
                test_params= dict(test_spec.get("params", {}))
            )

            summary_payload, _ = test_output
            summary_df, _ = summary_payload
            multiple_testing_df, _ = corrected_output

            test_results[test_id] = {
                "variant_name": variant_name,
                "test_method": test_method,
                "sample_scope": "train",
                "summary": summary_df,
                "multiple_testing": multiple_testing_df,
            }
        return ICValidationResult(
            test_results = test_results,
            metadata= {"backend": "python"}
        )

def create_python_ic_validation_engine(
        **params: Any
) -> ICValidationComponent:
    if params:
        unexpected = ", ".join(sorted(params))
        raise ValueError(
            f"unsupported Python IC validation parameters: {unexpected}"
        )

    return ICValidationComponent(
        id = "python_ic_validation",
        plugin = PythonICValidationPlugin(),
        requires_connection=False,
        metadata = {"backend": "python"}
    )

def resolve_ic_validation_component(
        spec: PluginSpec,
        *,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> ICValidationComponent:
    component = resolve_plugin(spec, allowed_module_prefixes= allowed_module_prefixes)

    if not isinstance(component, ICValidationComponent):
        raise TypeError(
            f"IC validation factory {spec.entry_point!r} returned {type(component).__name__}, expected ICValidationComponent"
        )

    return component
