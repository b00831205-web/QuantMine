import styles from './LoadingView.module.css';

export const LoadingView = ({ label = '加载中…' }: { label?: string }) => {
  return (
    <div className={styles.wrap} role="status" aria-live="polite">
      <div className={styles.spinner} />
      <span className={styles.label}>{label}</span>
    </div>
  );
};
