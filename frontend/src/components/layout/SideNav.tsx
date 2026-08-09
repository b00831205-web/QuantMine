import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import styles from './SideNav.module.css';

interface NavItem {
  to: string;
  labelKey: string;
  group: 'core' | 'ai';
  /** true 时 NavLink 精确匹配（/ai 不能匹配 /ai/config 前缀） */
  end?: boolean;
}

const ITEMS: NavItem[] = [
  { to: '/market', labelKey: 'nav.market', group: 'core' },
  { to: '/rebalance', labelKey: 'nav.rebalance', group: 'core' },
  { to: '/workflows', labelKey: 'nav.workflows', group: 'core' },
  { to: '/research', labelKey: 'nav.research', group: 'core' },
  { to: '/data', labelKey: 'nav.data', group: 'core' },
  { to: '/reports', labelKey: 'nav.reports', group: 'core' },
  { to: '/ai', labelKey: 'nav.ai', group: 'ai', end: true },
  { to: '/ai/config', labelKey: 'nav.aiConfig', group: 'ai' },
];

export const SideNav = () => {
  const { t } = useTranslation();
  const core = ITEMS.filter((i) => i.group === 'core');
  const ai = ITEMS.filter((i) => i.group === 'ai');
  return (
    <aside className={styles.nav}>
      <div className={styles.brand}>QUANTMINE</div>
      <nav className={styles.list}>
        {core.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            {...(item.end ? { end: true } : {})}
            className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
          >
            {t(item.labelKey)}
          </NavLink>
        ))}
        <div className={styles.divider} />
        {ai.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            {...(item.end ? { end: true } : {})}
            className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
          >
            {t(item.labelKey)}
          </NavLink>
        ))}
      </nav>
      <div className={styles.footer}>v0.0 · stage 0</div>
    </aside>
  );
};
