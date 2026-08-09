import { useEffect, useRef, useState } from 'react';
import { HttpError } from '@/api/http';
import { Paperclip } from 'lucide-react';
import { uploadAIAttachment, attachmentFileUrl } from '@/api/client/ai';
import {
  fetchAIConversations,
  fetchAIMessages,
  fetchAIModels,
  createAIConversation,
  sendAIMessage,
  confirmAIAction,
  deleteAIConversation
  // sendAIMessage,      // handleSend 里接入（见 TODO）
  // streamAIMessage,    // 流式回复（见 TODO / client/ai.ts）
  // confirmAIAction,    // 确认卡回传（见 TODO）
} from '@/api/client';
import type { AsyncState } from '@/types/api';
import type { AIConversation, AIMessage, AIConfirmRequest } from '@/types/ai';
import i18n from '@/i18n';

/* ────────────────────────── 通用异步小 hook ────────────────────────── */
function useAsync<T>(loader: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'idle' });
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading' });
    loader(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'success', data });
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof HttpError) setState({ status: 'error', error: error.apiError });
        else
          setState({
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
  }, deps);
  return state;
}

/* ────────────────────────── 引用来源（可折叠） ────────────────────────── */
const CitationList = ({
  citations,
}: {
  citations: NonNullable<AIMessage['citations']>;
}) => {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 'var(--sp-2)' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text-muted)',
          cursor: 'pointer',
          padding: 0,
          fontSize: 12,
        }}
      >
        {open ? '▾' : '▸'} 引用来源 ({citations.length})
      </button>
      {open && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
          {citations.map((c) => (
            <div
              key={c.sourceId}
              style={{
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: 'var(--sp-2)',
                background: 'var(--bg-surface)',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600 }}>{c.title}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.snippet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* ────────────────────────── 工具调用摘要 ────────────────────────── */
const TOOL_STATUS_LABEL: Record<string, string> = {
  pending: '待执行',
  confirmed: '已确认',
  rejected: '已拒绝',
  done: '完成',
};

const ToolCallList = ({
  toolCalls,
}: {
  toolCalls: NonNullable<AIMessage['toolCalls']>;
}) => (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 'var(--sp-2)' }}>
    {toolCalls.map((tc, i) => (
      <span
        key={`${tc.toolName}-${i}`}
        title={tc.argsSummary}
        style={{
          fontSize: 11,
          fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
          color: 'var(--text-muted)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          padding: '2px 6px',
          background: 'var(--bg-surface)',
        }}
      >
        🔧 {tc.toolName}({tc.argsSummary}) · {TOOL_STATUS_LABEL[tc.status] ?? tc.status}
      </span>
    ))}
  </div>
);

/* ────────────────────────── 高影响操作确认卡 ────────────────────────── */
const ConfirmCard = ({
  request,
  onDecide,
}: {
  request: AIConfirmRequest;
  onDecide: (approved: boolean) => void;
}) => {
  const resolved = request.status !== 'pending';
  return (
    <div
      style={{
        marginTop: 'var(--sp-2)',
        border: `1px solid ${request.status === 'rejected' ? 'var(--negative)' : 'var(--warning)'}`,
        borderRadius: 'var(--radius-sm)',
        padding: 'var(--sp-3)',
        background: 'var(--bg-surface)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 13 }}>
        <span style={{ color: 'var(--warning)' }}>⚠</span> {request.title}
      </div>
      <div style={{ color: 'var(--text-muted)', fontSize: 12, margin: '4px 0 var(--sp-3)' }}>
        {request.description}
      </div>
      {resolved ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {request.status === 'confirmed' ? '✓ 已确认执行' : '✕ 已拒绝'}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button type="button" onClick={() => onDecide(true)} style={confirmBtn('var(--positive)')}>
            确认
          </button>
          <button type="button" onClick={() => onDecide(false)} style={confirmBtn('var(--negative)')}>
            拒绝
          </button>
        </div>
      )}
    </div>
  );
};

/* ────────────────────────── 单条消息气泡 ────────────────────────── */
const MessageBubble = ({
  msg,
  onDecideConfirm,
}: {
  msg: AIMessage;
  onDecideConfirm: (messageId: string, approved: boolean) => void;
}) => {
  const isUser = msg.role === 'user';
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div
        style={{
          maxWidth: '78%',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--sp-3)',
          background: isUser ? 'var(--accent)' : 'var(--bg-surface-2)',
          color: isUser ? '#fff' : 'var(--text-primary)',
          border: isUser ? 'none' : '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{msg.content}</div>
        {msg.attachments && msg.attachments.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
            {msg.attachments.map((a) =>
              a.kind === 'image' ? (
                <img
                  key={a.attachmentId}
                  src={attachmentFileUrl(a.attachmentId)}
                  alt={a.filename}
                  style={{
                    maxWidth: 160,
                    maxHeight: 120,
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                  }}
                />
              ) : (
                <span
                  key={a.attachmentId}
                  style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '2px 6px',
                    background: 'var(--bg-surface)',
                  }}
                >
                  📎 {a.filename}
                </span>
              ),
            )}
          </div>
        )}
        {msg.citations && msg.citations.length > 0 && <CitationList citations={msg.citations} />}
        {msg.toolCalls && msg.toolCalls.length > 0 && <ToolCallList toolCalls={msg.toolCalls} />}
        {msg.confirmRequest && (
          <ConfirmCard
            request={msg.confirmRequest}
            onDecide={(approved) => onDecideConfirm(msg.messageId, approved)}
          />
        )}
      </div>
    </div>
  );
};

