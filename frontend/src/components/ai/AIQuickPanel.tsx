import { useLocation } from 'react-router-dom';
import { useState } from 'react';
import styles from './AIQuickPanel.module.css';

interface Props {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

/**
 * AI 快捷窗口：页面 1~6 共享的右侧栏，AI 工作台自身不渲染。
 * 展开时作为 grid 第三列参与布局，主内容收窄；收起时显示右下角气泡。
 */
export const AIQuickPanel = ({ open, onOpen, onClose }: Props) => {
  const { pathname } = useLocation();
  const showOnPage = pathname.startsWith('/ai') ? null : pathname;
  const [draft, setDraft] = useState('');

  if (!showOnPage) return null;

  if (!open) {
    return (
      <button className={styles.fab} onClick={onOpen} aria-label="打开 AI 助手">
        AI
      </button>
    );
  }

  return (
    <aside className={styles.panel}>
      <header className={styles.header}>
        <span className={styles.title}>AI 助手</span>
        <button className={styles.iconBtn} onClick={onClose} aria-label="收起">
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
