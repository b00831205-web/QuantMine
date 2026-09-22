"""Keep the public market-readiness contract documented in OpenAPI."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_openapi_documents_market_data_readiness() -> None:
    specification = yaml.safe_load(
        (
            Path(__file__).parents[2]
            / "docs"
            / "api"
            / "openapi.yaml"
        ).read_text(encoding="utf-8")
    )

    endpoint = specification["paths"]["/api/v1/market/data-readiness"]["get"]
    schema = specification["components"]["schemas"]["MarketDataReadiness"]

    assert endpoint["tags"] == ["market"]
    assert endpoint["parameters"] == [
        {
            "in": "query",
            "name": "asOfDate",
            "required": False,
            "description": (
                "解析截至该日期的最新基础版或同日修订版；"
                "省略时使用当前中国日期。"
            ),
            "schema": {"type": "string", "format": "date"},
        }
    ]
    assert endpoint["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/MarketDataReadiness"}
    assert set(schema["required"]) == {
        "market",
        "datasetId",
        "asOfDate",
        "revision",
        "researchReady",
        "reason",
    }
    assert schema["properties"]["marketDataVersion"]["type"] == [
        "string",
        "null",
    ]
    assert schema["properties"]["researchReady"]["type"] == "boolean"
