from quantmine import back_testing
from quantmine.ic_calculator import select_significant_factor_periods
from quantmine.ic_calculator import ICVariant, TestResult, REGISTER_FACTOR_SELECTOR
import pandas as pd

def run_backtest_job(close: pd.DataFrame, variant: ICVariant, test_result: TestResult, job_config: dict, constituents = None):
    part = job_config['part']
    cost_per_trade = job_config['cost_per_trade']
    test = variant.test

    if test_result.sample_scope != 'train':
        raise ValueError('factor selection must use train-scope test results')
    
    selector = job_config['selector']['name']
    if selector not in REGISTER_FACTOR_SELECTOR:
        raise ValueError(f'{selector} not in registry')
    selected_factor_periods = select_significant_factor_periods(test_result, selector_name = job_config['selector']['name'], selector_params = job_config['selector'].get('params',{}))

    if not selected_factor_periods:
        return {
            'status': 'no_significant_factor',
            'quantile_returns': {},
            'ticker_history': {},
            'daily_returns':{}, 
            'selected_factor_periods': [],
            
        }
    significant_factor_list = sorted({factor_name for factor_name, _ in selected_factor_periods})

    test_factor = test['factors']
    test_forward_return = test['forward_returns']

    if not test_factor:
        raise ValueError('variant test factors are empty')
    test_index = next(iter(test_factor.values())).index
    test_close = close.loc[test_index]
    quantile_result, ticker_history = back_testing.quantile_backtest(constituents=constituents, factors=test_factor, significant_factor_list=significant_factor_list, forward_returns=test_forward_return, part=job_config['part'], selected_factor_periods=selected_factor_periods)
    expand_to_daily_returns_result = back_testing.expand_all_to_daily_returns(ticker_history, test_close, parts=part ,cost_per_trade=cost_per_trade)

    return {
        'status': 'ok',
        'quantile_returns': quantile_result,
        'ticker_history': ticker_history,
        'daily_returns':expand_to_daily_returns_result,
        'selected_factor_periods': selected_factor_periods
    }


def back_test_workflow(back_test_job: dict, backtest_config: dict):
    if back_test_job['status'] == 'no_significant_factor':
        return {}
    quantile_backtest = back_test_job['quantile_returns']
    daily_returns = back_test_job['daily_returns']
    BacktestJobResult = {}
    for factor_period, factor_df in quantile_backtest.items():
        daily_df = daily_returns[factor_period]
        summary_df, net_return_df = back_testing.performance_summary(daily_df, periods=1)
        monotonicity_test_result = back_testing.monotonicity_test(factor_df, backtest_config['part'])
        cache_dict = {
            'status': 'ok',
            'back_test_job': back_test_job,
            'performance_summary': summary_df,
            'net_return_df': net_return_df,
            'monotonicity_test_result': monotonicity_test_result,
        }
        BacktestJobResult[factor_period] = cache_dict
    return BacktestJobResult

def apply_sanity_test(constituents, back_test_result:dict, variant: ICVariant, backtest_config:dict, close:pd.DataFrame):
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
) -> dict:
    results = {}
    for job in backtest_config['jobs']:
        job_id = job['id']
        variant = variants[job['variant']]
        test_output = test_results[job['selection_test']]

        test_result = TestResult(summary= test_output['summary'],
                                 multiple_testing= test_output['multiple_testing'],
                                 test_method= test_output['test_method'],
                                 sample_scope = test_output['sample_scope'])
        job_result = run_backtest_job(close = close, variant=variant , test_result= test_result, job_config=job, constituents=constituents)

        analysis = back_test_workflow(back_test_job= job_result, backtest_config=job)
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
