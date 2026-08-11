"""Authentication boundary tests.

Every other test overrides require_user through the conftest client fixture, so
authentication itself has to be verified here against the real dependency:
protected endpoints must return 401 when signed out, and open endpoints must be
unaffected.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.dependencies import get_request_engine


@pytest.fixture
def anonymous_client():
    """Signed-out client: keep the real require_user, swap only the database dependency."""
    app = create_app()
    app.dependency_overrides[get_request_engine] = lambda: object()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/market/series?symbols=AAPL&startDate=2024-01-01&endDate=2024-01-10",
        "/api/v1/market/latest-date",
        "/api/v1/research/options",
    ],
)
def test_protected_endpoints_reject_anonymous_requests(anonymous_client, path):
    """Without a session cookie, protected endpoints return 401 rather than leaking data or 500ing."""
    response = anonymous_client.get(path)
    assert response.status_code == 401


def test_health_stays_open_without_login(anonymous_client):
    """The health check must stay unauthenticated, or liveness probes get blocked by auth."""
    assert anonymous_client.get("/api/v1/health").status_code == 200


def test_login_endpoint_stays_open_without_login(anonymous_client):
    """The login endpoint itself must stay unauthenticated, or no session can ever be obtained.

    The request body deliberately omits fields: dependencies (auth) run before
    body validation, so an open endpoint reaches 422 while a gated one returns
    401. That asserts openness without touching the database.
    """
    response = anonymous_client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
