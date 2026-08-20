"""Explicit, allow-listable plugin factory resolution."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Iterable

from .contracts import PluginSpec

class PluginResolutionError(ValueError):
    """ Raised when a configured plugin cannot safely be resolved"""

def _parse_entry_point(entry_point: str) -> tuple[str, str]: #检查模块前缀白名单，未来普通用户只能选择管理员允许的已部署插件、不能借entry point执行任意python
    module_name, separator, attribute_name = entry_point.partition(':')
    if not separator or not module_name or not attribute_name:
        raise PluginResolutionError(
            "plugin entry_point must have the form 'package.modeul:factory'"
        )
    if "." in attribute_name or attribute_name.startswith('_'):
        raise PluginResolutionError(
            'plugin factory must be one public module attribute'
        )
    return module_name, attribute_name

def _module_is_allowed(
        module_name: str,
        allowed_module_prefixes: Iterable[str] | None,
) -> bool:
    if allowed_module_prefixes is None:
        return True
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}")
        for prefix in allowed_module_prefixes
    )

def resolve_plugin( #动态导入工厂、传入PluginSpec.params、获取组件实例
        spec: PluginSpec,
        *,
        allowed_module_prefixes: Iterable[str] | None = None,
) -> Any:
    """Instantiate a configured plugin factory.

    API-facing code must pass an allow-list. Resolving arbitrary import paths
    supplied by a user is code execution and must not be treated as safe.
    """
    module_name , attribute_name = _parse_entry_point(spec.entry_point)
    if not _module_is_allowed(module_name, allowed_module_prefixes):
        raise PluginResolutionError(
            f"plugin module '{module_name}' is not allowed" 
        )
    try: 
        module = import_module(module_name)
    except AttributeError as error:
        raise PluginResolutionError(
            f"plugin factory '{attribute_name}' was not found in '{module_name}'"
        ) from error

    try:
        factory: Callable[..., Any] = getattr(module, attribute_name)

    except AttributeError as error:
        raise PluginResolutionError(
            f"plugin factory '{attribute_name}' was not found in {module_name}"
        ) from error

    if not callable(factory):
        raise PluginResolutionError(
            f"plugin attribute '{spec.entry_point}' is not callable"
        )
    try:
        return factory(**dict(spec.params))
    except TypeError as error:
        raise PluginResolutionError(
            f"invalid parameters for plugin '{spec.entry_point}': {error}"
      ) from error