"""Name-to-implementation registries.

The plugin mechanism behind factors, factor selectors, variant processors, and
portfolio weighting. Each subsystem creates its own registry, implementations
register under a string name, and configs then select one by that name. Adding
an implementation therefore never requires editing a dispatch site.
"""


def make_registry():
    """Create a fresh registry and its decorator.

    Returns:
        A tuple of ``(registry, register)``. ``registry`` is the live
        ``{name: implementation}`` dict; ``register(name)`` returns a decorator
        that records the decorated object under ``name`` and returns it
        unchanged, so the implementation stays directly callable too.
    """
    registry = {}
    def register(name: str):
        """Return a decorator registering the decorated object as ``name``."""
        def decorator(func):
            """Record ``func`` under the captured name and return it unchanged."""
            registry[name] = func
            return func
        return decorator

    return registry, register

def validate_in_registry(value: str, registry: dict, field_name: str = 'value'):
    """Raise ValueError if ``value`` is not a registered name.

    Lets configs fail fast with a clear message at parse time, instead of
    surfacing a KeyError deep inside a run.
    """
    if value not in registry:
        raise ValueError(f"invalid {field_name}: '{value}' ")

