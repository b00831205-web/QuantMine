"""Persistence for IC artifacts and statistical test summaries."""

from pathlib import Path

import pandas as pd
from sqlalchemy import MetaData, Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
import json
import re

from ..ic_calculator import ICVariant
from .paths import resolve_artifact_path

def _save_scope_value(
    value,
    scope_dir: Path,
    key: str,
) -> dict:
    """Save one ICVariant scope value and return its manifest entry."""
    if isinstance(value, pd.DataFrame):
        path = scope_dir / f"{key}.parquet"
        value.to_parquet(path)
        return {
            "kind": "dataframe",
            "path": path.name,
        }

    if isinstance(value, dict):
        value_dir = scope_dir / key
        value_dir.mkdir(exist_ok=True)

        items = []
        for item_name, dataframe in value.items():
            if not isinstance(dataframe, pd.DataFrame):
                raise TypeError(
                    f"{key}[{item_name!r}] must be a DataFrame, "
                    f"got {type(dataframe).__name__}"
                )

            path = value_dir / f"{item_name}.parquet"
            dataframe.to_parquet(path)
            items.append({
                "key": item_name,
                "path": path.relative_to(scope_dir).as_posix(),
            })

        return {
            "kind": "dataframe_dict",
            "items": items,
        }

    return {
        "kind": "value",
        "value": value,
    }

