import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { MarketOverviewPage } from './pages/MarketOverviewPage';
import { RebalancePage } from './pages/RebalancePage';
import { WorkflowsPage } from './pages/WorkflowsPage';
import { ResearchPage } from './pages/ResearchPage';
import { FactorDetailPage } from './pages/FactorDetailPage';
import { DataExplorerPage } from './pages/DataExplorerPage';
import { ReportsPage } from './pages/ReportsPage';
import { AIWorkbenchPage } from './pages/AIWorkbenchPage';
import { AIConfigPage } from './pages/AIConfigPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/market" replace /> },
      { path: 'market', element: <MarketOverviewPage /> },
      { path: 'rebalance', element: <RebalancePage /> },
      { path: 'workflows', element: <WorkflowsPage /> },
      { path: 'research', element: <ResearchPage /> },
      { path: 'research/factors/:factorName', element: <FactorDetailPage /> },
      { path: 'data', element: <DataExplorerPage /> },
      { path: 'reports', element: <ReportsPage /> },
      { path: 'ai', element: <AIWorkbenchPage /> },
      { path: 'ai/config', element: <AIConfigPage /> },
    ],
  },
]);
