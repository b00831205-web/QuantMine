from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok_and_trace_id(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert "x-trace-id" in resp.headers
    # 16-byte hex (uuid4().hex) —— 长度 32
    assert len(resp.headers["x-trace-id"]) == 32


def test_trace_id_is_propagated_when_caller_provides_one(client: TestClient) -> None:
    """上游已传入 x-trace-id 时必须沿用，而不是另起一个。"""
    incoming = "deadbeefcafebabe1234567890abcdef"
    resp = client.get("/api/v1/health", headers={"x-trace-id": incoming})
    assert resp.status_code == 200
    assert resp.headers["x-trace-id"] == incoming
