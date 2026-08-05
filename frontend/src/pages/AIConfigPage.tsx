import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import type { AIConfig, AIProviderConfig} from '@/types/ai';
// TODO(USER_LEARNING): 保存时需要 `saveAIConfig`——从 '@/api/client' 引入。
import type { AsyncState } from '@/types/api';
import i18n from '@/i18n';
import {fetchAIConfig, saveAIConfig} from '@/api/client';

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--sp-2) var(--sp-3)',
  background: 'var(--bg-surface-2)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
};

const fieldLabel: React.CSSProperties = {
  display: 'block',
  fontSize: 'var(--fs-sm)',
  color: 'var(--text-muted)',
  marginBottom: 4,
};

const dangerBtn: React.CSSProperties = {
  padding: 'var(--sp-2) var(--sp-4)',
  borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--negative)',
  background: 'transparent',
  color: 'var(--negative)',
  cursor: 'pointer',
  fontSize: 'var(--fs-sm)',
};

/** 自定义供应商用 providerId 前缀区分（内置供应商不可改名/删除）。 */
const CUSTOM_PREFIX = 'custom-';
const isCustomProvider = (providerId: string) => providerId.startsWith(CUSTOM_PREFIX);

export const AIConfigPage = () => {
  const [configState, setConfigState] = useState<AsyncState<AIConfig>>({ status: 'idle' });
  const [draft, setDraft] = useState<AIConfig | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  // API Key 只写不回显（密钥不应随 GET 往返）；单独存草稿。
  const [keyDrafts, setKeyDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('')

  /* 加载配置，并同步到编辑草稿 */
  useEffect(() => {
    const controller = new AbortController();
    setConfigState({ status: 'loading' });
    fetchAIConfig(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setConfigState({ status: 'success', data });
          setDraft(data);
        }
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) {
          setConfigState({ status: 'error', error: error.apiError });
          return;
        }
        setConfigState({
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

  const patchProvider = (providerId: string, patch: Partial <AIProviderConfig>): void=>{
    setDraft((prev)=>
    prev ? {
      ...prev, providers: prev.providers.map((p)=>
      p.providerId === providerId? {...p, ...patch} : p,
    ),
    }
  : prev,
);
  };

  /** 新增一个空白自定义供应商并立即进入编辑。 */
  const addCustomProvider = (): void => {
    const id = `${CUSTOM_PREFIX}${Date.now()}`;
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            providers: [
              ...prev.providers,
              { providerId: id, name: '自定义供应商', configured: false, baseUrl: '', models: [] },
            ],
          }
        : prev,
    );
    setEditingId(id);
    setSavedMsg('');
  };

  /** 删除供应商（仅自定义）。 */
  const removeProvider = (providerId: string): void => {
    setDraft((prev) =>
      prev ? { ...prev, providers: prev.providers.filter((p) => p.providerId !== providerId) } : prev,
    );
    if (editingId === providerId) setEditingId(null);
    setSavedMsg('');
  };

  const handleSave = async (): Promise<void> => {
    if (draft === null) return;
    setSaving(true);
    setSavedMsg('')

    const next: AIConfig ={
      ...draft,
      providers: draft.providers.map((p) => 
      keyDrafts[p.providerId] ? {...p, configured: true} : p,),
    };

    try {
      const saved = await saveAIConfig(next);
      setConfigState({status: 'success', data: saved});
      setDraft(saved);
      setKeyDrafts({});
      setSavedMsg('已保存');
    } catch {
      setSavedMsg('保存失败，请重试');
    } finally{
      setSaving(false);
    }
  };

  const editing = draft?.providers.find((p) => p.providerId === editingId) ?? null;

  // TODO(USER_LEARNING): 默认模型下拉聚合
  //   把 draft.providers 里所有 models 摊平成 [{ provider: p.name, model }]，
  //   供下面 <select> 生成选项（选项文案 "OpenAI · gpt-4o"）。
  const allModels: Array<{ provider: string; model: string }> = 
  draft?.providers.flatMap((p)=>p.models.map((model)=>({provider: p.name, model})),) ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader title="AI 配置" subtitle="类 Dify 的集中配置页（简化版）· 仅管理员可修改" />

      <Card title="模型供应商">
        <AsyncBoundary
          state={configState}
          isEmpty={(d) => d.providers.length === 0}
          emptyTitle="暂无供应商"
          emptyHint="确认 /api/v1/ai/config 有数据"
        >
          {() =>
            draft && (
              <>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                    gap: 'var(--sp-3)',
                  }}
                >
                  {draft.providers.map((p) => {
                    const active = editingId === p.providerId;
                    return (
                      <button
                        key={p.providerId}
                        type="button"
                        onClick={() => setEditingId(active ? null : p.providerId)}
                        style={{
                          textAlign: 'left',
                          padding: 'var(--sp-3)',
                          border: `1px solid ${active ? 'var(--accent)' : 'var(--border-subtle)'}`,
                          borderRadius: 'var(--radius-md)',
                          background: active ? 'var(--bg-surface-2)' : 'transparent',
                          color: 'var(--text-primary)',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
                        <div
                          style={{
                            fontSize: 'var(--fs-sm)',
                            color: p.configured ? 'var(--positive)' : 'var(--text-muted)',
                          }}
                        >
                          {p.configured ? '已配置 ✓' : '未配置'}
                        </div>
                      </button>
                    );
                  })}

                  {/* 添加自定义供应商 */}
                  <button
                    type="button"
                    onClick={addCustomProvider}
                    style={{
                      padding: 'var(--sp-3)',
                      border: '1px dashed var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      background: 'transparent',
                      color: 'var(--text-muted)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      minHeight: 64,
                    }}
                  >
                    ＋ 添加自定义供应商
                  </button>
                </div>

                {/* 编辑表单 */}
                {editing && (
                  <div
                    style={{
                      marginTop: 'var(--sp-4)',
                      padding: 'var(--sp-4)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--bg-surface)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 'var(--sp-3)',
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>编辑：{editing.name}</div>

                    {/* 供应商名称 —— 仅自定义供应商可改名 */}
                    {isCustomProvider(editing.providerId) && (
                      <div>
                        <label style={fieldLabel}>供应商名称</label>
                        <input
                          type="text"
                          style={inputStyle}
                          placeholder="自定义供应商名称"
                          value={editing.name}
                          onChange={(e) =>
                            patchProvider(editing.providerId, { name: e.target.value })
                          }
                        />
                      </div>
                    )}

                    {/* API Key —— 已实现：写入 keyDrafts（局部 state，不回显） */}
                    <div>
                      <label style={fieldLabel}>
                        API Key {editing.configured && '（已配置，留空则不修改）'}
                      </label>
                      <input
                        type="password"
                        style={inputStyle}
                        placeholder={editing.configured ? '••••••••（留空保持不变）' : 'sk-...'}
                        value={keyDrafts[editing.providerId] ?? ''}
                        onChange={(e) =>
                          setKeyDrafts((prev) => ({ ...prev, [editing.providerId]: e.target.value }))
                        }
                      />
                    </div>

                    {/* TODO(USER_LEARNING): 供应商编辑表单的不可变更新
                        下面 Base URL / 模型列表 两个受控输入的 onChange 需要你实现：
                          - 写一个 patchProvider(providerId, patch: Partial<AIProviderConfig>)：
                            setDraft(prev => prev && {
                              ...prev,
                              providers: prev.providers.map(p =>
                                p.providerId === providerId ? { ...p, ...patch } : p),
                            })
                          - Base URL：patchProvider(editing.providerId, { baseUrl: e.target.value })
                          - 模型列表：把逗号分隔字符串 split(',').map(trim).filter(Boolean) 成数组
                        （记得从 '@/types/ai' 引入 AIProviderConfig 类型） */}
                    <div>
                      <label style={fieldLabel}>Base URL</label>
                      <input
                        type="text"
                        style={inputStyle}
                        placeholder="https://api.openai.com/v1"
                        value={editing.baseUrl}
                        onChange={(e) => {
                          patchProvider(editing.providerId, { baseUrl: e.target.value });
                        }}
                      />
                    </div>
                    <div>
                      <label style={fieldLabel}>模型列表（逗号分隔）</label>
                      <input
                        type="text"
                        style={inputStyle}
                        placeholder="gpt-4o, gpt-4o-mini"
                        value={editing.models.join(', ')}
                        onChange={(e) => {
                          patchProvider(editing.providerId, {
                            models: e.target.value
                            .split(',')
                            .map((s)=> s.trim())
                            .filter(Boolean)
                          })
                        }}
                      />
                    </div>

                    {/* 删除自定义供应商 */}
                    {isCustomProvider(editing.providerId) && (
                      <div>
                        <button
                          type="button"
                          onClick={() => removeProvider(editing.providerId)}
                          style={dangerBtn}
                        >
                          删除该供应商
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </>
            )
          }
        </AsyncBoundary>
      </Card>

      <Card title="默认模型">
        {draft ? (
          <select
            value={draft.defaultModel}
            onChange={(e) => {
              setDraft((prev)=>(prev ? {...prev, systemPrompt: e.target.value} : prev))
            }}
            style={{ ...inputStyle, width: 'auto', minWidth: 260 }}
          >
            {/* allModels 目前为空——实现上面的聚合 TODO 后这里才会有选项 */}
            {allModels.map(({ provider, model }) => (
              <option key={`${provider}-${model}`} value={model}>
                {provider} · {model}
              </option>
            ))}
          </select>
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>加载中…</div>
        )}
      </Card>

      <Card title="Agent 基本设置">
        {draft && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
            {
            /* TODO(USER_LEARNING): Agent 设置受控输入
                两个输入的 onChange 需要你把值不可变地写回 draft：
                  - systemPrompt：setDraft(prev => prev && { ...prev, systemPrompt: e.target.value })
                  - temperature：Number(e.target.value)，同理写回 draft.temperature */}
            <div>
              <label style={fieldLabel}>系统提示词</label>
              <textarea
                rows={3}
                style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
                value={draft.systemPrompt}
                onChange={(e) => {
                  setDraft((prev)=> (prev ? {...prev, defaultModel: e.target.value}: prev))
                }}
              />
            </div>
            <div style={{ maxWidth: 220 }}>
              <label style={fieldLabel}>温度（0 ~ 1）</label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.1}
                style={inputStyle}
                value={draft.temperature}
                onChange={(e) => {
                  setDraft((prev)=> prev? {...prev, temperature: Number(e.target.value)} : prev)
                }}
              />
            </div>
          </div>
        )}
      </Card>

      <Card title="RAG 知识库 / Skill / 外部 API / 审计日志">
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          后续阶段接入，当前为占位。
        </div>
      </Card>

      <div>
        <button
          type="button"
          onClick={handleSave}
          disabled={draft === null || saving}
          style={{
            padding: 'var(--sp-2) var(--sp-5)',
            borderRadius: 'var(--radius-sm)',
            border: 'none',
            background: 'var(--accent)',
            color: '#fff',
            cursor: draft === null ? 'not-allowed' : 'pointer',
            opacity: draft === null ? 0.5 : 1,
          }}
        >
          {saving ? '保存中...': '保存'}
        </button>
        {savedMsg && (
          <span 
          style = {{
            marginLeft : 'var(--sp-3)',
            fontSize: 'var(--fs-sm)',
            color: savedMsg.startsWith('已保存') ? 'var(--positive)' : 'var(--negative)',
          }}>
            {savedMsg}
          </span>
        )}
      </div>
    </div>
  );
};
