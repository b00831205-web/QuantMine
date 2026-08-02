import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { FactorResultRow, FactorResultPage, BacktestSummaryCard, BacktestSummaryPage, ResearchFilterOptions, BacktestSeriesQuery, BacktestSeriesResponse } from '@/types/research';
import type { AsyncState } from '@/types/api';
import styles from './ResearchPage.module.css';
import { useEffect, useState } from 'react';
import { fetchResearchOptions, fetchFactorResults, fetchBacktestSummaries, fetchBacktestSeries } from '@/api/client';
import { HttpError } from '@/api/http';
import { SeriesChart } from '@/components/chart/SeriesChart';




/* ──────────────────────────────────────────────
   状态骨架（类型由用户在学习任务中实现真实请求）
   TODO(USER_LEARNING): 用真实 fetch 替换下面的 useState 空数组。
   数据来源示例：
     GET /api/v1/research/options                          → ResearchRunFilterOptions
     GET /api/v1/research/factors?runId=...                 → TestSummary[]
     GET /api/v1/research/backtest-metrics?runId=...      → BacktestSummary[]
────────────────────────────────────────────── */
type BtState = AsyncState<BacktestSummaryPage>
type TestsState  = AsyncState<FactorResultPage>;
type OptionsState = AsyncState<ResearchFilterOptions>;
type CurveState = AsyncState<BacktestSeriesResponse>;

// TODO(USER_LEARNING)
const EMPTY_TESTS: TestsState   = { status: 'idle' };
const EMPTY_BT: BtState         = { status: 'idle' };
const EMPTY_FACTOR_PAGE : FactorResultPage = {
  items: [],
  total: 0,
  page : 1,
  pageSize: 25
}

/* ─── 全局筛选默认值 ──────────────────────────── */


/* ──────────────────────────────────────────────
   因子 IC 表格列定义
   预留完整列结构；render 骨架供用户填充真实数据展示逻辑
   TODO(USER_LEARNING): 在各列 render 中加入格式化（如 p<0.05 高亮）、
   趋势图标（↑↓）或单元格颜色映射。
────────────────────────────────────────────── */
const formatNumber = (value: number | null, digits : number): string =>
  value === null? '-': value.toFixed(digits);
const TEST_COLUMNS: Array<{
  key: string;
  header: string;
  align?: 'left' | 'center' |'right';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  render: (row: FactorResultRow) => React.ReactNode;
}> = [
  {
    key: 'factor', header: '因子名', align: 'left',
    render: (r) => <span className={styles.factorName}>{r.factorName}</span>,
  },
  {
    key: 'period', header: 'Period', align: 'right',
    render: (r) => String(r.period),  // TODO(USER_LEARNING): 取 r.period
  },
  {
    key: 'icMean', header: 'IC Mean', align: 'right',
    render: (r) => formatNumber(r.icMean, 4),
  },
  {
    key: 'icStd', header: 'IC Std', align: 'right',
    render: (r) => formatNumber(r.icStd, 4),
  },
  {
    key: 'ir', header: 'IR', align: 'right',
    render: (r) => formatNumber(r.ir, 4),
  },
  {
    key: 'tStat', header: 't 值', align: 'right',
    render: (r) => formatNumber(r.tStat, 3),
  },
  {
    key: 'pValue', header: 'p 值', align: 'right',
    render: (r) => formatNumber(r.pValue, 4),
  },
  {
    key: 'bhSignificant', header: 'BH 显著', align: 'center',
    render: (r) => (r.bhSignificant ? '✓' : '—'),
  },
];

/* ──────────────────────────────────────────────
   回测指标卡片中每个 quantile 的列名
   TODO(USER_LEARNING): 列名和 Quantile 数量由后端返回的 quantileReturns keys 决定，
   这里仅为骨架占位，用户需要在 fetch 后动态生成列。
────────────────────────────────────────────── */

