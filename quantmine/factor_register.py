import inspect
from . import datareader as dr
from .registry import make_registry

FACTOR_REGISTRY, factor_registry=make_registry()

def call_single_factors(func, param_pool: dict):
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

def calculate_all_factors(param_pool: dict)-> dict:
    result ={}
    failures = {}
    for factor_name, func in FACTOR_REGISTRY.items():
        try:
            result[factor_name] = call_single_factors(func, param_pool)
        except KeyError as e:
            print(f'factor {factor_name} lack kwargs: {e}')
            failures[factor_name] = str(e)
    pending, completed = try_loop(failures, result, param_pool)
    print(f"still failure: {pending}")
    return pending ,completed

def try_loop(failure: dict, result: dict, param_pool:dict):
    pending = failure.copy()
    completed = result.copy()
    while pending:
        length = len(pending)
        for factor_name in list(pending.keys()):
            param_pool_update = {**param_pool, **completed}
            try:
                completed[factor_name] = call_single_factors(FACTOR_REGISTRY[factor_name], param_pool_update)
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
