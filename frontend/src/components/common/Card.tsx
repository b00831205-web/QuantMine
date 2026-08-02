import type { ReactNode } from 'react';
import styles from './Card.module.css';

interface Props {
  title?: string;
  extra?: ReactNode;
  children: ReactNode;
  /** 控制最小高度，便于 loading/empty 状态不抖动 */
  minHeight?: number;
}

export const Card = ({ title, extra, children, minHeight = 160 }: Props) => {
  return (
    <section className={styles.card} style={{ minHeight }}>
      {title ? (
        <header className={styles.header}>
          <h3 className={styles.title}>{title}</h3>
          {extra ? <div className={styles.extra}>{extra}</div> : null}
        </header>
      ) : null}
      <div className={styles.body}>{children}</div>
    </section>
  );
};
