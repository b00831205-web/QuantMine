import { NavLink } from 'react-router-dom';
import styles from './SideNav.module.css';

interface NavItem {
  to: string;
  label: string;
  group: 'core' | 'ai';
}

const ITEMS: NavItem[] = [
  { to: '/market', label: '市场总览', group: 'core' },
  { to: '/rebalance', label: '调仓收益', group: 'core' },
  { to: '/workflows', label: 'Airflow 工作流', group: 'core' },
  { to: '/research', label: '研究结果', group: 'core' },
  { to: '/data', label: '数据库速查', group: 'core' },
  { to: '/reports', label: 'PDF 报告', group: 'core' },
  { to: '/ai', label: 'AI 工作台', group: 'ai' },
  { to: '/ai/config', label: 'AI 配置', group: 'ai' },
];

export const SideNav = () => {
  const core = ITEMS.filter((i) => i.group === 'core');
  const ai = ITEMS.filter((i) => i.group === 'ai');
  return (
    <aside className={styles.nav}>
      <div className={styles.brand}>QUANTMINE</div>
      <nav className={styles.list}>
        {core.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}>
            {item.label}
          </NavLink>
        ))}
        <div className={styles.divider} />
        {ai.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className={styles.footer}>v0.0 · stage 0</div>
    </aside>
  );
};
