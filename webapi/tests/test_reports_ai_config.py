from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

import app.api.v1.ai.router as ai_router
import app.api.v1.reports.router as reports_router


def test_report_history_returns_page_instead_of_500(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reports_router,
        "fetch_report_history",
        lambda _engine, *, page, page_size, run_id: (
            [
                {
                    "id": 7,
                    "run_id": 2,
                    "test_id": None,
                    "lang": "en",
                    "ai": False,
                    "artifact_type": "pdf",
                    "artifact_path": "data/reports/report-history-7.pdf",
                    "artifact_size": 1234,
                    "data_available": True,
                    "status": "ready",
                    "created_at": datetime(2026, 8, 11, 12, 0, 0),
                }
            ],
            1,
        ),
    )
    monkeypatch.setattr(
        reports_router,
        "resolve_report_artifact",
        lambda _path: __file__,
    )

    response = client.get("/api/v1/reports?page=1&pageSize=10&runId=2")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "reportId": "report-7",
                "runId": 2,
                "testId": None,
                "lang": "en",
                "ai": False,
                "artifactType": "pdf",
                "artifactAvailable": True,
                "artifactSize": 1234,
                "dataAvailable": True,
                "createdAt": "2026-08-11 12:00:00",
                "status": "ready",
            }
        ],
        "total": 1,
        "page": 1,
        "pageSize": 10,
    }


def test_report_history_file_serves_selected_pdf(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    pdf = tmp_path / "selected.pdf"
    pdf.write_bytes(b"%PDF-1.7 selected report")
    monkeypatch.setattr(
        reports_router,
        "fetch_report_history_item",
        lambda _engine, report_id: {
            "id": report_id,
            "run_id": 2,
            "test_id": None,
            "lang": "en",
            "artifact_type": "pdf",
            "artifact_path": "data/reports/selected.pdf",
            "status": "ready",
        },
    )
    monkeypatch.setattr(reports_router, "resolve_report_artifact", lambda _path: pdf)

    response = client.get("/api/v1/reports/report-7/file?inline=true")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content == b"%PDF-1.7 selected report"


def test_report_history_file_returns_404_when_artifact_is_missing(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reports_router,
        "fetch_report_history_item",
        lambda _engine, _report_id: {
            "id": 7,
            "artifact_path": None,
            "status": "ready",
        },
    )
    monkeypatch.setattr(reports_router, "resolve_report_artifact", lambda _path: None)

    response = client.get("/api/v1/reports/report-7/file")

    assert response.status_code == 404


def test_ai_config_normalizes_legacy_skills_and_returns_discovered_skills(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ai_router,
        "fetch_config",
        lambda _engine: {
            "providers": [],
            "defaultModel": "",
            "systemPrompt": "",
            "temperature": 0.7,
            "capabilities": {},
            "embeddingConfig": {"provider": "none"},
            # Older configurations could contain string entries. They must not
            # make the entire config endpoint fail with attribute errors.
            "skills": ["legacy-skill", {"name": "factor-scan", "enabled": True}],
        },
    )
    monkeypatch.setattr(
        ai_router,
        "discover_skills",
        lambda: [
            {
                "name": "factor-scan",
                "displayName": "Factor Scan",
                "description": "Scans significant factors",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )

    response = client.get("/api/v1/ai/config")

    assert response.status_code == 200
    assert response.json()["skills"] == [
        {
            "name": "factor-scan",
            "displayName": "Factor Scan",
            "description": "Scans significant factors",
            "parameters": {"type": "object", "properties": {}},
            "enabled": True,
        }
    ]
    assert "skill" not in response.json()
