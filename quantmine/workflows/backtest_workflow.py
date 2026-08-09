"""Config-driven backtest orchestration.

Turns a backtest job config into results: pick the significant factor/period
pairs with the configured selector, run the quantile backtest under the
configured weighting, then summarize performance and optionally sanity-test it.

Factor selection deliberately reads train-scope test results while the
backtest itself runs on test-scope data, so selection never sees the sample it
is evaluated on.
"""
from quantmine import back_testing
from quantmine.ic_calculator import select_significant_factor_periods
from quantmine.ic_calculator import ICVariant, TestResult, REGISTER_FACTOR_SELECTOR
from quantmine.weighting import REGISTER_WEIGHTING
from quantmine.registry import validate_in_registry
import pandas as pd

def run_backtest_job(close: pd.DataFrame, variant: ICVariant, test_result: TestResult, job_config: dict, constituents = None,
                     market_cap: pd.DataFrame | None = None):
    """Run one configured backtest job end to end.

    Args:
        close: Wide date-by-ticker close prices covering the test window.
        variant: IC variant supplying the test-scope factors and forward
            returns to trade on.
        test_result: Train-scope statistical test output used for selection.
        job_config: One entry of ``backtest.jobs``: ``part``,
            ``cost_per_trade``, ``selector`` and optional ``weighting``.
        constituents: Point-in-time universe source; ``None`` means every
            factor column (survivorship-biased).
        market_cap: Wide market caps, required when weighting is ``mcap``.

    Returns:
        A dict with ``status``, the per-rebalance ``quantile_returns``, the
        member ``ticker_history``, the expanded ``daily_returns``, the
        ``selected_factor_periods``, and the ``weighting`` name actually used.
        ``status`` is ``no_significant_factor`` (with empty results) when the
        selector approves nothing.

    Raises:
        ValueError: If ``test_result`` is not train-scope, or the selector or
            weighting name is not registered.
    """
    part = job_config['part']
    cost_per_trade = job_config['cost_per_trade']
    test = variant.test

    if test_result.sample_scope != 'train':
        raise ValueError('factor selection must use train-scope test results')

    selector = job_config['selector']['name']
    if selector not in REGISTER_FACTOR_SELECTOR:
        raise ValueError(f'{selector} not in registry')

    # 加权方法: 照 selector 的注册表模式, 配置里写 weighting: {name, params}; 缺省等权
    weighting = job_config.get('weighting', {'name': 'equal'})
    validate_in_registry(weighting['name'], REGISTER_WEIGHTING, 'weighting')
    weight_fn = REGISTER_WEIGHTING[weighting['name']]
    selected_factor_periods = select_significant_factor_periods(test_result, selector_name = job_config['selector']['name'], selector_params = job_config['selector'].get('params',{}))

    if not selected_factor_periods:
        return {
            'status': 'no_significant_factor',
            'quantile_returns': {},
            'ticker_history': {},
            'daily_returns':{},
            'selected_factor_periods': [],
            'weighting': weighting['name'],
        }
    significant_factor_list = sorted({factor_name for factor_name, _ in selected_factor_periods})

    test_factor = test['factors']
    test_forward_return = test['forward_returns']

    if not test_factor:
        raise ValueError('variant test factors are empty')
    test_index = next(iter(test_factor.values())).index
    test_close = close.loc[test_index]
    quantile_result, ticker_history = back_testing.quantile_backtest(constituents=constituents, factors=test_factor, significant_factor_list=significant_factor_list, forward_returns=test_forward_return, part=job_config['part'], selected_factor_periods=selected_factor_periods, weight_fn=weight_fn, market_cap=market_cap)
    expand_to_daily_returns_result = back_testing.expand_all_to_daily_returns(ticker_history, test_close, parts=part ,cost_per_trade=cost_per_trade, weight_fn=weight_fn, market_cap=market_cap)

    return {
        'status': 'ok',
        'quantile_returns': quantile_result,
        'ticker_history': ticker_history,
        'daily_returns':expand_to_daily_returns_result,
        'selected_factor_periods': selected_factor_periods,
        'weighting': weighting['name'],
    }


def _annualized_return(daily: pd.Series) -> float:
    """把一段日收益复利成年化收益（252 交易日/年）。空/无效返回 NaN。"""
    daily = daily.dropna()
    if daily.empty:
        return float('nan')
    n_years = len(daily) / 252
    net = float((1 + daily).prod())
    if net <= 0 or n_years <= 0:
        return float('nan')
    return net ** (1 / n_years) - 1


