from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_unified_error(body: dict, *, code: str, status: int) -> None:
    assert body["code"] == code
    assert body["status"] == status
    assert body["title"]
    assert "traceId" in body and body["traceId"]


def test_validation_error_returns_unified_format(client: TestClient) -> None:
    """缺少必填参数应返回 422 + ApiError 结构。"""
    resp = client.get("/api/v1/market/series")  # 缺 symbols / startDate / endDate
    assert resp.status_code == 422
    body = resp.json()
    _assert_unified_error(body, code="VALIDATION_FAILED", status=422)
    assert isinstance(body["fieldErrors"], list) and len(body["fieldErrors"]) > 0
    assert "x-trace-id" in resp.headers
    # 错误响应的 trace id 与响应 header 一致
    assert body["traceId"] == resp.headers["x-trace-id"]


def test_invalid_frequency_returns_422(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/market/series",
        params={
            "symbols": "AAPL",
            "startDate": "2024-01-01",
            "endDate": "2024-06-01",
            "frequency": "X",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    _assert_unified_error(body, code="VALIDATION_FAILED", status=422)


def test_unknown_path_returns_404_unified_format(client: TestClient) -> None:
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    _assert_unified_error(body, code="NOT_FOUND", status=404)
    assert body["traceId"] == resp.headers["x-trace-id"]


def test_cors_allows_localhost_5173(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
