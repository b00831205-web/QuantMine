import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "quantmine" / "storage" / "schema.sql"


def _schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def test_backtest_metric_unique_key_includes_selection_test():
    table_sql = re.search(
        r"CREATE TABLE IF NOT EXISTS backtest_metrics \((.*?)\n\);",
        _schema(),
        flags=re.DOTALL,
    ).group(1)
    unique_key = re.search(
        r"UNIQUE \((.*?)\)",
        table_sql,
        flags=re.DOTALL,
    ).group(1)

    assert "test_id" in unique_key


def test_schema_sql_is_the_only_ddl_source():
    """建表真相源唯一：不得再出现独立的 migrations 目录。

    初始化脚本（docker/postgres/init.sh、scripts/setup.py）无条件重放 schema.sql，
    若把新表写进别处，新库就会缺表。
    """
    assert not (ROOT / "webapi" / "migrations").exists()


def test_schema_sql_is_replayable():
    """schema.sql 每次初始化都原样重放，所有 DDL 必须幂等。"""
    offenders = [
        line.strip()
        for line in _schema().splitlines()
        if re.match(r"\s*CREATE (TABLE|INDEX|EXTENSION)\b", line, flags=re.IGNORECASE)
        and "IF NOT EXISTS" not in line.upper()
    ]

    assert offenders == []


def test_schema_sql_carries_no_grants():
    """授权由初始化脚本统一做（含 ALTER DEFAULT PRIVILEGES），schema.sql 不写死角色名。"""
    statements = re.sub(r"--[^\n]*", "", _schema())

    assert "GRANT" not in statements.upper()
