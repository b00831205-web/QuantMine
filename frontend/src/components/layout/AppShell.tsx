import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { AliveScope, KeepAlive } from 'react-activation';
import { SideNav } from './SideNav';
import { NAV_ITEMS } from './navItems';
import { TopBar } from './TopBar';
import { AIQuickPanel } from '../ai/AIQuickPanel';
import styles from './AppShell.module.css';

/**
 * 只有侧栏那几个页面值得缓存：切标签页时保住筛选和滚动位置。
 * 详情页（/research/factors/:factorName 等）必须排除——被缓存的页面永不卸载，
 * 它的请求照旧返回、effect 照旧写 URL，等你打开下一个因子时把地址栏 replace 回
 * 上一个，于是详情页显示的是上次选中的因子；顺带还会为每个访问过的参数留一份缓存。
 */
const CACHED_PATHS = new Set(NAV_ITEMS.map((item) => item.to));

const isCacheable = (pathname: string): boolean =>
  CACHED_PATHS.has(pathname.length > 1 ? pathname.replace(/\/$/, '') : pathname);

/**
 * 全局布局：
 * - 左侧固定 SideNav
 * - 顶部 TopBar（数据日期、用户、模型）
 * - 中间主区域 Outlet
 * - 右侧 AI 快捷窗口（仅页面 1~6 渲染，AI 工作台自身不重复显示）
 * - 小屏：AI 快捷窗口收起为右下角浮动按钮
 */
export const AppShell = () => {
  const { pathname } = useLocation();
  // Only the conversation workbench owns a fixed-height viewport. AI Config is
  // a regular, document-length settings page and must keep the shell scroller.
  const onAiWorkbench = pathname === '/ai' || pathname === '/ai/';
  const [aiOpen, setAiOpen] = useState(false);
  const contentRef = useRef<HTMLElement | null>(null);

  // 切换路由时回到内容区顶部（侧栏页面由 KeepAlive 缓存，不重新挂载）
  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [pathname]);

  return (
    <AliveScope>
      <div
        className={styles.shell}
        style={{
          gridTemplateColumns:
            onAiWorkbench || !aiOpen
              ? 'var(--sidenav-w) 1fr'
              : 'var(--sidenav-w) 1fr var(--ai-quickpanel-w)',
        }}
      >
        <SideNav />
        <div className={styles.main}>
          <TopBar />
          <main
            className={`${styles.content} ${onAiWorkbench ? styles.workbenchContent : ''}`}
            ref={contentRef}
          >
            {isCacheable(pathname) ? (
              <KeepAlive
                id={pathname}
                name={pathname}
                wrapperProps={{ className: onAiWorkbench ? styles.keepAliveFullHeight : '' }}
                contentProps={{ className: onAiWorkbench ? styles.keepAliveFullHeight : '' }}
              >
                <Outlet />
              </KeepAlive>
            ) : (
              <Outlet />
            )}
          </main>
        </div>
        <AIQuickPanel
          open={aiOpen}
          onOpen={() => setAiOpen(true)}
          onClose={() => setAiOpen(false)}
        />
      </div>
    </AliveScope>
  );
};
