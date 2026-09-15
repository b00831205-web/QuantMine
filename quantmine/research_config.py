"""Versioned, safe snapshots for reproducible factor-research runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

import pandas as pd

from .dataset_versions import (
    AS_OF_DATE_VERSION,
    resolve_versioned_dataset_binding,
)
from .plugins.bundles import ResearchBundle, get_research_bundle
from .plugins.contracts import (
    DataBinding,
    PluginSpec,
    VersionedDatasetBinding,
)

RESEARCH_RUN_CONFIG_VERSION = 4

def _default_ic_engine_spec() -> PluginSpec:
    return PluginSpec(
        entry_point=(
            "quantmine.plugins.ic_engines:create_python_ic_calculation_engine"
        )
    )

@dataclass(frozen = True)
class ResearchRunConfig:
    """Serializable input to one factor-research run.

    The snapshot stores connection aliases, never database URLs, passwords,
    engine objects, or filesystem roots.
    """

    bundle: ResearchBundle
    data_binding: DataBinding
    factor_parameters: Mapping[str, Any]
    ic_engine: PluginSpec = field(default_factory=_default_ic_engine_spec)
    ic_research: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_bundle_id(
        cls,
        bundle_id: str,
        data_binding: DataBinding,
        *,
        factor_parameters: Mapping[str, Any] | None = None,
        ic_engine: PluginSpec | None = None,
        ic_research: Mapping[str, Any] | None = None,
    )-> ResearchRunConfig:
        return cls(
            bundle = get_research_bundle(bundle_id),
            data_binding = data_binding,
            factor_parameters = dict(factor_parameters or {}),
            ic_engine = (
                ic_engine if ic_engine is not None else _default_ic_engine_spec()
            ),
            ic_research = dict(ic_research or {})
        )

    def to_snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot suitable for research_runs.config_snapshot."""

        snap_shot = {
            "schema_version": RESEARCH_RUN_CONFIG_VERSION,
            "bundle" : {
                "id": self.bundle.id,
                "display_name": self.bundle.display_name,
                "data_source": _plugin_spec_snapshot(
                    self.bundle.data_source
                ),
                "universe":(
                    _plugin_spec_snapshot(self.bundle.universe)
                    if self.bundle.universe is not None else None
                ),
                "factor_packs": [
                    _plugin_spec_snapshot(spec)
                    for spec in self.bundle.factor_packs
                ],
                "defaults": dict(self.bundle.defaults)
            },
            "data_binding": {
                "connection_ref": self.data_binding.connection_ref,
                "dataset": self.data_binding.dataset,
                "version": self.data_binding.version,
                "universe_dataset": self.data_binding.universe_dataset,
                "benchmark_dataset": self.data_binding.benchmark_dataset,
                "benchmark_ticker": self.data_binding.benchmark_ticker,
                "adjustment": self.data_binding.adjustment,
                "start": self.data_binding.start,
                "end": self.data_binding.end,
                "tickers": list(self.data_binding.tickers),
                "metadata": dict(self.data_binding.metadata),
                "eligibility_binding": _versioned_dataset_binding_snapshot(self.data_binding.eligibility_binding)
            },
            "factor_parameters": dict(self.factor_parameters),
            "ic_engine": _plugin_spec_snapshot(self.ic_engine),
            "ic_research": dict(self.ic_research),
        }
        return _json_copy(snap_shot, label = "ResearchRunConfig")

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
    ) -> ResearchRunConfig:
        """Restore a version-1 configuration snapshot"""

        payload = _mapping(snapshot, label="PresearchRunConfig snapshot")
        version = payload.get("schema_version")
        ic_research = _mapping(payload.get("ic_research", {}), label = "ic_research")

        if version not in {1, 2, 3, RESEARCH_RUN_CONFIG_VERSION}:
            raise ValueError(
                "Unsupported research-run config schema version "
                f"{version!r}; expected 1 or {RESEARCH_RUN_CONFIG_VERSION}"
            )
        bundle_payload = _mapping(payload.get("bundle"), label = "bundle")
        binding_payload = _mapping(
            payload.get("data_binding"),
            label = "data_binding",
        )
        factor_parameters = _mapping(
            payload.get("factor_parameters", {}),
            label = "factor_parameters",
        )
        universe_payload = bundle_payload.get("universe")
        universe = (
            None if universe_payload is None else _plugin_spec_from_snapshot(universe_payload)
        )

        factor_packs_payload = bundle_payload.get("factor_packs",[])
        if not isinstance(factor_packs_payload, list):
            raise TypeError("factor_packs must be a JSON list.")

        tickers = binding_payload.get("tickers", [])
        if not isinstance(tickers, list) or not all(isinstance(ticker, str) for ticker in tickers):
            raise TypeError("data_binding.tickers must be a list of strings.")

        bundle = ResearchBundle(
            id = _string(bundle_payload.get('id'), label="bundle.id"),
            display_name = _string(
                bundle_payload.get("display_name"),
                label="bundle.display_name",
            ),
            data_source = _plugin_spec_from_snapshot(
                bundle_payload.get("data_source")
            ),
            universe = universe,
            factor_packs = tuple(
                _plugin_spec_from_snapshot(item)
                for item in factor_packs_payload
            ),
            defaults = _mapping(
                bundle_payload.get("defaults",{}),
                label = "bundle.defaults",
            )
        )

        binding = DataBinding(
            connection_ref= _optional_string(
                binding_payload.get("connection_ref"),
                label = "data_binding.connection_ref"
            ),
            dataset = _string(
                binding_payload.get("dataset"),
                label = "data_binding.dataset",
            ),
            version = _optional_string(
                binding_payload.get("version"),
                label = "data_binding.version"
            ),
            universe_dataset = _optional_string(
                binding_payload.get("universe_dataset"),
                label = "data_binding.universe_dataset",
            ),
            benchmark_dataset = _optional_string(
                binding_payload.get("benchmark_dataset"),
                label = "data_binding.benchmark_dataset"
            ),
            benchmark_ticker = _optional_string(
                binding_payload.get("benchmark_ticker"),
                label = "data_binding.benchmark_ticker"
            ),
            adjustment = _optional_string(
                binding_payload.get("adjustment"),
                label = "data_binding.adjustment"
            ),

            start = _optional_string(
                binding_payload.get("start"),
                label = "data_binding.start",
            ),
            end = _optional_string(
                binding_payload.get("end"),
                label = "data_binding.end"
            ),
            tickers = tuple(tickers),
            metadata = _mapping(
                binding_payload.get("metadata", {}),
                label = "data_binding.metadata",
            ),
            eligibility_binding = _versioned_dataset_binding_from_snapshot(
                binding_payload.get("eligibility_binding")
            ) 
        )

        ic_engine_payload = payload.get("ic_engine")

        if ic_engine_payload is None:
            if version in {1,2,3}:
                ic_engine = _default_ic_engine_spec()
            else:
                raise TypeError(
                    "version-4 research-run config requires ic_engine"
                )

        else:
            ic_engine = _plugin_spec_from_snapshot(ic_engine_payload)

        return cls(
            bundle = bundle,
            data_binding = binding,
            factor_parameters = factor_parameters,
            ic_engine = ic_engine,
            ic_research = ic_research,
        )

