import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import { fetchResearchOptions } from '@/api/client';
import type { AsyncState } from '@/types/api';
import type { ResearchFilterOptions } from '@/types/research';
import type { ReportLang } from '@/types/report';
import { buildReportPdfUrl, buildReportXlsxUrl } from '@/api/client/report';
import type { ReportQuery } from '@/types/report';
import i18n from '@/i18n';
import {Download, Printer, FileSpreadsheet, RefreshCcw} from 'lucide-react'
import { PaginatedTable } from '@/components/common/PaginatedTable';
import { fetchReportHistory } from '@/api/client/report';
import type { ReportHistoryItem, ReportHistoryPage } from '@/types/report';
import type { Column } from '@/components/common/PaginatedTable';

/* URL 读取辅助：照 FactorDetailPage 的模式 */
const HISTORY_COLUMNS: Column<ReportHistoryItem>[]= [
  { key: 'reportId', header: '报告 ID', align: 'left', render: (r) => r.reportId },
  { key: 'runId', header: 'Run', align: 'right', render: (r) => String(r.runId) },
  { key: 'testId', header: 'Test ID', align: 'left', render: (r) => r.testId ?? '全部' },
  { key: 'lang', header: '语言', align: 'center', render: (r) => r.lang.toUpperCase() },
  { key: 'ai', header: 'AI', align: 'center', render: (r) => (r.ai ? '开' : '关') },
  { key: 'createdAt', header: '生成时间', align: 'left', render: (r) => r.createdAt },
  { key: 'status', header: '状态', align: 'center', render: (r) => (r.status === 'ready' ? '完成' : '失败') },
];

const readRunId = (sp: URLSearchParams): number | null => {
  const v = sp.get('runId');
  if (v === null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
};

const readTestId = (sp: URLSearchParams): string | null => sp.get('testId') ?? null;

const readLang = (sp: URLSearchParams): ReportLang =>
  sp.get('lang') === 'en' ? 'en' : 'zh';

const readAi = (sp: URLSearchParams): boolean => sp.get('ai') === 'true';

const iconBtnStyle : React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 28,
  height: 28,
  padding: 0,
  background: 'transparent',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-secondary)',
  cursor: 'pointer'
}

