import styles from './TopBar.module.css';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  fetchAIConfig,
  fetchAIModels,
  fetchLatestMarketDate,
  fetchWorkflows,
  saveAIConfig,
  fetchMe,
  logout,
} from '@/api/client';
import { stateLabel, stateColor } from '@/utils/workflowStatus';
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
  useEffect(() => {
    const controller = new AbortController();
    fetchWorkflows(controller.signal)
      .then((dags) => {
        if (controller.signal.aborted) return;
        const runs = dags
          .flatMap((dag) => dag.recentRuns ?? [])
          .filter((run) => run.startDate !== null)
          .sort((a, b) => (b.startDate! > a.startDate! ? 1 : -1));
        const latest = runs[0];
        setTaskStatus(
          latest ? { label: stateLabel(latest.state), color: stateColor(latest.state) } : null,
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setTaskStatus(null);
      });
    return () => controller.abort();
  }, []);

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
