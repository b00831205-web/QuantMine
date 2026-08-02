import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * AI 工作台（阶段 0 占位）。
 * 阶段 7 实现：完整对话、模型选择、引用、工具调用摘要、高影响操作确认。
 */
export const AIWorkbenchPage = () => {
  return (
    <>
      <PageHeader
        title="AI 工作台"
        subtitle="覆盖全流程的 Agent · 非按页面拆分的多 Agent"
      />
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 'var(--sp-3)', height: 'calc(100vh - 180px)' }}>
        <Card title="对话历史" minHeight={400}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            全局保存；可绑定多个 research run
          </div>
        </Card>
        <Card title="对话" minHeight={400}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-3)' }}>
            模型选择 · 完整消息 · 引用来源 · 工具调用 · 高影响操作确认卡片
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 7 接入</div>
        </Card>
      </div>
    </>
  );
};
