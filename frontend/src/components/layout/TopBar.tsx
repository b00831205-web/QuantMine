import styles from './TopBar.module.css';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import { runAwarePollMs, usePolledAsync } from '@/hooks/usePolledAsync';
import {
  fetchAIConfig,
  fetchAIModels,
  fetchLatestMarketDate,
  fetchWorkflows,
  saveAIConfig,
  fetchMe,
  logout,
} from '@/api/client';
import { stateLabel, stateColor, isActiveState } from '@/utils/workflowStatus';
import type { AIConfig } from '@/types/ai';

/**
 * 顶部状态条：数据日期、运行状态、用户角色、模型选择占位。
 * 阶段 0 只展示静态骨架，所有数据后续由 store/hook 注入。
 */

export const TopBar = () => {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [username, setUsername] = useState<string>('');
  const [latestTradeDate, setLatestTradeDate] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<{ label: string; color: string } | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [savingModel, setSavingModel] = useState(false);
  useEffect(() => {
    fetchLatestMarketDate()
      .then((data) => {
        setLatestTradeDate(data.latestTradeDate);
      })
      .catch(() => {
        setLatestTradeDate(null);
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((user) => {
        if (!controller.signal.aborted) setUsername(user?.username ?? '');
      })
      .catch(() => {
        if (!controller.signal.aborted) setUsername('');
      });
    return () => controller.abort();
  }, []);

  const handleLogout = async (): Promise<void> => {
    try {
      await logout();
    } finally {
      navigate('/login', { replace: true });
    }
  };
  // 这个指示器以前只在挂载时取一次，而 TopBar 挂在 AppShell 上、切页面不会重新挂载，
  // 所以 DAG 跑起来它纹丝不动，跑完也不变——必须整页刷新才更新。改成轮询：有任务在跑
  // 5 秒一次，空闲 30 秒一次（空闲也要轮，否则新 run 起来没人发现）。
  const [hasActiveRun, setHasActiveRun] = useState(false);
  const workflowsPoll = usePolledAsync((s) => fetchWorkflows(s), [], {
    pollMs: runAwarePollMs(hasActiveRun),
  });

  const latestRun = useMemo(() => {
    if (workflowsPoll.state.status !== 'success') return null;
    const runs = workflowsPoll.state.data
      .flatMap((dag) => dag.recentRuns ?? [])
      .filter((run) => run.startDate !== null)
      .sort((a, b) => (b.startDate! > a.startDate! ? 1 : -1));
    return runs[0] ?? null;
  }, [workflowsPoll.state]);

  useEffect(() => {
    setHasActiveRun(isActiveState(latestRun?.state));
    setTaskStatus(
      latestRun
        ? { label: stateLabel(latestRun.state), color: stateColor(latestRun.state) }
        : null,
    );
  }, [latestRun]);

  // 模型列表 + 全局默认模型：路由变化时刷新，配置页改完切回来能同步
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchAIModels(controller.signal), fetchAIConfig(controller.signal)])
      .then(([modelList, cfg]) => {
        if (controller.signal.aborted) return;
        setModels(modelList);
        setConfig(cfg);
        setSelectedModel(cfg.defaultModel || modelList[0] || '');
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setModels([]);
          setSelectedModel('');
        }
      });
    return () => controller.abort();
  }, [pathname]);

  const handleModelChange = async (value: string): Promise<void> => {
    if (!config || value === selectedModel) return;
    const previous = selectedModel;
    setSelectedModel(value);
    setSavingModel(true);
    try {
      const saved = await saveAIConfig({ ...config, defaultModel: value });
      setConfig(saved);
    } catch {
      setSelectedModel(previous);
    } finally {
      setSavingModel(false);
    }
  };
  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <span className={styles.label}>{t('topbar.dataDate')}</span>
        <span className={styles.value}>{latestTradeDate ?? '-'}</span>
        <span className={styles.sep}>·</span>
        <span className={styles.label}>{t('topbar.latestTask')}</span>
        <span
          className={styles.badge}
          style={taskStatus ? { color: taskStatus.color, background: 'transparent' } : undefined}
        >
          {taskStatus ? taskStatus.label : t('workflow.state.none')}
        </span>
      </div>
      <div className={styles.right}>
        <span className={styles.label}>{t('topbar.model')}</span>
        <select
          className={styles.modelSelect}
          value={selectedModel}
          disabled={models.length === 0 || savingModel}
          onChange={(e) => handleModelChange(e.target.value)}
        >
          {models.length === 0 ? (
            <option value="">{t('topbar.notConfigured')}</option>
          ) : (
            models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))
          )}
        </select>
        <span className={styles.user}>{username || 'guest'}</span>
        <button className={styles.logout} type="button" onClick={handleLogout}>
          {t('topbar.logout')}
        </button>
      </div>
    </header>
  );
};