export const ReportsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [optionsState, setOptionsState] = useState<AsyncState<ResearchFilterOptions>>({status: 'idle'})
  const [pdfLoaded, setPdfLoaded] = useState(false);
  const [historyState, setHistoryState] = useState<AsyncState<ReportHistoryPage>>({status: 'idle'});
  const [historyPage, setHistoryPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0)
  const [forceRefresh, setForceRefresh] = useState(0)
  const options = optionsState.status === 'success' ? optionsState.data : null;

  const runId = readRunId(searchParams);
  const testId = readTestId(searchParams);
  const lang = readLang(searchParams);
  const ai = readAi(searchParams);

  const buildQuery = ():ReportQuery | null =>
    runId ===null ? null: {runId, lang, ai, ...(testId ? {testId}:{})};

  const handleDownloadPdf = (): void =>{
    const q =buildQuery();
    if (q) window.open(buildReportPdfUrl(q,false), '_blank')
  };

  const handlePrint = (): void =>{
    const q =buildQuery();
    if (q) window.open(buildReportPdfUrl(q, true), '_blank')
  }

  const handleDownloadExcel = (): void =>{
    const q = buildQuery()
    if (q) window.open(buildReportXlsxUrl(q), '_blank')
  }

  const pdfUrl =
  runId === null? null : buildReportPdfUrl({runId, lang, ai, refresh: forceRefresh > 0, ...(testId? {testId}: {})}, true) + (forceRefresh > 0 ? `&t=${forceRefresh}` : '');

  useEffect(()=>{
    setPdfLoaded(false)
  }, [pdfUrl])


  const updateSearch = (
    next: Partial<{ runId: number | null; testId: string | null; lang: ReportLang | null; ai: boolean | null }>,
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
    setOptionsState({status:'loading'});
    fetchResearchOptions(
      undefined,
      controller.signal,
    ).then((data)=>{
      if(!controller.signal.aborted){
        setOptionsState({status: 'success', data});
        if (runId === null && data.defaultRunId){
          updateSearch({runId: data.defaultRunId});
        }
      }
    })
    .catch((error) => {
      if(error instanceof DOMException && error.name ==='AbortError'){
        return;
      }
      if(error instanceof HttpError){
        setOptionsState({status: 'error', error: error.apiError});
        return;
      }
      setOptionsState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          detail: i18n.t('common.networkError.detail'),
          status: 0,
        }
      });
    }
  );
  return ()=> controller.abort()
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setHistoryState({status:'loading'});
    fetchReportHistory(
      historyPage,
      10,
      controller.signal,
    ).then((data)=>{
      if(!controller.signal.aborted){
        setHistoryState({status: 'success', data});
      }
    })
    .catch((error) => {
      if(error instanceof DOMException && error.name ==='AbortError'){
        return;
      }
      if(error instanceof HttpError){
        setHistoryState({status: 'error', error: error.apiError});
        return;
      }
      setHistoryState({
        status: 'error',
        error: {
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          detail: i18n.t('common.networkError.detail'),
          status: 0,
        }
      });
    }
  );
  return ()=> controller.abort()
  }, [historyPage, refreshKey]);

  useEffect(() => {
    if (runId === null){
      setOptionsState({status: 'idle'})
      return;
    }
    const controller = new AbortController()
    setOptionsState({status: 'loading'});
    fetchResearchOptions(runId, controller.signal)
    .then((data) => {if(!controller.signal.aborted){
      setOptionsState({status: 'success', data});
      if(testId !== null && !data.testIds.includes(testId)){
        updateSearch({testId: null})
      }
    }
  })
    .catch((error)=>{
      if(error instanceof DOMException && error.name === 'AbortError'){
        return;
      }
      if(error instanceof HttpError){
        setOptionsState({status:'error', error: error.apiError});
        return;
      }
      setOptionsState({
        status: 'error',
        error:{
          code: 'NETWORK_ERROR',
          title: i18n.t('common.networkError.title'),
          detail: i18n.t('common.networkError.detail'),
          status: 0,
        }
      })
    });
    return ()=>controller.abort();
  }, [runId]);



  return (
    <div style = {{display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)'}}>
      <PageHeader
        title="报告下载"
        subtitle="生成、预览并下载研究报告"
        actions={
          <span style={{ color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)' }}>
            Run {runId ?? '-'} · {lang.toUpperCase()} · AI {ai ? '开' : '关'}
          </span>
        }
      />
      <Card title="报告设置">
        <AsyncBoundary
          state={optionsState}
          isEmpty={(d) => d.runs.length === 0}
          emptyTitle="暂无研究批次"
          emptyHint="确认 research/options 有数据"
        >
          {() => (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--sp-4)' }}>
              {/* Research Run */}
              <label style ={{display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)'}}>
                <span style = {{color: 'var(--text-secondary)', fontSize : 'var(--fs-sm)'}}>
                  Research Run
                </span>
                <select
                value = {runId === null? '': String(runId)}
                onChange={(e)=>{
                  const value = e.target.value;
                  updateSearch({runId: value === ''? null : Number(value), testId: null});
                }}
                style = {{width: '100%', padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)', color: 'var(--text-primary)', border : '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)'}}>
                  <option value ="">选择 Run</option>
                  {options?.runs.map((r)=>(
                    <option key = {r.runId} value = {String(r.runId)}>
                      Run {r.runId} · {r.createdAt}
                      </option>
                  ))}
                </select>
              </label>
              {/* Test ID */}
              <label style = {{display: 'flex', flexDirection: 'column', gap:'var(--sp-1)'}}>
                <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>
                  Test ID
                </span>
                <select
                value = {testId ?? ""}
                onChange = {(e)=> updateSearch({testId: e.target.value || null})}
                style = {{padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)', color: 'var(--text-primary)',border: '1px solid var(--border-subtle)', borderRadius:'var(--radius-sm)'}}>
                  <option value =''>全部</option>
                  {options?.testIds.map((t)=>(
                    <option key = {t} value ={t}>
                      {t}
                    </option>
                  ))}
                </select>
                </label>

                {/* Language */}
                <label style = {{display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)'}}>
                <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>
                  Language
                </span>
                <select
                value = {lang}
                onChange = {(e)=>updateSearch({lang: e.target.value === 'en'? 'en':'zh'})}
                style = {{padding: 'var(--sp-1) var(--sp-2)', background: 'var(--bg-surface-2)',color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)'}}
                >
                  <option value ='zh'>中文</option>
                  <option value ='en'>English</option>

                </select>
                </label>
            </div>
          )}
        </AsyncBoundary>
      </Card>
      <Card
      title = '报告历史'
      extra = {
        <button type = 'button' title = '刷新' disabled={historyState.status === 'loading'} onClick={() => setRefreshKey((k) => k + 1)} style = {iconBtnStyle}>
        <RefreshCcw size = {14}/>
        </button>
      }>
        <AsyncBoundary
        state = {historyState}
        isEmpty={(d)=> d.items.length === 0}
        emptyTitle= '暂无历史记录'
        emptyHint = '生成过的报告会出现在这里'
        >
          {(data)=> (
            <PaginatedTable
            columns = {HISTORY_COLUMNS}
            page = {data}
            rowKey={(row)=>row.reportId}
            onPageChange = {setHistoryPage}
            emptyHint='暂无历史记录'/>
          )}
        </AsyncBoundary>
      </Card>
      <Card 
      title = '报告预览'
      extra = {
        <div style = {{display: 'flex', alignItems: 'center', gap: 'var(--sp-3)'}}>
          <label style = {{display: 'flex', alignItems: 'center', gap: 'var(--sp-1)', cursor: 'pointer'}}>
            <input 
            type = 'checkbox'
            checked= {ai}
            onChange = {(e)=>updateSearch({ai: e.target.checked})}
            />
            <span style = {{color: 'var(--text-secondary)', fontSize: 'var(--fs-sm)'}}>AI分析</span>
          </label>
          <span style = {{color: 'var(--text-muted)', fontSize: 'var(--fs-xs)'}}>
            开启后报告中包含AI解读
          </span>
          <button type = 'button' title = '强制重新生成报告（绕过缓存）' disabled={runId === null} onClick={() => setForceRefresh((k) => k + 1)} style = {iconBtnStyle}>
            <RefreshCcw size = {14}/>
          </button>
          <button type = 'button' title ='下载PDF' disabled={runId === null} onClick={handleDownloadPdf} style = {iconBtnStyle}>
            <Download size = {14}/>
          </button>
          <button type = 'button' title = '打印' disabled = {runId === null} onClick={handlePrint} style ={iconBtnStyle}>
            <Printer size = {14}/>
            </button>
          <button type= 'button' title = '下载 Excel' disabled = {runId === null} onClick = {handleDownloadExcel} style = {iconBtnStyle}>
            <FileSpreadsheet size = {14}/>
            </button>
        </div>
      }>
        {pdfUrl === null?(
          <div style = {{color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', padding: 'var(--sp-5)'}}>
            请先选择 Research Run
          </div>
        ): (
          <div style = {{position: 'relative', height: '70vh'}}>
            {!pdfLoaded && (
              <div 
              style ={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--bg-surface)',
                zIndex: 1,
                color: 'var(--text-muted)',
                fontSize: 'var(--fs-sm)'
              }}
              >
                报告生成中...
                </div>
            )}
            <iframe
            key = {pdfUrl}
            src = {pdfUrl}
            onLoad = {()=> setPdfLoaded(true)}
            title = '报告预览'
            style = {{width: '100%', height: '100%', border: 'none', background: '#fff'}}/>
            
          </div>
        )}
        
      </Card>
      
    </div>
  );
};