def back_test_workflow(back_test_job: dict, backtest_config: dict, close: pd.DataFrame | None = None):
    """Summarize one job's raw returns into per-factor/period analysis.

    For each factor/period: net and gross performance summaries, monotonicity
    across quantiles, average turnover per group (``long_short`` charges both
    legs), and excess return over SPY.

    Args:
        back_test_job: Output of ``run_backtest_job``.
        backtest_config: The same job config, read for ``part``.
        close: Close prices; needed only for the SPY excess column. Without it
            (or without a SPY column) ``excess`` is NaN rather than an error.

    Returns:
        A dict keyed by ``(factor, period)``; empty when the job selected no
        significant factor.
    """
    if back_test_job['status'] == 'no_significant_factor':
        return {}
    quantile_backtest = back_test_job['quantile_returns']
    daily_returns = back_test_job['daily_returns']
    ticker_history_by_fp = back_test_job.get('ticker_history', {})
    part = backtest_config['part']
    BacktestJobResult = {}
    for factor_period, factor_df in quantile_backtest.items():
        daily_df = daily_returns[factor_period]
        summary_df, net_return_df = back_testing.performance_summary(daily_df, periods=1)
        monotonicity_test_result = back_testing.monotonicity_test(factor_df, backtest_config['part'])
        gross_summary, _ = back_testing.performance_summary(
            quantile_backtest[factor_period], periods=factor_period[1]
        )

        # —— 换手率（turnover）：每组按调仓取平均换手；long_short 用 Q1+Q_top 两腿之和 ——
        history = ticker_history_by_fp.get(factor_period, [])

        def _group_turnover(group: str) -> float:
            series = back_testing.calculate_turnover(history, group)
            return float(series.mean()) if len(series) else float('nan')

        turnover_map = {}
        for group in summary_df.index:
            if group == 'long_short':
                turnover_map[group] = _group_turnover(f'Q{part}') + _group_turnover('Q1')
            else:
                turnover_map[group] = _group_turnover(group)
        summary_df['turnover'] = pd.Series(turnover_map)

        # —— 超额（excess）：各组年化收益 − SPY 同区间年化收益 ——
        if close is not None and 'SPY' in close.columns and not daily_df.empty:
            spy_annual = _annualized_return(close['SPY'].pct_change().reindex(daily_df.index))
            summary_df['excess'] = summary_df['yearly_return'] - spy_annual
        else:
            summary_df['excess'] = float('nan')
        cache_dict = {
            'status': 'ok',
            'back_test_job': back_test_job,
            'performance_summary': summary_df,
            'net_return_df': net_return_df,
            'monotonicity_test_result': monotonicity_test_result,
            'gross_summary': gross_summary
        }
        BacktestJobResult[factor_period] = cache_dict
    return BacktestJobResult

def apply_sanity_test(constituents, back_test_result:dict, variant: ICVariant, backtest_config:dict, close:pd.DataFrame):
    """Re-run the backtest under perturbed settings to test robustness.

    A result that only survives one exact parameterization is usually a fluke,
    so this re-runs the selected factor/period pairs and compares against the
    original. ``backtest_config['sensitivity']['random_seed']`` keeps the
    perturbation reproducible.

    Returns:
        The sanity-test output, or an empty dict when the job did not succeed.
    """
    if back_test_result['status'] != 'ok':
        return {}
    selected_factor_periods = back_test_result['selected_factor_periods']
    significant_factor_list = sorted({factor_name for factor_name, _ in selected_factor_periods})

    periods = sorted({period for _, period in selected_factor_periods})
    factors = variant.test['factors']
    forward_returns = variant.test['forward_returns']
    test_index = next(iter(factors.values())).index
    test_close = close.loc[test_index]
   
    return back_testing.back_test_sanity_test(
        constituents = constituents, 
        significant_factor_list=significant_factor_list, 
        factors=factors, 
        forward_returns=forward_returns, 
        close=test_close, 
        periods=periods, 
        original_back_test=back_test_result['quantile_returns'], 
        parts=backtest_config['part'], 
        selected_factor_periods=selected_factor_periods, 
        random_seed=backtest_config.get('sensitivity', {}).get('random_seed'))

def run_backtest_workflow(
        close: pd.DataFrame,
        variants: dict[str, ICVariant],
        test_results: dict,
        backtest_config: dict,
        constituents = None,
        market_cap: pd.DataFrame | None = None,
) -> dict:
    """Run every job in the backtest config.

    Args:
        close: Wide date-by-ticker close prices.
        variants: IC variants by name, as referenced by ``job['variant']``.
        test_results: Statistical test outputs by id, as referenced by
            ``job['selection_test']``.
        backtest_config: The ``backtest`` config section, holding ``jobs``.
        constituents: Point-in-time universe source; ``None`` disables it.
        market_cap: Wide market caps, required by ``mcap`` weighting.

    Returns:
        A dict keyed by job id, each holding the raw ``job`` output, its
        ``analysis``, and ``sanity`` results (``None`` unless the job enables
        ``sensitivity``).
    """
    results = {}
    for job in backtest_config['jobs']:
        job_id = job['id']
        variant = variants[job['variant']]
        test_output = test_results[job['selection_test']]

        test_result = TestResult(summary= test_output['summary'],
                                 multiple_testing= test_output['multiple_testing'],
                                 test_method= test_output['test_method'],
                                 sample_scope = test_output['sample_scope'])
        job_result = run_backtest_job(close = close, variant=variant , test_result= test_result, job_config=job, constituents=constituents, market_cap=market_cap)

        analysis = back_test_workflow(back_test_job= job_result, backtest_config=job, close=close)
        sensitivity_config = job.get('sensitivity', {})
        sanity_results = None

        if (job_result['status'] == 'ok' and sensitivity_config.get('enabled', False)):
            sanity_results=apply_sanity_test(
                constituents=constituents,
                backtest_config = job,
                back_test_result = job_result,
                variant=variant,
                close=close
            )
        results[job_id] = {
            'job':job_result,
            'analysis': analysis,
            'sanity': sanity_results
        }
    return results
