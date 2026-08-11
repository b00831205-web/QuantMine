import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { fetchServices, setServiceAutostart } from '@/api/client';
import type { ServiceState } from '@/api/client/services';
import { toUserMessage } from '@/api/http';
import type { ApiError } from '@/types/api';
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
  const [services, setServices] = useState<ServiceState[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const getServiceLabel = (service: ServiceState): string =>
    t(`nav.services.${service.name}.label`, { defaultValue: service.label });

  const getServiceDescription = (service: ServiceState): string =>
    t(`nav.services.${service.name}.description`, {
      defaultValue: service.description,
    });

  useEffect(() => {
    const controller = new AbortController();
    fetchServices(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        // isSelf 排最后：它是最危险的一个（关掉后下次开机打不开本页面），
        // 不该是列表里最顺手点到的那个。
        setServices([...data].sort((a, b) => Number(a.isSelf) - Number(b.isSelf)));
      })
      .catch(() => {
        // 整块隐藏，而不是渲染一排“已关闭”——那会让人以为自启真的是关的
        if (!controller.signal.aborted) setServices(null);
      });
    return () => controller.abort();
  }, []);

  const handleToggleAutostart = async (service: ServiceState): Promise<void> => {
    if (!service.installed || busy) return;
    // 这个服务就是当前进程：关掉自启后下次开机需要手动启动才能打开本页面
    if (service.isSelf && service.autostart === true) {
      if (!window.confirm(t('nav.autostartConfirm', { label: getServiceLabel(service) }))) return;
    }
    setBusy(service.name);
    setError(null);
    try {
      const next = await setServiceAutostart(service.name, !service.autostart);
      setServices((prev) =>
        (prev ?? []).map((s) => (s.name === next.name ? next : s)),
      );
    } catch (err) {
      // 静默失败的话，用户只会看到“点了没反应”，分不清是点歪了还是后端拒绝了。
      // 后端在这里是给了可操作信息的（如「尚未安装；先运行 install-services.sh」），
      // 丢掉它等于把唯一的线索扔了。
      setError(toUserMessage(err as ApiError));
    } finally {
      setBusy(null);
    }
  };

  return (
    <aside className={styles.nav}>
      <div className={styles.brand}>
        <img
          className={styles.brandLogo}
          src="/brand/quantmine-blue.png"
          alt=""
          aria-hidden="true"
        />
        <span>QUANTMINE</span>
      </div>
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
      {services && services.length > 0 ? (
        <div className={styles.autostartBlock}>
          <div className={styles.autostartHeading}>{t('nav.autostart')}</div>
          {services.map((service) => {
            const label = getServiceLabel(service);
            const description = getServiceDescription(service);

            return (
              <div key={service.name} className={styles.autostartRow}>
                <span className={styles.autostartLabel} title={description}>
                  {label}
                </span>
                {service.installed ? (
                  <button
                    type="button"
                    role="switch"
                    aria-checked={service.autostart === true}
                    aria-label={`${t('nav.autostart')} — ${label}`}
                    disabled={busy !== null}
                    className={
                      service.autostart === true
                        ? `${styles.autoSwitch} ${styles.autoSwitchOn}`
                        : styles.autoSwitch
                    }
                    onClick={() => void handleToggleAutostart(service)}
                  >
                    <span className={styles.autoThumb} />
                  </button>
                ) : (
                  <span className={styles.autostartMissing} title={t('nav.autostartNotInstalled')}>
                    {t('nav.autostartNotInstalled')}
                  </span>
                )}
              </div>
            );
          })}
          {error ? (
            <p className={styles.autostartError} role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
      <div className={styles.footer}>v0.0 · stage 0</div>
    </aside>
  );
};
