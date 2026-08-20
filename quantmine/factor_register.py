"""Factor computation driver.

Factors declare their inputs through their parameter names, and this module
fills them from a shared pool by matching those names. Because one factor may
consume another's output, a first pass computes everything whose inputs are
already available and ``try_loop`` then retries the failures with newly
completed factors added to the pool. Dependency chains therefore resolve in any
declaration order, without factors having to name their dependencies.
"""
import inspect
from . import datareader as dr
from .registry import make_registry
from collections.abc import Iterable, Mapping

FACTOR_REGISTRY, factor_registry=make_registry()

def call_single_factors(func, param_pool: dict):
    """Call one factor, filling its parameters by name from ``param_pool``.

    Parameters carrying defaults may be absent from the pool.

    Raises:
        KeyError: If a parameter has neither a pooled value nor a default. The
            callers treat this as "inputs not ready yet" rather than fatal.
    """
    sig = inspect.signature(func)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name in param_pool:
            kwargs[name] = param_pool[name]
        elif param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default
        else:
            raise KeyError(f"missing value for '{name}'")
    return func(**kwargs)

def calculate_all_factors(param_pool: dict, factor_names: Iterable[str] | None = None)-> tuple[dict, dict]:
    """Compute every registered factor, resolving inter-factor dependencies.

    Returns:
        A tuple of ``(pending, completed)``. ``completed`` maps factor name to
        its frame, with None for factors whose dependencies never resolved;
        ``pending`` holds those unresolved names and their errors.
    """
    registry = (
        FACTOR_REGISTRY if factor_names is None else _selected_factor_registry(factor_names)
    )

    result = {}
    failures = {}
    for factor_name, func in registry.items():
        try:
            result[factor_name] = call_single_factors(func, param_pool)
        except KeyError as error:
            print(f"factor {factor_name} lacks kwargs: {error}")
            failures[factor_name] = str(error)
    pending, completed = try_loop(
        failures, result, param_pool, registry = registry
    )

    print(f"still failure: {pending}")
    return pending, completed


def try_loop(failure: dict, result: dict, param_pool:dict, *, registry : Mapping[str, object] | None = None)-> tuple[dict, dict]:
    """Retry unresolved factors until a full round makes no progress.
    """

    active_registry = FACTOR_REGISTRY if registry is None else registry
    pending = failure.copy()
    completed = result.copy()
    while pending:
        length = len(pending)
        for factor_name in list(pending.keys()):
            param_pool_update = {**param_pool, **completed}
            try:
                completed[factor_name] = call_single_factors(active_registry[factor_name], param_pool_update)
                del pending[factor_name]
            except KeyError:
                continue
        if len(pending) == length:
            #a full round with no progress means the remaining factors' dependencies
            #can never be satisfied: mark them all failed and exit the while loop,
            #otherwise this loops forever (marking only the first one and staying in
            #the loop leaks None into param_pool and raises an uncaught TypeError)
            for factor_name in pending:
                completed[factor_name] = None
                print(f"factor {factor_name} failed: unresolved dependencies")
            break
    return pending, completed

def build_param_pool(data: dr.MarketData, tickers: list = None, **extra_param)->dict:
    """Assemble the input pool factors draw their parameters from.

    Args:
        data: Loaded market data; only the fields actually present are added.
        tickers: Universe to compute over. Defaults to ``data.close``'s columns.
        **extra_param: Extra factor parameters (window lengths, half-lives),
            which override the derived entries.
    """
    param_pool = {}
    if tickers is None:
        param_pool['tickers'] = data.close.columns
    else: 
        param_pool['tickers'] = tickers
    if data.close is not None:
        param_pool['close'] = data.close
    if data.volume is not None:
        param_pool['volume'] = data.volume
    param_pool.update(extra_param)
    return param_pool


def drop_intermediates(factors: dict) -> dict:
    """Drop the intermediates, leaving only things worth scoring as signals.

    ``calculate_all_factors`` deliberately returns everything it computed,
    because a factor's dependencies are part of that result. But not everything
    computed is a factor: see ``factor_mining.INTERMEDIATE_FACTORS`` for why a
    stock's own return is an input rather than a signal. Persisting them would
    put them in front of the IC tests and the backtest, where they show up as
    findings.

    Imported lazily to keep this module free of a cycle: ``factor_mining``
    imports the registry from here.
    """
    from .factor_mining import INTERMEDIATE_FACTORS

    return {name: df for name, df in factors.items() if name not in INTERMEDIATE_FACTORS}

def _selected_factor_registry( #根据函数签名递归找依赖，例如选择 TwentyDayVolatility 时自动加入 daily_return；也会拒绝未知因子和循环依赖。
        factor_names: Iterable[str],
) -> dict[str, object]:
    """Return requested factors and all registry-defined dependencies"""

    requested = tuple(dict.fromkeys(factor_names))
    unknown = sorted(set(requested).difference(FACTOR_REGISTRY))
    if unknown:
        raise ValueError(f"Unknown factor names: {','.join(unknown)}")
    selected: dict[str, object] = {}
    visiting: set[str] = set()

    def include(factor_name: str) -> None:
        if factor_name in selected:
            return

        if factor_name in visiting:
            raise ValueError(
                f"Circular factor dependency detected at {factor_name!r}"
            )
        visiting.add(factor_name)
        factor = FACTOR_REGISTRY[factor_name]

        for parameter_name in inspect.signature(factor).parameters:
            if parameter_name in FACTOR_REGISTRY:
                include(parameter_name)

        visiting.remove(factor_name)
        selected[factor_name] = factor

    for factor_name in requested:
        include(factor_name)

    return selected