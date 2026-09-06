"""Tests for safe discovery of externally packaged research bundles."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from quantmine.plugins import catalog
from quantmine.plugins.bundles import ResearchBundle
from quantmine.plugins.contracts import PluginSpec
from quantmine.plugins.loader import PluginResolutionError


def _external_bundle(bundle_id: str = "vendor_cn_v1") -> ResearchBundle:
    return ResearchBundle(
        id=bundle_id,
        display_name="Vendor China strategy",
        data_source=PluginSpec("vendor_quant.cn:create_source"),
        universe=None,
        factor_packs=(
            PluginSpec("vendor_quant.cn:create_factor_pack"),
        ),
    )


@dataclass
class FakeEntryPoint:
    name: str
    module: str
    provider: object
    loads: int = 0

    def load(self) -> object:
        self.loads += 1
        return self.provider


def test_catalog_discovers_only_an_explicitly_enabled_external_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        name="vendor_cn",
        module="vendor_quant.provider",
        provider=lambda: (_external_bundle(),),
    )
    disabled = FakeEntryPoint(
        name="disabled",
        module="vendor_quant.disabled",
        provider=lambda: (_external_bundle("disabled_v1"),),
    )
    monkeypatch.setattr(
        catalog,
        "entry_points",
        lambda *, group: (entry, disabled),
    )

    discovered = catalog.load_research_bundle_catalog(
        enabled_provider_names=("vendor_cn",),
        allowed_module_prefixes=("quantmine", "vendor_quant"),
    )

    assert discovered.get("vendor_cn_v1") == _external_bundle()
    assert "us_equity_v1" in discovered.bundle_ids
    assert entry.loads == 1
    assert disabled.loads == 0


def test_catalog_rejects_a_provider_outside_the_import_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        name="untrusted",
        module="untrusted_vendor.provider",
        provider=lambda: (_external_bundle(),),
    )
    monkeypatch.setattr(
        catalog,
        "entry_points",
        lambda *, group: (entry,),
    )

    with pytest.raises(PluginResolutionError, match="not allowed"):
        catalog.load_research_bundle_catalog(
            enabled_provider_names=("untrusted",),
            allowed_module_prefixes=("quantmine", "vendor_quant"),
        )

    assert entry.loads == 0


def test_catalog_rejects_an_external_bundle_id_that_shadows_a_builtin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = FakeEntryPoint(
        name="shadow",
        module="vendor_quant.provider",
        provider=lambda: (_external_bundle("us_equity_v1"),),
    )
    monkeypatch.setattr(
        catalog,
        "entry_points",
        lambda *, group: (entry,),
    )

    with pytest.raises(PluginResolutionError, match="Duplicate research bundle"):
        catalog.load_research_bundle_catalog(
            enabled_provider_names=("shadow",),
            allowed_module_prefixes=("quantmine", "vendor_quant"),
        )
