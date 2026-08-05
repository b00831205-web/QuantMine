import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchRebalanceDetail } from '@/api/client';
import type { AsyncState } from '@/types/api';
import type { RebalanceDetail } from '@/types/rebalance';
import { PieChart } from '@/components/chart/PieChart';
import i18n from '@/i18n';

export const RebalanceDetailPage = () => {
  const { rebalanceId } = useParams<{ rebalanceId: string }>();
  const navigate = useNavigate();
  const [detailState, setDetailState] = useState<AsyncState<RebalanceDetail>>({status: 'idle'})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(()=>{
    if (rebalanceId === undefined){
      setDetailState({status: 'idle'})
      return;
    }
    const controller = new AbortController()
    setDetailState({status: 'loading'})

    fetchRebalanceDetail(rebalanceId, controller.signal)
    .then ((data)=>{if (!controller.signal.aborted){
      setDetailState({status: 'success', data})
    }})
    .catch((error)=>{
      if (error instanceof DOMException && error.name === 'AbortError'){
        return;
      }
      if (error instanceof HttpError){
        setDetailState({status: 'error', error: error.apiError});
        return;
      }
      setDetailState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          status: 0,
        }
      })
    });
    return ()=>controller.abort();
  }, [rebalanceId])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <button type="button" onClick={() => navigate('/rebalance')}>
        ← 返回
      </button>
      <PageHeader
        title={`调仓详情 ${rebalanceId ?? ''}`}
        subtitle="本期 Q1–Q5 实际持仓"
      />
            <AsyncBoundary state={detailState}>
        {(detail) => {
          const groups = new Map<string, RebalanceDetail['holdings']>();
          for (const h of detail.holdings) {
            const key = h.quantile ?? '其他';
            const list = groups.get(key) ?? [];
            list.push(h);
            groups.set(key, list);
          }
          return (
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--sp-5)' ,alignItems: 'start'}}>
              <Card title="持仓明细">
                {Array.from(groups.entries())
                  .sort((a, b) => a[0].localeCompare(b[0]))
                  .map(([quantile, holdings]) => {
                    const isOpen = expanded[quantile] ?? false;
                    return (
                      <div
                        key={quantile}
                        style={{
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-md)',
                          marginBottom: 'var(--sp-2)',
                        }}
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setExpanded((prev) => ({ ...prev, [quantile]: !prev[quantile] }))
                          }
                          style={{
                            width: '100%',
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: 'var(--sp-2) var(--sp-3)',
                            background: 'transparent',
                            border: 'none',
                            cursor: 'pointer',
                            color: 'var(--text-primary)',
                          }}
                        >
                          <span>{quantile} · {holdings.length} 只</span>
                          <span>{isOpen ? '−' : '+'}</span>
                        </button>
                        {isOpen && (
                          <ul
                            style={{
                              margin: 0,
                              padding: 'var(--sp-2) var(--sp-3)',
                              borderTop: '1px solid var(--border-subtle)',
                            }}
                          >
                            {holdings.map((h) => (
                              <li key={h.symbol}>
                                {h.symbol} · {(h.weight * 100).toFixed(2)}%
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
              </Card>
              <Card title="持股比例">
                <PieChart
                  data = {detail.holdings.map((h)=>({name: h.symbol, value: h.weight}))}
                  height={380}
                  showLegend={false}
                />
                <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', marginTop: 'var(--sp-3)' }}>
                  前 {Math.min(20, detail.holdings.length)} / 共 {detail.holdings.length} 只（完整明细见左侧「持仓明细」）
                </div>
                <table style ={{
                  width: '100%',
                  marginTop: 'var(--sp-2)',
                  fontSize: 'var(--fs-sm)',
                  borderCollapse: 'collapse',
                }}
                >
                  <thead>
                    <tr style = {{color: 'var(--text-muted)', textAlign: 'left'}}>
                      <th>Ticker</th>
                      <th style ={{textAlign: 'right'}}>Percent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.holdings.slice(0, 20).map((h)=>(
                      <tr key={h.symbol} style= {{borderBottom: '1px solid var(--border-subtle)'}}>
                        <td>{h.symbol}</td>
                        <td style={{textAlign: 'right'}}>{(h.weight*100).toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>
          );
        }}
      </AsyncBoundary>
    </div>
)}