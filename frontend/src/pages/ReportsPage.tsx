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

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchBacktestSummaries, fetchFactorResults, fetchResearchOptions } from '@/api/client';
import type { AsyncState } from '@/types/api';
import type { ResearchFilterOptions } from '@/types/research';
import type { ReportLang } from '@/types/report';
import {
  buildReportHistoryFileUrl,
  buildReportPdfUrl,
  buildReportXlsxUrl,
} from '@/api/client/report';
import type { ReportQuery } from '@/types/report';
import { fetchReportHistory } from '@/api/client/report';
import type { ReportHistoryItem, ReportHistoryPage } from '@/types/report';
import i18n from '@/i18n';
import { Download, FilePlus2, FileSpreadsheet, Printer, RefreshCcw } from 'lucide-react';
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
    key: 'artifactType',
    header: i18n.t('reports.col.type'),
    align: 'center',
    render: (r) => <span className={styles.monoCell}>{r.artifactType.toUpperCase()}</span>,
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
  const [historyState, setHistoryState] = useState<AsyncState<ReportHistoryPage>>({
    status: 'idle',
  });
  const [historyPage, setHistoryPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [generationError, setGenerationError] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [dataPresence, setDataPresence] = useState<DataPresence>('idle');
  const options = optionsState.status === 'success' ? optionsState.data : null;

  const runId = readRunId(searchParams);
  const testId = readTestId(searchParams);
  const lang = readLang(searchParams);
  const ai = readAi(searchParams);
  const runIdRef = useRef(runId);
  runIdRef.current = runId;

  const selectedReport =
    historyState.status === 'success'
      ? (historyState.data.items.find((report) => report.reportId === selectedReportId) ?? null)
      : null;
  const selectedFileUrl =
    selectedReport?.status === 'ready' &&
    selectedReport.artifactAvailable &&
    selectedReport.artifactType === 'pdf'
      ? buildReportHistoryFileUrl(selectedReport.reportId, true)
      : null;

  const historyReportQuery = (report: ReportHistoryItem): ReportQuery => ({
    runId: report.runId,
    lang: report.lang,
    ai: report.ai,
    ...(report.testId ? { testId: report.testId } : {}),
  });

  const currentQuery: ReportQuery | null =
    runId === null ? null : { runId, lang, ai, ...(testId ? { testId } : {}) };

  const handleGenerate = async (): Promise<void> => {
    if (!currentQuery || dataPresence !== 'hasData' || generating) return;
    setGenerating(true);
    setGenerationError(false);
    try {
      const response = await fetch(buildReportPdfUrl({ ...currentQuery, refresh: true }, true), {
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`report generation returned ${response.status}`);
      await response.arrayBuffer();
      setSelectedReportId(null);
      setHistoryPage(1);
      setRefreshKey((key) => key + 1);
    } catch {
      setGenerationError(true);
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadPdf = (): void => {
    if (selectedReport?.artifactType === 'pdf' && selectedReport.artifactAvailable) {
      window.open(buildReportHistoryFileUrl(selectedReport.reportId), '_blank');
    }
  };

  const handlePrint = (): void => {
    if (selectedReport?.artifactType === 'pdf' && selectedReport.artifactAvailable) {
      window.open(buildReportHistoryFileUrl(selectedReport.reportId, true), '_blank');
    }
  };

  const handleDownloadExcel = (): void => {
    if (!selectedReport?.artifactAvailable) return;
    if (selectedReport.artifactType === 'xlsx') {
      window.open(buildReportHistoryFileUrl(selectedReport.reportId), '_blank');
    } else if (selectedReport.dataAvailable) {
      window.open(buildReportXlsxUrl(historyReportQuery(selectedReport)), '_blank');
    }
  };

  const handleRegenerate = async (): Promise<void> => {
    if (!selectedReport?.dataAvailable || regenerating) return;
    setRegenerating(true);
    try {
      const response = await fetch(
        buildReportPdfUrl(
          {
            ...historyReportQuery(selectedReport),
            // Run/test identify the selected report's source data. Language and
            // AI are live preview controls and must use what the user just chose.
            lang,
            ai,
            refresh: true,
          },
          true,
        ),
        { credentials: 'include' },
      );
      if (!response.ok) throw new Error(`report regeneration returned ${response.status}`);
      await response.arrayBuffer();
      setSelectedReportId(null);
      setHistoryPage(1);
      setRefreshKey((key) => key + 1);
    } catch {
      setPreviewError(true);
    } finally {
      setRegenerating(false);
    }
  };

  const handleHistoryDownload = (report: ReportHistoryItem): void => {
    if (!report.dataAvailable) return;
    window.open(
      buildReportPdfUrl({ ...historyReportQuery(report), refresh: true }, false),
      '_blank',
    );
  };

  useEffect(() => setPreviewError(false), [selectedFileUrl]);

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
      .then((data) => data.total)
      .catch(() => 0);
    const backtestTotal = fetchBacktestSummaries(
      { runId, page: 1, pageSize: 1, ...(testId ? { testId } : {}) },
      controller.signal,
    )
      .then((data) => data.total)
      .catch(() => 0);
    Promise.all([factorTotal, backtestTotal]).then(([factors, backtests]) => {
      if (!controller.signal.aborted) {
        setDataPresence(factors > 0 || backtests > 0 ? 'hasData' : 'noData');
      }
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

  const updateReportSettings = (next: Parameters<typeof updateSearch>[0]): void => {
    setGenerationError(false);
    setPreviewError(false);
    updateSearch(next);
  };

  useEffect(() => {
    const controller = new AbortController();
    setOptionsState({ status: 'loading' });
    fetchResearchOptions(undefined, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setOptionsState({ status: 'success', data });
          if (runIdRef.current === null && data.defaultRunId !== null) {
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
    if (runId === null) {
      setHistoryState({ status: 'idle' });
      setSelectedReportId(null);
      return;
    }
    const controller = new AbortController();
    setHistoryState({ status: 'loading' });
    fetchReportHistory(runId, historyPage, 10, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setHistoryState({ status: 'success', data });
        const nextReport =
          data.items.find(
            (report) =>
              report.status === 'ready' &&
              report.artifactAvailable &&
              report.artifactType === 'pdf',
          ) ?? data.items[0];
        setSelectedReportId(nextReport?.reportId ?? null);
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
  }, [runId, historyPage, refreshKey]);

  useEffect(() => {
    if (runId === null) {
      setOptionsState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
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

  const handleSelectReport = (report: ReportHistoryItem): void => {
    setSelectedReportId(report.reportId);
    setPreviewError(false);
  };

  const historyColumns: Column<ReportHistoryItem>[] = [
    ...HISTORY_COLUMNS,
    {
      key: 'download',
      header: t('reports.col.actions'),
      align: 'right',
      render: (report) => (
        <button
          type="button"
          className={styles.iconBtn}
          disabled={!report.dataAvailable}
          title={
            report.dataAvailable ? t('reports.downloadHistory') : t('reports.historyDataMissing')
          }
          aria-label={`${t('reports.downloadHistory')} ${report.reportId}`}
          onClick={(event) => {
            event.stopPropagation();
            handleHistoryDownload(report);
          }}
        >
          <Download size={13} strokeWidth={1.75} aria-hidden="true" />
        </button>
      ),
    },
  ];

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
              setHistoryPage(1);
              setSelectedReportId(null);
              updateReportSettings({ runId: value === '' ? null : Number(value), testId: null });
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
            onChange={(e) => updateReportSettings({ testId: e.target.value || null })}
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
            onChange={(e) => updateReportSettings({ lang: e.target.value === 'en' ? 'en' : 'zh' })}
          >
            <option value="zh">{t('reports.langZh')}</option>
            <option value="en">{t('reports.langEn')}</option>
          </select>
        </div>
        <button
          id="generate-report-button"
          type="button"
          className={styles.generateBtn}
          disabled={dataPresence !== 'hasData' || generating}
          title={dataPresence === 'noData' ? t('reports.noDataForRun') : undefined}
          onClick={() => void handleGenerate()}
        >
          <FilePlus2 size={14} strokeWidth={1.75} aria-hidden="true" />
          {generating ? t('reports.generatingReport') : t('reports.generateReport')}
        </button>
      </div>

      {/* 报告预览（主证据） */}
      <section className={styles.panel} aria-label={t('reports.previewTitle')}>
        <div className={styles.panelHead}>
          <h2>{t('reports.previewTitle')}</h2>
          <div className={styles.headActions}>
            <button
              id="report-ai-toggle"
              type="button"
              className={ai ? `${styles.aiChip} ${styles.aiChipOn}` : styles.aiChip}
              aria-pressed={ai}
              title={t('reports.aiToggleHint')}
              onClick={() => updateReportSettings({ ai: !ai })}
            >
              <span className={styles.chipDot} aria-hidden="true" />
              {t('reports.aiLabel')}
            </button>
            <button
              id="report-regenerate-button"
              type="button"
              className={styles.iconBtn}
              title={t('reports.forceRefresh')}
              disabled={!selectedReport?.dataAvailable || regenerating}
              onClick={() => void handleRegenerate()}
            >
              <RefreshCcw size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.downloadPdf')}
              disabled={
                !selectedReport ||
                selectedReport.status !== 'ready' ||
                !selectedReport.artifactAvailable ||
                selectedReport.artifactType !== 'pdf'
              }
              onClick={handleDownloadPdf}
            >
              <Download size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.print')}
              disabled={
                !selectedReport ||
                selectedReport.status !== 'ready' ||
                !selectedReport.artifactAvailable ||
                selectedReport.artifactType !== 'pdf'
              }
              onClick={handlePrint}
            >
              <Printer size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              title={t('reports.downloadExcel')}
              disabled={
                !selectedReport ||
                selectedReport.status !== 'ready' ||
                !selectedReport.artifactAvailable ||
                (selectedReport.artifactType !== 'xlsx' && !selectedReport.dataAvailable)
              }
              onClick={handleDownloadExcel}
            >
              <FileSpreadsheet size={13} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
        </div>

        {runId === null ? (
          <div className={styles.emptyPreview}>{t('reports.selectRunFirst')}</div>
        ) : historyState.status === 'loading' ? (
          <div className={styles.emptyPreview} role="status">
            {t('common.loading')}
          </div>
        ) : generationError ? (
          <div className={styles.emptyPreview}>{t('reports.generateFailed')}</div>
        ) : !selectedReport ? (
          <div className={styles.emptyPreview}>{t('reports.noReportsForRun')}</div>
        ) : previewError ? (
          <div className={styles.emptyPreview}>{t('reports.previewLoadFailed')}</div>
        ) : selectedReport.status !== 'ready' || !selectedReport.artifactAvailable ? (
          <div className={styles.emptyPreview}>{t('reports.artifactMissing')}</div>
        ) : selectedReport.artifactType !== 'pdf' ? (
          <div className={styles.emptyPreview}>{t('reports.previewUnsupported')}</div>
        ) : (
          <div className={styles.preview}>
            <iframe
              key={selectedFileUrl}
              src={selectedFileUrl ?? undefined}
              onError={() => setPreviewError(true)}
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
              columns={historyColumns}
              page={data}
              rowKey={(row) => row.reportId}
              onRowClick={handleSelectReport}
              selectedRowKey={selectedReportId ?? undefined}
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
