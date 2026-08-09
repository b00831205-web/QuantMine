"""登录鉴权边界测试。

其余测试用 conftest 的 client fixture 覆盖掉了 require_user，因此鉴权本身
必须在这里针对真实依赖验证：受保护端点未登录一律 401，开放端点不受影响。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.dependencies import get_request_engine


@pytest.fixture
def anonymous_client():
    """未登录客户端：保留真实 require_user，只替换数据库依赖。"""
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
    """无会话 Cookie 时受保护端点返回 401，而不是泄漏数据或 500。"""
    response = anonymous_client.get(path)
    assert response.status_code == 401


def test_health_stays_open_without_login(anonymous_client):
    """健康检查必须免登录，否则探活会被鉴权挡掉。"""
    assert anonymous_client.get("/api/v1/health").status_code == 200


def test_login_endpoint_stays_open_without_login(anonymous_client):
    """登录端点本身必须免登录，否则永远无法取得会话。

    故意发送缺字段的请求体：依赖（鉴权）先于请求体校验执行，所以端点开放时
    会走到 422，被鉴权挡住则是 401。这样既能断言开放性，又不必碰数据库。
    """
    response = anonymous_client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
