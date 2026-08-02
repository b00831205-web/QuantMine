import pandas as pd
from .datareader import ConstituentsSource, MembershipTableSource
import numpy as np
from scipy.stats import spearmanr


def truncate_quantile(cross_section_series: list|pd.Series, part:int =5):
    """Split a sorted cross-sectional series into quantile buckets.

    Args:
        cross_section_series: A 1D sorted sequence of tickers or values.
            The input must already be sorted in ascending order before calling.
        part: Number of groups to split into. Default is 5.

    Returns:
        A list of length ``part``. Each element is a slice of the input series.

    Notes:
        This function does not sort the data. It only slices by position, so
        the input order determines the quantile grouping.
    """
    length = len(cross_section_series)
    batch_size = length // part
    batch = []
    for i in range(part):
        if i == part-1:
            quantile = cross_section_series[i*batch_size:length]
        else:
            quantile = cross_section_series[i*batch_size: (i+1)*batch_size]
        batch.append(quantile)
    return list(batch)
        

def quantile_backtest(constituents: ConstituentsSource | pd.DataFrame | None ,
                      factors: dict[str, pd.DataFrame], 
                      significant_factor_list:list, 
                      forward_returns: dict[int,pd.DataFrame], 
                      part:int =5,
                      selected_factor_periods: list[tuple[str,int]] | None = None):
    """Run a quantile long-short backtest for each selected factor.

    Args:
        constituents: Point-in-time universe source implementing
            ``get_constituents(date) -> set[str]``. A raw membership dataframe
            (ticker/start_date/end_date columns) is auto-wrapped in
            ``MembershipTableSource``. Pass ``None`` to use every factor
            column (survivorship-biased fixed universe).
        factors: Mapping of factor name to a date-by-ticker value dataframe.
        significant_factor_list: Factor names to evaluate.
        forward_returns: Mapping of holding period (in trading days) to a
            date-by-ticker forward return dataframe.
        part: Number of quantile groups to form. Default is 5.

    Returns:
        A tuple ``(all_result, all_ticker_history)``. Both are keyed by
        ``(factor_name, period)``; results hold Q1..Qn plus ``long_short``
        returns per rebalance date, histories hold the member set per group.
    """
    if part < 2:
        raise ValueError("part must be at least 2")

    if isinstance(constituents, pd.DataFrame):
        constituents = MembershipTableSource(constituents)

    all_result={}
    all_ticker_history = {}
    selected_pairs = (set(selected_factor_periods) if selected_factor_periods is not None else None)

    for significant_factor in significant_factor_list:
        factor_df = factors[significant_factor]
        for period, forward_return_df in forward_returns.items():
            if selected_pairs is not None:
                if (significant_factor, period) not in selected_pairs:
                    continue
            result=[]
            ticker_history = []
            for index in range(0, len(factor_df), period):
                curr_date = factor_df.index[index]
                if curr_date not in forward_return_df.index:
                    continue
                return_tickers = set(forward_return_df.columns)
                if constituents is None:
                    available_tickers = [
                        ticker
                        for ticker in factor_df.columns
                        if ticker in return_tickers
                    ]
                else:
                    valid_tickers = constituents.get_constituents(curr_date)
                    #intersect in factor-column order: valid_tickers is a set with
                    #non-deterministic iteration order, and after stable sorting of tied
                    #ranks the bucket-boundary members would drift between runs
                    available_tickers = [
                        ticker
                        for ticker in factor_df.columns
                        if ticker in valid_tickers and ticker in return_tickers
                    ]

                cross_section_factor = factor_df.loc[
                    curr_date,
                    available_tickers,
                ].dropna()
                if len(cross_section_factor) < part:
                    continue
                ranked_cross_section = cross_section_factor.rank(ascending=True)
                ranked_cross_section = ranked_cross_section.sort_values(
                    kind="mergesort",
                )
                tickers = ranked_cross_section.index

                group_list = truncate_quantile(tickers ,part = part)
                
                _return = {'date':curr_date}    
                _tickers = {'date':curr_date}
                for i in range(part):
                    group_return = forward_return_df.loc[curr_date, group_list[i]]
                    _return[f'Q{i+1}'] = group_return.mean()
                    _tickers[f'Q{i+1}'] = set(group_list[i])
                ticker_history.append(_tickers)
                result.append(_return)
            if not result:
                continue
            result_df = pd.DataFrame(result).set_index('date')
            result_df['long_short'] = result_df[f'Q{part}']-result_df['Q1']
            all_ticker_history[(significant_factor,period)] = ticker_history
            all_result[(significant_factor,period)] = result_df
    return all_result, all_ticker_history

