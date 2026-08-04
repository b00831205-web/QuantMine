import { http, HttpResponse } from 'msw';

/*
 * 开发环境 mock：等后端 /api/v1/rebalances 系列接口就绪后，删除本文件即可。
 */

const unit = 'decimal' as const;

interface MockRebalance {
  rebalanceId: string;
  backtestJob: string;
  variant: string;
  factor: string;
  holdingPeriod: number;
  type: 'quantile' | 'long_short';
  rebalanceDate: string;
  netReturn: number;
  spyReturn: number;
  excessReturn: number;
  turnover: number;
  holdingsCount: number;
  tradingDaysToNext: number;
  unit: 'percent' | 'decimal';
}

const rebalances: MockRebalance[] = [
  {
    rebalanceId: 'rb-2026-04-01',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2026-04-01',
    netReturn: 0.041,
    spyReturn: 0.027,
    excessReturn: 0.014,
    turnover: 0.34,
    holdingsCount: 10,
    tradingDaysToNext: 8,
    unit,
  },
  {
    rebalanceId: 'rb-2026-03-04',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2026-03-04',
    netReturn: 0.018,
    spyReturn: 0.011,
    excessReturn: 0.007,
    turnover: 0.29,
    holdingsCount: 10,
    tradingDaysToNext: 6,
    unit,
  },
  {
    rebalanceId: 'rb-2026-02-02',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2026-02-02',
    netReturn: -0.012,
    spyReturn: 0.005,
    excessReturn: -0.017,
    turnover: 0.41,
    holdingsCount: 10,
    tradingDaysToNext: 5,
    unit,
  },
  {
    rebalanceId: 'rb-2025-12-29',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-12-29',
    netReturn: 0.033,
    spyReturn: 0.019,
    excessReturn: 0.014,
    turnover: 0.22,
    holdingsCount: 10,
    tradingDaysToNext: 4,
    unit,
  },
  {
    rebalanceId: 'rb-2025-11-25',
    backtestJob: 'job-2025-12',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-11-25',
    netReturn: 0.025,
    spyReturn: 0.02,
    excessReturn: 0.005,
    turnover: 0.3,
    holdingsCount: 10,
    tradingDaysToNext: 3,
    unit,
  },
  {
    rebalanceId: 'rb-2025-10-28',
    backtestJob: 'job-2026-06',
    variant: 'orthogonalized',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-10-28',
    netReturn: 0.011,
    spyReturn: 0.013,
    excessReturn: -0.002,
    turnover: 0.27,
    holdingsCount: 10,
    tradingDaysToNext: 3,
    unit,
  },
  {
    rebalanceId: 'rb-2025-09-29',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-09-29',
    netReturn: 0.036,
    spyReturn: 0.021,
    excessReturn: 0.015,
    turnover: 0.33,
    holdingsCount: 10,
    tradingDaysToNext: 4,
    unit,
  },
  {
    rebalanceId: 'rb-2025-09-02',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'reversal',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-09-02',
    netReturn: -0.008,
    spyReturn: 0.004,
    excessReturn: -0.012,
    turnover: 0.38,
    holdingsCount: 10,
    tradingDaysToNext: 5,
    unit,
  },
  {
    rebalanceId: 'rb-2025-08-04',
    backtestJob: 'job-2026-06',
    variant: 'raw',
    factor: 'momentum',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-08-04',
    netReturn: 0.019,
    spyReturn: 0.017,
    excessReturn: 0.002,
    turnover: 0.26,
    holdingsCount: 10,
    tradingDaysToNext: 5,
    unit,
  },
  {
    rebalanceId: 'rb-2025-07-07',
    backtestJob: 'job-2026-06',
    variant: 'orthogonalized',
    factor: 'reversal',
    holdingPeriod: 21,
    type: 'quantile',
    rebalanceDate: '2025-07-07',
    netReturn: 0.028,
    spyReturn: 0.015,
    excessReturn: 0.013,
    turnover: 0.31,
    holdingsCount: 10,
    tradingDaysToNext: 4,
    unit,
  },
];