def save_ic_artifacts(
    engine: Engine,
    run_id: int,
    variants: dict[str, ICVariant],
    output_dir: str | Path,
) -> int:
    """Write variant IC frames to Parquet and register their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = MetaData()
    table = Table("ic_artifacts", metadata, autoload_with=engine)
    rows: list[dict] = []

    for variant_name, variant in variants.items():
        for sample_scope in ("train", "test"):
            variant_data = getattr(variant, sample_scope)
            scope_dir = output_dir/variant_name/sample_scope
            scope_dir.mkdir(parents= True, exist_ok= True)
            manifest = {
                'transforms': variant.transforms,
                'entries':{
                    key: _save_scope_value(value, scope_dir, key)
                    for key, value in variant_data.items()
                },
            }
            manifest_path = scope_dir/'manifest.json'
            with manifest_path.open('w', encoding = 'utf-8') as file:
                json.dump(manifest, file, ensure_ascii=False, indent=2)
            rows.append(
                {
                    "run_id": run_id,
                    "variant_name": variant_name,
                    "sample_scope": sample_scope,
                    "transforms": variant.transforms,
                    "path": str(manifest_path),
                }
            )

    if not rows:
        return 0

    statement = pg_insert(table).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["run_id", "variant_name", "sample_scope"],
        set_={
            "transforms": statement.excluded.transforms,
            "path": statement.excluded.path,
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(rows)


def _build_test_result_rows(
    *,
    run_id: int,
    variant_name: str,
    test_id: str,
    test_method: str,
    sample_scope: str,
    transforms: list[dict],
    summary_df: pd.DataFrame,
    multiple_testing_df: pd.DataFrame,
) -> pd.DataFrame:
    result = summary_df.copy()
    corrected = multiple_testing_df.reindex(result.index)

    if "NW_t" in result:
        result["t_stat"] = result["NW_t"]
    elif "t" in corrected:
        result["t_stat"] = corrected["t"]

    if "p_value" not in result and "p_value" in corrected:
        result["p_value"] = corrected["p_value"]
    result["significant"] = corrected.get("significant")
    result["bh_significant"] = corrected.get("BH_significant")

    result = result.reset_index().rename(
        columns={
            "factor": "factor_name",
            "IC_mean": "ic_mean",
            "IC_std": "ic_std",
            "IR": "ir",
        }
    )
    result["run_id"] = run_id
    result["variant_name"] = variant_name
    result["test_id"] = test_id
    result["test_method"] = test_method
    result["sample_scope"] = sample_scope
    result["transforms"] = [transforms] * len(result)

    columns = [
        "run_id",
        "factor_name",
        "period",
        "variant_name",
        "test_id",
        "test_method",
        "sample_scope",
        "transforms",
        "ic_mean",
        "ic_std",
        "ir",
        "n",
        "t_stat",
        "p_value",
        "significant",
        "bh_significant",
    ]
    return result.reindex(columns=columns)


def save_workflow_results(
    engine: Engine,
    run_id: int,
    variants: dict[str, ICVariant],
    test_results: dict[str, dict],
) -> int:
    """Persist all normalized test outputs returned by the IC workflow."""
    frames: list[pd.DataFrame] = []
    for test_id, result in test_results.items():
        variant_name = result["variant_name"]
        variant = variants[variant_name]
        frames.append(
            _build_test_result_rows(
                run_id=run_id,
                variant_name=variant_name,
                test_id=test_id,
                test_method=result["test_method"],
                sample_scope=result.get("sample_scope", "train"),
                transforms=variant.transforms,
                summary_df=result["summary"],
                multiple_testing_df=result["multiple_testing"],
            )
        )

    if not frames:
        return 0

    frame = pd.concat(frames, ignore_index=True)
    records = (
        frame.astype(object)
        .where(pd.notna(frame), None)
        .to_dict(orient="records")
    )
    metadata = MetaData()
    table = Table("test_results", metadata, autoload_with=engine)
    statement = pg_insert(table).values(records)
    statement = statement.on_conflict_do_update(
        index_elements=[
            "run_id",
            "variant_name",
            "test_id",
            "sample_scope",
            "factor_name",
            "period",
        ],
        set_={
            column: getattr(statement.excluded, column)
            for column in (
                "test_method",
                "transforms",
                "ic_mean",
                "ic_std",
                "ir",
                "n",
                "t_stat",
                "p_value",
                "significant",
                "bh_significant",
            )
        },
    )
    with engine.begin() as connection:
        connection.execute(statement)
    return len(records)

def _load_scope_value(entry:dict, scope_dir: Path):
    kind = entry['kind']

    if kind == 'dataframe':
        return pd.read_parquet(scope_dir/entry['path'])

    if kind == 'dataframe_dict':
        return {
            item['key']: pd.read_parquet(scope_dir/item['path'])
            for item in entry['items']
        }
    if kind == 'value':
        return entry['value']
    raise ValueError(f'Unknown IC artifact entry kind: {kind}')

def load_ic_variants(
        engine: Engine,
        run_id: int,
) -> dict[str,ICVariant]:
    metadata = MetaData()
    table = Table('ic_artifacts', metadata, autoload_with = engine)

    statement = (
        select(
            table.c.variant_name,
            table.c.sample_scope,
            table.c.transforms,
            table.c.path,
        )
    .where(table.c.run_id == run_id).order_by(table.c.variant_name, table.c.sample_scope)
    )
    with engine.connect() as connection:
        artifact_rows = connection.execute(statement).mappings().all()

    grouped: dict[str, dict] = {}

    for artifact_row in artifact_rows:
        variant_name = artifact_row['variant_name']
        sample_scope = artifact_row['sample_scope']
        manifest_path = resolve_artifact_path(artifact_row['path'])
        with manifest_path.open(encoding = 'utf-8') as file:
            manifest = json.load(file)
        scope_data = {
            key: _load_scope_value(entry, manifest_path.parent)
            for key, entry in manifest['entries'].items()
        } 
        grouped.setdefault(
            variant_name,
            {
            'transforms':manifest['transforms'],
            'scopes':{}  
            },
        )['scopes'][sample_scope] = scope_data

    variants = {}
    for variant_name, data in grouped.items():
        scopes = data['scopes']

        if set(scopes) != {'train', 'test'}:
            raise ValueError(f'Variant {variant_name!r} must contain train and test artifacts;'
                             f'found {sorted(scopes)}')
        variants[variant_name] = ICVariant(
            train = scopes['train'],
            test = scopes['test'],
            transforms= data['transforms']
        )
    return variants

def load_test_results(
    engine: Engine,
    run_id: int,
) -> dict[str, dict]:
    metadata = MetaData()
    table = Table(
        "test_result_artifacts",
        metadata,
        autoload_with=engine,
    )

    statement = (
        select(table)
        .where(table.c.run_id == run_id)
        .order_by(
            table.c.test_id,
            table.c.sample_scope,
            table.c.artifact_type,
        )
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).mappings().all()

    grouped: dict[str, dict] = {}

    for row in rows:
        test_id = row["test_id"]

        test_data = grouped.setdefault(
            test_id,
            {
                "variant_name": row["variant_name"],
                "sample_scope": row["sample_scope"],
                "test_method": row["metadata"].get("test_method"),
                "artifact_paths": {},
            },
        )

        if test_data["variant_name"] != row["variant_name"]:
            raise ValueError(
                f"test_id {test_id!r} contains more than one variant"
            )

        if test_data["sample_scope"] != row["sample_scope"]:
            raise ValueError(
                f"test_id {test_id!r} contains more than one sample scope"
            )

        test_data["artifact_paths"][row["artifact_type"]] = row["path"]

    test_results = {}

    for test_id, test_data in grouped.items():
        artifact_paths = test_data["artifact_paths"]

        if "summary" not in artifact_paths:
            raise ValueError(
                f"test_id {test_id!r} has no summary artifact"
            )

        multiple_testing_path = artifact_paths.get("multiple_testing")

        test_results[test_id] = {
            "variant_name": test_data["variant_name"],
            "summary": pd.read_parquet(resolve_artifact_path(artifact_paths["summary"])),
            "multiple_testing": (
                pd.read_parquet(resolve_artifact_path(multiple_testing_path))
                if multiple_testing_path is not None
                else None
            ),
            "test_method": test_data["test_method"],
            "sample_scope": test_data["sample_scope"],
        }

    return test_results

def _safe_path_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)

def save_test_result_artifacts(
    engine: Engine,
    run_id: int,
    test_results: dict[str, dict],
    output_dir: str | Path,
) -> int:
    """Persist complete test-result DataFrames and register their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = MetaData()
    table = Table(
        "test_result_artifacts",
        metadata,
        autoload_with=engine,
    )
    rows = []

    for test_id, test_output in test_results.items():
        variant_name = test_output["variant_name"]
        sample_scope = test_output.get("sample_scope", "train")
        test_method = test_output["test_method"]

        test_dir = (
            output_dir
            / _safe_path_component(test_id)
            / _safe_path_component(sample_scope)
        )
        test_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {
            "summary": test_output["summary"],
            "multiple_testing": test_output.get("multiple_testing"),
        }

        for artifact_type, dataframe in artifacts.items():
            if dataframe is None:
                continue

            if not isinstance(dataframe, pd.DataFrame):
                raise TypeError(
                    f"{test_id!r} {artifact_type!r} must be a DataFrame, "
                    f"got {type(dataframe).__name__}"
                )

            path = test_dir / f"{artifact_type}.parquet"
            dataframe.to_parquet(path)

            rows.append(
                {
                    "run_id": run_id,
                    "variant_name": variant_name,
                    "test_id": test_id,
                    "sample_scope": sample_scope,
                    "artifact_type": artifact_type,
                    "path": str(path),
                    "metadata": {
                        "test_method": test_method,
                    },
                }
            )

    if not rows:
        return 0

    statement = pg_insert(table).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[
            "run_id",
            "variant_name",
            "test_id",
            "sample_scope",
            "artifact_type",
        ],
        set_={
            "path": statement.excluded.path,
            "metadata": statement.excluded.metadata,
        },
    )

    with engine.begin() as connection:
        connection.execute(statement)

    return len(rows)