def expand_to_daily_returns(tickers_history:list, close_data: pd.DataFrame, cost_per_trade: float = 0.001, parts: int = 5):
    """Expand periodic rebalance snapshots into a net-of-cost daily return series.

    Between two rebalance dates the portfolio holds the quantile members
    fixed, so each daily return is the equal-weighted mean of member returns.
    Transaction costs are charged on the first trading day after each
    rebalance, scaled by the actual membership turnover of that quantile.

    Args:
        tickers_history: List of dicts produced by ``quantile_backtest``. Each
            item holds the rebalance ``date`` and the member set per quantile.
        close_data: Close price dataframe covering all member tickers.
        cost_per_trade: One-way cost per unit of turnover. The deduction is
            ``turnover * 2 * cost_per_trade`` to cover both buys and sells.

    Returns:
        A wide dataframe of daily returns with columns ``Q1``..``Q5`` and a
        ``long_short`` spread column.

    Notes:
        The price window must include the rebalance date itself: ``pct_change``
        makes the window's first row NaN, and that row is dropped. Without the
        rebalance-day anchor, each window's first daily return is lost and the
        cost deduction lands on a NaN (i.e. costs are silently never charged).
    """
    quantile_columns = [f"Q{i}" for i in range(1, parts + 1)]
    output_columns = [*quantile_columns, "long_short"]
    if len(tickers_history) < 2:
        return pd.DataFrame(
            columns=output_columns,
            index=pd.DatetimeIndex([], name="date"),
            dtype=float,
        )

    daily_records = []
    for i in range(len(tickers_history)-1):
        curr = tickers_history[i]
        next_date = tickers_history[i+1]['date']
        curr_date = curr['date']

        #window includes its start (the rebalance day): after pct_change that row is NaN
        #and dropped, keeping the rebalance-day -> next-day return. The right edge includes
        #next_date (attributed to the old portfolio); the next window starts one day after,
        #so days are covered exactly once
        window_dates = close_data.index[(close_data.index >= curr_date) & (close_data.index <= next_date)]
        for q in quantile_columns:
            tickers_in_group = list(curr[q])
            group_price = close_data.loc[window_dates, tickers_in_group]
            portfolio_daily_return = group_price.pct_change().mean(axis=1).iloc[1:]

            if i>0:
                prev_set = set(tickers_history[i-1][q])
                curr_set = curr[q]
                overlap = len(prev_set & curr_set)
                turnover = 1 - overlap/len(curr_set)
            else:
                turnover = 1.0 #initial position build counts as full turnover

            cost_today = turnover *2 *cost_per_trade

            for j, (d, r) in enumerate(portfolio_daily_return.items()):
                if j == 0:
                    r = r - cost_today
                daily_records.append({'date':d, 'group':q, 'return':r})
    if not daily_records:
        return pd.DataFrame(
            columns=output_columns,
            index=pd.DatetimeIndex([], name="date"),
            dtype=float,
        )

    daily_long = pd.DataFrame(daily_records)
    daily_wide = daily_long.pivot(index='date', columns='group', values='return')
    daily_wide = daily_wide.reindex(columns=quantile_columns)
    daily_wide.columns.name = None
    daily_wide['long_short'] = daily_wide[f'Q{parts}'] - daily_wide['Q1']
    return daily_wide

