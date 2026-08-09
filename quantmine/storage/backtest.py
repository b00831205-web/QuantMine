"""Persistence helpers for quantile-backtest results."""

import pandas as pd
from sqlalchemy import MetaData, Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from pathlib import Path


def build_backtest_rows(
    all_results: dict[tuple[str, int], pd.DataFrame],
    *,
    run_id: int,
    variant_name: str,
    backtest_id: str,
    test_id: str,
    weighting: str = 'equal',
) -> pd.DataFrame:
    """Convert wide quantile-return frames into database-ready long rows."""
    frames: list[pd.DataFrame] = []
    for (factor_name, period), result in all_results.items():
        frame = result.reset_index()
        date_column = frame.columns[0]
        value_columns = [column for column in frame if column != date_column]
        frame = frame.melt(
            id_vars=[date_column],
            value_vars=value_columns,
            var_name="quantile",
            value_name="return_value",
        ).rename(columns={date_column: "trade_date"})
        frame["quantile_rank"] = frame["quantile"].map(
            lambda value: 0
            if value == "long_short"
            else int(str(value).removeprefix("Q"))
        )
        frame["run_id"] = run_id
        frame["variant_name"] = variant_name
        frame["backtest_id"] = backtest_id
        frame["test_id"] = test_id
        frame["factor_name"] = factor_name
        frame["period"] = period
        frame["weighting"] = weighting
        frames.append(frame.drop(columns=["quantile"]))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_ticker_history_rows(
    ticker_history: list[dict],
) -> pd.DataFrame:
    """Flatten one factor/period's per-rebalance holdings into long rows.

    ``ticker_history`` is the list produced by ``quantile_backtest``: one dict
    per rebalance date with keys ``date`` and ``Q1``..``Qn`` (each a set of
    tickers). Returns a long frame ``[trade_date, quantile_rank, ticker]`` so
    the API can read the holdings of any rebalance date and quantile. Members
    are sorted for deterministic parquet output.
    """
    records = []
    for snapshot in ticker_history:
        trade_date = snapshot["date"]
        for key, members in snapshot.items():
            if key == "date":
                continue
            quantile_rank = int(str(key).removeprefix("Q"))
            for ticker in sorted(members):
                records.append(
                    {
                        "trade_date": trade_date,
                        "quantile_rank": quantile_rank,
                        "ticker": ticker,
                    }
                )
    return pd.DataFrame(
        records, columns=["trade_date", "quantile_rank", "ticker"]
    )


