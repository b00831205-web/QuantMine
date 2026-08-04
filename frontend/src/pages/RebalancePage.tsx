import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchRebalances, fetchRebalanceDetail, fetchRebalanceReturns, fetchSeries } from '@/api/client';
import type { AsyncState, Unit } from '@/types/api';
import type { RebalancePage as RebalancePageData, RebalanceDetail } from '@/types/rebalance';
import type {SeriesPoint, SeriesResponse} from '@/types/market'
import { SeriesChart } from '@/components/chart/SeriesChart';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { RebalanceSummary } from '@/types/rebalance';
import { useNavigate } from 'react-router-dom';
import type {Column} from '@/components/common/PaginatedTable'
import i18n from '@/i18n';


const formatReturn = (value: number, unit: Unit): string=> 
    unit ==='percent' ? `${value.toFixed(2)}%` : `${(value * 100).toFixed(2)}%`

const REBALANCE_COLUMNS: Column<RebalanceSummary>[] = [
  { key: 'rebalanceDate', header: '调仓日期', align: 'left', render: (r) => r.rebalanceDate },
  { key: 'netReturn', header: '净收益', align: 'right', render: (r) => formatReturn(r.netReturn, r.unit) },
  { key: 'spyReturn', header: 'SPY', align: 'right', render: (r) => formatReturn(r.spyReturn, r.unit) },
  { key: 'excessReturn', header: '超额', align: 'right', render: (r) => formatReturn(r.excessReturn, r.unit) },
  { key: 'turnover', header: '换手率', align: 'right', render: (r) => `${(r.turnover * 100).toFixed(1)}%` },
  { key: 'holdingsCount', header: '持仓数', align: 'right', render: (r) => String(r.holdingsCount) },
  { key: 'tradingDaysToNext', header: '距下次(天)', align: 'right', render: (r) => String(r.tradingDaysToNext) },
];
export const RebalancePage = () => {
  const [listState, setListState] = useState<AsyncState<RebalancePageData>>({status : 'idle'});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [returnState, setReturnState] = useState<AsyncState<{series : SeriesPoint[]}>>({status: 'idle'});
  const [spyState, setSpyState] = useState<AsyncState<SeriesResponse>>({status: 'idle'})
  const [detailState, setDetailState] = useState<AsyncState<RebalanceDetail>>({status: 'idle'})
  const [backtestJob, setBacktestJob] = useState('');
  const [variant, setVariant] = useState('');
  const [factor, setFactor] = useState('')

  const filterOptions = listState.status ==='success'?{
    backtestJob: Array.from(new Set(listState.data.items.map((r)=> r.backtestJob))),
    variants: Array.from(new Set(listState.data.items.map((r)=>r.variant))),
    factors: Array.from(new Set(listState.data.items.map((r)=>r.factor))),
  }:
  {backtestJob: [], variants: [], factors: []};

  const navigate = useNavigate();
  
  useEffect(()=>{
    if(selectedId === null){
      setDetailState({status: 'idle'});
      return;
    }
    const controller = new AbortController();
    setDetailState({status: 'loading'});
    fetchRebalanceDetail(selectedId, controller.signal)
    .then((data)=>{if(!controller.signal.aborted){
      setDetailState({status: 'success', data})
    }})
    .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (error instanceof HttpError) {
          setDetailState({ status: 'error', error: error.apiError });
          return;
        }
        setDetailState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
  
  });
  return ()=> controller.abort();},[selectedId])

  useEffect(() => {
    const controller = new AbortController();
    setListState({ status: 'loading' });
    fetchRebalances({
      page : 1,
      pageSize: 20,
      ...(backtestJob? {backtestJob}: {}),
      ...(variant? {variant}: {}),
      ...(factor? {factor}: {}),
    },
  controller.signal)
      .then((data) => {
        if(!controller.signal.aborted){
          setListState({
            status: 'success',
            data
          });
          setSelectedId((prev) => prev ?? data.items[0]?.rebalanceId ?? null)
        }
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (error instanceof HttpError) {
          setListState({ status: 'error', error: error.apiError });
          return;
        }
        setListState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });

    return () => controller.abort();
  }, [backtestJob, variant, factor]);

  useEffect(()=>{
    setSelectedId(null);
  }, [backtestJob, variant, factor])

  useEffect(()=>{
    if (selectedId === null){
      setReturnState({status: 'idle'});
      return;
    }
    const controller = new AbortController()
    setReturnState({status: 'loading'});
    fetchRebalanceReturns(selectedId, controller.signal)
    .then((data)=>{if(!controller.signal.aborted){
      setReturnState({status: 'success', data})
    }})
    .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (error instanceof HttpError) {
          setReturnState({ status: 'error', error: error.apiError });
          return;
        }
        setReturnState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
  
  });
  return ()=> controller.abort();},[selectedId])

  useEffect(() => {
    if (returnState.status !== 'success' || returnState.data.series.length === 0) {
      setSpyState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setSpyState({ status: 'loading' });

    const series = returnState.data.series;
    const firstPoint = series[0];
    const lastPoint = series[series.length - 1];
    if (firstPoint === undefined || lastPoint === undefined){
      setSpyState({status: 'idle'});
      return;
    }
    const startDate = firstPoint.date
    const endDate = lastPoint.date
    

    fetchSeries({symbols: ['SPY'], startDate, endDate}, controller.signal)
    .then((data)=> {if(!controller.signal.aborted){setSpyState({status: 'success', data})}})
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        if (error instanceof HttpError) {
          setSpyState({ status: 'error', error: error.apiError });
          return;
        }
        setSpyState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
  
  });

    return () => controller.abort();
  }, [returnState]);

    return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)'}}>
      <PageHeader
        title="调仓收益"
        subtitle="正式策略组合的当前与历史调仓表现"
      />
      <Card title="本期收益曲线">
        <AsyncBoundary
          state={returnState}
          isEmpty={(d) => d.series.length === 0}
          emptyTitle="暂无曲线数据"
          emptyHint="确认 /api/v1/rebalances/{id}/returns 有数据"
        >
          {(data) => {
            const spySeries = spyState.status === 'success' ? spyState.data.series : [];
            return (
              <SeriesChart
                series={[
                  { symbol: '组合', points: data.series },
                  ...spySeries,
                ]}
                height={300}
              />
            );
          }}
        </AsyncBoundary>
      </Card>

      <Card title="筛选条件" minHeight={120}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--sp-4)' }}>
          <label style ={{display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)'}}>
            <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>Backtest Job</span>
            <select
            value = {backtestJob}
            onChange = {(e)=>setBacktestJob(e.target.value)}
            style = {{width:'100%', padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)'}}>
              <option value =''>全部</option>
              {filterOptions.backtestJob.map((v)=>(
                <option key = {v} value = {v}>{v}</option>
              ))}
            </select>
          </label>
          <label style ={{display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)'}}>
            <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>Variant</span>
            <select
            value = {variant}
            onChange = {(e)=>setVariant(e.target.value)}
            style = {{padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)'}}>
              <option value =''>全部</option>
              {filterOptions.variants.map((v)=>(
                <option key = {v} value = {v}>{v}</option>
              ))}
            </select>
          </label>
          <label style ={{display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)'}}>
            <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>Factor</span>
            <select
            value = {factor}
            onChange = {(e)=>setFactor(e.target.value)}
            style = {{padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)'}}>
              <option value =''>全部</option>
              {filterOptions.factors.map((v)=>(
                <option key = {v} value = {v}>{v}</option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 'var(--sp-5)' }}>
        <Card title="调仓列表">
          <AsyncBoundary
            state={listState}
            isEmpty={(data) => data.items.length === 0}
            emptyTitle="暂无调仓数据"
            emptyHint="确认 /api/v1/rebalances 有数据"
          >
            {(data) => (
              <PaginatedTable
                columns={REBALANCE_COLUMNS}
                page={data}
                rowKey={(row) => row.rebalanceId}
                onRowClick={(row) => setSelectedId(row.rebalanceId)}
                onRowDoubleClick={(row) => navigate(`/rebalance/${row.rebalanceId}`)
                  
                }
                selectedRowKey={selectedId ?? undefined}
                emptyHint="暂无调仓记录"
              />
            )}
          </AsyncBoundary>
        </Card>

        <Card title="前 20 只股票收益">
          <AsyncBoundary state={detailState}>
            {(detail) => {
              const quantileBySymbol = new Map(
                detail.holdings.map((h)=> [h.symbol, h.quantile]),
              );
              const top = [...detail.contributions]
                .sort((a, b) => b.contribution - a.contribution)
                .slice(0, 20);
              return (
                <table style = {{width: '100%', fontSize: 'var(--fs-sm)', borderCollapse: 'collapse'}}>
                  <thead>
                    <tr style = {{color: 'var(--text-muted)', textAlign: 'left'}}>
                      <th>#</th>
                      <th>Ticker</th>
                      <th style = {{background: 'var(--bg-surface-2)', textAlign: 'center'  , width: '6em'}}>Quantile</th>
                      <th style = {{textAlign: 'right'}}>return</th>
                      </tr>
                  </thead>
                  <tbody>
                
                  {top.map((c, index) => (
                    <tr key = {c.symbol} style = {{borderBottom: '1px solid var(--border-subtle)'}}>
                      <td style = {{color: 'var(--text-muted)'}}>{index+1}</td>
                      <td>{c.symbol}</td>
                      <td style = {{color: 'var(--text-muted)', background: 'var(--bg-surface-2)',textAlign: 'center'}}>
                        {quantileBySymbol.get(c.symbol)?? '-'}
                      </td>
                      <td style = {{textAlign: 'right',
                        fontWeight: 600,
                        color: c.contribution>=0 ? 'var(--positive)': 'var(--negative)'
                      }}
                      >
                        {formatReturn(c.contribution, detail.unit)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
              );
            }}
          </AsyncBoundary>
        </Card>
      </div>
    </div>
  );
}