import { useTranslation } from 'react-i18next';
import styles from './EmptyView.module.css';

interface Props {
  title?: string;
  hint?: string;
}

export const EmptyView = ({ title, hint }: Props) => {
  const { t } = useTranslation();
  return (
    <div className={styles.wrap}>
      <div className={styles.title}>{title ?? t('common.noData')}</div>
      {hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
};
