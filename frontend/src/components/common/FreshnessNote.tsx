/**
 * 「这块数据有多新」的小标注。
 *
 * 存在的理由：自动刷新如果是无声的，用户看到一个不动的界面时，仍然分不清是
 * 「任务还没跑完」还是「页面又卡住了」——那正是自动刷新想解决的困惑本身。
 * 所以把刷新这件事显性化：正在刷新、上次成功刷新于何时、刷新是否已经失败。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import styles from './FreshnessNote.module.css';

export interface FreshnessNoteProps {
  lastUpdatedAt: number | null;
  isRefreshing: boolean;
  /** 后台刷新连续失败：屏幕上还是旧数据，必须说清楚，不能假装是新的。 */
  isStale: boolean;
  /** 当前轮询间隔，用于决定「n 秒前」这行字多久重算一次。 */
  pollMs: number;
}

const fmtClock = (ts: number): string =>
  new Date(ts).toLocaleTimeString(undefined, { hour12: false });

export const FreshnessNote = ({
  lastUpdatedAt,
  isRefreshing,
  isStale,
  pollMs,
}: FreshnessNoteProps) => {
  const { t } = useTranslation();
  // 只用来驱动重渲染，让「最后更新」随时间走字；节奏跟轮询一致就够了。
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setTick((n) => n + 1), Math.min(pollMs, 10000));
    return () => window.clearInterval(timer);
  }, [pollMs]);

  if (lastUpdatedAt === null) return null;

  return (
    <span
      className={`${styles.note} ${isStale ? styles.stale : ''}`}
      // 状态变化要让读屏用户也知道，但别打断当前朗读。
      aria-live="polite"
    >
      <span
        className={`${styles.dot} ${isRefreshing ? styles.dotActive : ''}`}
        aria-hidden="true"
      />
      {isStale
        ? t('workflow.freshness.stale', { time: fmtClock(lastUpdatedAt) })
        : t('workflow.freshness.updated', { time: fmtClock(lastUpdatedAt) })}
    </span>
  );
};
