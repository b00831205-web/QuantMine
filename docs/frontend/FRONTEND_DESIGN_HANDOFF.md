# QUANTMINE 前端设计交接文档

## 1. 产品目标

QUANTMINE 是一个覆盖市场数据、因子研究、统计检验、回测、任务调度、存储和 AI
解释的全流程量化研究平台。

前端的主要目标：

1. 展示 S&P 500 从 2015 年至今的市场数据。
2. 展示正式策略组合的当前和历史调仓表现。
3. 查看 Airflow DAG 的运行情况。
4. 查看因子 IC、显著性、稳定性和回测总结。
5. 以安全的只读方式快速查询业务数据库。
6. 生成、预览、下载可打印的 PDF 研究报告。
7. 使用一个理解完整工作流的 AI Agent 查询、解释和执行受控操作。
8. 集中配置 AI 模型、知识库、Skill 和外部 API。

## 2. 用户和权限

首版至少区分：

- 普通用户：查看数据、研究结果、报告并使用已配置的 AI。
- 管理员：配置模型、知识库、Skill、外部 API 和权限。

操作权限建议：

| 操作 | 默认行为 |
|---|---|
| 查询行情、任务、IC、回测 | 自动执行 |
| 读取允许的 artifact | 自动执行 |
| 生成 PDF | 用户确认 |
| 触发 DAG、重跑失败节点 | 用户确认 |
| 修改 AI 配置 | 仅管理员 |
| 任意 SQL、任意数据库写入 | 禁止 |

## 3. 全局布局

桌面端采用：

- 左侧固定导航。
- 中间主内容区域。
- 页面 1～6 提供可展开/收起的 AI 快捷窗口。
- AI 快捷窗口和完整 AI 工作台共享 conversation。
- 小屏幕隐藏固定快捷窗口，改为右下角浮动按钮。

主导航：

1. 市场总览
2. 调仓收益
3. Airflow 工作流
4. 研究结果
5. 数据库速查
6. PDF 报告
7. AI 工作台
8. AI 配置

## 4. 页面设计

### 4.1 市场总览

用途：自由查看并比较市场行情，不展示正式调仓明细。

主要内容：

- S&P 500 股票或 SPY 的时间序列。
- 最早支持到 2015-01-01。
- 单只股票、多只股票或自定义组合比较。
- 不同曲线统一换算为基期 100。
- 时间范围快捷选择：1M、1Y、5Y、ALL。
- 鼠标滚轮缩放、拖拽时间窗口、双击复位。
- 点击图例显示/隐藏曲线。
- 最新数据日期、当日收益、上涨家数、市场宽度和最新任务状态。

性能要求：

- 不允许一次请求全部股票的完整历史。
- 接口按 ticker、起止日期和频率查询。
- 长区间应支持服务端降采样或前端可控抽样。

### 4.2 调仓收益

用途：查看 DAG/回测产生的正式策略组合，不承载临时自定义组合。

筛选条件：

- backtest job；
- variant；
- factor；
- holding period；
- quantile/long-short；
- rebalance batch。

主要内容：

- 最近调仓日和最新数据日。
- 当前调仓周期扣除交易成本后的累计收益。
- 同期 SPY 收益和超额收益。
- 本次换手率、持仓数量、距下次调仓的交易日数。
- 当前周期组合净值与 SPY 曲线。
- 当前持仓及权重。
- 单只股票收益贡献。
- 最近历史调仓周期及收益。
- 本次调仓明细下载。

统一口径：

- “当前调仓收益”默认指最近一次调仓日至最新交易日的累计净收益。
- 基准使用完全相同的起止日期。
- 页面必须明确显示毛收益或净收益口径。

### 4.3 Airflow 工作流

用途：显示工作流整体状态，不复制完整 Airflow 管理后台。

主要内容：

- DAG 当前状态。
- 最近一次 run、数据日期、总耗时和下次计划时间。
- 下载、清洗、因子、IC、市场入库、回测节点拓扑。
- 每个节点的状态、开始时间、结束时间、耗时和重试次数。
- 历史运行列表。
- 选中节点的日志摘要。
- 跳转到 Airflow 原始日志。
- 手动触发 DAG 和重跑失败节点；操作前确认。

约束：

- 浏览器不直连 Airflow。
- FastAPI 后端负责认证、请求代理、响应归一化和审计。

### 4.4 研究结果

用途：在同一个 research run 内查看因子和回测结论。

全局筛选：