def expand_all_to_daily_returns(
    all_ticker_history: dict,
    close_data: pd.DataFrame,
    parts: int,
    cost_per_trade: float = 0.001,
) -> dict:
    """Expand every ticker history produced by ``quantile_backtest`` at once.

    Args:
        all_ticker_history: Mapping keyed by ``(factor, period)`` as returned by
            ``quantile_backtest``.
        close_data: Close price dataframe covering all member tickers.
        cost_per_trade: One-way cost per unit of turnover.

    Returns:
        A dict with the same ``(factor, period)`` keys, each holding a daily
        Q1..Q5 + ``long_short`` return table.
    """
    all_daily_returns = {}
    for key, ticker_history in all_ticker_history.items():
        all_daily_returns[key] = expand_to_daily_returns(ticker_history, close_data, cost_per_trade, parts)
    return all_daily_returns

def calculate_turnover(ticker_history: list, group: str)->pd.Series:
    """Compute per-rebalance membership turnover for one quantile group.

    Args:
        ticker_history: List of dicts produced by ``quantile_backtest``.
        group: Quantile column name, e.g. ``"Q1"`` or ``"Q5"``.

    Returns:
        A series aligned with the rebalance sequence. The first element is NaN
        because turnover is undefined before the initial holdings exist.

    Notes:
        Turnover is ``1 - |prev ∩ curr| / |curr|``, the fraction of the current
        portfolio that had to be newly bought at this rebalance.
    """
    if not ticker_history:
        return pd.Series(
            index=pd.DatetimeIndex([], name="date"),
            name=group,
            dtype=float,
        )

    turnovers = [np.nan]
    rebalance_dates = [ticker_history[0]['date']]
    for i in range(1, len(ticker_history)):
        prev_set = ticker_history[i-1][group]
        curr_set = ticker_history[i][group]
        overlap = len(prev_set & curr_set)
        turnover = (
            1 - (overlap / len(curr_set))
            if curr_set
            else np.nan
        )
        turnovers.append(turnover)
        rebalance_dates.append(ticker_history[i]['date'])
    return pd.Series(turnovers, index = pd.to_datetime(rebalance_dates), name= group, dtype = float,)


