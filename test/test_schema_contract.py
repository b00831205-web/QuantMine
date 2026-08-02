import re
from pathlib import Path


def test_backtest_metric_unique_key_includes_selection_test():
    schema = (
        Path(__file__).parents[1] / "quantmine" / "storage" / "schema.sql"
    ).read_text(encoding="utf-8")
    table_sql = re.search(
        r"CREATE TABLE backtest_metrics \((.*?)\n\);",
        schema,
        flags=re.DOTALL,
    ).group(1)
    unique_key = re.search(
        r"UNIQUE \((.*?)\)",
        table_sql,
        flags=re.DOTALL,
    ).group(1)

    assert "test_id" in unique_key