- research run；
- variant；
- test id；
- sample scope；
- backtest job；
- factor/period。

因子部分：

- IC mean、IC std、IR、样本量、t-stat、p-value。
- 多重检验结果，如 BH significant。
- IC 时序曲线、滚动 IC、年度统计和稳定性。

回测部分：

- Q1～Qn 和 long-short。
- 总收益、年化收益、波动率、Sharpe、最大回撤、胜率。
- 分组单调性结果。
- 净值曲线。
- 交易成本口径。
- sanity/sensitivity 检验摘要。

原则：

- 不得把不同 run 的数据混在同一结论中。
- 页面显示数据口径、variant、test 和 sample scope。
- 提供 CSV 下载和生成 PDF 的入口。

### 4.5 数据库速查

用途：业务数据只读查询，不是通用 SQL 客户端。

允许查询的业务对象包括：

- `market_latest`
- `market_bars`
- `research_runs`
- `test_results`
- `backtest_results`
- `backtest_metrics`
- IC/test/backtest artifacts 的业务视图

能力：

- 白名单字段。
- 结构化筛选器。
- 排序。
- 服务端分页。
- CSV 导出。
- 字段说明。

禁止：

- 任意 SQL。
- 任意 join。
- 任意数据库写入。
- 向浏览器暴露数据库连接信息。

### 4.6 PDF 报告

用途：生成可打印、可下载、可追溯的研究报告。

用户选择：

- research run；
- variants；
- tests；
- backtest jobs；
- 报告章节。

建议章节：

1. 执行摘要
2. 数据范围与质量
3. 方法和配置
4. IC 与显著性
5. 时序稳定性
6. 回测与交易成本
7. 单调性和稳健性
8. 风险与限制
9. 参数快照、Git commit 和 artifact 清单

报告流程：

- 创建异步生成任务。
- 查询生成状态。
- 页面预览。
- 下载 PDF。
- 保存历史报告记录。
- 生成完成后可自动加入报告 RAG 知识库。

### 4.7 AI 工作台

AI 是一个覆盖全流程的 Agent，不按页面拆成多个 Agent。

能力范围：

- 市场行情。
- Airflow 状态与日志。
- `airflow_batch -> run_id -> variant -> test -> backtest -> artifact -> report`
  全链路关联。
- IC、显著性、回测和风险解释。
- PDF 报告生成。
- 受控 Airflow 操作。
- Skill 和外部 API 调用。

页面内容：

- 对话历史。
- 完整消息区。
- 输入框。
- 模型选择下拉框。
- 引用来源。
- 工具调用摘要。
- 高影响操作确认卡片。

页面不展示：

- RAG 多选器。
- Provider API Key。
- Skill 配置。
- 复杂检索参数。

其他页面的 AI 快捷窗口：

- 使用同一个 Agent 和 conversation。
- 可以继续当前对话。
- 自动附加当前页面选择作为临时上下文。
- 可以跳转到完整 AI 工作台。

聊天历史建议：

- 全局保存。
- conversation 可以绑定、切换或同时引用多个 research run。
- 页面切换不创建新 Agent。

### 4.8 AI 配置

类似 Dify 的集中配置页面，仅管理员可修改。

配置分区：

- Agent 基本设置。
- 模型供应商和模型列表。
- 默认模型和可选模型。
- RAG 知识库。
- Skill/工具注册。
- 外部 API。
- 权限与确认策略。
- 调用日志。

知识库建议：

- 项目文档与方法论。
- research run artifacts。
- 历史 PDF 报告。
- 代码与数据库 schema。
- 用户上传的论文和研究资料。

RAG 要求：

- 每个知识库拥有独立权限和索引版本。
- 显示最后同步时间和状态。
- DAG 成功后可同步新 artifacts。
- PDF 完成后可同步新报告。
- 回答显示引用来源。
- 聊天历史属于会话记忆，不与文档 RAG 混成一层。

模型要求：

- 配置页定义供应商、模型、能力、价格等级和是否支持工具调用。
- 对话页只显示已配置且当前用户有权限使用的模型。
- API Key 只保存在服务端。

## 5. 当前后端结构

当前代码主要分为：

- `quantmine/`：研究计算库。
- `quantmine/workflows/`：IC、回测和市场存储工作流。
- `quantmine/storage/`：PostgreSQL 与 Parquet artifact 持久化。
- `pipelines/`：Airflow CLI task 和 DAG。
- `test/`：单元、回归和 golden tests。

主要数据库表：

