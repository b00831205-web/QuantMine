/**
 * 报告下载页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：报告预览是页面唯一的主证据区；设置退居一条工具条，导出与历史
 *         动作环绕预览而非各自成卡。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于选中/焦点/主要动作；预览本身是浅色纸张，让报告成为
 *         视觉中心。
 * STORY：研究员选定 run/test/语言，看报告渲染，下载或打印，再扫生成历史。
 * FIRST VIEWPORT：页头 + 设置工具条 + 单块预览面板（头带 AI 开关与导出
 *         动作 + 纸张预览），历史表在首屏之下。
 * FORM：Evidence Ledger，与市场 / 调仓 / 研究结果 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchResearchOptions, fetchFactorResults, fetchBacktestSummaries } from '@/api/client';
import type { AsyncState } from '@/types/api';
import type { ResearchFilterOptions } from '@/types/research';
import type { ReportLang } from '@/types/report';
import { buildReportPdfUrl, buildReportXlsxUrl } from '@/api/client/report';
import type { ReportQuery } from '@/types/report';
import { fetchReportHistory } from '@/api/client/report';
import type { ReportHistoryItem, ReportHistoryPage } from '@/types/report';
import i18n from '@/i18n';
import { Download, FileSpreadsheet, Printer, RefreshCcw } from 'lucide-react';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { Column } from '@/components/common/PaginatedTable';
import styles from './ReportsPage.module.css';

const HISTORY_COLUMNS: Column<ReportHistoryItem>[] = [
  {
    key: 'reportId',
    header: i18n.t('reports.col.id'),
    align: 'left',
    render: (r) => <span className={styles.idCell}>{r.reportId}</span>,
  },
  {
    key: 'runId',
    header: i18n.t('reports.col.run'),
    align: 'center',
    render: (r) => <span className={styles.monoCell}>{String(r.runId)}</span>,
  },
  {
    key: 'testId',
    header: i18n.t('reports.col.testId'),
    align: 'left',
    render: (r) => <span className={styles.monoCell}>{r.testId ?? i18n.t('common.all')}</span>,
  },
  {
    key: 'lang',
    header: i18n.t('reports.col.lang'),
    align: 'center',
    render: (r) => <span className={styles.monoCell}>{r.lang.toUpperCase()}</span>,
  },
  {
    key: 'ai',
    header: 'AI',
    align: 'center',
    render: (r) => (
      <span className={styles.monoCell}>{r.ai ? i18n.t('reports.on') : i18n.t('reports.off')}</span>
    ),
  },
  {
    key: 'createdAt',
    header: i18n.t('reports.col.createdAt'),
    align: 'left',
    render: (r) => <span className={styles.monoCell}>{r.createdAt}</span>,
  },
  {
    key: 'status',
    header: i18n.t('reports.col.status'),
    align: 'left',
    render: (r) =>
      r.status === 'ready' ? (
        <span className={`${styles.status} ${styles.statusReady}`}>
          <span className={styles.statusDot} aria-hidden="true" />
          {i18n.t('reports.ready')}
        </span>
      ) : (
        <span className={`${styles.status} ${styles.statusFailed}`}>
          <span className={styles.statusDot} aria-hidden="true" />
          {i18n.t('reports.failed')}
        </span>
      ),
  },
];

const readRunId = (sp: URLSearchParams): number | null => {
  const v = sp.get('runId');
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
};

const readTestId = (sp: URLSearchParams): string | null => sp.get('testId') ?? null;

const readLang = (sp: URLSearchParams): ReportLang => (sp.get('lang') === 'en' ? 'en' : 'zh');

const readAi = (sp: URLSearchParams): boolean => sp.get('ai') === 'true';

type DataPresence = 'idle' | 'checking' | 'hasData' | 'noData';

export const ReportsPage = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [optionsState, setOptionsState] = useState<AsyncState<ResearchFilterOptions>>({
    status: 'idle',
  });
  const [pdfLoaded, setPdfLoaded] = useState(false);
  const [historyState, setHistoryState] = useState<AsyncState<ReportHistoryPage>>({
    status: 'idle',
  });
  const [historyPage, setHistoryPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [forceRefresh, setForceRefresh] = useState(0);
  const [dataPresence, setDataPresence] = useState<DataPresence>('idle');
  const options = optionsState.status === 'success' ? optionsState.data : null;

  const runId = readRunId(searchParams);
  const testId = readTestId(searchParams);
  const lang = readLang(searchParams);
  const ai = readAi(searchParams);

  const buildQuery = (): ReportQuery | null =>
    runId === null ? null : { runId, lang, ai, ...(testId ? { testId } : {}) };

  const handleDownloadPdf = (): void => {
    const q = buildQuery();
    if (q) window.open(buildReportPdfUrl(q, false), '_blank');
  };

  const handlePrint = (): void => {
    const q = buildQuery();
    if (q) window.open(buildReportPdfUrl(q, true), '_blank');
  };

  const handleDownloadExcel = (): void => {
    const q = buildQuery();
    if (q) window.open(buildReportXlsxUrl(q), '_blank');
  };

  const pdfUrl =
    runId === null
      ? null
      : buildReportPdfUrl(
          { runId, lang, ai, refresh: forceRefresh > 0, ...(testId ? { testId } : {}) },
          true,
        ) + (forceRefresh > 0 ? `&t=${forceRefresh}` : '');

  useEffect(() => {
    setPdfLoaded(false);
  }, [pdfUrl]);

  /* 运行数据存在性检查：IC 与回测都为空时不生成报告 */
  useEffect(() => {
    if (runId === null) {
      setDataPresence('idle');
      return;
    }
    const controller = new AbortController();
    setDataPresence('checking');
    const factorTotal = fetchFactorResults(
      { runId, page: 1, pageSize: 1, ...(testId ? { testId } : {}) },
      controller.signal,
    )
      .then((d) => d.total)
      .catch(() => 0);
    const btTotal = fetchBacktestSummaries(
      { runId, page: 1, pageSize: 1, ...(testId ? { testId } : {}) },
      controller.signal,
    )
      .then((d) => d.total)
      .catch(() => 0);
    Promise.all([factorTotal, btTotal]).then(([factors, backtests]) => {
      if (controller.signal.aborted) return;
      setDataPresence(factors > 0 || backtests > 0 ? 'hasData' : 'noData');
    });
    return () => controller.abort();
  }, [runId, testId]);

  const updateSearch = (
    next: Partial<{
      runId: number | null;
      testId: string | null;
      lang: ReportLang | null;
      ai: boolean | null;
    }>,
  ): void => {
    const params = new URLSearchParams(searchParams);
    (Object.entries(next) as Array<[string, number | string | boolean | null]>).forEach(
      ([key, value]) => {
        if (value === null || value === '') {
          params.delete(key);
        } else {
          params.set(key, String(value));
        }
      },
    );
    setSearchParams(params, { replace: true });
  };

  useEffect(() => {
    const controller = new AbortController();
    setOptionsState({ status: 'loading' });
    fetchResearchOptions(undefined, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setOptionsState({ status: 'success', data });
          if (runId === null && data.defaultRunId) {
            updateSearch({ runId: data.defaultRunId });
          }
        }
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setOptionsState({ status: 'error', error: error.apiError });
          return;
        }
        setOptionsState({
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setHistoryState({ status: 'loading' });
    fetchReportHistory(historyPage, 10, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setHistoryState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setHistoryState({ status: 'error', error: error.apiError });
          return;
        }
        setHistoryState({
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
  }, [historyPage, refreshKey]);

  useEffect(() => {
    if (runId === null) {
      setOptionsState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setOptionsState({ status: 'loading' });
    fetchResearchOptions(runId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setOptionsState({ status: 'success', data });
          if (testId !== null && !data.testIds.includes(testId)) {
            updateSearch({ testId: null });
          }
        }
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setOptionsState({ status: 'error', error: error.apiError });
          return;
        }
        setOptionsState({
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  /* 高亮与当前预览上下文匹配的历史行 */
  const historySelectedKey =
    runId === null || historyState.status !== 'success'
      ? undefined
      : historyState.data.items.find(
          (r) =>
            r.runId === runId && (r.testId ?? null) === testId && r.lang === lang && r.ai === ai,
        )?.reportId;

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader
          title={t('reports.title')}
          subtitle={t('reports.subtitle')}
          actions={
            <span className={styles.headerMeta}>
              {t('reports.headerSummary', {
                runId: runId ?? '-',
                lang: lang.toUpperCase(),
                aiState: ai ? t('reports.on') : t('reports.off'),
              })}
            </span>
          }
        />
      </div>

      {/* 报告设置工具条 */}
      <div className={styles.toolbar} role="group" aria-label={t('reports.settingsTitle')}>
        <div className={`${styles.filter} ${styles.filterRun}`}>
          <label htmlFor="report-run">{t('research.filter.researchRun')}</label>
          <select
            id="report-run"
            value={runId === null ? '' : String(runId)}
            onChange={(e) => {
              const value = e.target.value;
              updateSearch({ runId: value === '' ? null : Number(value), testId: null });
            }}
          >
            <option value="">{t('reports.selectRun')}</option>
            {options?.runs.map((r) => (
              <option key={r.runId} value={String(r.runId)}>
                {`Run ${r.runId} · ${r.createdAt}`}
              </option>
            ))}
          </select>
        </div>
        <div className={`${styles.filter} ${styles.filterTest}`}>
          <label htmlFor="report-test">{t('research.filter.testId')}</label>
          <select
            id="report-test"
            value={testId ?? ''}
            onChange={(e) => updateSearch({ testId: e.target.value || null })}
          >
            <option value="">{t('common.all')}</option>
            {options?.testIds.map((tid) => (
              <option key={tid} value={tid}>
                {tid}
              </option>
            ))}
          </select>
        </div>
        <div className={`${styles.filter} ${styles.filterLang}`}>
          <label htmlFor="report-lang">{t('reports.col.lang')}</label>
          <select
            id="report-lang"
            value={lang}
            onChange={(e) => updateSearch({ lang: e.target.value === 'en' ? 'en' : 'zh' })}
          >
            <option value="zh">{t('reports.langZh')}</option>
            <option value="en">{t('reports.langEn')}</option>
          </select>
        </div>
      </div>

      {/* 报告预览（主证据） */}
      <section className={styles.panel} aria-label={t('reports.previewTitle')}>
        <div className={styles.panelHead}>
          <h2>{t('reports.previewTitle')}</h2>
          <div className={styles.headActions}>
            <button
              type="button"
              className={ai ? `${styles.aiChip} ${styles.aiChipOn}` : styles.aiChip}
              aria-pressed={ai}
              onClick={() => updateSearch({ ai: !ai })}
            >
              <span className={styles.chipDot} aria-hidden="true" />
              {t('reports.aiLabel')}
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.forceRefresh')}
              disabled={runId === null || dataPresence !== 'hasData'}
              onClick={() => setForceRefresh((k) => k + 1)}
            >
              <RefreshCcw size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.downloadPdf')}
              disabled={runId === null || dataPresence !== 'hasData'}
              onClick={handleDownloadPdf}
            >
              <Download size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.print')}
              disabled={runId === null || dataPresence !== 'hasData'}
              onClick={handlePrint}
            >
              <Printer size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.downloadExcel')}
              disabled={runId === null || dataPresence !== 'hasData'}
              onClick={handleDownloadExcel}
            >
              <FileSpreadsheet size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
        </div>

        {runId === null ? (
          <div className={styles.emptyPreview}>{t('reports.selectRunFirst')}</div>
        ) : dataPresence === 'checking' ? (
          <div className={styles.emptyPreview} role="status">
            {t('reports.checking')}
          </div>
        ) : dataPresence === 'noData' ? (
          <div className={styles.emptyPreview}>{t('reports.noDataForRun')}</div>
        ) : (
          <div className={styles.preview}>
            {!pdfLoaded ? (
              <div className={styles.previewLoading} role="status">
                {t('reports.generating')}
              </div>
            ) : null}
            <iframe
              key={pdfUrl}
              src={pdfUrl ?? undefined}
              onLoad={() => setPdfLoaded(true)}
              title={t('reports.previewTitle')}
              className={styles.previewFrame}
            />
          </div>
        )}
      </section>

      {/* 报告历史 */}
      <section className={styles.panel} aria-label={t('reports.historyTitle')}>
        <div className={styles.panelHead}>
          <h2>{t('reports.historyTitle')}</h2>
          <div className={styles.headActions}>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.refresh')}
              disabled={historyState.status === 'loading'}
              onClick={() => setRefreshKey((k) => k + 1)}
            >
              <RefreshCcw size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
        </div>
        <AsyncBoundary
          state={historyState}
          isEmpty={(d) => d.items.length === 0}
          emptyTitle={t('reports.noHistory')}
          emptyHint={t('reports.historyHint')}
        >
          {(data) => (
            <PaginatedTable
              columns={HISTORY_COLUMNS}
              page={data}
              rowKey={(row) => row.reportId}
              onRowClick={(row) =>
                updateSearch({
                  runId: row.runId,
                  testId: row.testId ?? null,
                  lang: row.lang,
                  ai: row.ai,
                })
              }
              selectedRowKey={historySelectedKey}
              onPageChange={setHistoryPage}
              emptyHint={t('reports.noHistory')}
            />
          )}
        </AsyncBoundary>
      </section>

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};
