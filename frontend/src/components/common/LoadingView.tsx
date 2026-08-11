import { useTranslation } from 'react-i18next';
import styles from './LoadingView.module.css';

export const LoadingView = ({ label }: { label?: string }) => {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap} role="status" aria-live="polite">
      <div className={styles.spinner} />
      <span className={styles.label}>{label ?? t('common.loading')}</span>
    </div>
  );
};
