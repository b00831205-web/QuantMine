import type { CSSProperties, ReactNode } from 'react';
import styles from './Card.module.css';

interface Props {
  title?: string;
  extra?: ReactNode;
  children: ReactNode;
  /** 控制最小高度，便于 loading/empty 状态不抖动 */
  minHeight?: number;
  /** 透传到卡根元素，用于布局（如撑满高度） */
  style?: CSSProperties;
}

export const Card = ({ title, extra, children, minHeight = 160, style }: Props) => {
  return (
    <section className={styles.card} style={{ minHeight, ...style }}>
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
