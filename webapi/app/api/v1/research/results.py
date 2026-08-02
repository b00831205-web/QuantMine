"""Research-result filter endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import MetaData, Table, select, func, or_, select, and_
from sqlalchemy.engine import Engine

from ....dependencies import get_request_engine

from ....schemas import ResearchFilterOptions, ResearchRunOption, FactorResultRow, FactorResultsResponse, BacktestSummariesResponse


router = APIRouter()


@router.get("/research/options", response_model=ResearchFilterOptions)
async def get_research_options(
    run_id: int | None = Query(None, alias="runId"),
    engine: Engine = Depends(get_request_engine),
) -> ResearchFilterOptions:
    run_rows = fetch_research_runs(engine)
    default_run_id = run_rows[0]["run_id"] if run_rows else None

    if run_id is not None and not research_run_exists(engine, run_id):
        raise HTTPException(status_code=404, detail="Research run not found")

    selected_run_id = run_id if run_id is not None else default_run_id

    if selected_run_id is None:
        filter_values = {
            "variants": [],
            "test_ids": [],
            "sample_scopes": [],
        }
    else:
        filter_values = fetch_research_filter_values(engine, selected_run_id)

    return ResearchFilterOptions(
        default_run_id=default_run_id,
        runs=[
            ResearchRunOption(
                run_id=row["run_id"],
                created_at=row["run_timestamp"],
            )
            for row in run_rows
        ],
        variants=filter_values["variants"],
        test_ids=filter_values["test_ids"],
        sample_scopes=filter_values["sample_scopes"],
    )

def fetch_research_runs(engine: Engine) -> list[dict]:
    metadata = MetaData()
    table = Table('research_runs', metadata, autoload_with= engine)

    statement = select(table.c.run_id, table.c.run_timestamp).order_by(table.c.run_id.desc())
    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()
    return [dict(row) for row in rows]

def fetch_research_filter_values(engine: Engine, run_id: int) -> dict:
    metadata = MetaData()
    table = Table('test_results', metadata, autoload_with=engine)
    run_condition = table.c.run_id == run_id
    with engine.connect() as connection:
        variants = connection.execute(select(table.c.variant_name).where(run_condition).distinct().order_by(table.c.variant_name)).scalars().all()
        test_ids = connection.execute(select(table.c.test_id).where(run_condition).distinct().order_by(table.c.test_id)).scalars().all()
        sample_scopes = connection.execute(select(table.c.sample_scope).where(run_condition).distinct().order_by(table.c.sample_scope)).scalars().all()
    return {
        'variants': variants,
        'test_ids': test_ids,
        'sample_scopes': sample_scopes
    }

#.mapping().all()： 要整行字典时用；
#.scalars().all()： 只选一列，只要字符串列表时用；

def research_run_exists(engine: Engine, run_id: int)-> bool:
    metadata = MetaData()
    table = Table('research_runs', metadata, autoload_with=engine)

    statement = (select(table.c.run_id)
    .where(table.c.run_id == run_id)
    .limit(1))

    with engine.connect() as connection:
        result = connection.execute(statement).scalar_one_or_none() #.scalar_one_or_none：取单列单个值，有就返回
    return result is not None
    
def fetch_factor_rows(engine: Engine,
                      *, #意思是后面的参数必须写名字调用
                      run_id: int,
                      variant: str | None = None,
                      test_id: str | None = None,
                      sample_scope: str | None = None,
                      factor_name: str | None = None,
                      period :int | None = None,
                      page: int = 1 ,
                      page_size : int = 25) -> tuple[list[dict], int]:
    metadata = MetaData()
    table = Table('test_results', metadata, autoload_with=engine)
    conditions = [table.c.run_id == run_id]

    # filter_columns = {
    #     'variant': table.c.variant_name,
    #     'test_id': table.c.test_id,
    #     'sample_scope': table.c.sample_scope,
    #     'factor_name':table.c.factor_name,
    #     'period': table.c.period,
    # }
    if variant is not None:
        conditions.append(table.c.variant_name == variant)

    if test_id is not None:
        conditions.append(table.c.test_id == test_id)

    if sample_scope is not None:
        conditions.append(table.c.sample_scope == sample_scope)

    if factor_name is not None:
        conditions.append(table.c.factor_name == factor_name)

    if period is not None:
        conditions.append(table.c.period == period)

    total_statement = (select(func.count()).select_from(table).where(*conditions)) #这里的*代表列表展开
    rows_statement = (select(table).where(*conditions).order_by(table.c.bh_significant.desc(),table.c.p_value.asc(),table.c.factor_name.asc(),table.c.period.asc()).limit(page_size).offset((page-1)*page_size))

    with engine.connect() as connection:
        total_result = connection.execute(total_statement).scalar_one()
        rows_result = connection.execute(rows_statement).mappings().all()

    return [dict(row) for row in rows_result], total_result

@router.get('/research/factors', response_model = FactorResultsResponse)
async def get_factor_results(
    run_id: int = Query(..., alias = 'runId'),
    variant: str | None = None,
    test_id: str | None = Query(None, alias = 'testId'),
    sample_scope: str | None = Query(None, alias='sampleScope'),
    factor_name: str | None = Query(None, alias='factorName'),
    period: int | None = None,
    page: int = Query(1, ge = 1), #ge= greater than or equal
    page_size : int = Query(25,alias = 'pageSize', ge=1, le=100), #less than or equal
    engine: Engine = Depends(get_request_engine),
) -> FactorResultsResponse:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status_code= 404, detail = 'Research run not found')
    
    row_results, total_result = fetch_factor_rows(engine, 
                        run_id = run_id, 
                        variant = variant, 
                        test_id = test_id, 
                        sample_scope = sample_scope,
                        factor_name = factor_name,
                        period = period,
                        page = page,
                        page_size= page_size)
    return FactorResultsResponse(items = [FactorResultRow(**row) for row in row_results],
                                    total = total_result,
                                    page = page,
                                    page_size = page_size)

def fetch_backtest_summary_rows(engine: Engine, 
                                *, 
                                run_id: int, 
                                variant: str |None, 
                                test_id: str|None = None, 
                                factor_name: str|None = None, 
                                period : int|None = None, 
                                page: int = 1,
                                page_size: int = 25) -> tuple[list[dict],int]:
    metadata = MetaData()
    table = Table('backtest_metrics', metadata, autoload_with = engine)

    conditions = [table.c.run_id == run_id]

    if variant is not None:
        conditions.append(table.c.variant_name == variant)

    if test_id is not None:
        conditions.append(table.c.test_id == test_id)

    if factor_name is not None:
        conditions.append(table.c.factor_name == factor_name)

    if period is not None:
        conditions.append(table.c.period == period)

    group_columns = (
        table.c.variant_name,
        table.c.backtest_id,
        table.c.test_id,
        table.c.factor_name,
        table.c.period,
    )

    group_statement = (select(*group_columns).where(*conditions).distinct().order_by(table.c.factor_name.asc(),table.c.period.asc(),table.c.backtest_id.asc()))
    total_statement = select(func.count()).select_from(group_statement.subquery())
    page_statement = group_statement.limit(page_size).offset((page -1)*page_size)

    with engine.connect() as connection:
        total = connection.execute(total_statement).scalar_one()
        selected_groups = connection.execute(page_statement).mappings().all()

        if not selected_groups:
            return [], total

        selected_group_conditions = [
            and_(table.c.variant_name == group['variant_name'],
                 table.c.backtest_id == group['backtest_id'],
                 table.c.test_id == group['test_id'],
                 table.c.factor_name == group['factor_name'],
                 table.c.period == group['period'],) for group in selected_groups
        ]
        metric_statement = (select(table).where(*conditions, or_(*selected_group_conditions)).order_by(
            table.c.factor_name.asc(),
            table.c.period.asc(),
            table.c.quantile_rank.asc(),
            table.c.metric_name.asc()
        ))
        metric_rows = connection.execute(metric_statement).mappings().all()

        cards = build_backtest_summary_cards([dict(row) for row in metric_rows])
        return cards, total
@router.get('/research/backtest-summaries', response_model = BacktestSummariesResponse)
async def get_backtest_summaries(run_id: int = Query(...,alias='runId'),
                                 variant: str| None = None,
                                 test_id: str| None = Query(None, alias = 'testId'),
                                 factor_name: str|None = Query(None, alias = 'factorName'),
                                 period: int | None = None,
                                 page: int = Query(1, ge = 1),
                                 page_size: int = Query(25, alias = 'pageSize', ge=1, le = 100),
                                 engine: Engine = Depends(get_request_engine),) -> BacktestSummariesResponse:
    if not research_run_exists(engine, run_id):
        raise HTTPException(status_code = 404, detail= 'Research run not found')
    rows, total = fetch_backtest_summary_rows(engine, run_id = run_id, variant= variant, test_id=test_id, factor_name=factor_name,
                                              period = period, page=page, page_size = page_size,)
    return BacktestSummariesResponse(items = rows, total = total, page=page, page_size = page_size)

def build_backtest_summary_cards(metric_rows: list[dict]) -> list[dict]:
    cards_by_key: dict[tuple, dict] = {}
    for row in metric_rows:
        key = (
            row['variant_name'],
            row['backtest_id'],
            row['test_id'],
            row['factor_name'],
            row['period'],
        )

        if key not in cards_by_key:
            cards_by_key[key] = {
                'variant_name': row['variant_name'],
                'backtest_id': row['backtest_id'],
                'test_id': row['test_id'],
                'factor_name': row['factor_name'],
                'period': row['period'],
                'quantile_yearly_returns':{},
                'sharpe': None,
                'max_drawdown':None,
                'win_rate':None,
            }
        card = cards_by_key[key]
        metric_name = row['metric_name']
        metric_value = row['metric_value']
        quantile_rank = row['quantile_rank']

        if metric_value is None:
            continue

        if metric_name == 'yearly_return':
            quantile_name = 'longShort' if quantile_rank == 0 else f"Q{quantile_rank}"
            card['quantile_yearly_returns'][quantile_name] = float(metric_value)

        if quantile_rank != 0:
            continue

        metric_to_field = {
            'sharp_ratio': 'sharpe',
            'max_drawdown': 'max_drawdown',
            'win_rate': 'win_rate',
        }
        target_field = metric_to_field.get(metric_name)

        if target_field is not None:
            card[target_field] = float(metric_value)
    return list(cards_by_key.values())