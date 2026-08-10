/**
 * 数据库速查页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：结果表是页面唯一的主证据区；资源、筛选与字段参考退居一条工具条
 *         与一条安静的参考带，查询模式共用同一套表格语言。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于选中/焦点/主要动作；机器值一律等宽数字。
 * STORY：研究员选资源、筛行、扫读密集结果表、导出 CSV，再切到 Query
 *         构建结构化条件或执行 SELECT。
 * FIRST VIEWPORT：页头 + 浏览/查询分段 tab + 工具条 + 单块结果面板 +
 *         字段参考带。
 * FORM：Evidence Ledger，与市场 / 调仓 / 研究结果 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchDataCatalog, fetchDataPage, buildDataExportUrl } from '@/api/client';
import { fetchStructuredQuery, fetchSqlQuery } from '@/api/client';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { Column } from '@/components/common/PaginatedTable';
import type { AsyncState } from '@/types/api';
import type { Catalog, DataResource, DataPage } from '@/types/data';
import type { QueryResult, StructuredCondition } from '@/types/data';
import { QueryResultTable } from '@/components/common/QueryResultTable';
import i18n from '@/i18n';
import CodeMirror from '@uiw/react-codemirror';
import { sql } from '@codemirror/lang-sql';
import { EditorView } from '@codemirror/view';
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { tags } from '@lezer/highlight';
import styles from './DataExplorerPage.module.css';

/** SQL 终端编辑器：透明底、等宽字体、钴蓝光标 */
const sqlTerminalTheme = EditorView.theme(
  {
    '&': {
      backgroundColor: 'transparent',
      color: 'var(--text-primary)',
      fontSize: 'var(--fs-sm)',
      height: 'auto',
    },
    '.cm-scroller': {
      fontFamily: 'var(--font-mono)',
      lineHeight: '1.6',
    },
    '.cm-content': {
      caretColor: 'var(--accent)',
      minHeight: '110px',
      padding: '0',
    },
    '.cm-line': {
      padding: '0',
    },
    '.cm-cursor': {
      borderLeftColor: 'var(--accent)',
    },
    '&.cm-focused': {
      outline: 'none',
    },
    '.cm-placeholder': {
      color: 'var(--text-muted)',
    },
  },
  { dark: true },
);

/** SQL 语法糖配色：关键字/函数钴蓝系，字符串薄荷，数字琥珀，注释静默 */
const sqlHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: '#56b6ff', fontWeight: '600' },
  { tag: tags.operator, color: '#9aa3b8' },
  { tag: tags.string, color: '#4ec98a' },
  { tag: tags.number, color: '#f0b35e' },
  { tag: tags.comment, color: '#6b7388', fontStyle: 'italic' },
  { tag: tags.punctuation, color: '#6b7388' },
  { tag: tags.function(tags.variableName), color: '#6ea0ff' },
  { tag: tags.typeName, color: '#6ea0ff' },
  { tag: tags.bool, color: '#f0b35e' },
  { tag: tags.null, color: '#f0b35e' },
]);

const sqlExtensions = [sql(), syntaxHighlighting(sqlHighlightStyle), sqlTerminalTheme];

const CONDITION_OPS: Array<{ value: StructuredCondition['op']; label: string }> = [
  { value: 'eq', label: '=' },
  { value: 'ne', label: '≠' },
  { value: 'gt', label: '>' },
  { value: 'lt', label: '<' },
];