const tickersByRebalance: Record<string, string[]> = {
  'rb-2026-04-01': ['NVDA', 'MSFT', 'AAPL', 'AMZN', 'GOOGL', 'META', 'AVGO', 'TSLA', 'JPM', 'V'],
  'rb-2026-03-04': ['AAPL', 'MSFT', 'NVDA', 'LLY', 'UNH', 'XOM', 'WMT', 'COST', 'HD', 'PG'],
  'rb-2026-02-02': ['TSLA', 'META', 'AMZN', 'GOOGL', 'NFLX', 'ORCL', 'CRM', 'AMD', 'INTC', 'QCOM'],
  'rb-2025-12-29': ['JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'C', 'AXP', 'BLK'],
  'rb-2025-11-25': ['LLY', 'UNH', 'XOM', 'CVX', 'WMT', 'COST', 'HD', 'PG', 'KO', 'PEP'],
  'rb-2025-10-28': ['AVGO', 'AMD', 'QCOM', 'INTC', 'MU', 'TXN', 'ADBE', 'CRM', 'ORCL', 'NFLX'],
  'rb-2025-09-29': ['MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'NVDA', 'TSLA', 'NFLX', 'ADBE', 'CRM'],
  'rb-2025-09-02': ['JPM', 'GS', 'MS', 'BAC', 'C', 'WFC', 'AXP', 'BLK', 'SCHW', 'USB'],
  'rb-2025-08-04': ['WMT', 'COST', 'TGT', 'KR', 'CVS', 'WBA', 'LOW', 'HD', 'NKE', 'SBUX'],
  'rb-2025-07-07': ['XOM', 'CVX', 'COP', 'SLB', 'OXY', 'EOG', 'PSX', 'VLO', 'MPC', 'HAL'],
};

const makeHoldings = (tickers: string[]) =>
  tickers.map((symbol, i) => ({
    symbol,
    weight: 1 / tickers.length,
    quantile: `Q${Math.min(5, Math.floor((i / tickers.length) * 5) + 1)}`,
  }));

const makeContributions = (tickers: string[]) =>
  tickers.map((symbol, i) => ({
    symbol,
    contribution: Number((0.012 - i * 0.0022).toFixed(4)),
  }));

const details = rebalances.map((rb) => {
  const tickers = tickersByRebalance[rb.rebalanceId] ?? [];
  return {
    ...rb,
    asOfDate: rb.rebalanceDate,
    holdings: makeHoldings(tickers),
    contributions: makeContributions(tickers),
  };
});

const detailById = new Map(details.map((d) => [d.rebalanceId, d]));

const toDateStr = (d: Date): string => d.toISOString().slice(0, 10);

function weekdayPoints(startDate: string, totalReturn: number, days = 21) {
  const cursor = new Date(`${startDate}T00:00:00Z`);
  const daily = Math.pow(1 + totalReturn, 1 / days) - 1;
  const points: Array<{ date: string; value: number }> = [];
  let value = 100;
  while (points.length < days) {
    const dow = cursor.getUTCDay();
    if (dow !== 0 && dow !== 6) {
      value *= 1 + daily;
      points.push({ date: toDateStr(cursor), value: Number(value.toFixed(4)) });
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return points;
}

function rangePoints(startDate: string | null, endDate: string | null) {
  if (startDate === null || endDate === null) return [];
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  const points: Array<{ date: string; value: number }> = [];
  let value = 100;
  const cursor = new Date(start);
  while (cursor <= end) {
    const dow = cursor.getUTCDay();
    if (dow !== 0 && dow !== 6) {
      value *= 1.0008;
      points.push({ date: toDateStr(cursor), value: Number(value.toFixed(4)) });
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return points;
}

const dataCatalog = [
  {
    resource: 'market_latest',
    label: '行情最新快照',
    description: 'S&P 500 成分股最新交易快照',
    fields: [
      { name: 'symbol', type: 'string', description: '股票代码', filterable: true },
      { name: 'name', type: 'string', description: '股票名称', filterable: false },
      { name: 'price', type: 'number', description: '最新价', filterable: false },
      { name: 'change_pct', type: 'number', description: '涨跌幅 %', filterable: false },
      { name: 'volume', type: 'number', description: '成交量', filterable: false },
      { name: 'trade_date', type: 'date', description: '交易日', filterable: true },
    ],
  },
  {
    resource: 'research_runs',
    label: '研究批次',
    description: '一次 research run 的元信息',
    fields: [
      { name: 'run_id', type: 'number', description: '批次 ID', filterable: true },
      { name: 'run_timestamp', type: 'date', description: '运行时间', filterable: false },
      { name: 'git_commit', type: 'string', description: '代码版本', filterable: false },
      { name: 'status', type: 'string', description: '状态', filterable: true },
    ],
  },
  {
    resource: 'test_results',
    label: '因子检验结果',
    description: '因子 IC 检验明细',
    fields: [
      { name: 'run_id', type: 'number', description: '批次 ID', filterable: true },
      { name: 'variant_name', type: 'string', description: '变体', filterable: true },
      { name: 'factor_name', type: 'string', description: '因子', filterable: true },
      { name: 'period', type: 'number', description: '持有期', filterable: true },
      { name: 'ic_mean', type: 'number', description: 'IC 均值', filterable: false },
      { name: 't_stat', type: 'number', description: 't 值', filterable: false },
      { name: 'p_value', type: 'number', description: 'p 值', filterable: false },
    ],
  },
];

const dataRows: Record<string, Record<string, unknown>[]> = {
  market_latest: [
    { symbol: 'AAPL', name: 'Apple', price: 218.24, change_pct: 1.24, volume: 48200000, trade_date: '2026-08-04' },
    { symbol: 'MSFT', name: 'Microsoft', price: 415.12, change_pct: -0.31, volume: 21700000, trade_date: '2026-08-04' },
    { symbol: 'NVDA', name: 'NVIDIA', price: 132.66, change_pct: 3.02, volume: 301000000, trade_date: '2026-08-04' },
    { symbol: 'AMZN', name: 'Amazon', price: 186.4, change_pct: 0.78, volume: 33400000, trade_date: '2026-08-04' },
    { symbol: 'GOOGL', name: 'Alphabet', price: 178.02, change_pct: 0.42, volume: 25100000, trade_date: '2026-08-04' },
  ],
  research_runs: [
    { run_id: 42, run_timestamp: '2026-07-30 09:00:00', git_commit: 'abc1234', status: 'success' },
    { run_id: 41, run_timestamp: '2026-07-01 09:00:00', git_commit: 'def5678', status: 'success' },
    { run_id: 40, run_timestamp: '2026-06-15 09:00:00', git_commit: 'ghi9012', status: 'failed' },
  ],
  test_results: [
    { run_id: 42, variant_name: 'raw', factor_name: 'momentum', period: 21, ic_mean: 0.0321, t_stat: 4.21, p_value: 0.0001 },
    { run_id: 42, variant_name: 'orthogonalized', factor_name: 'momentum', period: 21, ic_mean: 0.0287, t_stat: 3.98, p_value: 0.0002 },
    { run_id: 42, variant_name: 'raw', factor_name: 'reversal', period: 10, ic_mean: -0.0182, t_stat: -2.11, p_value: 0.0348 },
    { run_id: 41, variant_name: 'raw', factor_name: 'momentum', period: 21, ic_mean: 0.0244, t_stat: 3.12, p_value: 0.0018 },
  ],
};

const filterRows = (
  rows: Record<string, unknown>[],
  filters: string | null,
): Record<string, unknown>[] => {
  if (!filters) return rows;
  try {
    const cond = JSON.parse(filters) as Record<string, unknown>;
    return rows.filter((row) =>
      Object.entries(cond).every(([key, value]) => row[key] === value),
    );
  } catch {
    return rows;
  }
};

const sortRows = (
  rows: Record<string, unknown>[],
  sortBy: string | null,
  sortDir: string | null,
): Record<string, unknown>[] => {
  if (!sortBy || !sortDir) return rows;
  return [...rows].sort((a, b) => {
    const av = a[sortBy];
    const bv = b[sortBy];
    const cmp =
      typeof av === 'number' && typeof bv === 'number'
        ? av - bv
        : String(av).localeCompare(String(bv));
    return sortDir === 'asc' ? cmp : -cmp;
  });
};

export const handlers = [
  http.get('/api/v1/market/latest-date', () =>
    HttpResponse.json({ latestTradeDate: '2026-08-01' }),
  ),

  http.get('/api/v1/research/options', ({ request }) => {
    const url = new URL(request.url);
    const runId = url.searchParams.get('runId');
    return HttpResponse.json({
      defaultRunId: 42,
      runs: [
        { runId: 42, createdAt: '2026-07-30T09:00:00' },
        { runId: 41, createdAt: '2026-07-01T09:00:00' },
      ],
      variants: ['raw', 'orthogonalized'],
      testIds: runId === '41' ? ['legacy_raw'] : ['newey_orthogonalized', 'newey_raw'],
      sampleScopes: ['train', 'test'],
    });
  }),

  http.get('/api/v1/reports', ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('pageSize') ?? '10');
    const items = [
      { reportId: 'rpt-20260804-001', runId: 42, testId: 'newey_orthogonalized', lang: 'zh', ai: false, createdAt: '2026-08-04 09:12:33', status: 'ready' },
      { reportId: 'rpt-20260803-002', runId: 42, testId: 'newey_raw', lang: 'zh', ai: true, createdAt: '2026-08-03 16:40:02', status: 'ready' },
      { reportId: 'rpt-20260802-003', runId: 41, testId: 'legacy_raw', lang: 'en', ai: false, createdAt: '2026-08-02 11:05:47', status: 'ready' },
      { reportId: 'rpt-20260730-004', runId: 41, testId: null, lang: 'zh', ai: false, createdAt: '2026-07-30 14:22:19', status: 'failed' },
      { reportId: 'rpt-20260728-005', runId: 42, testId: 'newey_orthogonalized', lang: 'en', ai: true, createdAt: '2026-07-28 10:51:08', status: 'ready' },
    ];
    return HttpResponse.json({
      items: items.slice((page - 1) * pageSize, page * pageSize),
      total: items.length,
      page,
      pageSize,
    });
  }),

  // /api/v1/workflows* 已由真实 FastAPI 后端接管（读 Airflow 元数据库），mock 已移除。
  // 未命中的请求经 vite 代理打到 http://localhost:8000。

  http.get('/api/v1/data/catalog', () => HttpResponse.json(dataCatalog)),

  http.get('/api/v1/data/:resource', ({ request, params }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('pageSize') ?? '10');
    const rows = sortRows(
      filterRows(dataRows[String(params.resource)] ?? [], url.searchParams.get('filters')),
      url.searchParams.get('sortBy'),
      url.searchParams.get('sortDir'),
    );
    return HttpResponse.json({
      items: rows.slice((page - 1) * pageSize, page * pageSize),
      total: rows.length,
      page,
      pageSize,
    });
  }),

  http.get('/api/v1/data/:resource/export', ({ request, params }) => {
    const url = new URL(request.url);
    const rows = filterRows(
      dataRows[String(params.resource)] ?? [],
      url.searchParams.get('filters'),
    );
    const first = rows[0];
    const headers = first ? Object.keys(first) : [];
    const lines = [
      headers.join(','),
      ...rows.map((row) => headers.map((h) => String(row[h] ?? '')).join(',')),
    ];
    return HttpResponse.text(lines.join('\n'), {
      headers: { 'Content-Type': 'text/csv' },
    });
  }),

  http.post('/api/v1/data/query/structured', async ({ request }) => {
    const body = (await request.json()) as {
      resource?: string;
      fields?: string[];
      conditions?: Array<{ field: string; op: string; value: unknown }>;
      limit?: number;
    };
    const rows = dataRows[body.resource ?? ''] ?? [];
    const filtered = (body.conditions ?? []).reduce<Record<string, unknown>[]>((acc, c) => {
      return acc.filter((row) => {
        const v = row[c.field];
        switch (c.op) {
          case 'eq':
            return v === c.value;
          case 'ne':
            return v !== c.value;
          case 'gt':
            return (v as number) > (c.value as number);
          case 'lt':
            return (v as number) < (c.value as number);
          case 'contains':
            return String(v).includes(String(c.value));
          default:
            return true;
        }
      });
    }, rows);
    const first = rows[0];
    const fields = body.fields && body.fields.length > 0 ? body.fields : first ? Object.keys(first) : [];
    const limited = filtered.slice(0, body.limit ?? 100);
    return HttpResponse.json({
      columns: fields,
      rows: limited.map((row) =>
        Object.fromEntries(fields.map((f) => [f, row[f] ?? null])),
      ),
    });
  }),

  http.post('/api/v1/data/query/sql', async ({ request }) => {
    const body = (await request.json()) as { sql?: string };
    const sql = (body.sql ?? '').trim();
    if (!/^select\b/i.test(sql)) {
      return HttpResponse.json(
        { code: 'FORBIDDEN', title: '只允许 SELECT 查询', status: 403 },
        { status: 403 },
      );
    }
    // mock 简易解析：识别 FROM 表名，命中 dataRows 就返回该资源数据（最多 100 行）
    const match = /from\s+([a-z_]+)/i.exec(sql);
    const resource = match ? (match[1] ?? '') : '';
    const rows = dataRows[resource];
    if (rows) {
      const first = rows[0];
      const columns = first ? Object.keys(first) : [];
      return HttpResponse.json({
        columns,
        rows: rows.slice(0, 100),
      });
    }
    return HttpResponse.json({
      columns: ['sql', 'note'],
      rows: [{ sql, note: '未识别的表，mock 返回占位；真实后端执行白名单 SQL' }],
    });
  }),

  http.get('/api/v1/rebalances', ({ request }) => {
    const url = new URL(request.url);
    const page = Number(url.searchParams.get('page') ?? '1');
    const pageSize = Number(url.searchParams.get('pageSize') ?? '20');
    const job = url.searchParams.get('backtestJob');
    const variant = url.searchParams.get('variant');
    const factor = url.searchParams.get('factor');
    let filtered = rebalances;
    if (job) filtered = filtered.filter((r) => r.backtestJob === job);
    if (variant) filtered = filtered.filter((r) => r.variant === variant);
    if (factor) filtered = filtered.filter((r) => r.factor === factor);
    const items = filtered.slice((page - 1) * pageSize, page * pageSize);
    return HttpResponse.json({ items, total: filtered.length, page, pageSize });
  }),

  http.get('/api/v1/rebalances/:rebalanceId', ({ params }) => {
    const detail = detailById.get(String(params.rebalanceId));
    if (!detail) {
      return HttpResponse.json(
        { code: 'NOT_FOUND', title: '调仓不存在', status: 404 },
        { status: 404 },
      );
    }
    return HttpResponse.json(detail);
  }),

  http.get('/api/v1/rebalances/:rebalanceId/returns', ({ params }) => {
    const rb = rebalances.find((r) => r.rebalanceId === String(params.rebalanceId));
    if (!rb) {
      return HttpResponse.json(
        { code: 'NOT_FOUND', title: '调仓不存在', status: 404 },
        { status: 404 },
      );
    }
    return HttpResponse.json({ series: weekdayPoints(rb.rebalanceDate, rb.netReturn) });
  }),

  http.get('/api/v1/market/series', ({ request }) => {
    const url = new URL(request.url);
    const symbols = url.searchParams.getAll('symbols');
    const startDate = url.searchParams.get('startDate');
    const endDate = url.searchParams.get('endDate');
    const series = symbols.map((symbol) => ({
      symbol,
      points: rangePoints(startDate, endDate),
    }));
    return HttpResponse.json({ baseDate: startDate ?? undefined, series });
  }),
];
