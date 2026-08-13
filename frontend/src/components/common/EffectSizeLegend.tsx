/**
 * Key for the grey-to-blue ramp on the significance chips.
 *
 * The chips carry two facts at once -- the word says the IC is reliably
 * non-zero, the colour says how large it is -- and a reader has no way to know
 * the second one is there without being told.
 *
 * The ends are labelled by size rather than by significance on purpose. Grey
 * covers both "not significant" and "significant but tiny", so a grey-to-blue
 * bar reading "not significant → significant" would contradict the very chips
 * it explains: a 0.9% IC prints the word "significant" in grey.
 */
import { useTranslation } from 'react-i18next';

import { STRONG_IC } from '@/utils/effectSize';
import styles from './EffectSizeLegend.module.css';

export const EffectSizeLegend = () => {
  const { t } = useTranslation();
  const strong = `${(STRONG_IC * 100).toFixed(0)}%`;

  return (
    <span className={styles.legend}>
      <span className={styles.label}>{t('research.effectSize.weak')}</span>
      <span className={styles.ramp} aria-hidden="true" />
      <span className={styles.label}>{t('research.effectSize.strong', { strong })}</span>
    </span>
  );
};
