# 阶段 0 验收清单

目标：**不连接真实数据库**的前提下，把 8 个页面的路由、API 契约、类型、错误格式、四态 UI、骨架组件、错误边界、FastAPI 最小壳全部落地。

## 通过标准

### 前端
- [ ] `npm install` 成功
- [ ] `npm run typecheck` 零错误（strict + noUncheckedIndexedAccess + exactOptionalPropertyTypes）
- [ ] `npm run lint` 零警告
- [ ] `npm run test` 通过（AsyncBoundary 4 用例 + AppShell 1 用例）
- [ ] `npm run build` 成功
- [ ] `npm run dev` 后 8 个页面都能渲染骨架；左侧导航高亮当前路径

### 后端
- [ ] `uv sync --extra webapi --extra test-webapi` 成功
- [ ] `uv run pytest -q` 通过（test_health + test_errors）
- [ ] `curl localhost:8000/api/v1/health` 返回 `{"status":"ok"}`
- [ ] `curl 'localhost:8000/api/v1/market/series'`（缺参数）返回 422 + ApiError
- [ ] `curl 'localhost:8000/api/v1/does-not-exist'` 返回 404 + ApiError
- [ ] CORS 允许 `http://localhost:5173`

### 契约
- [ ] `docs/api/openapi.yaml` 与 `frontend/src/types/*.ts` 字段一一对应
- [ ] `docs/api/ERROR_MAP.md` 覆盖 401/403/404/422/429/502/5xx/超时

## 学习配额（6 处 TODO USER_LEARNING，阶段 0 必须留空）

| # | 文件 | 函数 | 期望用时 |
|---|---|---|---|
| 1 | `frontend/src/api/http.ts` | `http()` | 30 min |
| 2 | `frontend/src/api/http.ts` | `toUserMessage()` | 15 min |
| 3 | `frontend/src/api/client/market.ts` | `fetchSeries()` | 15 min |
| 4 | `frontend/src/pages/MarketOverviewPage.tsx` | 数据拉取 `useEffect` | 30 min |
| 5 | `frontend/src/components/chart/normalize.ts` | `normalizeToBase100()` | 20 min |
| 6 | `webapi/app/api/v1/market/series.py` | `get_market_series()` handler | 25 min |

合计约 2 小时。建议顺序：5 → 1 → 2 → 3 → 4 → 6。

## 阶段 0 不做的事

- 不接 MSW handler 与 fixture（阶段 2 之前由前端 dev 自带 dev mock）
- 不写任何 `quantmine/` 研究代码
- 不连 PostgreSQL / Airflow
- 不实现认证 / session / 权限
- 不创建任何 PDF、AI Provider、SSE 通道
- 不引入 Redux / 状态机

## 下一阶段预览（阶段 1）

应用外壳定型后，阶段 2（市场总览纵向切片）会：
1. 补齐 MSW handlers + fixtures（覆盖全部 §7 端点）
2. 把上面 6 个 TODO 全部填上
3. 接入 `quantmine/storage/market.py` 的真实查询
4. 加 E2E 测试（Playwright）
