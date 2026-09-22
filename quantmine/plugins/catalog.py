"""Safe discovery of built-in and externally packaged research bundles"""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import entry_points

from typing import Callable

from .bundles import DEFAULT_RESEARCH_BUNDLES, ResearchBundle

from .loader import PluginResolutionError

RESEARCH_BUNDLE_PROVIDER_GROUP = "quantmine.research_bundle_providers"
ResearchBundleProvider = Callable[[], Iterable[ResearchBundle]]

class ResearchBundleCatalog:
    """An immutable lookup of built_in and deployment-enabled bundles"""

    def __init__(self, bundles: Iterable[ResearchBundle]) -> None:
        indexed: dict[str, ResearchBundle] = {}
        for bundle in bundles:
            if not isinstance(bundle, ResearchBundle):
                raise TypeError(
                    "Research bundle prociders must return ResearchBundle instances"
                )
            if bundle.id in indexed:
                raise PluginResolutionError(
                    f"Duplicate research bundle id: {bundle.id!r}"
                )

            indexed[bundle.id] = bundle

        self._bundles = indexed

    @property
    def bundle_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._bundles))

    def get(self, bundle_id: str) -> ResearchBundle:
        try:
            return self._bundles[bundle_id]

        except KeyError as error:
            available = ",".join(self.bundle_ids) or "<none>"
            raise PluginResolutionError(
                f"Unknown research bundle {bundle_id!r}; available: {available}"
            ) from error

def load_research_bundle_catalog(
        *,
        enabled_provider_names: Iterable[str] = (),
        allowed_module_prefixes: Iterable[str] = ("quantmine",),
) -> ResearchBundleCatalog:
    """Load built-ins plus explicitly enabled exteranl bundle providers"""

    allowed_prefixes = tuple(allowed_module_prefixes)
    enabled_names = tuple(dict.fromkeys(enabled_provider_names))

    discovered = tuple(
        entry_points(group=RESEARCH_BUNDLE_PROVIDER_GROUP)
    )
    by_name = {entry.name : entry for entry in discovered}

    missing = sorted(set(enabled_names).difference(by_name))
    if missing:
        raise PluginResolutionError(
            "Enabled research bundle providers are not installed: "
            + ",".join(missing)
        )

    bundles = list(DEFAULT_RESEARCH_BUNDLES.values())

    for provider_name in enabled_names:
        entry = by_name[provider_name]

        if not _module_is_allowed(entry.module, allowed_prefixes):
            raise PluginResolutionError(
                f"Research bundle provider {provider_name!r} from module "
                f"{entry.module!r} is not allowed by the import policy"
            )

        provider = entry.load()
        if not callable(provider):
            raise TypeError(
                f"Research bundle provider {provider_name!r} must be callable"
            )

        try: 
            provided_bundles = tuple(provider())
        except TypeError as error:
            raise TypeError(
                f"Research bundle provider {provider_name!r} "
                f"must return an iterable of ResearchBundle"
            )
        bundles.extend(provided_bundles)
    return ResearchBundleCatalog(bundles)
            
def _module_is_allowed(
        module_name: str,
        allowed_prefixes: Iterable[str],
) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in allowed_prefixes
    )