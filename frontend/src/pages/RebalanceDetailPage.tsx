/**
 * 调仓详情页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：持仓集中度扇面环图是页面唯一的主证据区，分位明细退居次级手风琴栏。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于交互，环图使用单一低饱和蓝阶 + 「其他」中性色。
 * STORY：研究员一眼读到集中度与结构，再按分位展开持仓明细。
 * FIRST VIEWPORT：返回链 + 页头 + 3:2 分栏（左环图面板含图例与前 20 表，右持仓手风琴）。
 * FORM：Evidence Ledger，与市场总览 / 调仓收益 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchRebalanceDetail } from '@/api/client';
import type { AsyncState, Unit } from '@/types/api';
import type { RebalanceDetail } from '@/types/rebalance';
import { PieChart, SEGMENTED_OTHER_COLOR, SEGMENTED_PALETTE } from '@/components/chart/PieChart';
import i18n from '@/i18n';
import styles from './RebalanceDetailPage.module.css';

/** 收益数字统一带正负号，中性文本色 */
const formatReturn = (value: number, unit: Unit): string => {
  const pct = unit === 'percent' ? value : value * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
};

export const RebalanceDetailPage = () => {
  const { t } = useTranslation();
  const { rebalanceId } = useParams<{ rebalanceId: string }>();
  const navigate = useNavigate();
  const [detailState, setDetailState] = useState<AsyncState<RebalanceDetail>>({ status: 'idle' });

  useEffect(() => {
    if (rebalanceId === undefined) {
      setDetailState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setDetailState({ status: 'loading' });
    fetchRebalanceDetail(rebalanceId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setDetailState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setDetailState({ status: 'error', error: error.apiError });
          return;
        }
        setDetailState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            status: 0,
          },
        });
      });
    return () => controller.abort();
  }, [rebalanceId]);

  return (
    <div className={styles.page}>
      <button type="button" className={styles.back} onClick={() => navigate('/rebalance')}>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M7.5 2 3.5 6l4 4" stroke="currentColor" strokeWidth={1.4} />
        </svg>
        {t('rebalanceDetail.back')}
      </button>

      <div className={styles.headerWrap}>
        <PageHeader title={t('rebalanceDetail.title')} subtitle={t('rebalanceDetail.subtitle')} />
      </div>

      <AsyncBoundary state={detailState}>
        {(detail) => {
          if (detail.holdings.length === 0) {
            return <div className={styles.empty}>{t('rebalanceDetail.empty')}</div>;
          }

          const holdings = detail.holdings;
          const othersName = t('rebalanceDetail.othersLabel');
          const contribBySymbol = new Map(
            detail.contributions.map((c) => [c.symbol, c.contribution]),
          );
          const hasContrib = detail.contributions.length > 0;
          const sorted = [...holdings].sort((a, b) => b.weight - a.weight);
          const top10 = sorted.slice(0, 10);
          const top20 = sorted.slice(0, 20);
          const top20Weight = top20.reduce((s, h) => s + h.weight, 0) * 100;
          const restWeight = Math.max(1 - top10.reduce((s, h) => s + h.weight, 0), 0);
          const restCount = Math.max(holdings.length - top10.length, 0);
          const pieData = [
            ...top10.map((h) => ({ name: h.symbol, value: h.weight })),
            { name: othersName, value: restWeight },
          ];
          const pieColors = [...SEGMENTED_PALETTE.slice(0, top10.length), SEGMENTED_OTHER_COLOR];

          const groups = new Map<string, RebalanceDetail['holdings']>();
          for (const h of holdings) {
            const key = h.quantile ?? othersName;
            const list = groups.get(key) ?? [];
            list.push(h);
            groups.set(key, list);
          }
          const sortedGroups = Array.from(groups.entries()).sort((a, b) =>
            a[0].localeCompare(b[0]),
          );

          const renderReturn = (symbol: string) => {
            const contribution = contribBySymbol.get(symbol) ?? null;
            if (!hasContrib) {
              return <span className={styles.mutedCell}>{t('rebalance.notApplicable')}</span>;
            }
            if (contribution === null) return <span className={styles.mutedCell}>—</span>;
            return (
              <span className={styles.numCell}>{formatReturn(contribution, detail.unit)}</span>
            );
          };

          return (
            <div className={styles.split}>
              <section className={styles.panel} aria-label={t('rebalanceDetail.donutTitle')}>
                <div className={styles.panelHead}>
                  <h2>{t('rebalanceDetail.donutTitle')}</h2>
                  <span className={styles.panelMeta}>
                    {t('rebalanceDetail.meta', {
                      date: detail.rebalanceDate,
                      variant: detail.variant,
                      holdingPeriod: detail.holdingPeriod,
                      asOf: detail.asOfDate,
                    })}
                  </span>
                </div>

                <div className={styles.donutRow}>
                  <div className={styles.donutWrap}>
                    <PieChart
                      data={pieData}
                      height={300}
                      showLegend={false}
                      segmented
                      colors={pieColors}
                    />
                    <div className={styles.donutCenter}>
                      <span className={styles.donutMain}>
                        {t('rebalanceDetail.holdingsCount', { count: holdings.length })}
                      </span>
                      <span className={styles.donutSub}>
                        {t('rebalanceDetail.top20Weight', { weight: top20Weight.toFixed(1) })}
                      </span>
                    </div>
                  </div>

                  <div className={styles.legend}>
                    {pieData.map((d, i) => {
                      const isOther = d.name === othersName;
                      return (
                        <div
                          key={d.name}
                          className={
                            isOther
                              ? `${styles.legendItem} ${styles.legendOthers}`
                              : styles.legendItem
                          }
                        >
                          <span
                            className={styles.legendDot}
                            style={{ background: pieColors[i] ?? SEGMENTED_OTHER_COLOR }}
                          />
                          <span className={styles.legendSym}>
                            {isOther ? t('rebalanceDetail.others', { count: restCount }) : d.name}
                          </span>
                          <span className={styles.legendWeight}>{(d.value * 100).toFixed(1)}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className={styles.tableWrap}>
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Ticker</th>
                        <th>{t('rebalanceDetail.col.quantile')}</th>
                        <th className={styles.numHead}>{t('rebalanceDetail.col.weight')}</th>
                        <th className={styles.numHead}>{t('rebalanceDetail.col.return')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top20.map((h, i) => (
                        <tr key={h.symbol}>
                          <td className={styles.rank}>{i + 1}</td>
                          <td className={styles.ticker}>{h.symbol}</td>
                          <td>
                            {h.quantile ? <span className={styles.qBadge}>{h.quantile}</span> : '-'}
                          </td>
                          <td className={i < 3 ? `${styles.num} ${styles.strong}` : styles.num}>
                            {(h.weight * 100).toFixed(2)}%
                          </td>
                          <td>{renderReturn(h.symbol)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className={styles.panelNote}>
                  {t('rebalanceDetail.panelNote', {
                    shown: top20.length,
                    total: holdings.length,
                  })}
                </p>
              </section>

              <aside className={styles.accordion} aria-label={t('rebalanceDetail.holdingsTitle')}>
                <div className={styles.accordionHead}>
                  <h2>{t('rebalanceDetail.holdingsTitle')}</h2>
                  <span className={styles.accordionHint}>{t('rebalanceDetail.byQuantile')}</span>
                </div>

                {sortedGroups.map(([quantile, list], idx) => {
                  const groupWeight = list.reduce((s, h) => s + h.weight, 0) * 100;
                  const rows = [...list].sort((a, b) => b.weight - a.weight);
                  return (
                    <details key={quantile} className={styles.group} open={idx === 0}>
                      <summary>
                        <span className={styles.groupLeft}>
                          {quantile}
                          <span className={styles.groupMeta}>
                            {t('rebalanceDetail.groupMeta', {
                              count: rows.length,
                              weight: groupWeight.toFixed(1),
                            })}
                          </span>
                        </span>
                        <span className={styles.chevron}>
                          <svg
                            width="12"
                            height="12"
                            viewBox="0 0 12 12"
                            fill="none"
                            aria-hidden="true"
                          >
                            <path d="m3 4.5 3 3 3-3" stroke="currentColor" strokeWidth={1.4} />
                          </svg>
                        </span>
                      </summary>
                      <div className={styles.groupBody}>
                        <table>
                          <thead>
                            <tr>
                              <th>Ticker</th>
                              <th className={styles.numHead}>{t('rebalanceDetail.col.weight')}</th>
                              <th className={styles.numHead}>{t('rebalanceDetail.col.return')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rows.map((h) => (
                              <tr key={h.symbol}>
                                <td className={styles.ticker}>{h.symbol}</td>
                                <td className={styles.num}>{(h.weight * 100).toFixed(2)}%</td>
                                <td>{renderReturn(h.symbol)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  );
                })}

                <p className={styles.accordionNote}>{t('rebalanceDetail.accordionNote')}</p>
              </aside>
            </div>
          );
        }}
      </AsyncBoundary>

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};
