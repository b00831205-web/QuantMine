"""pytest fixtures for webapi tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.dependencies import get_request_engine
from app.security import require_user

TEST_USER = {"userId": 1, "username": "test-user"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Fresh API client with database access and login replaced by test doubles.

    These are contract tests for the endpoints themselves, so the session
    check is stubbed out with an already-authenticated user. Auth behaviour
    (401 on missing or expired sessions) is covered separately in
    ``test_auth.py`` against the real dependency.
    """
    app = create_app()
    # FastAPI resolves dependencies before it reaches route parameter
    # validation.  API contract tests must therefore override the real
    # database dependency even when the request is deliberately invalid.
    app.dependency_overrides[get_request_engine] = lambda: object()
    app.dependency_overrides[require_user] = lambda: TEST_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
