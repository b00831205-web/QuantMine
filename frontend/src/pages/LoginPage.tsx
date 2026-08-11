import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '@/api/client/auth';
import { HttpError } from '@/api/http';
import styles from './LoginPage.module.css';

/**
 * 登录页（Airflow 风格：居中卡片）。
 * 成功后后端下发会话 Cookie，前端跳回首页；AuthGuard 会放行。
 */
export const LoginPage = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(
        err instanceof HttpError
          ? err.apiError.detail ?? err.apiError.title ?? t('login.failed')
          : t('login.failed'),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <div className={styles.brandLockup}>
          <img
            className={styles.brandLogo}
            src="/brand/quantmine-blue.png"
            alt=""
            aria-hidden="true"
          />
          <div className={styles.brand}>QUANTMINE</div>
        </div>
        <div className={styles.subtitle}>{t('login.subtitle')}</div>

        <label className={styles.field}>
          <span>{t('login.username')}</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
          />
        </label>

        <label className={styles.field}>
          <span>{t('login.password')}</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        {error && <div className={styles.error}>{error}</div>}

        <button
          className={styles.submit}
          type="submit"
          disabled={submitting || !username || !password}
        >
          {submitting ? t('login.loggingIn') : t('login.login')}
        </button>
      </form>
    </div>
  );
};
