# QUANTMINE Web API

阶段 0 仅产出 FastAPI 最小壳：

- `GET /api/v1/health`
- `GET /api/v1/market/series`（handler 留 `TODO(USER_LEARNING)`）
- 统一错误中间件（422 / 4xx / 5xx → 统一 ApiError）
- 全局 trace-id 中间件（成功响应与错误响应都携带 `x-trace-id`）
- CORS（开发态允许 5173）

## 安装与运行

> 所有命令均在 `webapi/` 目录下执行。

```bash
cd webapi

# 安装依赖（仅 webapi + 测试相关 extras）
uv sync --extra webapi --extra test-webapi

# 启动开发服务（默认 8000 端口）
uv run uvicorn app.main:app --reload --port 8000

# 跑测试
uv run pytest -q
```

可访问的端点：

- `GET http://localhost:8000/api/v1/health` → `{"status":"ok"}`
- `GET http://localhost:8000/api/v1/market/series?symbols=AAPL&startDate=2024-01-01&endDate=2024-06-01`
  → 缺参时 422；handler 体未实现时会返回 500（受 TODO 限制）
- `GET http://localhost:8000/docs` → 自动生成的 Swagger UI

## 与前端的契约

见 `../docs/api/openapi.yaml`。任何字段变更必须先改契约，再改实现。

## 目录组织

```
webapi/
├── pyproject.toml
├── app/
│   ├── main.py                  # create_app() + 中间件装配
│   ├── errors.py                # TraceIdMiddleware + 统一错误响应
│   ├── schemas.py               # Pydantic 模型（mirror OpenAPI）
│   └── api/
│       ├── __init__.py          # 唯一聚合点（api_router）
│       └── v1/
│           ├── health.py
│           └── market/series.py # 唯一保留 TODO(USER_LEARNING) 的端点
└── tests/
    ├── conftest.py              # client fixture
    ├── test_health.py
    ├── test_errors.py
    └── test_trace_id.py
```

新增业务域时：在 `app/api/v1/<domain>/` 下新增模块并暴露 `router`，
然后在 `app/api/__init__.py` 中 `include_router` 即可。

## 阶段 0 学习配额

仅 1 处：

- `app/api/v1/market/series.py` 中 `GET /market/series` handler 函数体
  - 输入：symbols、startDate、endDate、frequency、normalize
  - 输出：`SeriesResponse`
  - 约束：参数校验、服务调用占位、统一错误格式