def save_backtest_results(
    engine: Engine,
    rows: pd.DataFrame,
) -> int:
    """Upsert normalized backtest rows using the schema's unique key."""
    if rows.empty:
        return 0

    records = (
        rows.astype(object).where(pd.notna(rows), None).to_dict(orient="records")
    )
    metadata = MetaData()
    table = Table("backtest_results", metadata, autoload_with=engine)
    statement = pg_insert(table).values(records)
    statement = statement.on_conflict_do_update(
        index_elements=[
            "run_id",
            "variant_name",
            "backtest_id",
            "factor_name",
            "period",
            "test_id",
            "trade_date",
            "quantile_rank",
        ],
        set_={
            "test_id": statement.excluded.test_id,
            "return_value": statement.excluded.return_value,
            "weighting": statement.excluded.weighting,
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(records)

def build_backtest_metric_rows(
    analysis: dict,
    run_id: int,
    variant_name: str,
    backtest_id: str,
    test_id: str,
) -> pd.DataFrame:
    """Flatten one job's analysis into long metric rows.

    Melts the performance summary (one row per portfolio and metric) and
    appends the monotonicity results, so every scalar the analysis produced
    lands in ``backtest_metrics`` under a ``(portfolio, metric_name)`` key.
    """
    rows = []

    for (factor_name, period), factor_period_analysis in analysis.items():
        summary_df = factor_period_analysis["performance_summary"]
        summary_row = (
            summary_df
            .rename_axis("portfolio")
            .reset_index()
            .melt(
                id_vars="portfolio",
                value_vars=summary_df.columns,
                var_name="metric_name",
                value_name="metric_value",
            )
        )

        summary_row["quantile_rank"] = summary_row["portfolio"].map(
            lambda name: 0 if name == "long_short" else int(name.removeprefix("Q"))
        )
        summary_row["run_id"] = run_id
        summary_row["variant_name"] = variant_name
        summary_row["backtest_id"] = backtest_id
        summary_row["test_id"] = test_id
        summary_row["factor_name"] = factor_name
        summary_row["period"] = period

        monotonicity_df  = pd.Series(factor_period_analysis['monotonicity_test_result']).drop('part', errors = 'ignore').rename_axis('metric_name').reset_index(name='metric_value')
        monotonicity_df['metric_name'] = ('monotonicity_'+monotonicity_df['metric_name'])
        monotonicity_df['quantile_rank'] = 0
        monotonicity_df['run_id'] = run_id
        monotonicity_df["variant_name"] = variant_name
        monotonicity_df["backtest_id"] = backtest_id
        monotonicity_df["test_id"] = test_id
        monotonicity_df["factor_name"] = factor_name
        monotonicity_df["period"] = period

        rows.append(
            summary_row[
                [
                    "run_id",
                    "variant_name",
                    "backtest_id",
                    "test_id",
                    "factor_name",
                    "period",
                    "quantile_rank",
                    "metric_name",
                    "metric_value",
                ]
            ]
        )
        rows.append(monotonicity_df[
                ["run_id",
                "variant_name",
                "backtest_id",
                "test_id",
                "factor_name",
                "period",
                "quantile_rank",
                "metric_name",
                "metric_value",]
            ])
        gross_summary = factor_period_analysis.get("gross_summary")
        if gross_summary is not None and not gross_summary.empty:
            gross_row = (
                gross_summary
                .rename_axis("portfolio")
                .reset_index()
                .melt(
                    id_vars="portfolio",
                    value_vars=gross_summary.columns,
                    var_name="metric_name",
                    value_name="metric_value",
                )
            )
            gross_row["metric_name"] = "gross_" + gross_row["metric_name"]
            gross_row["quantile_rank"] = gross_row["portfolio"].map(
                lambda name: 0 if name == "long_short" else int(name.removeprefix("Q"))
            )
            gross_row["run_id"] = run_id
            gross_row["variant_name"] = variant_name
            gross_row["backtest_id"] = backtest_id
            gross_row["test_id"] = test_id
            gross_row["factor_name"] = factor_name
            gross_row["period"] = period
            rows.append(gross_row[
                [
                    "run_id", "variant_name", "backtest_id", "test_id",
                    "factor_name", "period", "quantile_rank",
                    "metric_name", "metric_value",
                ]
            ])
    if not rows:
        return pd.DataFrame(
            columns=[
                "run_id", "variant_name", "backtest_id", "test_id",
                "factor_name", "period", "quantile_rank",
                "metric_name", "metric_value",
            ]
        )

    return pd.concat(rows, ignore_index=True)

def save_backtest_metrics(engine, metric_rows: pd.DataFrame)->int:
    """Upsert metric rows, returning how many were written.

    ``metric_metadata`` is filled with empty dicts when absent, so callers that
    do not carry extra context still satisfy the NOT NULL column.
    """
    if metric_rows.empty:
            return 0

    rows_to_save = metric_rows.copy()
    if 'metric_metadata' not in rows_to_save.columns:
        rows_to_save['metric_metadata'] = [{} for _ in range(len(rows_to_save))]
    records = (
        rows_to_save.astype(object).where(pd.notna(rows_to_save), None).to_dict(orient="records")
    )
    metadata = MetaData()
    
    table = Table("backtest_metrics", metadata, autoload_with=engine)
    statement = pg_insert(table).values(records)
    statement = statement.on_conflict_do_update(
        index_elements=[
            "run_id",
            "variant_name",
            "backtest_id",
            'test_id',
            "factor_name",
            "period",
            "quantile_rank",
            "metric_name",
        ],
        set_={
            "metric_value": statement.excluded.metric_value,
            "metric_metadata": statement.excluded.metric_metadata,
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(records)

def write_dataframe_artifact(
        dataframe: pd.DataFrame,
        artifact_dir: str|Path,
        run_id: int,
        backtest_id: str,
        artifact_type: str,
        artifact_key: str,
) -> tuple[str, int]:
    """Write a dataframe to ``<artifact_dir>/<run_id>/<backtest_id>/`` as parquet.

    Large per-run tables (holdings, series) live on disk rather than in the
    database; only a pointer row is stored. Slashes in the type/key are
    replaced so they cannot escape the target directory.

    Returns:
        A tuple of ``(path, row_count)`` for the accompanying record.
    """
    target_dir = Path(artifact_dir)/str(run_id)/backtest_id
    target_dir.mkdir(parents = True, exist_ok = True)

    safe_artifact_type = artifact_type.replace('/',"_") #防止未来输入含“/”的名称
    safe_artifact_key = artifact_key.replace('/',"_")
    path = target_dir/f'{safe_artifact_type}__{safe_artifact_key}.parquet'
    dataframe.to_parquet(path)
    return str(path), len(dataframe)

def save_backtest_artifact_record(engine, 
                                  run_id:int,
                                  variant_name: str,
                                  backtest_id: str,
                                  artifact_type: str,
                                  artifact_key: str,
                                  path: str,
                                  row_count: int,
                                  artifact_metadata: dict|None = None)->int:
    """Register one on-disk artifact in ``backtest_artifacts``.

    Note:
        The stored ``path`` is whatever the writing process saw, so it may be
        Windows-absolute while a reader runs under Linux. Readers must resolve
        artifacts through ``storage.paths.resolve_artifact_path`` instead of
        trusting this column.
    """
    metadata = MetaData()
    table = Table('backtest_artifacts', metadata, autoload_with= engine)
    record = {
        'run_id': run_id,
        'variant_name': variant_name,
        'backtest_id': backtest_id,
        'artifact_type':artifact_type,
        'artifact_key': artifact_key,
        'path': path,
        'row_count': row_count,
        'metadata': artifact_metadata or {}
    }
    statement = pg_insert(table).values(record)
    statement = statement.on_conflict_do_update(
        index_elements = [
            'run_id',
            'variant_name',
            'backtest_id',
            'artifact_type',
            'artifact_key',
        ],
        set_={
            'path': statement.excluded.path,
            'row_count': statement.excluded.row_count,
            'metadata': statement.excluded.metadata
        }
    )
    with engine.begin() as connection:
        connection.execute(statement)

    return 1

def save_backtest_workflow_results(
        engine, 
        workflow_results:dict,
        run_id: int,
        backtest_config: dict,
        artifact_dir: str|Path
):
    """Persist every job's results: rows, metrics, sanity output, artifacts.

    Args:
        engine: Database engine.
        workflow_results: Output of ``run_backtest_workflow``.
        run_id: Research run these results belong to.
        backtest_config: The ``backtest`` section, used to recover each job's
            variant and selection test by id.
        artifact_dir: Root directory for parquet artifacts.

    Returns:
        A dict keyed by backtest id with the per-job written counts. Jobs that
        did not succeed are reported with their status and zero counts rather
        than raising, so one bad job does not abort the rest.
    """
    job_configs = {job_config['id']: job_config for job_config in backtest_config['jobs']}
    saved_counts = {}
    for backtest_id, workflow_output in workflow_results.items():
        job_result = workflow_output['job']

        if job_result['status'] != 'ok':
            saved_counts[backtest_id] = {
                'status': job_result['status'],
                'result_rows':0,
                'metric_rows':0,
                'artifact_rows':0
            }
            continue
        job_config = job_configs[backtest_id]
        variant_name = job_config['variant']
        test_id = job_config['selection_test']

        result_rows = build_backtest_rows(
            job_result['daily_returns'],
            run_id = run_id,
            variant_name = variant_name,
            backtest_id=backtest_id,
            test_id=test_id,
            weighting=job_result.get('weighting', 'equal'),
        )
        saved_result_rows = save_backtest_results(engine, result_rows)

        metric_rows = build_backtest_metric_rows(
            workflow_output['analysis'],
            run_id = run_id,
            variant_name=variant_name,
            backtest_id = backtest_id,
            test_id = test_id,
        )
        saved_metric_rows = save_backtest_metrics(engine, metric_rows)

        sanity = workflow_output.get('sanity') or {}
        sanity_summary = sanity.get('summary')
        if sanity_summary is not None and not sanity_summary.empty:
            sanity_rows = build_sanity_metric_rows(
                sanity_summary,
                run_id=run_id,
                variant_name=variant_name,
                backtest_id=backtest_id,
                test_id=test_id
            )
            save_backtest_metrics(engine, sanity_rows)

        saved_artifact_rows = 0
        for (factor_name, period), factor_period_analysis in workflow_output['analysis'].items():
            net_return_df = factor_period_analysis['net_return_df']
            artifact_key = f'{factor_name}__{period}'

            path, row_count = write_dataframe_artifact(
                dataframe=net_return_df,
                artifact_dir=artifact_dir,
                run_id=run_id,
                backtest_id=backtest_id,
                artifact_type='net_return_curve',
                artifact_key = artifact_key,
            )

            saved_artifact_rows += save_backtest_artifact_record(
                engine = engine,
                run_id = run_id,
                variant_name = variant_name,
                backtest_id = backtest_id,
                artifact_type = 'net_return_curve',
                artifact_key=artifact_key,
                path = path,
                row_count = row_count,
                artifact_metadata={
                    'factor_name': factor_name,
                    'period': period
                }
            )

            #持仓(ticker_history)以前算了就丢, 现在落成长表 parquet 供详情页读取
            holdings_history = job_result.get('ticker_history', {}).get((factor_name, period))
            if holdings_history:
                holdings_df = build_ticker_history_rows(holdings_history)
                if not holdings_df.empty:
                    holdings_path, holdings_count = write_dataframe_artifact(
                        dataframe=holdings_df,
                        artifact_dir=artifact_dir,
                        run_id=run_id,
                        backtest_id=backtest_id,
                        artifact_type='ticker_history',
                        artifact_key=artifact_key,
                    )
                    saved_artifact_rows += save_backtest_artifact_record(
                        engine=engine,
                        run_id=run_id,
                        variant_name=variant_name,
                        backtest_id=backtest_id,
                        artifact_type='ticker_history',
                        artifact_key=artifact_key,
                        path=holdings_path,
                        row_count=holdings_count,
                        artifact_metadata={
                            'factor_name': factor_name,
                            'period': period,
                        },
                    )
        saved_counts[backtest_id] = {
            'status': 'ok',
            'result_rows': saved_result_rows,
            'metric_rows': saved_metric_rows,
            'artifact_rows': saved_artifact_rows,
        }
    return saved_counts

def build_sanity_metric_rows(
    summary: pd.DataFrame,
    *,
    run_id: int,
    variant_name: str,
    backtest_id: str,
    test_id: str,
) -> pd.DataFrame:
    """把 sanity summary 展开成 backtest_metrics 行（quantile_rank=0）。"""
    if summary.empty:
        return pd.DataFrame(
            columns=[
                "run_id", "variant_name", "backtest_id", "test_id",
                "factor_name", "period", "quantile_rank",
                "metric_name", "metric_value",
            ]
        )
    frame = summary.copy()
    long = frame.melt(
        id_vars=["scenario", "factor_name", "period"],
        value_vars=[
            "long_short_mean_difference",
            "long_short_std_difference",
            "long_short_mean_to_std",
        ],
        var_name="metric",
        value_name="metric_value",
    )
    long["metric_name"] = (
        "sanity_"
        + long["scenario"]
        + "_"
        + long["metric"].str.replace("long_short_", "", regex=False)
    )
    long["quantile_rank"] = 0
    long["run_id"] = run_id
    long["variant_name"] = variant_name
    long["backtest_id"] = backtest_id
    long["test_id"] = test_id
    return long[
        [
            "run_id", "variant_name", "backtest_id", "test_id",
            "factor_name", "period", "quantile_rank",
            "metric_name", "metric_value",
        ]
    ]