def back_test_sanity_test(constituents: ConstituentsSource | pd.DataFrame | None ,significant_factor_list:list, factors: dict[str,pd.DataFrame] ,forward_returns: dict[int,pd.DataFrame], close:pd.DataFrame, periods:list,
                          original_back_test: dict, parts: int = 5,
                          selected_factor_periods: list[tuple[str, int]]|None = None,
                          random_seed: int | None = None):
    """Run sensitivity tests against factor displacement and shuffled factors.

    Args:
        constituents: Point-in-time universe source (see ``quantile_backtest``).
        significant_factor_list: Factor names to evaluate.
        factors: Mapping of factor name to a date-by-ticker value dataframe.
        forward_returns: Mapping of holding period to a forward return dataframe.
        close: Close price table used to recompute forward returns.
        periods: List of holding periods in trading days.
        origincal_back_test: Baseline quantile backtest results used as the
            comparison reference.

    Returns:
        A tuple of ``(total_difference, displace_difference, shuffle_difference)``.

    Notes:
        This function compares the baseline backtest against two perturbations:
        shifting factor values by one period and randomly shuffling factor rows.
    """
    tickers = list(close.columns)
    rng = np.random.default_rng(random_seed)
    factors_shifting = {}
    for factor_name, factor in factors.items():
        factors_shifting[factor_name] = factor.shift(-1)
    #shuffle is based on the original factors, and each frame must be deep-copied:
    #dict.copy() is shallow, so an in-place shuffle would also corrupt factors_shifting
    shuffle_data = {factor_name: factor.copy() for factor_name, factor in factors.items()}
    for factor_name, factor in shuffle_data.items():
        for idx in factor.index:
            factor.loc[idx] = rng.permutation(factor.loc[idx].values)
    


    period_difference = {}

    
    for period in periods:
        #holding period return and close data shifting difference
        
        raw_return = pd.DataFrame({ticker : close[ticker].pct_change(period).shift(-period) for ticker in tickers})
        common_col = forward_returns[period].columns.intersection(raw_return.columns)
        diff = (forward_returns[period][common_col]-raw_return[common_col]).abs().sum().sum() #first sum gives a Series, second sum collapses it to a scalar
        period_difference[period] = diff

    #factor displacement
    factor_displacement_result , _ = quantile_backtest(constituents, factors_shifting,significant_factor_list, forward_returns, parts, selected_factor_periods)

    #shuffle data
    shuffle_data_return, _ = quantile_backtest(constituents,shuffle_data, significant_factor_list, forward_returns, parts, selected_factor_periods)

    total_difference = 0
    for period, diff in period_difference.items():
        total_difference += diff
    
    displace_difference = {}
    for (factor_name, period), df in factor_displacement_result.items():
        displace_difference[(factor_name,period)] = df - original_back_test[(factor_name, period)]
    
    shuffle_difference = {}
    for (factor_name, period), df in shuffle_data_return.items():
        shuffle_difference[(factor_name,period)] = df - original_back_test[(factor_name, period)]
    
    summary_rows=[]
    scenarios = {
        'displaced': displace_difference,
        'shuffled': shuffle_difference,
    }
    for scenario, difference in scenarios.items():
        for (factor_name, period), diff in difference.items():
            long_short_diff = diff['long_short'].dropna()

            std = long_short_diff.std()
            mean = long_short_diff.mean()

            summary_rows.append({'scenario': scenario, 
                                'factor_name': factor_name,
                                'period': period,
                                'long_short_mean_difference': mean,
                                'long_short_std_difference': std,
                                'long_short_mean_to_std':(mean/std if pd.notna(std) and std!=0 else np.nan)})
    sanity_summary=pd.DataFrame(summary_rows)
    return {'forward_return_difference':total_difference, 
            'displaced_differences':displace_difference, 
            'shuffled_differences':shuffle_difference,
            'summary': sanity_summary
            }

def performance_summary(back_test_quantile:pd.DataFrame, periods:int):
    """Summarize quantile backtest performance.

    Args:
        back_test_quantile: Dataframe of periodic returns for each quantile.
        periods: Holding period in trading days used to annualize metrics.

    Returns:
        A tuple of ``(summary_dataframe, net_return_series)`` where the
        dataframe contains annualized return, volatility, Sharpe ratio, max
        drawdown, and win rate.

    Notes:
        The input should contain return series, not cumulative returns.
    """
    summary_columns = [
        "total_return",
        "yearly_return",
        "volatility",
        "sharp_ratio",
        "max_drawdown",
        "win_rate",
        "n_observations",
    ]
    if back_test_quantile.empty:
        return (
            pd.DataFrame(
                columns=summary_columns,
                index=pd.Index([], name="quantile"),
            ),
            pd.DataFrame(index=back_test_quantile.index),
        )

    result = []
    net_returns = {}
    for col in back_test_quantile.columns:
        r = back_test_quantile[col].dropna()
        if r.empty:
            continue

        net_return = (1+r).cumprod()
        net_returns[col] = net_return
        
        total_return = net_return.iloc[-1] - 1
        n_years = len(r) * periods / 252 
        
        if net_return.iloc[-1] > 0:
            yearly_return = net_return.iloc[-1]**(1/n_years)-1
        else:
            yearly_return = np.nan
        volatility = r.std() * np.sqrt(252/periods)
        sharp = yearly_return / volatility if (volatility != 0 and not np.isnan(yearly_return)) else np.nan
        
        rolling_max = net_return.cummax()
        drawdown = (net_return - rolling_max) / rolling_max
        max_drawdown = drawdown.min()

        win_rate = (r>0).mean()
        summary = {
            'quantile': col,
            'total_return': total_return,
            'yearly_return': yearly_return,
            'volatility' :volatility,
            'sharp_ratio': sharp,
            'max_drawdown':max_drawdown,
            'win_rate': win_rate,
            'n_observations': len(r)
        }
        result.append(summary)
    if not result:
        summary_df = pd.DataFrame(
            columns=summary_columns,
            index=pd.Index([], name="quantile"),
        )
    else:
        summary_df = pd.DataFrame(result).set_index('quantile')
    net_return_df = pd.DataFrame(net_returns)
    return summary_df, net_return_df

