# QUANTMINE Frontend

阶段 0 脚手架。覆盖：React 18 + TypeScript 严格模式 + Vite + React Router + ECharts + Vitest。

## 命令

```bash
npm install
npm run dev          # http://localhost:5173
npm run typecheck    # tsc --noEmit
npm run lint
npm run test         # vitest run
npm run build
```

## 目录

```
src/
├── main.tsx, router.tsx
├── styles/         # 全局 CSS 与设计 token
├── types/          # 公共类型（api/market/rebalance/...）
├── api/
│   ├── http.ts     # fetch 封装 + 错误归一化（含 TODO）
│   └── client/     # 端点客户端（含 TODO）
├── components/
│   ├── layout/     # AppShell、SideNav、TopBar
│   ├── common/     # AsyncBoundary、Card、PaginatedTable 等
│   ├── chart/      # SeriesChart（含归一化 TODO）
│   └── ai/         # AIQuickPanel
└── pages/          # 8 个页面骨架
```

## 阶段 0 学习配额（TODO USER_LEARNING）

本阶段刻意留空 6 处供你练习，详见 `docs/frontend/STAGE_0_CHECKLIST.md`：

1. `src/api/http.ts` — `http()` 与 `toUserMessage()` 函数体
2. `src/api/client/market.ts` — `fetchSeries()` 函数体
3. `src/pages/MarketOverviewPage.tsx` — `useEffect` 数据拉取
4. `src/components/chart/normalize.ts` — `normalizeToBase100()`
5. 父子组件 props 传递（在 `MarketOverviewPage` 中体现）
6. 错误消息映射（在 `http.ts` 中体现）
