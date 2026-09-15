"""Replaceable IC calculation-engine contracts and built-in implementations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .context import SourceContext
from .contracts import PluginSpec
from .loader import resolve_plugin


@dataclass(frozen=True)
class ICScopeInput:
    """Aligned factor and forward-return matrices for one research scope."""

    factors: Mapping[str, pd.DataFrame]
    forward_returns: Mapping[int, pd.DataFrame]

    def __post_init__(self) -> None:
        if not self.factors:
            raise ValueError("factors must not be empty")

        if not self.forward_returns:
            raise ValueError("forward_returns must not be empty")

        for factor_name, frame in self.factors.items():
            if not factor_name or factor_name.strip() != factor_name:
                raise ValueError(
                    "factor name must be a non-empty trimmed string"
                )

            if not isinstance(frame, pd.DataFrame):
                raise TypeError(
                    f"factor '{factor_name}' must be a pandas DataFrame"
                )

        for period, frame in self.forward_returns.items():
            if (
                not isinstance(period, int) or isinstance(period, bool) or period <= 0
            ):
                raise ValueError(
                    "forward-return period must be a positive integer"
                )

            if not isinstance(frame, pd.DataFrame):
                raise TypeError(
                    f"forward return period {period} must be a pandas DataFrame"
                )

        expected_columns = next(iter(self.factors.values())).columns

        for factor_name, frame in self.factors.items():
            if not frame.columns.equals(expected_columns):
                raise ValueError(
                    f"factor '{factor_name}' ticker columns do not align"
                )

        for factor_name, frame in self.forward_returns.items():
            if not frame.columns.equals(expected_columns):
                raise ValueError(
                    f"forward return period {period} ticker columns "
                    "do not align with factor columns"
                )

@dataclass(frozen=True)
class ICCalculationRequest:
    """Serializable calculation request shared by every IC backend."""

    scopes: Mapping[str, ICScopeInput]
    method: str = "pearson"

    def __post_init__(self) -> None:
        if not self.scopes:
            raise ValueError("IC calculation scopes must not be empty")

        if self.method not in {"pearson"}:
            raise ValueError(
                f"unsupported IC calculation method: '{self.method}'"
            )

        for scope_name, scope in self.scopes.items():
            if not scope_name or scope_name.strip() != scope_name:
                raise ValueError(
                    "scope name must be a non-empty trimmed string"
                )
            if not isinstance(scope, ICScopeInput):
                raise TypeError(
                    f"scope '{scope_name}' must be an ICScopeInput"
                )

@dataclass(frozen= True)
class ICCalculationResult:
    """Normalized IC matrices produced by an engine"""

    scopes: Mapping[str, pd.DataFrame]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scopes, Mapping):
            raise TypeError("IC result scopes must be a mapping")

        for scope_name, frame in self.scopes.items():
            if not scope_name or scope_name.strip() != scope_name:
                raise ValueError(
                    "result scope must be a non-empty trimmed string"
                )
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(
                    f"result scope '{scope_name}' must be a pandas DataFrame"
                )

@runtime_checkable
class ICCalculationPlugin(Protocol):
    """Runtime interface implemented by python, C++, or CUDA IC engines."""

    def calculate(
            self,
            request: ICCalculationRequest,
            context: SourceContext,
    ) -> ICCalculationResult:
        """Calculate one IC matrix for every requested scope."""
        ...

@dataclass(frozen=True)
class ICCalculationComponent:
    """Descriptor for one replaceable IC calculation implementation."""

    id: str
    plugin: ICCalculationPlugin
    connection_ref: str | None = None
    requires_connection: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or self.id.strip() != self.id:
            raise ValueError(
                "IC calculation component id must be a non-empty trimmed string"
            )

        if not isinstance(self.plugin, ICCalculationPlugin):
            raise TypeError(
                "plugin must implement ICCalculationPlugin"
            )

        if self.requires_connection and self.connection_ref is None:
            raise ValueError(
                "connection_ref is required when requires_connection is true"
            )

def calculate_ic_component(
        component: ICCalculationComponent,
        request: ICCalculationRequest,
        context: SourceContext
) -> ICCalculationResult:
    """Run one IC component and validate its scope-level output contract"""

    result = component.plugin.calculate(request, context)

    if not isinstance(result, ICCalculationResult):
        raise TypeError(
            f"IC component '{component.id}' returned "
            f"{type(result).__name__}, expected ICCalculationResult"
        )

    requested_scopes = set(request.scopes)
    returned_scopes = set(result.scopes)

    if returned_scopes != requested_scopes:
        missing = sorted(requested_scopes - returned_scopes)
        unexpected = sorted(returned_scopes - requested_scopes)
        raise ValueError(
            f"IC component '{component.id}' returned invalid scopes: missing={missing}, unexpected={unexpected}"
        )

    return result

@dataclass(frozen=True)
class PythonICCalculationPlugin:
    """Built-in pandas implementation of cross-sectional IC."""

    def calculate(
            self,
            request: ICCalculationRequest,
            context: SourceContext
    ) -> ICCalculationResult:
        del context

        scope_results: dict[str, pd.DataFrame] = {}

        for scope_name, scope in request.scopes.items():
            columns: dict[tuple[str, int], pd.Series] = {}

            for factor_name, factor_frame in scope.factors.items():
                for period, return_frame in scope.forward_returns.items():
                    columns[(factor_name, period)] = (
                        factor_frame.corrwith(
                            return_frame,
                            axis = 1,
                            method = request.method,
                        )
                    )

            result_frame = pd.DataFrame(columns)
            result_frame.columns = pd.MultiIndex.from_tuples(
                result_frame.columns,
                names = ["factor", "period"]
            )
            scope_results[scope_name] = result_frame

        return ICCalculationResult(
            scopes = scope_results,
            metadata = {
                "backend": "python",
                "method": request.method
            }
        )

def create_python_ic_calculation_engine(
        **params: Any,
) -> ICCalculationComponent:
    """Create the built-in pandas cross-sectional IC component"""

    if params:
        unexpected = ", ".join(sorted(params))
        raise ValueError(
            f"unsupported Python IC engine parameters: {unexpected}"
        )

    return ICCalculationComponent(
        id = "python_cross_sectional_ic",
        plugin=PythonICCalculationPlugin(),
        requires_connection = False,
        metadata= {
            "backend": "python"
        }
    )

def resolve_ic_calculation_component(
        spec: PluginSpec,
        *,
        allowed_module_prefixes: Iterable[str] | None = ("quantmine",),
) -> ICCalculationComponent:
    """Resolve and validate one configured IC calculation component"""

    component = resolve_plugin(
        spec,
        allowed_module_prefixes= allowed_module_prefixes
    )

    if not isinstance(component, ICCalculationComponent):
        raise TypeError(
            f"IC engine factory {spec.entry_point!r} returned "
            f"{type(component).__name__}, expected ICCalculationComponent"
        )

    return component