export const DataExplorerPage = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<'browse' | 'query'>('browse');
  const [queryMode, setQueryMode] = useState<'structured' | 'sql'>('structured');
  const [sqlText, setSqlText] = useState('');
  const [sqlResultState, setSqlResultState] = useState<AsyncState<QueryResult>>({ status: 'idle' });
  const [catalogState, setCatalogState] = useState<AsyncState<Catalog[]>>({ status: 'idle' });
  const [pageState, setPageState] = useState<AsyncState<DataPage>>({ status: 'idle' });
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [appliedFilters, setAppliedFilters] = useState<Record<string, string>>({});
  const [queryResource, setQueryResource] = useState<DataResource | null>(null);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [conditions, setConditions] = useState<StructuredCondition[]>([]);
  const [queryResultState, setQueryResultState] = useState<AsyncState<QueryResult>>({
    status: 'idle',
  });

  const resourceParam = searchParams.get('resource');
  const catalog = useMemo(
    () => (catalogState.status === 'success' ? catalogState.data : []),
    [catalogState],
  );
  const resource =
    catalog.find((c) => c.resource === resourceParam)?.resource ?? catalog[0]?.resource ?? null;

  const setResource = (r: DataResource): void => {
    const params = new URLSearchParams(searchParams);
    params.set('resource', r);
    setSearchParams(params, { replace: true });
    setPage(1);
    setFilters({});
    setAppliedFilters({});
  };

  const updateCondition = (index: number, patch: Partial<StructuredCondition>): void => {
    setConditions((prev) => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };

  const runStructuredQuery = (): void => {
    if (queryResource === null) return;
    setQueryResultState({ status: 'loading' });
    fetchStructuredQuery({
      resource: queryResource,
      fields: selectedFields,
      conditions: conditions
        .filter((c) => c.field !== '' && c.value !== '')
        .map((c) => ({
          ...c,
          value: Number.isNaN(Number(c.value)) ? c.value : Number(c.value),
        })),
      limit: 100,
    })
      .then((data) => {
        setQueryResultState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setQueryResultState({ status: 'error', error: error.apiError });
          return;
        }
        setQueryResultState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
  };

  const runSqlQuery = (): void => {
    if (sqlText.trim() === '') return;
    setSqlResultState({ status: 'loading' });
    fetchSqlQuery(sqlText)
      .then((data) => {
        setSqlResultState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setSqlResultState({ status: 'error', error: error.apiError });
          return;
        }
        setSqlResultState({
          status: 'error',
          error: {
            code: 'NETWORK_ERROR',
            title: i18n.t('common.networkError.title'),
            detail: i18n.t('common.networkError.detail'),
            status: 0,
          },
        });
      });
  };

  useEffect(() => {
    if (catalog.length === 0) return;
    const valid = catalog.some((c) => c.resource === resourceParam);
    const first = catalog[0];
    if (!valid && first) {
      const params = new URLSearchParams(searchParams);
      params.set('resource', first.resource);
      setSearchParams(params, { replace: true });
    }
  }, [catalog, resourceParam, searchParams, setSearchParams]);

  useEffect(() => {
    if (queryResource === null && catalog.length > 0) {
      setQueryResource(catalog[0]?.resource ?? null);
    }
  }, [catalog, queryResource]);

  const queryCatalog = catalog.find((c) => c.resource === queryResource) ?? null;

  useEffect(() => {
    const controller = new AbortController();
    setCatalogState({ status: 'loading' });
    fetchDataCatalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setCatalogState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setCatalogState({ status: 'error', error: error.apiError });
          return;
        }
        setCatalogState({
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
  }, []);

  useEffect(() => {
    if (resource === null) {
      setPageState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setPageState({ status: 'loading' });
    fetchDataPage(
      {
        resource,
        page,
        pageSize: 10,
        ...(Object.keys(appliedFilters).length > 0 ? { filters: appliedFilters } : {}),
      },
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setPageState({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setPageState({ status: 'error', error: error.apiError });
          return;
        }
        setPageState({
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
  }, [resource, page, appliedFilters]);

  const current = resource !== null ? (catalog.find((c) => c.resource === resource) ?? null) : null;

  const columns: Column<Record<string, unknown>>[] = current
    ? current.fields.map((f) => ({
        key: f.name,
        header: f.name,
        align: f.type === 'number' ? 'right' : 'left',
        render: (row: Record<string, unknown>) => String(row[f.name] ?? ''),
      }))
    : [];

  const browseCount =
    pageState.status === 'success'
      ? t('common.pagination', {
          total: pageState.data.total,
          page: pageState.data.page,
          pages: Math.max(1, Math.ceil(pageState.data.total / pageState.data.pageSize)),
        })
      : '';

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader title={t('nav.data')} subtitle={t('data.subtitle')} />
      </div>

      <div className={styles.tabs} role="tablist" aria-label={t('data.tabTitle')}>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'browse'}
          className={tab === 'browse' ? styles.tabActive : styles.tab}
          onClick={() => setTab('browse')}
        >
          {t('data.tab.browse')}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'query'}
          className={tab === 'query' ? styles.tabActive : styles.tab}
          onClick={() => setTab('query')}
        >
          {t('data.tab.query')}
        </button>
      </div>

      {tab === 'browse' ? (
        <>
          <div className={styles.toolbar}>
            <div className={styles.filterResource}>
              <label htmlFor="browse-resource">{t('data.resource')}</label>
              <select
                id="browse-resource"
                value={resource ?? ''}
                onChange={(e) => setResource(e.target.value as DataResource)}
              >
                {catalog.map((c) => (
                  <option key={c.resource} value={c.resource}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            {current?.fields
              .filter((f) => f.filterable)
              .map((f) => (
                <div className={styles.filterCond} key={f.name}>
                  <label htmlFor={`filter-${f.name}`}>{f.name}</label>
                  <input
                    id={`filter-${f.name}`}
                    type="text"
                    value={filters[f.name] ?? ''}
                    onChange={(e) => setFilters((prev) => ({ ...prev, [f.name]: e.target.value }))}
                  />
                </div>
              ))}
            <button
              type="button"
              className={styles.applyBtn}
              onClick={() => {
                setAppliedFilters(filters);
                setPage(1);
              }}
            >
              {t('data.apply')}
            </button>
            <div className={styles.toolbarSpacer} />
            <span className={styles.count}>{browseCount}</span>
            {resource !== null ? (
              <a
                className={styles.exportLink}
                href={buildDataExportUrl({
                  resource,
                  ...(Object.keys(appliedFilters).length > 0 ? { filters: appliedFilters } : {}),
                })}
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path
                    d="M6 1.5v6m0 0 2.5-2.5M6 7.5 3.5 5M2 10.5h8"
                    stroke="currentColor"
                    strokeWidth={1.3}
                  />
                </svg>
                {t('data.exportCsv')}
              </a>
            ) : null}
          </div>

          <section className={styles.panel} aria-label={t('data.resultTitle')}>
            <div className={styles.panelHead}>
              <h2>{t('data.resultTitle')}</h2>
              <span className={styles.panelMeta}>{resource ?? '-'}</span>
            </div>
            <AsyncBoundary
              state={pageState}
              isEmpty={(d) => d.items.length === 0}
              emptyTitle={t('common.noData')}
              emptyHint={t('data.adjustFilterOrResource')}
            >
              {(data) => (
                <PaginatedTable
                  columns={columns}
                  page={data}
                  rowKey={(row) => JSON.stringify(row)}
                  onPageChange={setPage}
                  emptyHint={t('common.noData')}
                />
              )}
            </AsyncBoundary>
          </section>

          <section className={styles.ref} aria-label={t('data.fieldsTitle')}>
            <div className={styles.refTitle}>
              {t('data.fieldsTitle')} · {resource ?? '-'}
            </div>
            <div className={styles.refGrid}>
              {current?.fields.map((f) => (
                <div className={styles.refItem} key={f.name}>
                  <div className={styles.refRow1}>
                    <span className={styles.refName}>{f.name}</span>
                    <span className={styles.refType}>{f.type}</span>
                    {f.filterable ? (
                      <span className={styles.refTag}>{t('data.filterable')}</span>
                    ) : null}
                  </div>
                  {f.description ? <div className={styles.refDesc}>{f.description}</div> : null}
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <>
          <div className={styles.modeTabs} role="tablist" aria-label={t('data.queryMode')}>
            <button
              type="button"
              role="tab"
              aria-selected={queryMode === 'structured'}
              className={queryMode === 'structured' ? styles.tabActive : styles.tab}
              onClick={() => setQueryMode('structured')}
            >
              {t('data.mode.structured')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={queryMode === 'sql'}
              className={queryMode === 'sql' ? styles.tabActive : styles.tab}
              onClick={() => setQueryMode('sql')}
            >
              {t('data.mode.sql')}
            </button>
          </div>

          <section className={styles.panel} aria-label={t('data.tab.query')}>
            <div className={styles.panelHead}>
              <h2>{t('data.tab.query')}</h2>
              <span className={styles.panelMeta}>{t('data.limitHint', { limit: 100 })}</span>
            </div>

            {queryMode === 'structured' ? (
              <div className={styles.queryForm}>
                <div className={styles.qBlock}>
                  <div className={styles.filterResource}>
                    <label htmlFor="query-resource">{t('data.resource')}</label>
                    <select
                      id="query-resource"
                      value={queryResource ?? ''}
                      onChange={(e) => setQueryResource(e.target.value as DataResource)}
                    >
                      {catalog.map((c) => (
                        <option key={c.resource} value={c.resource}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className={styles.qBlock}>
                  <span className={styles.qLabel}>{t('data.fieldsHint')}</span>
                  <div className={styles.fieldChips}>
                    {queryCatalog?.fields.map((f) => {
                      const checked = selectedFields.includes(f.name);
                      return (
                        <button
                          key={f.name}
                          type="button"
                          className={checked ? `${styles.chip} ${styles.chipOn}` : styles.chip}
                          aria-pressed={checked}
                          onClick={() =>
                            setSelectedFields((prev) =>
                              checked ? prev.filter((n) => n !== f.name) : [...prev, f.name],
                            )
                          }
                        >
                          {f.name}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className={styles.qBlock}>
                  <span className={styles.qLabel}>{t('data.conditions')}</span>
                  <div className={styles.conditionList}>
                    {conditions.map((c, i) => (
                      <div key={i} className={styles.conditionRow}>
                        <select
                          className={styles.condField}
                          value={c.field}
                          onChange={(e) => updateCondition(i, { field: e.target.value })}
                        >
                          {queryCatalog?.fields.map((f) => (
                            <option key={f.name} value={f.name}>
                              {f.name}
                            </option>
                          ))}
                        </select>
                        <select
                          className={styles.condOp}
                          value={c.op}
                          onChange={(e) =>
                            updateCondition(i, { op: e.target.value as StructuredCondition['op'] })
                          }
                        >
                          {CONDITION_OPS.map((op) => (
                            <option key={op.value} value={op.value}>
                              {op.label}
                            </option>
                          ))}
                          <option value="contains">{t('data.op.contains')}</option>
                        </select>
                        <input
                          className={styles.condValue}
                          value={c.value}
                          onChange={(e) => updateCondition(i, { value: e.target.value })}
                        />
                        <button
                          type="button"
                          className={styles.delBtn}
                          aria-label={t('data.delete')}
                          onClick={() =>
                            setConditions((prev) => prev.filter((_, idx) => idx !== i))
                          }
                        >
                          <svg
                            width="10"
                            height="10"
                            viewBox="0 0 10 10"
                            fill="none"
                            aria-hidden="true"
                          >
                            <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth={1.2} />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    className={styles.addBtn}
                    onClick={() =>
                      setConditions((prev) => [...prev, { field: '', op: 'eq', value: '' }])
                    }
                  >
                    ＋ {t('data.addCondition')}
                  </button>
                </div>

                <div>
                  <button type="button" className={styles.runBtn} onClick={runStructuredQuery}>
                    {t('data.runQuery')}
                  </button>
                </div>

                <AsyncBoundary
                  state={queryResultState}
                  isEmpty={(d) => d.rows.length === 0}
                  emptyTitle={t('common.noMatch')}
                  emptyHint={t('data.adjustQuery')}
                >
                  {(result) => <QueryResultTable result={result} />}
                </AsyncBoundary>
              </div>
            ) : (
              <div className={styles.queryForm}>
                <div className={styles.sqlTerminal}>
                  <span className={styles.termPrompt} aria-hidden="true">
                    {'postgres=>'}
                  </span>
                  <CodeMirror
                    value={sqlText}
                    height="auto"
                    extensions={sqlExtensions}
                    onChange={(value) => setSqlText(value)}
                    placeholder={t('data.sqlPlaceholder')}
                    basicSetup={{
                      lineNumbers: false,
                      foldGutter: false,
                      highlightActiveLine: false,
                      highlightActiveLineGutter: false,
                      autocompletion: false,
                    }}
                    className={styles.cmWrap}
                  />
                </div>
                <div>
                  <button
                    type="button"
                    className={styles.runBtn}
                    onClick={runSqlQuery}
                    disabled={sqlText.trim() === ''}
                  >
                    {t('data.execute')}
                  </button>
                </div>
                <AsyncBoundary
                  state={sqlResultState}
                  isEmpty={(d) => d.rows.length === 0}
                  emptyTitle={t('common.noMatch')}
                  emptyHint={t('data.typeSqlToRun')}
                >
                  {(result) => <QueryResultTable result={result} />}
                </AsyncBoundary>
              </div>
            )}
          </section>
        </>
      )}

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};