/* ──────────────────────────────────────────────
   主组件
────────────────────────────────────────────── */
export const ResearchPage = () => {
  /* ── 全局筛选状态 ── */

  const [variant,     setVariant]     = useState<string>('');
  const [testId,      setTestId]      = useState<string>('');
  const [sampleScope, setSampleScope] = useState<string>('');

  /* ── 因子区状态 ── */
  const [testsState, setTestsState] = useState<TestsState>(EMPTY_TESTS);
  const [selectedFactor, setSelectedFactor] = useState<FactorResultRow | null>(null);
  const [optionsState, setOptionsState] = useState<OptionsState>({status: 'idle'});
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [filterOptionsState, setFilterOptionsState] = useState<OptionsState>({status: 'idle'});

  /* ── 回测区状态 ── */
  const [btState, setBtState] = useState<BtState>(EMPTY_BT);
  const [expandedBacktest, setExpandedBacktest] = useState<BacktestSeriesQuery | null>(null);
  const [curveState, setCurveState] = useState<CurveState>({status: 'idle'})
  /* ── 单击行 → 选中因子 ── */
  const handleRowClick = (row: FactorResultRow): void => {
    setSelectedFactor(row);
  };

  /* ── 双击行 → 跳转因子详情 ── */
  const navigate = useNavigate();
  const handleRowDoubleClick = (row: FactorResultRow): void =>{
    if (activeRunId === null){
      return;
    }
    const search = new URLSearchParams({
      runId: String(activeRunId),
      variant: row.variantName,
      testId: row.testId,
      sampleScope: row.sampleScope,
      period: String(row.period)
    });
    navigate(`/research/factors/${encodeURIComponent(row.factorName)}?${search}`,
  );
  };
  /* ── 选中因子展开区 ──
     实现：
       1. 关键指标（来自当前选中的 FactorResultRow）
       2. 对应回测卡列表（按 factorName 在 btState.items 中过滤）
     留在未来学习的：IC 时序曲线（详情页已实现）、滚动/年度 IC（spec 没要求）。
  ── */
  useEffect(()=>{let cancelled = false;
    
    setOptionsState ({'status': 'loading'});

    fetchResearchOptions().then((data)=>{if (cancelled) return;
      setOptionsState({status: 'success', data});
      setFilterOptionsState({status: 'success', data});
      setActiveRunId(data.defaultRunId);
    }).catch((error)=>{if (cancelled) return;
      if(error instanceof HttpError){setOptionsState({status: 'error', error: error.apiError});
    return;}
      setOptionsState({
        status: 'error',
        error:{
          code: 'NETWORK_ERROR',
          title: '网络请求失败',
          detail: '请确认后端服务正在运行',
          status: 0
        },
      });
  });
  return ()=>{cancelled = true;};},[]);
  
  useEffect(() => {
  if (activeRunId === null) return;

  const controller = new AbortController();

  setVariant('');
  setTestId('');
  setSampleScope('');
  setFilterOptionsState({ status: 'loading' });

  fetchResearchOptions(activeRunId, controller.signal)
    .then((data) => {
      if (controller.signal.aborted) return;
      setFilterOptionsState({ status: 'success', data });
    })
    .catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return;
      }

      if (error instanceof HttpError) {
        setFilterOptionsState({
          status: 'error',
          error: error.apiError,
        });
        return;
      }

      setFilterOptionsState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: '网络请求失败',
          detail: '请确认后端服务正在运行',
          status: 0,
        },
      });
    });

  return () => {
    controller.abort();
  };
}, [activeRunId]);

  useEffect(()=>{if (activeRunId === null){
    setTestsState({
      status: 'success',
      data : EMPTY_FACTOR_PAGE,
    });
    return;
  }
  const controller = new AbortController();
  setTestsState({status : 'loading'});
  setSelectedFactor(null);
  const validSampleScope =
  sampleScope === 'train' || sampleScope === 'test'
    ? sampleScope
    : undefined;
  
    

  fetchFactorResults(
  {
    runId: activeRunId,
    page: 1,
    pageSize: 25,

    ...(variant ? { variant } : {}),
    ...(testId ? { testId } : {}),
    ...(validSampleScope ? { sampleScope: validSampleScope } : {}),
  },
  controller.signal,
).then((data)=> {setTestsState({status : 'success', data});
  }).catch((error)=> {if (error instanceof DOMException && error.name === 'AbortError'){
    return;
  }
  if (error instanceof HttpError){
    setTestsState({status: 'error', error: error.apiError});
    return ;
  }
  setTestsState({
    status: 'error',
    error: {
      code: 'NETWORK_ERROR',
      title: '网络请求失败',
      detail: '请确认后端服务正在运行',
      status:0,
    },
  });
  });
  return () => {
    controller.abort();
  };
  }, [activeRunId, variant, testId, sampleScope]);
  
  useEffect(()=>{
    if (activeRunId === null){
      setBtState({
        status : 'success',
        data : {items: [], total: 0, page: 1, pageSize: 25}
      });
      return ;
    }
    const contorller = new AbortController();
    setBtState({status: 'loading'});
    fetchBacktestSummaries({
      runId: activeRunId,
      page: 1,
      pageSize: 25,
      ...(variant? {variant}: {}),
      ...(testId? {testId}: {}),
    },
  contorller.signal,)
  .then((data)=>{if(!contorller.signal.aborted){setBtState({status: 'success', data});
}
}).catch((error)=>{if(error instanceof DOMException && error.name === 'AbortError'){return;}
if (error instanceof HttpError){setBtState({status: 'error', error: error.apiError}); return;}

setBtState({status: 'error', error:{
  code: 'NETWORK_ERROR',
  title: "网络请求失败",
  detail:'请确认后端服务正在运行',
  status: 0,
},
});
});
return () => contorller.abort();
  },[activeRunId, variant, testId])

  useEffect(()=>{
    setExpandedBacktest(null);
  },[activeRunId, variant, testId])

  useEffect(()=>{
    if(expandedBacktest === null){
      setCurveState({status: 'idle'});
      return;
    }
    const controller = new AbortController();
    setCurveState({status: 'loading'});

    fetchBacktestSeries(expandedBacktest, controller.signal)
    .then((data)=>{if (!controller.signal.aborted){setCurveState({status: 'success', data});
  }
}).catch((error)=>{if(error instanceof DOMException && error.name === 'AbortError'){
  return;
}
if (error instanceof HttpError){
  setCurveState({status: 'error', error: error.apiError});
  return ;
}
setCurveState({
  status: 'error',
  error:{
    code: 'NETWORK_ERROR',
    title: '网络请求失败',
    detail: '请确认后端服务正在运行',
    status: 0
  },
});
});
    return () => controller.abort();},[expandedBacktest]);
 
  const availableRuns = optionsState.status === 'success' ? optionsState.data.runs : [];
  const filterOptions = filterOptionsState.status === 'success' ? filterOptionsState.data : null;

  /* ── 选中因子对应的回测卡（从 btState.items 里过滤） ── */
  const selectedFactorBacktests =
    selectedFactor !== null && btState.status === 'success'
      ? btState.data.items.filter(
          (item) => item.factorName === selectedFactor.factorName,
        )
      : [];

  return (
    <div className={styles.page}>
      {/* 1. 页面标题 */}
      <PageHeader
        title="研究结果"
        subtitle="同一 research run 内的因子与回测结论"
      />

      {/* 2. 顶部全局筛选卡 */}
      <Card title="全局筛选">
        <div className={styles.filterRow}>
          {/* research run 下拉 */}
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>Research Run</span>
            <select
              className={styles.filterSelect}
              value = {activeRunId ?? ''}
              disabled = {optionsState.status === 'loading'}
              // TODO(USER_LEARNING): 绑定后端返回的 runId 列表
              onChange={(e) => {
                // 切换 run 时重置选中因子、重新请求 tests + backtests
                const value = e.target.value;
                setActiveRunId(value === ''? null: Number(value));
                setSelectedFactor(null);
              }}
            >
              <option value="">- 选择 research run -</option>
                {availableRuns.map((run) => (
                  <option key={run.runId} value = {run.runId}>
                    {`Run ${run.runId} · ${run.createdAt}`}
                    </option>
                ))}
              </select>
            </label>
          {/* variant */}
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>Variant</span>
            <select
              className={styles.filterSelect}
              value={variant}
              disabled = {filterOptionsState.status !== 'success'}
              onChange={(e) => setVariant(e.target.value)}
            >
          <option value = ''>全部</option>

          {filterOptions?.variants.map((value) => (<option key ={value} value = {value}>{value}</option>))}
          </select>
          </label>

          {/* test id */}
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>Test ID</span>
            <select
              className={styles.filterSelect}
              value={testId}
              disabled = {filterOptionsState.status !== 'success'}
              onChange={(e) => setTestId(e.target.value)}
            >
          <option value = ''>全部</option>
          {filterOptions?.testIds.map((value)=><option key={value} value={value}>{value}</option>)}
          </select>
          </label>

          {/* sample scope */}
          <label className={styles.filterField}>
            <span className={styles.filterLabel}>Sample Scope</span>
            <select
              className={styles.filterSelect}
              value={sampleScope}
              disabled = {filterOptionsState.status !== 'success'}
              onChange={(e) => setSampleScope(e.target.value)}
            >
          <option value = ''>全部</option>
          {filterOptions?.sampleScopes.map((value)=>(<option key = {value} value={value}>{value}</option>))}
          </select>
          </label>
        </div>
      </Card>

      {/* 3. 因子 IC 与显著性区域（全宽纵向） */}
      <Card
        title="因子 · IC 与显著性"
        extra={
          <span className={styles.cardMeta}>
            {activeRunId!== null
              ? `${activeRunId}`
              : '无选中 run'}
          </span>
        }
      >
        <AsyncBoundary
          state={testsState}
          isEmpty={(data) => data.items.length === 0}
          emptyTitle="该 run 暂无因子测试结果"
          emptyHint={`Run: ${activeRunId}`}
        >
          {(data) => (
            <PaginatedTable
              columns={TEST_COLUMNS}
              page={data}
              rowKey={(row) => `${row.factorName}-${row.period}-${row.testId}`}
              onRowClick={handleRowClick}
              onRowDoubleClick={handleRowDoubleClick}
              selectedRowKey={
                selectedFactor
                  ? `${selectedFactor.factorName}-${selectedFactor.period}-${selectedFactor.testId}`
                  : undefined
              }
              onPageChange={(page) => {
                void page;
                // TODO(USER_LEARNING): 真实分页请求 — 携带 activeRunId + variant/testId/sampleScope 拉取 page=page
              }}
              emptyHint="无匹配因子"
            />
          )}
        </AsyncBoundary>

        {/* 当前选中因子展开区 */}
        {selectedFactor && (
          <FactorExpandSection
            factor={selectedFactor}
            items={selectedFactorBacktests}
            onClose={() => setSelectedFactor(null)}
          />
        )}
      </Card>

      {/* 4. 回测结果区域（全宽纵向，在因子区之后） */}
      <Card
        title="回测 · Q1~Qn 与 Long-Short"
        extra={
          <span className={styles.cardMeta}>
            扣除交易成本口径
          </span>
        }
      >
        <AsyncBoundary
          state={btState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle="该 run 暂无回测结果"
          emptyHint={`Run: ${activeRunId}`}
        >
          {(data) => (
            <BacktestSection 
            items={data.items}
            expandedBacktest = {expandedBacktest}
            curveState={curveState}
            onToggleCurve = {(item)=>{
              const next: BacktestSeriesQuery={
                runId: activeRunId!,
                variant: item.variantName,
                backtestId: item.backtestId,
                testId: item.testId,
                factorName: item.factorName,
                period:item.period,
              };
              setExpandedBacktest((current)=>(
                current?.backtestId === next.backtestId
                && current.factorName === next.factorName
                && current.period === next.period? null : next
              ));
            }} 
            />
          )}
        </AsyncBoundary>
      </Card>
    </div>
  );
}

