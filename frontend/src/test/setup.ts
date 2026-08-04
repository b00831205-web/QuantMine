import '@testing-library/jest-dom/vitest';
import i18n from '@/i18n';

// 测试环境锁定中文，让断言中的中文文案稳定；真实运行时才走 navigator.language 检测
void i18n.changeLanguage('zh');
