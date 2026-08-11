"""Example Skill: query significant factors of the latest research run."""
from sqlalchemy import MetaData, Table, select


def manifest() -> dict:
    return {
        "name": "latest_significant_factors",
        "displayName": "Latest Significant Factors",
        "description": "Query BH-significant factors from the latest research run",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max rows to return"}
            },
        },
    }


def execute(engine, params: dict) -> str:
    limit = int(params.get("limit") or 20)
    runs = Table("research_runs", MetaData(), autoload_with=engine)
    results = Table("test_results", MetaData(), autoload_with=engine)

    latest_run = select(runs.c.run_id).order_by(runs.c.run_id.desc()).limit(1)
    with engine.connect() as conn:
        run_id = conn.execute(latest_run).scalar_one_or_none()
        if run_id is None:
            return "No research run found"
        statement = (
            select(
                results.c.factor_name,
                results.c.period,
                results.c.ic_mean,
                results.c.ir,
            )
            .where(
                results.c.run_id == run_id,
                results.c.bh_significant.is_(True),
            )
            .order_by(results.c.ir.desc())
            .limit(limit)
        )
        rows = conn.execute(statement).mappings().all()

    if not rows:
        return f"run {run_id}: no BH-significant factors"
    lines = [f"run {run_id} significant factors:"]
    for row in rows:
        lines.append(
            f"- {row['factor_name']} {row['period']}d "
            f"IC={row['ic_mean']} IR={row['ir']}"
        )
    return "\n".join(lines)
