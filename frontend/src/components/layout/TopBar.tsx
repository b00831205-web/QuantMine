import styles from './TopBar.module.css';
import { useEffect, useState } from 'react';
import { fetchLatestMarketDate } from '@/api/client';

/**
 * 顶部状态条：数据日期、运行状态、用户角色、模型选择占位。
 * 阶段 0 只展示静态骨架，所有数据后续由 store/hook 注入。
 */

export const TopBar = () => {
  const [latestTradeDate, setLatestTradeDate] = useState<string | null> (null);
  useEffect(()=>{
    fetchLatestMarketDate().then((data) => {setLatestTradeDate(data.latestTradeDate);}).catch(()=>{setLatestTradeDate(null);})
  },[])
  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <span className={styles.label}>数据日期</span>
        <span className={styles.value}>{latestTradeDate ?? '-'}</span>
        <span className={styles.sep}>·</span>
        <span className={styles.label}>最新任务</span>
        <span className={styles.badge}>IDLE</span>
      </div>
      <div className={styles.right}>
        <span className={styles.label}>模型</span>
        <select className={styles.modelSelect} disabled>
          <option>未配置</option>
        </select>
        <span className={styles.user}>guest</span>
      </div>
    </header>
  );
};
