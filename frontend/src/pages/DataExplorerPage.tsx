import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchDataCatalog, fetchDataPage, buildDataExportUrl } from '@/api/client';
import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { Column } from '@/components/common/PaginatedTable';
import type { AsyncState } from '@/types/api';
import type { Catalog, DataResource, DataPage } from '@/types/data';
import { QueryResultTable } from '@/components/common/QueryResultTable';
import i18n from '@/i18n';
import {fetchStructuredQuery} from "@/api/client"
import type {QueryResult, StructuredCondition} from '@/types/data'
import { fetchSqlQuery } from '@/api/client';

const inputStyle: React.CSSProperties = {
  padding: 'var(--sp-1) var(--sp-2)',
  background: 'var(--bg-surface-2)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-sm)',
};

export const DataExplorerPage = () => {
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
  const [queryResultState, setQueryResultState] = useState<AsyncState<QueryResult>>({ status: 'idle' });
  


  const resourceParam = searchParams.get('resource');
  const catalog = catalogState.status === 'success' ? catalogState.data : [];
  /* 以 catalog 为唯一事实来源：URL 里的资源名不在 catalog 中时落到第一个 */
  const resource =
    catalog.find((c) => c.resource === resourceParam)?.resource ??
    catalog[0]?.resource ??
    null;

  /* 切换资源：写回 URL + 重置分页和筛选 */
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
    fetchStructuredQuery(
      {
        resource: queryResource,
        fields: selectedFields,
        conditions: conditions
          .filter((c) => c.field !== '' && c.value !== '')
          .map((c) => ({
            ...c,
            // 长得像数字的字符串转成数字（mock 的 eq 是严格 ===，'42' 匹配不上 42）
            value: Number.isNaN(Number(c.value)) ? c.value : Number(c.value),
          })),
        limit: 100,
      },
    )
      .then((data) => {
        setQueryResultState({ status: 'success', data });
      })
      .catch((error) => {
        if(error instanceof DOMException && error.name ==='AbortError'){
        return;
      }
      if(error instanceof HttpError){
        setQueryResultState({status: 'error', error: error.apiError});
        return;
      }
      setQueryResultState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          detail: i18n.t('common.networkError.detail'),
          status: 0,
        }
      });
    });
  }
    const runSqlQuery = (): void => {
    if (sqlText.trim() === '') return;
    setSqlResultState({ status: 'loading' });
    fetchSqlQuery(sqlText)
      .then((data) => {
        setSqlResultState({ status: 'success', data });
      })
      .catch((error) => {
        if(error instanceof DOMException && error.name ==='AbortError'){
        return;
      }
      if(error instanceof HttpError){
        setSqlResultState({status: 'error', error: error.apiError});
        return;
      }
      setSqlResultState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          detail: i18n.t('common.networkError.detail'),
          status: 0,
        }
      });
        // 项目模板照抄，state 是 sqlResultState
        // 注意：mock 对非 SELECT 返回 403，会走 HttpError 分支，ErrorView 显示"只允许 SELECT 查询"
      });
  };
      

  /* catalog 就绪后，URL 资源名无效/缺失时写回第一个资源 */
  useEffect(() => {
    if (catalog.length === 0) return;
    const valid = catalog.some((c) => c.resource === resourceParam);
    const first = catalog[0];
    if (!valid && first) {
      const params = new URLSearchParams(searchParams);
      params.set('resource', first.resource);
      setSearchParams(params, { replace: true });
    }
  }, [catalog, resourceParam]);

  
    useEffect(() => {
    if (queryResource === null && catalog.length > 0) {
      setQueryResource(catalog[0]?.resource ?? null);
    }
  }, [catalog, queryResource]);

    const queryCatalog = catalog.find((c) => c.resource === queryResource) ?? null;
  /* 资源目录 */
  useEffect(() => {
    const controller = new AbortController();
    setCatalogState({ status: 'loading' });
    fetchDataCatalog(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setCatalogState({ status: 'success', data });
        }
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
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

  /* 资源数据（筛选/分页） */
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
        if (!controller.signal.aborted) {
          setPageState({ status: 'success', data });
        }
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
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

  const current =
    resource !== null ? catalog.find((c) => c.resource === resource) ?? null : null;

  /* 动态列：从字段说明生成（数字右对齐，其余左对齐） */
  const columns: Column<Record<string, unknown>>[] = current
    ? current.fields.map((f) => ({
        key: f.name,
        header: f.name,
        align: f.type === 'number' ? 'right' : 'left',
        render: (row: Record<string, unknown>) => String(row[f.name] ?? ''),
      }))
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader
        title="数据库速查"
        subtitle="白名单业务对象 · 服务端筛选/分页 · CSV 导出"
      />

      {/* Tab 切换 */}
      <div style={{ display: 'flex', gap: 'var(--sp-3)' }}>
        <button
          type="button"
          onClick={() => setTab('browse')}
          style={{
            padding: 'var(--sp-2) var(--sp-4)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            background: tab === 'browse' ? 'var(--bg-surface-2)' : 'transparent',
            color: tab === 'browse' ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          白名单浏览
        </button>
        <button
          type="button"
          onClick={() => setTab('query')}
          style={{
            padding: 'var(--sp-2) var(--sp-4)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-sm)',
            background: tab === 'query' ? 'var(--bg-surface-2)' : 'transparent',
            color: tab === 'query' ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          Query 查询
        </button>
      </div>

      {tab === 'browse' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '280px 1fr',
            gap: 'var(--sp-5)',
            alignItems: 'start',
          }}
        >
          {/* 左列：资源目录 + 字段说明 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
            <Card title="资源目录">
              <AsyncBoundary
                state={catalogState}
                isEmpty={(d) => d.length === 0}
                emptyTitle="暂无资源"
                emptyHint="确认 /api/v1/data/catalog 有数据"
              >
                {(data) => (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                    {data.map((c) => (
                      <button
                        key={c.resource}
                        type="button"
                        onClick={() => setResource(c.resource)}
                        style={{
                          textAlign: 'left',
                          padding: 'var(--sp-2) var(--sp-3)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          background:
                            resource === c.resource ? 'var(--bg-surface-2)' : 'transparent',
                          color:
                            resource === c.resource ? 'var(--accent)' : 'var(--text-primary)',
                          cursor: 'pointer',
                        }}
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                )}
              </AsyncBoundary>
            </Card>

            <Card title="字段说明">
              {current === null ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
                  选择资源查看字段说明
                </div>
              ) : (
                <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                  {current.fields.map((f) => (
                    <li
                      key={f.name}
                      style={{ padding: 'var(--sp-1) 0', fontSize: 'var(--fs-sm)' }}
                    >
                      <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                        {f.name}
                      </span>
                      <span style={{ color: 'var(--text-muted)', marginLeft: 'var(--sp-2)' }}>
                        {f.type}
                        {f.filterable ? ' · 可筛选' : ''}
                      </span>
                      <div style={{ color: 'var(--text-secondary)' }}>{f.description}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {/* 右列：筛选 + 结果 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
            <Card title="筛选">
              {current === null ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
                  选择资源后显示可筛选字段
                </div>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    gap: 'var(--sp-3)',
                    flexWrap: 'wrap',
                    alignItems: 'flex-end',
                  }}
                >
                  {current.fields
                    .filter((f) => f.filterable)
                    .map((f) => (
                      <label
                        key={f.name}
                        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}
                      >
                        <span
                          style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}
                        >
                          {f.name}
                        </span>
                        <input
                          value={filters[f.name] ?? ''}
                          onChange={(e) =>
                            setFilters((prev) => ({ ...prev, [f.name]: e.target.value }))
                          }
                          style={inputStyle}
                        />
                      </label>
                    ))}
                  <button
                    type="button"
                    onClick={() => {
                      setAppliedFilters(filters);
                      setPage(1);
                    }}
                  >
                    应用
                  </button>
                </div>
              )}
            </Card>

            <Card
              title="结果"
              extra={
                resource !== null ? (
                  <a
                    href={buildDataExportUrl({
                      resource,
                      ...(Object.keys(appliedFilters).length > 0
                        ? { filters: appliedFilters }
                        : {}),
                    })}
                  >
                    导出 CSV
                  </a>
                ) : undefined
              }
            >
              <AsyncBoundary
                state={pageState}
                isEmpty={(d) => d.items.length === 0}
                emptyTitle="暂无数据"
                emptyHint="调整筛选或切换资源"
              >
                {(data) => (
                  <PaginatedTable
                    columns={columns}
                    page={data}
                    rowKey={(row) => JSON.stringify(row)}
                    onPageChange={setPage}
                    emptyHint="暂无数据"
                  />
                )}
              </AsyncBoundary>
            </Card>
          </div>
        </div>
      )}

      {tab === 'query' && (
        <Card title="Query 查询">
          <div style={{ display: 'flex', gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)' }}>
            <button
              type="button"
              onClick={() => setQueryMode('structured')}
              style={{
                padding: 'var(--sp-1) var(--sp-3)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                background: queryMode === 'structured' ? 'var(--bg-surface-2)' : 'transparent',
                color:
                  queryMode === 'structured' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              结构化
            </button>
            <button
              type="button"
              onClick={() => setQueryMode('sql')}
              style={{
                padding: 'var(--sp-1) var(--sp-3)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                background: queryMode === 'sql' ? 'var(--bg-surface-2)' : 'transparent',
                color: queryMode === 'sql' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              SQL
            </button>
          </div>

          {queryMode === 'structured' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
              {/* 资源选择 */}
              <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
                <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>资源</span>
                <select
                  value={queryResource ?? ''}
                  onChange={(e) => setQueryResource(e.target.value as DataResource)}
                  style={inputStyle}
                >
                  {catalog.map((c) => (
                    <option key={c.resource} value={c.resource}>{c.label}</option>
                  ))}
                </select>
              </label>

              {/* 字段勾选 */}
              <div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-2)' }}>
                  字段（不选默认全部）
                </div>
                <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
                  {queryCatalog?.fields.map((f) => {
                    const checked = selectedFields.includes(f.name);
                    return (
                      <label
                        key={f.name}
                        style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-1)', fontSize: 'var(--fs-sm)', cursor: 'pointer' }}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() =>
                            setSelectedFields((prev) =>
                              checked ? prev.filter((n) => n !== f.name) : [...prev, f.name],
                            )
                          }
                        />
                        {f.name}
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* 条件行 */}
              <div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-2)' }}>条件</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                  {conditions.map((c, i) => (
                    <div key={i} style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                      <select value={c.field} onChange={(e) => updateCondition(i, { field: e.target.value })} style={inputStyle}>
                        {queryCatalog?.fields.map((f) => (
                          <option key={f.name} value={f.name}>{f.name}</option>
                        ))}
                      </select>
                      <select value={c.op} onChange={(e) => updateCondition(i, { op: e.target.value as StructuredCondition['op'] })} style={inputStyle}>
                        <option value="eq">=</option>
                        <option value="ne">≠</option>
                        <option value="gt">&gt;</option>
                        <option value="lt">&lt;</option>
                        <option value="contains">包含</option>
                      </select>
                      <input value={c.value} onChange={(e) => updateCondition(i, { value: e.target.value })} style={inputStyle} />
                      <button type="button" onClick={() => setConditions((prev) => prev.filter((_, idx) => idx !== i))}>删除</button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => setConditions((prev) => [...prev, { field: '', op: 'eq', value: '' }])}
                  >
                    添加条件
                  </button>
                </div>
              </div>

              {/* 执行 */}
              <div>
                <button type="button" onClick={runStructuredQuery}>执行查询</button>
              </div>
                            <AsyncBoundary
                state={queryResultState}
                isEmpty={(d) => d.rows.length === 0}
                emptyTitle="无结果"
                emptyHint="调整查询条件后执行"
              >
                {(result) => <QueryResultTable result={result} />}
              </AsyncBoundary>
            </div>
          ) : (
            <div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
              <textarea
                value={sqlText}
                onChange={(e) => setSqlText(e.target.value)}
                placeholder="SELECT ...（仅允许 SELECT，最多 100 行）"
                rows={5}
                style={{ ...inputStyle, fontFamily: 'var(--font-mono)', resize: 'vertical' }}
              />
              <div>
                <button type="button" onClick={runSqlQuery} disabled={sqlText.trim() === ''}>
                  执行
                </button>
              </div>
              <AsyncBoundary
                state={sqlResultState}
                isEmpty={(d) => d.rows.length === 0}
                emptyTitle="无结果"
                emptyHint="输入 SELECT 语句后执行"
              >
                {(result) => <QueryResultTable result={result} />}
              </AsyncBoundary>
            </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};
