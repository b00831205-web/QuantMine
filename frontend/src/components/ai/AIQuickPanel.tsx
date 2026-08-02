import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import styles from './AIQuickPanel.module.css';

/**
 * AI 快捷窗口：1~6 页面共享的浮层，AI 工作台自身不渲染。
 * 阶段 0 仅展示静态骨架 + 输入框；具体对话逻辑留待阶段 7。
 */
export const AIQuickPanel = () => {
  const { pathname } = useLocation();
  const showOnPage = pathname.startsWith('/ai') ? null : pathname;
  const [collapsed, setCollapsed] = useState(false);
  const [draft, setDraft] = useState('');

  if (!showOnPage) return null;

  if (collapsed) {
    return (
      <button className={styles.fab} onClick={() => setCollapsed(false)} aria-label="打开 AI 助手">
        AI
      </button>
    );
  }

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <span className={styles.title}>AI 助手</span>
        <button className={styles.iconBtn} onClick={() => setCollapsed(true)} aria-label="收起">
          ×
        </button>
      </header>
      <div className={styles.context}>
        <span className={styles.contextLabel}>已附加</span>
        <span className={styles.contextValue}>{showOnPage}</span>
      </div>
      <div className={styles.messages}>
        <div className={styles.placeholder}>在阶段 7 之前，对话区为骨架。</div>
      </div>
      <footer className={styles.composer}>
        <input
          className={styles.input}
          placeholder="向 AI 提问…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled
        />
        <button className={styles.send} disabled>
          发送
        </button>
      </footer>
    </aside>
  );
};
