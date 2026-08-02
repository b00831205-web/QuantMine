import type { ApiError } from '@/types/api';
import styles from './ErrorView.module.css';

interface Props {
  error: ApiError;
  onRetry?: () => void;
}

export const ErrorView = ({ error, onRetry }: Props) => {
  return (
    <div className={styles.wrap} role="alert">
      <div className={styles.code}>{error.code}</div>
      <div className={styles.title}>{error.title}</div>
      {error.detail ? <div className={styles.detail}>{error.detail}</div> : null}
      {onRetry ? (
        <button className={styles.retry} onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
};