/* ────────────────────────── 页面 ────────────────────────── */
export const AIWorkbenchPage = () => {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState('');
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const sendControllerRef = useRef<AbortController | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<
    Array<{
      key: string;
      attachmentId?: string;
      filename: string;
      kind: string;
      status: 'uploading' | 'ready' | 'failed';
    }>
  >([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [conversationRefreshKey, setConversationRefreshKey] = useState(0);
  const conversationsState = useAsync<AIConversation[]>(
    (s) => fetchAIConversations(s),
    [conversationRefreshKey],
  );
  const modelsState = useAsync<string[]>((s) => fetchAIModels(s), []);
  const messagesState = useAsync<AIMessage[]>(
    (s) => (activeId ? fetchAIMessages(activeId, s) : Promise.resolve([])),
    [activeId],
  );

  // 模型就绪 → 默认选第一个
  useEffect(() => {
    if (selectedModel === '' && modelsState.status === 'success') {
      setSelectedModel(modelsState.data[0] ?? '');
    }
  }, [modelsState, selectedModel]);

  // 消息就绪 → 灌入本地可变副本（便于乐观追加 / 更新确认卡状态）
  useEffect(() => {
    // 隐藏 role='tool' 的原始查询结果（噪音）；保留 assistant 的工具调用摘要 + 最终答复
    if (messagesState.status === 'success')
      setMessages(messagesState.data.filter((m) => m.role !== 'tool'));
    if (activeId === null) setMessages([]);
  }, [messagesState, activeId]);

  // 新消息 → 滚到底
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

    useEffect(() => {
    sendControllerRef.current?.abort();
  }, [activeId]);

  const startNewConversation = async () => {
    setActiveId(null);
    setMessages([]);
    setDraft('');
    try {
      const conv = await createAIConversation();
      setActiveId(conv.conversationId);
      setConversationRefreshKey((k) => k + 1);
    } catch {
      // 创建失败：保留空会话状态，可稍后重试
    }
  };

  const handleDeleteConversation = async (conversationId: string): Promise<void> =>{
    if (!window.confirm('删除该对话后及所有信息无法恢复，确定删除？')) return;
    try {
      await deleteAIConversation(conversationId);
      if (activeId === conversationId){
        setActiveId(null);
        setMessages([]);
      }
      setConversationRefreshKey((k)=> k+1);
    } catch{
      //删除失败，保持现状，不打断用户
    }
  };
  

  const ensureConversation = async (): Promise<string | null> => {
    if (activeId !== null) return activeId;
    try {
      const conv = await createAIConversation();
      setActiveId(conv.conversationId);
      setConversationRefreshKey((k) => k + 1);
      return conv.conversationId;
    } catch {
      return null;
    }
  };

  const handleFilesSelected = async (files: File[]) => {
    if (files.length === 0) return;
    const cid = await ensureConversation();
    if (cid === null) return;

    const placeholders = files.map((file) => ({
      key: `local-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      filename: file.name,
      kind: file.type.startsWith('image/') ? 'image' : 'file',
      status: 'uploading' as const,
    }));
    setPendingAttachments((prev) => [...prev, ...placeholders]);
    setUploading(true);

    for (const [index, file] of files.entries()) {
      const placeholder = placeholders[index];
      if (!placeholder) continue;
      try {
        const res = await uploadAIAttachment(cid, file);
        setPendingAttachments((prev) =>
          prev.map((a) =>
            a.key === placeholder.key
              ? { ...a, attachmentId: res.attachmentId, kind: res.kind, status: 'ready' }
              : a,
          ),
        );
      } catch {
        setPendingAttachments((prev) =>
          prev.map((a) =>
            a.key === placeholder.key ? { ...a, status: 'failed' } : a,
          ),
        );
      }
    }

    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handlePaste = (e: React.ClipboardEvent): void => {
    const items = Array.from(e.clipboardData?.items ?? []);
    const images = items
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);
    if (images.length === 0) return;
    e.preventDefault();
    void handleFilesSelected(images);
  };

  const handleSend = async () => {
    const text = draft.trim();
    if (!text || sending) return;

    // 首条消息发送后，标题由后端后台异步生成；记录下来以便稍后刷新会话列表
    const isFirstMessage = messages.length === 0;

    // 乐观追加用户消息（本地立即可见）
    const userMsg: AIMessage = {
      messageId: `local-${Date.now()}`,
      conversationId: activeId ?? 'new',
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft('');
    setSending(true);

    const controller = new AbortController();
    sendControllerRef.current = controller;

    try {
      let conversationId = activeId;
      if (conversationId === null){
        const conv = await createAIConversation(controller.signal);
        conversationId = conv.conversationId;
        setActiveId(conversationId);
      }
    
    await sendAIMessage(
      conversationId,
      {
        content: text,
        modelId: selectedModel,
        ...(pendingAttachments.some((a) => a.status === 'ready')
          ? {
              attachments: pendingAttachments
                .filter((a) => a.status === 'ready')
                .map((a) => ({ attachmentId: a.attachmentId })),
            }
          : {}),
      },
      controller.signal,
    );
    setPendingAttachments([]);
    // 后端可能自动跑了多步白名单工具，刷新整段对话（隐藏原始工具结果）
    const all = await fetchAIMessages(conversationId, controller.signal);
    setMessages(all.filter((m) => m.role !== 'tool'));
    // 首条消息：刷新会话列表（顺带让新建会话入列）；标题在后台生成，稍后再刷一次以显示
    if (isFirstMessage) {
      setConversationRefreshKey((k) => k + 1);
      setTimeout(() => setConversationRefreshKey((k) => k + 1), 1500);
    }
  } catch {setMessages((prev)=>prev.filter((m)=> m.messageId !== userMsg.messageId));

  }finally {
    sendControllerRef.current = null;
    setSending(false);
  }
    
    // TODO(USER_LEARNING): 接入 AI 回复
    //   1. 若 activeId 为 null，先 createConversation 拿到 id（后端接口，见 client/ai.ts 待补）
    //   2. 非流式：await sendAIMessage(id, { content: text, modelId: selectedModel })
    //            → setMessages(prev => [...prev, 返回的 assistant 消息])
    //   3. 流式：streamAIMessage(id, payload, (chunk) => 增量拼接最后一条 assistant 消息)
    //            （见 client/ai.ts 的 SSE 契约）
    //   4. 用 try/catch 处理错误；无论成败，finally 里 setSending(false)
    //   5. 记得携带 AbortController，切换对话时中断
    // 占位：接入真实调用后由 finally 负责
    
  };
  

  const handleDecideConfirm = async (messageId: string, approved: boolean) => {
    // 乐观更新确认卡状态
    setMessages((prev) =>
      prev.map((m) =>
        m.messageId === messageId && m.confirmRequest
          ? { ...m, confirmRequest: { ...m.confirmRequest, status: approved ? 'confirmed' : 'rejected' } }
          : m,
      ),
    );
    const msg = messages.find((m)=> m.messageId === messageId);
    if(!msg?.confirmRequest || activeId === null) return;

    setSending(true); // 确认后执行工具 + 生成答复期间，同样算“思考中”，禁用输入框
    try {
      await confirmAIAction(activeId, {
        toolCallId: msg.confirmRequest.toolCallId,
        approved,
      })
      // 确认后端可能继续自动跑白名单工具，刷新整段对话
      const all = await fetchAIMessages(activeId);
      setMessages(all.filter((m) => m.role !== 'tool'));
    } catch{
      setMessages((prev)=> prev.map((m)=> m.messageId === messageId && m.confirmRequest? {...m, confirmRequest: {...m.confirmRequest, status: 'pending'}}: m
    ),);
    } finally {
      setSending(false);
    }
    // TODO(USER_LEARNING): 回传后端
    //   const msg = messages.find(m => m.messageId === messageId);
    //   await confirmAIAction(activeId!, { toolCallId: msg.confirmRequest.toolCallId, approved });
    //   用返回的消息对齐最终态（如执行结果、新的 assistant 消息）；失败则回滚上面的乐观更新
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: 'grid',
          gridTemplateColumns: '260px minmax(0, 1fr)',
          gap: 'var(--sp-5)',
        }}
      >
        {/* ── 左：对话历史 ── */}
        <aside
          style={{
            display: 'flex',
            flexDirection: 'column',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            minHeight: 0,
          }}
        >
          <div style={{ padding: 'var(--sp-3)', borderBottom: '1px solid var(--border-subtle)' }}>
            <button
              type="button"
              onClick={startNewConversation}
              style={{
                width: '100%',
                padding: 'var(--sp-2)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--accent)',
                background: 'transparent',
                color: 'var(--accent)',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              ＋ 新建对话
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--sp-2)' }}>
            {conversationsState.status === 'loading' && (
              <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', padding: 'var(--sp-2)' }}>
                加载中…
              </div>
            )}
            {conversationsState.status === 'success' &&
                            conversationsState.data.map((c) => {
                const active = activeId === c.conversationId;
                return (
                  <div
                    key={c.conversationId}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      marginBottom: 4,
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid',
                      borderColor: active ? 'var(--accent)' : 'transparent',
                      background: active ? 'var(--bg-surface-2)' : 'transparent',
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => setActiveId(c.conversationId)}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 'var(--sp-2)',
                        textAlign: 'left',
                        padding: 'var(--sp-2) var(--sp-3)',
                        background: 'transparent',
                        border: 'none',
                        color: active ? 'var(--accent)' : 'var(--text-primary)',
                        cursor: 'pointer',
                      }}
                    >
                      <span style={{ color: active ? 'var(--accent)' : 'var(--text-muted)' }}>
                        {active ? '●' : '○'}
                      </span>
                      <span
                        style={{
                          flex: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {c.title}
                      </span>
                    </button>
                    <button
                      type="button"
                      title="删除对话"
                      onClick={() => handleDeleteConversation(c.conversationId)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        padding: 'var(--sp-1) var(--sp-2)',
                        fontSize: 14,
                      }}
                    >
                      ×
                    </button>
                  </div>
                );
              })}
          </div>
        </aside>

        {/* ── 右：聊天区 ── */}
        <section
          style={{
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
          }}
        >
          {/* 顶部：模型选择 */}
          <header
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: 'var(--sp-3)',
              borderBottom: '1px solid var(--border-subtle)',
            }}
          >
            <span style={{ fontWeight: 600 }}>
              {activeId
                ? conversationsState.status === 'success'
                  ? conversationsState.data.find((c) => c.conversationId === activeId)?.title ?? '对话'
                  : '对话'
                : '新对话'}
            </span>
            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>模型</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={{
                  padding: 'var(--sp-1) var(--sp-2)',
                  background: 'var(--bg-surface-2)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {modelsState.status === 'success'
                  ? modelsState.data.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))
                  : null}
              </select>
            </label>
          </header>

          {/* 消息流 */}
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              padding: 'var(--sp-4)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--sp-3)',
            }}
          >
            {activeId === null && messages.length === 0 ? (
              <div style={emptyHint}>新建或从左侧选择一个对话开始</div>
            ) : messagesState.status === 'loading' ? (
              <div style={emptyHint}>加载消息…</div>
            ) : messagesState.status === 'error' ? (
              <div style={{ ...emptyHint, color: 'var(--negative)' }}>
                {messagesState.error.title}
              </div>
            ) : messages.length === 0 ? (
              <div style={emptyHint}>暂无消息，向 AI 提问开始</div>
            ) : (
              messages.map((m) => (
                <MessageBubble key={m.messageId} msg={m} onDecideConfirm={handleDecideConfirm} />
              ))
            )}
            {sending && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div
                  style={{
                    padding: 'var(--sp-3)',
                    borderRadius: 'var(--radius-md)',
                    background: 'var(--bg-surface-2)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-muted)',
                    fontSize: 'var(--fs-sm)',
                  }}
                >
                  AI 正在思考…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* 输入栏 */}
          {activeId !== null && (
            <>
          {pendingAttachments.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
                padding: 'var(--sp-2) var(--sp-3)',
                borderTop: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                附件（{pendingAttachments.length}）
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {pendingAttachments.map((a) => (
                  <span
                    key={a.key}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 11,
                      color: 'var(--text-secondary)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '2px 8px',
                      background: 'var(--bg-surface)',
                    }}
                  >
                    {a.kind === 'image' ? '🖼' : '📎'} {a.filename}
                    {a.status === 'uploading' && (
                      <span style={{ color: 'var(--warning)' }}>上传中…</span>
                    )}
                    {a.status === 'ready' && (
                      <span style={{ color: 'var(--positive)' }}>✓</span>
                    )}
                    {a.status === 'failed' && (
                      <span style={{ color: 'var(--negative)' }}>✗</span>
                    )}
                    <button
                      type="button"
                      onClick={() =>
                        setPendingAttachments((prev) =>
                          prev.filter((x) => x.key !== a.key),
                        )
                      }
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: 12,
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
          <div
            style={{
              display: 'flex',
              gap: 'var(--sp-2)',
              padding: 'var(--sp-3)',
              borderTop: '1px solid var(--border-subtle)',
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => handleFilesSelected(Array.from(e.target.files ?? []))}
            />
            <button
              type="button"
              title="上传附件"
              disabled={sending || uploading}
              onClick={() => fileInputRef.current?.click()}
              style={{
                padding: 'var(--sp-2)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                background: 'transparent',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                opacity: uploading ? 0.5 : 1,
              }}
            >
              <Paperclip size={14} />
            </button>
            <input
              style={{
                flex: 1,
                padding: 'var(--sp-2) var(--sp-3)',
                background: 'var(--bg-surface-2)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                opacity: sending ? 0.5 : 1,
              }}
              disabled={sending}
              placeholder={sending ? 'AI 思考中，请稍候…' : '向 AI 提问…（Enter 发送）'}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSend();
              }}
              onPaste={handlePaste}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={draft.trim() === '' || sending}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                borderRadius: 'var(--radius-sm)',
                border: 'none',
                background: 'var(--accent)',
                color: '#fff',
                cursor: draft.trim() === '' || sending ? 'not-allowed' : 'pointer',
                opacity: draft.trim() === '' || sending ? 0.5 : 1,
              }}
            >
              发送
            </button>
          </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
};

/* ────────────────────────── 内联样式助手 ────────────────────────── */
const emptyHint: React.CSSProperties = {
  margin: 'auto',
  color: 'var(--text-muted)',
  fontSize: 'var(--fs-sm)',
};

const confirmBtn = (color: string): React.CSSProperties => ({
  padding: '4px 14px',
  borderRadius: 'var(--radius-sm)',
  border: `1px solid ${color}`,
  background: 'transparent',
  color,
  cursor: 'pointer',
  fontSize: 12,
});
