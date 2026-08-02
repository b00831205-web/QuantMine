import styles from './EmptyView.module.css';

interface Props {
  title?: string;
  hint?: string;
}

export const EmptyView = ({ title = '暂无数据', hint }: Props) => {
  return (
    <div className={styles.wrap}>
      <div className={styles.title}>{title}</div>
      {hint ? <div className={styles.hint}>{hint}</div> : null}
    </div>
  );
};