def resolve_research_run_config_for_as_of_date(
        config: ResearchRunConfig,
        *,
        as_of_date: pd.Timestamp | str,
) -> ResearchRunConfig:
    """Resolve date-version selectors before one scheduled research run."""

    if not isinstance(config, ResearchRunConfig):
        raise TypeError("config must be a ResearchRunConfig")

    date = pd.Timestamp(as_of_date)
    if pd.isna(date):
        raise ValueError("as_of_date must not be NaT")

    binding = config.data_binding
    resolved_eligibility = (
        None
        if binding.eligibility_binding is None
        else resolve_versioned_dataset_binding(
            binding.eligibility_binding,
            as_of_date=date,
        )
    )
    resolved_version = (
        date.strftime("%Y%m%d")
        if binding.version == AS_OF_DATE_VERSION
        else binding.version
    )
    return replace(
        config,
        data_binding = replace(
            binding, version = resolved_version, eligibility_binding = resolved_eligibility
        )
    )

def _plugin_spec_snapshot(spec: PluginSpec)-> dict[str, Any]:
    return {
        "entry_point": spec.entry_point,
        "params": dict(spec.params)
    }

def _plugin_spec_from_snapshot(value: object) -> PluginSpec:
    payload = _mapping(value, label="plugin specfication")
    return PluginSpec(
        entry_point = _string(
            payload.get("entry_point"),
            label = "plugin specfication.entry_point",
        ),
        params = _mapping(
            payload.get("params", {}),
            label = "plugin specfication.params"
        )
    )

def _json_copy(value: object, *, label: str)-> dict[str,Any]:
    try:
        serialized = json.dumps(
            value,
            allow_nan = False,
            sort_keys= True,
        )
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{label} must contain only JSON-serializable values"
        ) from error

    result = json.loads(serialized)
    return _mapping(result, label= label)

def _mapping(value: object, *, label: str)->dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a JSON object")
    return dict(value)

def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{label} must be a non-empty string")
    return value

def _optional_string(value:object, * ,label: str) -> str |None:
    if value is None:
        return None

    return _string(value, label= label)

def _versioned_dataset_binding_snapshot(
        binding: VersionedDatasetBinding | None,
) -> dict[str, str] | None:
    if binding is None:
        return None

    return {
        "connection_ref" : binding.connection_ref,
        "dataset": binding.dataset,
        "market": binding.market,
        "version": binding.version
    }

def _versioned_dataset_binding_from_snapshot(
        value: object,
) -> VersionedDatasetBinding | None:
    if value is None:
        return None

    payload = _mapping(value, label = "data_binding.eligibility_binding")
    return VersionedDatasetBinding(
        connection_ref=_string(payload.get("connection_ref"), label = "data_binding.eligibility_binding.connection_ref"),
        dataset = _string(payload.get("dataset"), label = "data_binding.eligibility_binding.dataset"),
        market = _string(payload.get("market"), label = "data_binding.eligibility_binding.market"),
        version = _string(payload.get("version"), label="data_binding.eligibility_binding.version")
    )
