# 统一错误响应 → 前端用户消息

源：`docs/api/openapi.yaml` 中的 `ApiError` schema。

| HTTP | `code`              | 前端标题          | 建议展示语（≤ 24 字）            | 行为                          |
| ---- | ------------------- | ------------- | ------------------------ | --------------------------- |
| 400  | `VALIDATION_FAILED` | 参数校验失败        | 请检查输入参数                    | 表单内联展示 `fieldErrors`          |
| 401  | `UNAUTHENTICATED`   | 未登录           | 请先登录                      | 跳转登录；附带 `traceId`             |
| 403  | `FORBIDDEN`         | 没有权限          | 当前账号无权执行该操作               | 隐藏敏感按钮；管理员联系入口                |
| 404  | `NOT_FOUND`         | 资源不存在         | 找不到对应数据                   | 显示空状态；提供返回                    |
| 409  | `CONFLICT`          | 状态冲突          | 当前状态不允许该操作                | 禁用按钮 + 解释                     |
| 422  | `VALIDATION_FAILED` | 语义校验失败        | 请求参数有误                    | 表单内联 + 顶部 banner               |
| 429  | `RATE_LIMITED`      | 请求过于频繁        | 操作太频繁，请稍后再试              | 倒计时禁用按钮                       |
| 502  | `UPSTREAM_FAILURE`  | 上游服务异常        | 上游依赖暂时不可用                 | 提供重试；记录 traceId               |
| 503  | `UPSTREAM_FAILURE`  | 服务暂不可用        | 系统维护中，请稍后再试              | 顶部 banner                    |
| 5xx  | `INTERNAL_ERROR`    | 内部错误          | 系统开小差，已记录 traceId         | 提供重试；管理员邮箱                    |
| —    | 超时 / 网络中断         | —             | 网络不稳定，请检查连接              | 重试；保留表单内容                    |

## 实现位置

- `frontend/src/api/http.ts` 的 `toUserMessage()` 为**学习者留白**，覆盖上述所有映射。
- 所有错误经 `<AsyncBoundary />` → `<ErrorView />` 渲染，自动附 `traceId` 链接。
