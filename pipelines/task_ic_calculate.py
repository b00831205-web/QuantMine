"""DAG step: run the IC research workflow and persist its results.

Creates the research run that later steps attach to (they find it by Airflow
batch id), then saves the IC variants, workflow output, and test results.
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantmine.storage.database import get_engine
from quantmine.storage.ic import save_ic_artifacts, save_workflow_results, save_test_result_artifacts
from quantmine.storage.membership import fetch_membership
from quantmine.storage.runs import create_run
from quantmine.workflows.ic import run_ic_workflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_factors(factors_dir: Path) -> dict[str,pd.DataFrame]:
    factors = {}
    for factor_path in sorted(factors_dir.glob('*.parquet')):
        factors[factor_path.stem] = pd.read_parquet(factor_path)
    if not factors:
        raise FileNotFoundError(f'No factor parquet files found in {factors_dir}')

    return factors

def load_ic_research_config(config_path: Path)->dict:
    with config_path.open(encoding='utf-8') as file:
        config = yaml.safe_load(file) or {}

    if 'ic_research' not in config:
        raise KeyError('Missing "ic_research" section in config file')
    return config['ic_research']

def main():
    parser = argparse.ArgumentParser(
        description='Run config IC research workflow'
    )
    parser.add_argument('--date', required = True)
    parser.add_argument('--batch', required = True)
    parser.add_argument(
        '--config',
        default= 'config.yaml',
        help = 'YAML file containing the ic_research section',
    )    

    args = parser.parse_args()
    close = pd.read_parquet(
        PROJECT_ROOT/ 'data'/'processed'/'processed_close.parquet'
    )
    factors = load_factors(PROJECT_ROOT/'tmp'/'factors')
    research_config = load_ic_research_config(
        PROJECT_ROOT/args.config
    )

    safe_batch = re.sub(r"[^A-Za-z0-9_.-]+", "_", args.batch)
    artifact_dir = PROJECT_ROOT / "data" / "artifacts" / "ic" / safe_batch
    artifact_dir.mkdir(parents = True, exist_ok = True)
    config_snapshot = {
        'airflow_date': args.date,
        'airflow_batch':args.batch,
        'ic_research':research_config
    }
    engine = get_engine()
    run_id = create_run(engine, config_snapshot)

    # Point-in-time universe. Without it the cross-section on any given day is
    # "every ticker we ever downloaded", which both keeps names after they left
    # the index and admits them before they joined.
    membership = fetch_membership(engine)
    if membership.empty:
        raise RuntimeError(
            "index_membership is empty; run task_0_universe first. Computing IC "
            "without it would silently use a look-ahead universe."
        )

    variants, test_results = run_ic_workflow(
        close=close,
        factors=factors,
        research_config=research_config,
        membership=membership,
    )

    save_workflow_results(
        engine = engine,
        run_id = run_id,
        variants = variants,
        test_results = test_results,
    )

    #关键 artifact 先存: ic_artifacts 驱动前端 IC 时序图, 必须落库
    save_ic_artifacts(
        engine=engine,
        run_id=run_id,
        variants=variants,
        output_dir=artifact_dir,
    )

    #辅助 artifact 放最后且尽力而为: test_result_artifacts 只是完整 summary 的存档,
    #不在展示路径上; 存档失败(如权限缺失)不应让整条 run 作废。
    try:
        save_test_result_artifacts(
            engine=engine,
            run_id=run_id,
            test_results=test_results,
            output_dir=artifact_dir / "test_results",
        )
    except Exception as error:
        print(f"WARNING: skipped test_result_artifacts ({type(error).__name__}: {error})")

    print(f'IC workflow completed: run_id = {run_id},' f'variants = {list(variants)}, tests = {list(test_results)}')

if __name__ == '__main__':
    main()
