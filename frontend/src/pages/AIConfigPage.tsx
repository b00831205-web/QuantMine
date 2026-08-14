/**
 * AI 配置页 · Evidence Ledger（证据账本）
 *
 * 方向契约：
 * THESIS：供应商与模型配置是一份连贯的设置账本；保存常驻页头，各区块以
 *         安静面板呈现而非等重卡片堆叠。
 * OWN-WORLD：沿用 DESIGN.md 的哑光深色研究终端语言——平层色阶、1px 细线、
 *         钴蓝只用于主保存动作/选中/焦点；API Key 环境变量名、端点等
 *         机器值使用等宽字体。
 * STORY：管理员过一遍供应商、内联编辑其一、选默认模型、调 Agent 与权限、
 *         配置 Embedding，然后从页头保存。
 * FIRST VIEWPORT：页头（含保存动作）+ 供应商面板（卡片 + 编辑表单），
 *         默认模型/Agent、权限、Embedding、Skill 在首屏之下。
 * FORM：Evidence Ledger，与市场 / 调仓 / 研究结果 template 同构。
 * FINISH：unreviewed and undocumented is unfinished；本次以类型/测试/构建与人工视觉复核收口。
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/common/PageHeader';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { HttpError } from '@/api/http';
import type { AsyncState } from '@/types/api';
import i18n from '@/i18n';
import { fetchAIConfig, saveAIConfig } from '@/api/client';
import type {
  AIConfig,
  AICapabilities,
  AIProviderConfig,
  AIEmbeddingConfig,
  AISkill,
} from '@/types/ai';
import styles from './AIConfigPage.module.css';

const CUSTOM_PREFIX = 'custom-';
const isCustomProvider = (providerId: string): boolean => providerId.startsWith(CUSTOM_PREFIX);

/**
 * Presets for OpenAI-compatible providers.
 *
 * Only the two stable, hard-to-remember fields are filled in: the API base URL
 * and the conventional env var name. `models` is deliberately left empty --
 * model identifiers change often enough that a stale built-in list would send
 * users into 400s that read like a broken integration, and the page already
 * lets them be typed in.
 *
 * Everything here stays editable after insertion; a preset is a starting point,
 * not a locked profile.
 */
