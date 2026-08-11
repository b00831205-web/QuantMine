import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  confirmAIAction,
  createAIConversation,
  fetchAIMessages,
  sendAIMessage,
} from '@/api/client';
import type { AIConfirmRequest, AIMessage } from '@/types/ai';
import styles from './AIQuickPanel.module.css';

interface Props {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

/** 全局共享会话：所有页面的快捷 AI 共用同一个会话 */
const GLOBAL_CONVERSATION_KEY = 'quantmine.ai.globalConversationId';

const ConfirmCard = ({
  request,
  onDecide,
}: {
  request: AIConfirmRequest;
  onDecide: (approved: boolean) => void;
}) => {
  const { t } = useTranslation();
  const resolved = request.status !== 'pending';
  return (
    <div
      style={{
        marginTop: 8,
        border: `1px solid ${request.status === 'rejected' ? 'var(--negative)' : 'var(--warning)'}`,
        borderRadius: 'var(--radius-sm)',
        padding: 'var(--sp-2)',
        background: 'var(--bg-surface)',
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 12 }}>⚠ {request.title}</div>
      <div style={{ color: 'var(--text-muted)', fontSize: 11, margin: '4px 0 8px' }}>
        {request.description}
      </div>
      {resolved ? (
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {request.status === 'confirmed'
            ? `✅ ${t('aiPanel.confirmed')}`
            : `❌ ${t('aiPanel.rejected')}`}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={() => onDecide(true)}
            style={{
              border: '1px solid var(--positive)',
              color: 'var(--positive)',
              background: 'transparent',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 10px',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            {t('aiPanel.approve')}
          </button>
          <button
            type="button"
            onClick={() => onDecide(false)}
            style={{
              border: '1px solid var(--negative)',
              color: 'var(--negative)',
              background: 'transparent',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 10px',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            {t('aiPanel.reject')}
          </button>
        </div>
      )}
    </div>
  );
};

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
          maxWidth: '85%',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--sp-2) var(--sp-3)',
          background: isUser ? 'var(--accent)' : 'var(--bg-surface-2)',
          color: isUser ? '#fff' : 'var(--text-primary)',
          border: isUser ? 'none' : '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5, fontSize: 'var(--fs-sm)' }}>
          {msg.content}
        </div>
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {msg.toolCalls.map((tc, i) => (
              <span
                key={`${tc.toolName}-${i}`}
                style={{
                  fontSize: 10,
                  fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '1px 5px',
                  background: 'var(--bg-surface)',
                }}
              >
                🔧 {tc.toolName}({tc.argsSummary})
              </span>
            ))}
          </div>
        )}
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

export const AIQuickPanel = ({ open, onOpen, onClose }: Props) => {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const showOnPage = pathname.startsWith('/ai') ? null : pathname;
  const [conversationId, setConversationId] = useState<string | null>(() =>
    localStorage.getItem(GLOBAL_CONVERSATION_KEY),
  );
  const [messages, setMessages] = useState<AIMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open || !showOnPage) return;
    let cancelled = false;

    const ensureConversation = async () => {
      setLoading(true);
      try {
        let id = localStorage.getItem(GLOBAL_CONVERSATION_KEY);
        if (!id) {
          const conv = await createAIConversation();
          id = conv.conversationId;
          localStorage.setItem(GLOBAL_CONVERSATION_KEY, id);
          setConversationId(id);
          setMessages([]);
        } else {
          const all = await fetchAIMessages(id);
          if (!cancelled) setMessages(all.filter((m) => m.role !== 'tool'));
        }
      } catch {
        // 全局会话可能已被删除，重建一个
        try {
          const conv = await createAIConversation();
          localStorage.setItem(GLOBAL_CONVERSATION_KEY, conv.conversationId);
          setConversationId(conv.conversationId);
          setMessages([]);
        } catch {
          // 保持现状
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    ensureConversation();
    return () => {
      cancelled = true;
    };
  }, [open, showOnPage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const handleSend = async () => {
    const text = draft.trim();
    if (!text || sending || loading) return;

    let id = conversationId ?? localStorage.getItem(GLOBAL_CONVERSATION_KEY);
    if (!id) {
      try {
        const conv = await createAIConversation();
        id = conv.conversationId;
        localStorage.setItem(GLOBAL_CONVERSATION_KEY, id);
        setConversationId(id);
      } catch {
        return;
      }
    }

    const userMsg: AIMessage = {
      messageId: `local-${Date.now()}`,
      conversationId: id,
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft('');
    setSending(true);

    try {
      await sendAIMessage(id, {
        content: text,
        modelId: '',
        attachedContext: { page: showOnPage ?? '/ai' },
      });
      const all = await fetchAIMessages(id);
      setMessages(all.filter((m) => m.role !== 'tool'));
    } catch {
      setMessages((prev) => prev.filter((m) => m.messageId !== userMsg.messageId));
    } finally {
      setSending(false);
    }
  };

  const handleDecideConfirm = async (messageId: string, approved: boolean) => {
    const id = conversationId ?? localStorage.getItem(GLOBAL_CONVERSATION_KEY);
    const msg = messages.find((m) => m.messageId === messageId);
    if (!id || !msg?.confirmRequest) return;

    setMessages((prev) =>
      prev.map((m) =>
        m.messageId === messageId && m.confirmRequest
          ? {
              ...m,
              confirmRequest: {
                ...m.confirmRequest,
                status: approved ? 'confirmed' : 'rejected',
              },
            }
          : m,
      ),
    );
    setSending(true);
    try {
      await confirmAIAction(id, {
        toolCallId: msg.confirmRequest.toolCallId,
        approved,
      });
      const all = await fetchAIMessages(id);
      setMessages(all.filter((m) => m.role !== 'tool'));
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.messageId === messageId && m.confirmRequest
            ? { ...m, confirmRequest: { ...m.confirmRequest, status: 'pending' } }
            : m,
        ),
      );
    } finally {
      setSending(false);
    }
  };

  if (!showOnPage) return null;

  if (!open) {
    return (
      <button className={styles.fab} onClick={onOpen} aria-label={t('aiPanel.open')}>
        AI
      </button>
    );
  }

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <span className={styles.title}>{t('aiPanel.title')}</span>
        <button className={styles.iconBtn} onClick={onClose} aria-label={t('aiPanel.collapse')}>
          ×
        </button>
      </header>
      <div className={styles.context}>
        <span className={styles.contextLabel}>{t('aiPanel.attached')}</span>
        <span className={styles.contextValue}>{showOnPage}</span>
      </div>
      <div className={styles.messages}>
        {loading ? (
          <div className={styles.placeholder}>{t('aiPanel.loading')}</div>
        ) : messages.length === 0 ? (
          <div className={styles.placeholder}>{t('aiPanel.emptyHint')}</div>
        ) : (
          messages.map((m) => (
            <MessageBubble key={m.messageId} msg={m} onDecideConfirm={handleDecideConfirm} />
          ))
        )}
        {sending && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div
              style={{
                padding: 'var(--sp-2) var(--sp-3)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface-2)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-muted)',
                fontSize: 'var(--fs-sm)',
              }}
            >
              {t('aiPanel.thinking')}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <footer className={styles.composer}>
        <input
          className={styles.input}
          placeholder={sending ? t('aiPanel.placeholderThinking') : t('aiPanel.placeholder')}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSend();
          }}
          disabled={sending || loading}
        />
        <button
          className={styles.send}
          onClick={handleSend}
          disabled={draft.trim() === '' || sending || loading}
        >
          {t('aiPanel.send')}
        </button>
      </footer>
    </aside>
  );
};
