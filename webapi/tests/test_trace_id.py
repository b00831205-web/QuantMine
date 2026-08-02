"""验证 trace-id 中间件行为：成功响应同样携带 x-trace-id。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_successful_response_has_generated_trace_id(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    trace_id = resp.headers["x-trace-id"]
    # uuid4().hex 长度为 32
    assert len(trace_id) == 32


def test_successful_response_reuses_upstream_trace_id(client: TestClient) -> None:
    incoming = "11112222333344445555666677778888"
    resp = client.get("/api/v1/health", headers={"x-trace-id": incoming})
    assert resp.status_code == 200
    assert resp.headers["x-trace-id"] == incoming
