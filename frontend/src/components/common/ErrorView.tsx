import type { ApiError } from '@/types/api';
import { useTranslation } from 'react-i18next';
import styles from './ErrorView.module.css';

interface Props {
  error: ApiError;
  onRetry?: () => void;
}

export const ErrorView = ({ error, onRetry }: Props) => {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap} role="alert">
      <div className={styles.code}>{error.code}</div>
      <div className={styles.title}>{error.title}</div>
      {error.detail ? <div className={styles.detail}>{error.detail}</div> : null}
      {onRetry ? (
        <button className={styles.retry} onClick={onRetry}>
          {t('common.retry')}
        </button>
      ) : null}
    </div>
  );
};