/* ──────────────────────────────────────────────
   选中因子展开区
   - 顶部摘要：因子名 + 当前行关键指标
   - 对应回测卡列表（从 BacktestSummaryCard[] 中过滤同名因子）
────────────────────────────────────────────── */
const FactorExpandSection = ({
  factor,
  items,
  onClose,
}: {
  factor: FactorResultRow;
  items: BacktestSummaryCard[];
  onClose: () => void;
}) => {
  return (
    <div className={styles.expandSection}>
      <div className={styles.expandHeader}>
        <span className={styles.expandTitle}>
          当前选中因子：<strong>{factor.factorName}</strong>
          <span className={styles.expandMeta}>
            {` · period ${factor.period} · ${factor.variantName} · ${factor.testId} · ${factor.sampleScope}`}
          </span>
        </span>
        <button className={styles.expandClose} onClick={onClose}>
          收起 ×
        </button>
      </div>

      <div className={styles.expandKpiRow}>
        <ExpandKpi label="IC Mean"    value={formatNumber(factor.icMean, 4)} />
        <ExpandKpi label="IC Std"     value={formatNumber(factor.icStd, 4)} />
        <ExpandKpi label="IR"         value={formatNumber(factor.ir, 3)} />
        <ExpandKpi label="t 值"       value={formatNumber(factor.tStat, 3)} />
        <ExpandKpi label="p 值"       value={formatNumber(factor.pValue, 4)} />
        <ExpandKpi label="BH 显著"    value={factor.bhSignificant ? '是' : '否'} />
      </div>

      <div className={styles.expandBtSummary}>
        <div className={styles.expandSubLabel}>
          对应回测卡（{items.length}）
        </div>
        {items.length === 0 ? (
          <div className={styles.expandPlaceholder}>
            当前 run 暂无 {factor.factorName} 的回测卡。
          </div>
        ) : (
          <div className={styles.expandBtList}>
            {items.map((item) => (
              <BtMetricCard
                key={`${item.backtestId}-${item.factorName}-${item.period}`}
                item={item}
                compact
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const ExpandKpi = ({
  label,
  value,
}: {
  label: string;
  value: string;
}) => (
  <div className={styles.expandKpi}>
    <span className={styles.expandKpiLabel}>{label}</span>
    <span className={styles.expandKpiValue}>{value}</span>
  </div>
);

/* ──────────────────────────────────────────────
   回测结果区域
   - 卡片网格 + 展开式净值曲线（spec: expandable-backtest-curves）
────────────────────────────────────────────── */
const BacktestSection = ({ items,
  expandedBacktest, curveState, onToggleCurve }: { 
    items: BacktestSummaryCard[],
    expandedBacktest: BacktestSeriesQuery|null;
    curveState : CurveState; 
    onToggleCurve: (item: BacktestSummaryCard)=>void; }) => {
  if (items.length === 0) {
    return <div className={styles.btEmpty}>暂无回测数据</div>;
  }
  return (
    <div className={styles.btGrid}>
      {/* 指标汇总卡 */}
      <div className={styles.btMetricsRow}>
        {items.map((item) => (
          <BtMetricCard key={`${item.backtestId}-${item.factorName}-${item.period}`} item={item} 
          isExpanded = {
            expandedBacktest?.backtestId === item.backtestId
            && expandedBacktest.factorName === item.factorName
            && expandedBacktest.period === item.period
          }
          onToggleCurve = {()=>onToggleCurve(item)}/>
        ))}
      </div>

      {/* 净值曲线占位 */}
      <div className={styles.btChartArea}>
        {expandedBacktest && (
        <BacktestCurvePanel
    query={expandedBacktest}
    state={curveState}
      />
    )}
      </div>
    </div>
  );
};

const BacktestCurvePanel = ({
  query,
  state,
}: {
  query: BacktestSeriesQuery;
  state: CurveState;
}) => {
  return (
    <div className={styles.btChartArea}>
      <div className={styles.expandSubLabel}>
        {`净值曲线 · ${query.factorName} · ${query.period}天`}
      </div>

      <AsyncBoundary
        state={state}
        isEmpty={(data) => data.series.length === 0}
        emptyTitle="该回测暂无逐日收益数据"
        emptyHint="请先导入对应回测的日收益结果。"
      >
        {(data) => (
          <SeriesChart
            series={data.series}
            baseDate={data.baseDate ?? undefined}
            height={300}
          />
        )}
      </AsyncBoundary>
    </div>
  );
};

/* ──────────────────────────────────────────────
   单次回测指标卡
   TODO(USER_LEARNING): 指标全部来自 BacktestSummary 字段，
   用户可在此添加趋势图标（↑↓）、高亮逻辑、点击跳转详情等。
────────────────────────────────────────────── */
const BtMetricCard = ({
  item,
  isExpanded,
  onToggleCurve,
  compact = false,
}: {
  item: BacktestSummaryCard;
  isExpanded?: boolean;
  onToggleCurve?: () => void;
  compact?: boolean;
}) => {
  return (
    <div className={compact ? styles.btCardCompact : styles.btCard}>
      <div className={styles.btCardHeader}>
        <span className={styles.btFactor}>{item.factorName}</span>
        <span className={styles.btJob}>{item.backtestId}</span>
      </div>

      <div className={styles.btQuantileRow}>
        {Object.entries(item.quantileYearlyReturns).map(([key, value]) => (
          <div key={key} className={styles.btQuantile}>
            <span className={styles.btQuantLabel}>
              {key === 'longShort' ? 'Long-Short' : key}
            </span>
            <span className={styles.btQuantVal}>
              {(value * 100).toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      <div className={styles.btStatGrid}>
        <BtStat label="Sharpe"     value={formatNumber(item.sharpe, 2)} />
        <BtStat label="最大回撤"   value={item.maxDrawdown === null ? '-' : `${(item.maxDrawdown * 100).toFixed(1)}%`} />
        <BtStat label="胜率"       value={item.winRate === null ? '-' : `${(item.winRate * 100).toFixed(1)}%`} />
        <BtStat label="持有期"     value={`${item.period}天`} />
      </div>
      {!compact && onToggleCurve && (
        <button
          type="button"
          className={styles.btCurveButton}
          onClick={onToggleCurve}
        >
          {isExpanded ? '收起净值曲线' : '查看净值曲线'}
        </button>
      )}
    </div>
  );
};

const BtStat = ({ label, value }: { label: string; value: string }) => (
  <div className={styles.btStat}>
    <span className={styles.btStatLabel}>{label}</span>
    <span className={styles.btStatValue}>{value}</span>
  </div>
);
