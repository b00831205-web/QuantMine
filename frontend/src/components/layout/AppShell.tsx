import { Outlet, useLocation } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { AliveScope, KeepAlive } from 'react-activation';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';
import { AIQuickPanel } from '../ai/AIQuickPanel';
import styles from './AppShell.module.css';

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

  // 切换路由时回到内容区顶部（页面本身由 KeepAlive 缓存，不重新挂载）
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
            <KeepAlive
              id={pathname}
              name={pathname}
              wrapperProps={{ className: onAiWorkbench ? styles.keepAliveFullHeight : '' }}
              contentProps={{ className: onAiWorkbench ? styles.keepAliveFullHeight : '' }}
            >
              <Outlet />
            </KeepAlive>
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
