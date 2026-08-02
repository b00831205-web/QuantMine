"""pytest fixtures for webapi tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.dependencies import get_request_engine


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Fresh API client with database access replaced by a harmless test double."""
    app = create_app()
    # FastAPI resolves dependencies before it reaches route parameter
    # validation.  API contract tests must therefore override the real
    # database dependency even when the request is deliberately invalid.
    app.dependency_overrides[get_request_engine] = lambda: object()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
