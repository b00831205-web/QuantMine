import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import zh from './locales/zh.json';

/**
 * i18n 初始化。
 * - LanguageDetector 读取系统/浏览器语言（navigator.language）、localStorage、URL ?lng=
 * - supportedLngs 限定为 en / zh；nonExplicitSupportedLngs 让 zh-CN、zh-TW → zh，en-US → en
 * - 命中不了支持列表的语言（如 fr、ja）回退到英文
 * 新增语言：加一个 locales/xx.json，在 resources 与 supportedLngs 里登记即可。
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
