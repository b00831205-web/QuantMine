# 下一阶段工程设计：市场数据完整性、统一 DAG 与前端多市场支持

> 文档版本：`v2026.09.21`  
> 状态：不可变基线（immutable baseline）  
> 规则：后续修订必须创建新的带版本号文件，不修改本文件。

## 1. 阶段目标

建立“完整交易日解析 + 自动缺口回填 + 统一市场 DAG”的数据生产体系，并让前端能够按市场正确展示数据、因子研究和检验指标。

## 2. 当前问题

1. A 股 `daily_production` 在收盘前手动触发时会请求当天盘中快照，并因数据尚未完整而 retry。
2. A 股历史回填脚本独立存在，但尚未由每日 DAG 根据数据缺口自动编排。
3. A 股使用配置化 pipeline 与版本化数据湖；美股仍使用旧式脚本串联 DAG。
4. 前端全局数据日期和市场概览仍从旧美股 `market_bars` 读取，无法展示 A 股版本化数据。
5. 研究结果前端固定依赖 `ic_mean`、`t_stat`、`p_value` 等字段，不能完整显示新检验方法的结果。

## 3. 后端目标架构

```text
调度或手动触发
  → 完整交易日解析
  → session_gate
  → reference_refresh
  → market_data_refresh
  → coverage_audit
  → factor_research
  → ic_research
  → backtest
  → attribution
```

- 收盘前手动触发：使用最近一个完整交易日。
- 收盘后日常调度：使用当天完整数据。
- 周末或节假日：使用最近一个交易日。
- 用户显式补跑：提供 `as_of_date`，并通过交易日历和数据可用性校验。
- `retry` 仅用于网络、限流等临时故障；盘中数据未就绪不应 retry。

## 4. 数据完整性与回填

新增 `coverage_audit` stage：

- 以交易日历、证券主数据与已发布 market-data version 为依据；
- 输出缺失日期、缺失股票、缺失字段及缺口规模；
- 生成持久化的回填计划。

新增受控 `history_backfill` worker：

- 日常增量优先，回填不得阻塞当天生产；
- 按日期和股票分批，具备速率限制、checkpoint、断点续跑和重试；
- 每次执行设置最大任务数、股票数及时间窗口；
- 不允许每次发现缺口时重跑全量历史。

新增 `research_readiness_gate`：

- 研究、IC、回测只消费通过覆盖率策略的数据版本；
- 数据未完整时下游 stage 为 skip，而不是产生不完整结果；
- 运行产物记录数据版本、覆盖率、缺口数与插件版本。

## 5. 统一市场 DAG

统一外层阶段契约：

```text
session_gate
→ reference_refresh
→ market_data_refresh
→ coverage_audit
→ factor_research
→ ic_research
→ backtest
→ attribution
```

市场差异仅由 Bundle 与插件实现：

- A 股：停牌、涨跌停、资格表、T+1、交易成本；
- 美股：交易日历、证券池、数据源和市场规则；
- DAG：不直接认识 AkShare、yfinance 或市场特有业务细节。

美股旧步骤映射如下：

| 旧美股步骤 | 统一阶段 |
| --- | --- |
| `universe_refresh` | `reference_refresh` |
| `data_downloading` + `data_cleaning` | `market_data_refresh` |
| `factor_calculation` | `factor_research` |
| `ic_calculation` | `ic_research` |
| `backtest` | `backtest` |
| `attribution` | `attribution` |

旧 `quant_factor_mining` DAG 暂时保留兼容；美股新 pipeline 连续稳定运行后再标记废弃。

## 6. 前端目标

### 6.1 全局市场上下文

新增 `MarketContext`，市场选择至少包含市场标识、显示名称、时区与货币。左上角提供市场下拉框；选择变化后同步刷新：

- TopBar 的 `Data Date`；
- Market Overview；
- Research Results 与 Factor Detail；
- Backtest / Attribution；
- Database Explorer 的数据集筛选。

`Data Date` 必须来自所选市场最近一个“已发布且完整”的 market-data version，不再从旧美股表做全局查询。

### 6.2 多市场 Market Overview

市场 API 增加 `market` 参数：

```text
GET /api/v1/market/latest-date?market=CN
GET /api/v1/market/overview?market=CN
GET /api/v1/market/series?market=CN&symbols=...
```

后端通过 MarketData Bundle / 发布版本读取数据；前端不感知 PostgreSQL、Parquet 或未来存储实现。

每个市场由配置提供默认标的：

- US：SPY、AAPL、MSFT 等；
- CN：沪深指数、代表性 ETF 或配置的默认 A 股标的。

概览页展示市场、时区、最近完整数据日、数据版本、覆盖率与回填状态。

### 6.3 动态检验指标

研究与检验结果统一为动态指标数组：

```ts
type ResearchMetric = {
  key: string;
  label: string;
  value: number | string | boolean | null;
  format?: 'number' | 'percent' | 'ratio' | 'date' | 'boolean';
  role?: 'primary' | 'diagnostic' | 'warning';
};

type ValidationResult = {
  methodId: string;
  methodLabel: string;
  verdict?: 'pass' | 'fail' | 'warning';
  metrics: ResearchMetric[];
};
```

传统 IC 检验可返回 `t_stat`、`p_value`；其他检验方法无需伪造这些字段。机器学习、多因子回归和未来检验插件均可声明自身指标。

### 6.4 持久化回测结果

新增 position-backtest artifact reader API，前端展示：

- 净值、日收益、现金曲线；
- 持仓、目标权重、请求成交量与实际成交量；
- 手续费、未成交原因及 A 股交易约束；
- 数据版本、市场规则版本、研究 run 与回测 run 的关联。

前端只调用后端 reader API，不直接读取 artifact 文件。

## 7. 推荐实施顺序

1. 完整交易日解析，消除收盘前手动触发的无效 retry。
2. 覆盖率审计与自动缺口回填。
3. 数据完整性门禁。
4. 多市场查询 API。
5. 前端 MarketContext、市场下拉框与 Market Overview 切换。
6. 动态检验指标 API 契约与前端渲染。
7. Position-backtest artifact API 与回测详情页面。
8. 美股旧 DAG 迁入统一配置化 pipeline。

## 8. 本阶段不包含

- C++ / CUDA 计算引擎；
- Redis、多用户、权限体系；
- 模拟盘投资建议模块；
- A 股交易规则的进一步扩展。

## 9. 验收标准

1. 收盘前手动触发 A 股 DAG 不写入盘中数据，且不发生无意义 retry。
2. 收盘后调度可发布当天不可变市场数据版本。
3. 人为制造历史缺口后，系统可发现、记录并限量回填。
4. 数据未达完整性阈值时，研究、IC、回测不执行。
5. A 股与美股均通过同一 DAG 工厂和阶段契约运行。
6. 前端可切换 US/CN，并展示对应市场的完整数据日期、版本和概览。
7. 新因子和任意检验方法均可显示，无需强制 `p_value`、`t_stat`。