- `research_runs`
- `market_bars`
- `market_latest`
- `ic_artifacts`
- `test_results`
- `test_result_artifacts`
- `backtest_results`
- `backtest_metrics`
- `backtest_artifacts`
- `factor_artifacts`
- `interaction_logs`

当前还没有正式 Web API 和前端工程。

## 6. 前端需要但当前后端尚缺的内容

以下属于实施前需要明确或补齐的缺口：

1. FastAPI 应用和统一错误响应。
2. Web API 的认证与权限。
3. 市场时间序列查询与降采样。
4. 自定义股票组合的权重和收益计算接口。
5. 当前正式持仓和历史调仓持仓的持久化。
6. 单只股票的调仓收益贡献数据。
7. Airflow REST API 代理。
8. research run 聚合查询。
9. artifact 的安全读取与下载。
10. 报告任务、报告历史和报告 artifact 表。
11. conversation 和 message 存储。
12. 模型供应商、模型、知识库、文档、索引版本和 Skill 配置存储。
13. AI 操作审批和更完整的审计模型。
14. SSE 或 WebSocket，用于流式聊天、报告进度和任务状态。

## 7. 建议 API 边界

这只是契约方向，具体字段在阶段 0 固化。

### 市场

- `GET /api/v1/market/tickers`
- `GET /api/v1/market/series`
- `POST /api/v1/market/compare`
- `GET /api/v1/market/latest`

### 调仓

- `GET /api/v1/rebalances`
- `GET /api/v1/rebalances/{rebalance_id}`
- `GET /api/v1/rebalances/{rebalance_id}/returns`
- `GET /api/v1/rebalances/{rebalance_id}/holdings`
- `GET /api/v1/rebalances/{rebalance_id}/contributions`

### Airflow

- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{dag_id}/runs`
- `GET /api/v1/workflows/{dag_id}/runs/{run_id}`
- `GET /api/v1/workflows/{dag_id}/runs/{run_id}/tasks`
- `POST /api/v1/workflows/{dag_id}/trigger`
- `POST /api/v1/workflows/{dag_id}/runs/{run_id}/retry`

### 研究

- `GET /api/v1/research/runs`
- `GET /api/v1/research/runs/{run_id}`
- `GET /api/v1/research/runs/{run_id}/tests`
- `GET /api/v1/research/runs/{run_id}/ic-series`
- `GET /api/v1/research/runs/{run_id}/backtests`
- `GET /api/v1/research/runs/{run_id}/metrics`

### 数据速查

- `GET /api/v1/data/catalog`
- `GET /api/v1/data/{resource}`
- `GET /api/v1/data/{resource}/export`

### 报告

- `POST /api/v1/reports`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{report_id}`
- `GET /api/v1/reports/{report_id}/download`

### AI

- `GET /api/v1/ai/conversations`
- `POST /api/v1/ai/conversations`
- `GET /api/v1/ai/conversations/{conversation_id}/messages`
- `POST /api/v1/ai/conversations/{conversation_id}/messages`
- `GET /api/v1/ai/models`
- `GET/POST /api/v1/admin/ai/providers`
- `GET/POST /api/v1/admin/ai/knowledge-bases`
- `GET/POST /api/v1/admin/ai/skills`
- `GET/POST /api/v1/admin/ai/connections`

## 8. 统一响应和错误

API 应明确区分：

- 成功数据；
- 参数错误；
- 未认证；
- 无权限；
- 资源不存在；
- 外部服务失败；
- 任务仍在处理；
- 内部错误。

前端每个数据区域必须拥有：

- loading；
- empty；
- error；
- success；
- stale/refreshing（必要时）。

## 9. 非功能要求

- TypeScript 开启严格模式。
- 前端不得存储服务端密钥。
- 时间、时区和交易日口径明确。
- 表格服务端分页。
- 图表在长时间序列下仍可交互。
- 后端接口带超时和外部依赖错误映射。
- 高影响操作可审计。
- PDF 和研究结果可追溯。
- API、核心组件和权限逻辑有自动化测试。
- 首版优先桌面端，保证小屏幕基本可用，不要求完整移动端重设计。

## 10. 首版非目标

- 不实现通用 SQL 编辑器。
- 不复制完整 Airflow UI。
- 不建立复杂 Redux 架构。
- 不支持用户自定义执行 Python 代码。
- 不允许 Agent 任意修改数据库。
- 不一次实现所有模型供应商。
- 不追求首版像素级设计系统。