const PROVIDER_PRESETS: ReadonlyArray<{
  name: string;
  baseUrl: string;
  apiKeyEnv: string;
}> = [
  { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', apiKeyEnv: 'OPENAI_API_KEY' },
  { name: 'DeepSeek', baseUrl: 'https://api.deepseek.com', apiKeyEnv: 'DEEPSEEK_API_KEY' },
  { name: 'SiliconFlow', baseUrl: 'https://api.siliconflow.cn/v1', apiKeyEnv: 'SILICONFLOW_API_KEY' },
  { name: 'Moonshot', baseUrl: 'https://api.moonshot.cn/v1', apiKeyEnv: 'MOONSHOT_API_KEY' },
  {
    name: 'DashScope (Qwen)',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    apiKeyEnv: 'DASHSCOPE_API_KEY',
  },
  { name: 'Zhipu', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', apiKeyEnv: 'ZHIPU_API_KEY' },
  { name: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', apiKeyEnv: 'OPENROUTER_API_KEY' },
  // Inside a container `localhost` is the container itself, so a host Ollama is
  // unreachable at localhost:11434. The symptom is a connection timeout, which
  // does not point at the cause -- hence the host.docker.internal default here.
  { name: 'Ollama', baseUrl: 'http://host.docker.internal:11434/v1', apiKeyEnv: '' },
];

/** 开关（胶囊拨动），与全站工作流开关同语言 */
const Switch = ({
  on,
  label,
  onChange,
  disabled,
}: {
  on: boolean;
  label: string;
  onChange: (on: boolean) => void;
  disabled?: boolean;
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={on}
    aria-label={label}
    disabled={disabled}
    className={on ? `${styles.switch} ${styles.switchOn}` : styles.switch}
    onClick={() => onChange(!on)}
  >
    <span className={styles.thumb} />
  </button>
);

export const AIConfigPage = () => {
  const { t } = useTranslation();
  const capabilityLabels: Array<{ key: keyof AICapabilities; label: string; hint: string }> = [
    {
      key: 'read_research',
      label: t('aiConfig.cap.readResearch'),
      hint: t('aiConfig.cap.readResearchHint'),
    },
    {
      key: 'read_market',
      label: t('aiConfig.cap.readMarket'),
      hint: t('aiConfig.cap.readMarketHint'),
    },
    {
      key: 'read_reports',
      label: t('aiConfig.cap.readReports'),
      hint: t('aiConfig.cap.readReportsHint'),
    },
    {
      key: 'query_database',
      label: t('aiConfig.cap.queryDatabase'),
      hint: t('aiConfig.cap.queryDatabaseHint'),
    },
    {
      key: 'use_chat_history',
      label: t('aiConfig.cap.useChatHistory'),
      hint: t('aiConfig.cap.useChatHistoryHint'),
    },
    {
      key: 'rag_corpus',
      label: t('aiConfig.cap.ragCorpus'),
      hint: t('aiConfig.cap.ragCorpusHint'),
    },
  ];
  const [overrideIds, setOverrideIds] = useState<Record<string, boolean>>({});
  const [configState, setConfigState] = useState<AsyncState<AIConfig>>({ status: 'idle' });
  const [draft, setDraft] = useState<AIConfig | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');
  const [presetOpen, setPresetOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setConfigState({ status: 'loading' });
    fetchAIConfig(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          const normalized: AIConfig = {
            ...data,
            embeddingConfig: data.embeddingConfig ?? {
              provider: 'none',
              baseUrl: '',
              model: '',
              apiKeyEnv: '',
              dimensions: 1024,
              skills: data.skills ?? [],
            },
          };
          setConfigState({ status: 'success', data: normalized });
          setDraft(normalized);
        }
      })
      .catch((error: unknown) => {
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

  const patchProvider = (providerId: string, patch: Partial<AIProviderConfig>): void => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            providers: prev.providers.map((p) =>
              p.providerId === providerId ? { ...p, ...patch } : p,
            ),
          }
        : prev,
    );
  };

  const patchGlobalCapability = (key: keyof AICapabilities, value: boolean): void => {
    setDraft((prev) =>
      prev ? { ...prev, capabilities: { ...prev.capabilities, [key]: value } } : prev,
    );
  };

  const patchEmbedding = (patch: Partial<AIEmbeddingConfig>): void => {
    setDraft((prev) =>
      prev ? { ...prev, embeddingConfig: { ...prev.embeddingConfig, ...patch } } : prev,
    );
  };

  const toggleSkill = (name: string): void => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            skills: prev.skills.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s)),
          }
        : prev,
    );
  };

  /** Add a provider, optionally seeded from a preset. Presets stay fully editable. */
  const addProvider = (preset?: (typeof PROVIDER_PRESETS)[number]): void => {
    const id = `${CUSTOM_PREFIX}${Date.now()}`;
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            providers: [
              ...prev.providers,
              {
                providerId: id,
                name: preset?.name ?? t('aiConfig.customProviderName'),
                configured: false,
                baseUrl: preset?.baseUrl ?? '',
                models: [],
                apiKeyEnv: preset?.apiKeyEnv ?? '',
              },
            ],
          }
        : prev,
    );
    setEditingId(id);
    setPresetOpen(false);
    setSavedMsg('');
  };

  const removeProvider = (providerId: string): void => {
    setDraft((prev) =>
      prev
        ? { ...prev, providers: prev.providers.filter((p) => p.providerId !== providerId) }
        : prev,
    );
    if (editingId === providerId) setEditingId(null);
    setSavedMsg('');
  };

  const handleSave = async (): Promise<void> => {
    if (draft === null) return;
    setSaving(true);
    setSavedMsg('');
    try {
      const saved = await saveAIConfig({ ...draft });
      setConfigState({ status: 'success', data: saved });
      setDraft(saved);
      setSavedMsg(t('aiConfig.saved'));
    } catch {
      setSavedMsg(t('aiConfig.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const editing = draft?.providers.find((p) => p.providerId === editingId) ?? null;

  const allModels: Array<{ provider: string; model: string }> =
    draft?.providers.flatMap((p) => p.models.map((model) => ({ provider: p.name, model }))) ?? [];

  const configuredCount = draft?.providers.filter((p) => p.configured).length ?? 0;
  const saveMsgOk = savedMsg !== '' && savedMsg.startsWith(t('aiConfig.saved'));

  return (
    <div className={styles.page}>
      <div className={styles.headerWrap}>
        <PageHeader
          title={t('aiConfig.title')}
          subtitle={t('aiConfig.subtitle')}
          actions={
            <div className={styles.headActions}>
              {savedMsg ? (
                <span className={saveMsgOk ? styles.saveMsgOk : styles.saveMsgErr}>{savedMsg}</span>
              ) : null}
              <button
                type="button"
                className={styles.saveBtn}
                onClick={handleSave}
                disabled={draft === null || saving}
              >
                {saving ? t('aiConfig.saving') : t('aiConfig.save')}
              </button>
            </div>
          }
        />
      </div>

      {/* 模型供应商 */}
      <section className={styles.panel} aria-label={t('aiConfig.providersCard')}>
        <div className={styles.panelHead}>
          <h2>{t('aiConfig.providersCard')}</h2>
          <span className={styles.panelMeta}>
            {draft
              ? `${draft.providers.length} · ${configuredCount} ${t('aiConfig.configured')}`
              : ''}
          </span>
        </div>
        <AsyncBoundary
          state={configState}
        >
          {() =>
            draft ? (
              <>
                {draft.providers.length === 0 ? (
                  <div className={styles.providerEmpty}>
                    <div className={styles.providerEmptyTitle}>
                      {t('aiConfig.providersEmptyTitle')}
                    </div>
                    <div className={styles.providerEmptyHint}>
                      {t('aiConfig.providersEmptyHint')}
                    </div>
                  </div>
                ) : null}
                <div className={styles.providerGrid}>
                  {draft.providers.map((p) => {
                    const active = editingId === p.providerId;
                    return (
                      <button
                        key={p.providerId}
                        type="button"
                        className={
                          active ? `${styles.provider} ${styles.providerActive}` : styles.provider
                        }
                        onClick={() => setEditingId(active ? null : p.providerId)}
                      >
                        <div className={styles.providerName}>{p.name}</div>
                        <div
                          className={
                            p.configured
                              ? `${styles.providerState} ${styles.providerStateOk}`
                              : styles.providerState
                          }
                        >
                          {p.configured ? t('aiConfig.configured') : t('aiConfig.notConfigured')}
                        </div>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    className={styles.providerAdd}
                    aria-expanded={presetOpen}
                    onClick={() => setPresetOpen((open) => !open)}
                  >
                    ＋ {t('aiConfig.addProvider')}
                  </button>
                </div>

                {presetOpen ? (
                  <div className={styles.presetMenu}>
                    <div className={styles.presetHint}>{t('aiConfig.presetHint')}</div>
                    <div className={styles.presetGrid}>
                      {PROVIDER_PRESETS.map((preset) => (
                        <button
                          key={preset.name}
                          type="button"
                          className={styles.presetItem}
                          onClick={() => addProvider(preset)}
                        >
                          <span className={styles.presetName}>{preset.name}</span>
                          <span className={styles.presetUrl}>{preset.baseUrl}</span>
                        </button>
                      ))}
                      <button
                        type="button"
                        className={styles.presetItem}
                        onClick={() => addProvider()}
                      >
                        <span className={styles.presetName}>{t('aiConfig.customProviderName')}</span>
                        <span className={styles.presetUrl}>{t('aiConfig.presetBlank')}</span>
                      </button>
                    </div>
                  </div>
                ) : null}

                {editing ? (
                  <div className={styles.edit}>
                    <div className={styles.editTitle}>
                      {t('aiConfig.editing', { name: editing.name })}
                    </div>

                    {isCustomProvider(editing.providerId) ? (
                      <div className={styles.field}>
                        <label>{t('aiConfig.providerName')}</label>
                        <input
                          type="text"
                          placeholder={t('aiConfig.providerNamePlaceholder')}
                          value={editing.name}
                          onChange={(e) =>
                            patchProvider(editing.providerId, { name: e.target.value })
                          }
                        />
                      </div>
                    ) : null}

                    <div className={styles.cols}>
                      <div className={styles.field}>
                        <label>{t('aiConfig.apiKeyEnv')}</label>
                        <input
                          type="text"
                          placeholder="OPENAI_API_KEY"
                          value={editing.apiKeyEnv ?? ''}
                          onChange={(e) =>
                            patchProvider(editing.providerId, { apiKeyEnv: e.target.value })
                          }
                        />
                        <div className={styles.fieldHint}>{t('aiConfig.apiKeyEnvHint')}</div>
                      </div>
                      <div className={styles.field}>
                        <label>{t('aiConfig.baseUrl')}</label>
                        <input
                          type="text"
                          placeholder="https://api.openai.com/v1"
                          value={editing.baseUrl}
                          onChange={(e) =>
                            patchProvider(editing.providerId, { baseUrl: e.target.value })
                          }
                        />
                      </div>
                    </div>

                    <div className={styles.field}>
                      <label>{t('aiConfig.modelList')}</label>
                      <input
                        type="text"
                        placeholder="gpt-4o, gpt-4o-mini"
                        value={editing.models.join(', ')}
                        onChange={(e) =>
                          patchProvider(editing.providerId, {
                            models: e.target.value
                              .split(',')
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </div>

                    <label className={styles.overrideRow}>
                      <input
                        type="checkbox"
                        checked={overrideIds[editing.providerId] ?? false}
                        onChange={(e) => {
                          const on = e.target.checked;
                          setOverrideIds((prev) => ({ ...prev, [editing.providerId]: on }));
                          patchProvider(
                            editing.providerId,
                            on
                              ? { capabilities: { ...(draft?.capabilities ?? {}) } }
                              : { capabilities: undefined },
                          );
                        }}
                      />
                      {t('aiConfig.overrideCapabilities')}
                    </label>
                    {overrideIds[editing.providerId] ? (
                      <div className={styles.capList}>
                        {capabilityLabels.map(({ key, label, hint }) => (
                          <div key={key} className={styles.capRow}>
                            <div>
                              <span className={styles.capLabel}>{label}</span>
                              <span className={styles.capHint}>{hint}</span>
                            </div>
                            <Switch
                              on={editing.capabilities?.[key] ?? true}
                              label={label}
                              onChange={(v) =>
                                patchProvider(editing.providerId, {
                                  capabilities: { ...(editing.capabilities ?? {}), [key]: v },
                                })
                              }
                            />
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {isCustomProvider(editing.providerId) ? (
                      <div className={styles.deleteRow}>
                        <button
                          type="button"
                          className={styles.deleteBtn}
                          onClick={() => removeProvider(editing.providerId)}
                        >
                          {t('aiConfig.deleteProvider')}
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : null
          }
        </AsyncBoundary>
      </section>

      {/* 默认模型 + Agent */}
      <section className={styles.panel} aria-label={t('aiConfig.modelAgentCard')}>
        <div className={styles.panelHead}>
          <h2>{t('aiConfig.modelAgentCard')}</h2>
        </div>
        {draft ? (
          <div className={styles.cols}>
            <div className={styles.field}>
              <label>{t('aiConfig.defaultModelCard')}</label>
              <select
                value={draft.defaultModel}
                onChange={(e) =>
                  setDraft((prev) => (prev ? { ...prev, defaultModel: e.target.value } : prev))
                }
              >
                {allModels.map(({ provider, model }) => (
                  <option key={`${provider}-${model}`} value={model}>
                    {provider} · {model}
                  </option>
                ))}
              </select>
            </div>
            <div className={styles.field}>
              <label>{t('aiConfig.temperature')}</label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={draft.temperature}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, temperature: Number(e.target.value) } : prev,
                  )
                }
              />
            </div>
          </div>
        ) : (
          <div className={styles.loadingText}>{t('aiConfig.loading')}</div>
        )}
        {draft ? (
          <div className={styles.field}>
            <label>{t('aiConfig.systemPrompt')}</label>
            <textarea
              rows={3}
              value={draft.systemPrompt}
              onChange={(e) =>
                setDraft((prev) => (prev ? { ...prev, systemPrompt: e.target.value } : prev))
              }
            />
          </div>
        ) : null}
      </section>

      {/* AI 权限（全局默认） */}
      <section className={styles.panel} aria-label={t('aiConfig.capabilitiesCard')}>
        <div className={styles.panelHead}>
          <h2>{t('aiConfig.capabilitiesCard')}</h2>
        </div>
        {draft ? (
          <>
            {capabilityLabels.map(({ key, label, hint }) => (
              <div key={key} className={styles.permRow}>
                <div>
                  <div className={styles.permText}>{label}</div>
                  <div className={styles.permHint}>{hint}</div>
                </div>
                <Switch
                  on={draft.capabilities?.[key] ?? false}
                  label={label}
                  onChange={(v) => patchGlobalCapability(key, v)}
                />
              </div>
            ))}
            <div className={styles.permNote}>{t('aiConfig.capabilitiesHint')}</div>
          </>
        ) : (
          <div className={styles.loadingText}>{t('aiConfig.loading')}</div>
        )}
      </section>

      {/* Embedding / RAG */}
      <section className={styles.panel} aria-label={t('aiConfig.embeddingCard')}>
        <div className={styles.panelHead}>
          <h2>{t('aiConfig.embeddingCard')}</h2>
        </div>
        {draft ? (
          <>
            <div className={styles.field} style={{ maxWidth: 320 }}>
              <label>{t('aiConfig.embeddingType')}</label>
              <select
                value={draft.embeddingConfig.provider}
                onChange={(e) =>
                  patchEmbedding({ provider: e.target.value as AIEmbeddingConfig['provider'] })
                }
              >
                <option value="none">{t('aiConfig.embeddingOff')}</option>
                <option value="openai_compatible">{t('aiConfig.embeddingOpenAI')}</option>
                <option value="ollama">{t('aiConfig.embeddingOllama')}</option>
              </select>
            </div>
            {draft.embeddingConfig.provider !== 'none' ? (
              <div className={styles.cols}>
                <div className={styles.field}>
                  <label>{t('aiConfig.baseUrl')}</label>
                  <input
                    type="text"
                    placeholder="https://api.siliconflow.cn/v1"
                    value={draft.embeddingConfig.baseUrl}
                    onChange={(e) => patchEmbedding({ baseUrl: e.target.value })}
                  />
                </div>
                <div className={styles.field}>
                  <label>{t('aiConfig.embeddingModel')}</label>
                  <input
                    type="text"
                    placeholder="BAAI/bge-m3"
                    value={draft.embeddingConfig.model}
                    onChange={(e) => patchEmbedding({ model: e.target.value })}
                  />
                </div>
                {draft.embeddingConfig.provider === 'openai_compatible' ? (
                  <div className={styles.field}>
                    <label>{t('aiConfig.embeddingApiKeyEnv')}</label>
                    <input
                      type="text"
                      placeholder="SILICONFLOW_API_KEY"
                      value={draft.embeddingConfig.apiKeyEnv ?? ''}
                      onChange={(e) => patchEmbedding({ apiKeyEnv: e.target.value })}
                    />
                  </div>
                ) : null}
                <div className={styles.field} style={{ maxWidth: 220 }}>
                  <label>{t('aiConfig.embeddingDimensions')}</label>
                  <input
                    type="number"
                    min={64}
                    step={1}
                    value={draft.embeddingConfig.dimensions}
                    onChange={(e) => patchEmbedding({ dimensions: Number(e.target.value) })}
                  />
                </div>
              </div>
            ) : null}
            <div className={styles.permNote}>{t('aiConfig.embeddingHint')}</div>
          </>
        ) : (
          <div className={styles.loadingText}>{t('aiConfig.loading')}</div>
        )}
      </section>

      {/* Skill / 插件 */}
      <section className={styles.panel} aria-label={t('aiConfig.skillCard')}>
        <div className={styles.panelHead}>
          <h2>{t('aiConfig.skillCard')}</h2>
          {draft ? (
            <span className={styles.panelMeta}>
              {t('aiConfig.skillCount', { count: draft.skills.length })}
            </span>
          ) : null}
        </div>
        {draft ? (
          draft.skills.length === 0 ? (
            <div className={styles.skillEmpty}>{t('aiConfig.skillEmpty')}</div>
          ) : (
            draft.skills.map((skill: AISkill) => (
              <div key={skill.name} className={styles.skillRow}>
                <div>
                  <div className={styles.skillName}>
                    {skill.displayName}
                    <span className={styles.skillKey}>{skill.name}</span>
                  </div>
                  {skill.description ? (
                    <div className={styles.skillDesc}>{skill.description}</div>
                  ) : null}
                </div>
                <Switch
                  on={skill.enabled}
                  label={skill.displayName}
                  onChange={() => toggleSkill(skill.name)}
                />
              </div>
            ))
          )
        ) : (
          <div className={styles.loadingText}>{t('aiConfig.loading')}</div>
        )}
      </section>

      <p className={styles.footnote}>
        For research and educational purposes only. Not investment advice. Past performance does not
        guarantee future results.
      </p>
    </div>
  );
};
