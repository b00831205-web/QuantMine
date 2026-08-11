import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import zh from './locales/zh.json';

/**
 * i18n initialization.
 * - LanguageDetector reads the system/browser language (navigator.language),
 *   localStorage, and the URL's ?lng=
 * - supportedLngs is limited to en / zh; nonExplicitSupportedLngs maps zh-CN and
 *   zh-TW to zh, and en-US to en
 * - languages outside the supported list (fr, ja, ...) fall back to English
 * To add a language: drop in a locales/xx.json and register it in resources and
 * supportedLngs.
 */
void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh'],
    nonExplicitSupportedLngs: true,
    interpolation: {
      escapeValue: false, // React 自身已做 XSS 转义
    },
    detection: {
      order: ['querystring', 'localStorage', 'navigator'],
      lookupQuerystring: 'lng',
      caches: ['localStorage'],
    },
    react: {
      useSuspense: false, // 资源已随包内联，无需 Suspense 异步加载
    },
  });

export default i18n;
