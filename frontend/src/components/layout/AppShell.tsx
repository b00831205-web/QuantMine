import { Outlet } from 'react-router-dom';
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
  return (
    <div className={styles.shell}>
      <SideNav />
      <div className={styles.main}>
        <TopBar />
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
      <AIQuickPanel />
    </div>
  );
};