def monotonicity_test(result_df: pd.DataFrame, part: int = 5)->dict:
    """Test whether quantile returns are monotonically increasing.

    Args:
        result_df: Dataframe containing quantile columns named ``Q1`` to
            ``Qn``.
        part: Number of quantile groups to inspect. Default is 5.

    Returns:
        A dictionary with the mean-based Spearman correlation, its p-value,
        the average daily correlation, and the fraction of positive daily
        correlations.

    Notes:
        Rows with missing quantile values are skipped in the daily test.
    """
    quantile_cols = [f'Q{i}' for i in range(1,part+1)]
    missing_cols = set(quantile_cols) - set(result_df.columns)

    if missing_cols:
        raise ValueError(f'result_df is missing quantile columns: {sorted(missing_cols)}')
    ranks = list(range(1, part+1))
    means = result_df[quantile_cols].mean()
    corr_simple, pval_simple = spearmanr(ranks, means.values)
    
    daily_corrs = []
    for _, row in result_df[quantile_cols].iterrows():
        if row.isnull().any():
            continue
        c, _ = spearmanr(ranks, row.values)
        daily_corrs.append(c)
    daily_corr_series = pd.Series(daily_corrs, dtype = float)
    return {'mean_based_corr': corr_simple,
            'mean_based_pvalue': pval_simple,
            'daily_avg_corr': daily_corr_series.mean(),
            'daily_corr_positive_pct':(daily_corr_series>0).mean(),
            'part':part}

def apply_transcation_cost(result_df: pd.DataFrame, ticker_history: list,cost_per_trade: float =0.001, part: int = 5)-> pd.DataFrame:
    """Apply turnover-based transaction costs to quantile returns.

    Args:
        result_df: Quantile return dataframe produced by the backtest.
        ticker_history: Per-rebalance member sets from ``quantile_backtest``,
            used to compute the actual turnover of each group.
        cost_per_trade: One-way cost per unit of turnover. Default is 0.001.

    Returns:
        A new dataframe with transaction costs deducted from each quantile and
        from the ``long_short`` spread.

    Notes:
        Each group's charge is ``turnover * 2 * cost_per_trade`` (buys plus
        sells). The spread column is charged for both legs, so its turnover is
        the sum of the Q1 and Q5 turnovers.
    """
    quantile_cols = [f"Q{i}" for i in range(1, part + 1)]
    top_group = quantile_cols[-1]
    bottom_group = quantile_cols[0]

    result_after_cost = result_df.copy()

    for group in quantile_cols:
        turnover = calculate_turnover(
            ticker_history=ticker_history,
            group=group,
        ).reindex(result_df.index)

        cost = turnover.fillna(1.0) * 2 * cost_per_trade

        result_after_cost[group] = result_df[group] - cost

    bottom_turnover = calculate_turnover(
        ticker_history=ticker_history,
        group=bottom_group,
    ).reindex(result_df.index)

    top_turnover = calculate_turnover(
        ticker_history=ticker_history,
        group=top_group,
    ).reindex(result_df.index)

    long_short_cost = (
        bottom_turnover.fillna(1.0)
        + top_turnover.fillna(1.0)
    ) * 2 * cost_per_trade

    result_after_cost["long_short"] = (
        result_df["long_short"] - long_short_cost
    )

    return result_after_cost
back_test_senity_test = back_test_sanity_test
