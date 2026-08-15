export interface NavItem {
  to: string;
  labelKey: string;
  group: 'core' | 'ai';
  /** true 时 NavLink 精确匹配（/ai 不能匹配 /ai/config 前缀） */
  end?: boolean;
}

/** 侧栏页面。AppShell 只缓存这几个路径，见那里的注释。 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/market', labelKey: 'nav.market', group: 'core' },
  { to: '/rebalance', labelKey: 'nav.rebalance', group: 'core' },
  { to: '/workflows', labelKey: 'nav.workflows', group: 'core' },
  { to: '/research', labelKey: 'nav.research', group: 'core' },
  { to: '/data', labelKey: 'nav.data', group: 'core' },
  { to: '/reports', labelKey: 'nav.reports', group: 'core' },
  { to: '/ai', labelKey: 'nav.ai', group: 'ai', end: true },
  { to: '/ai/config', labelKey: 'nav.aiConfig', group: 'ai' },
];
