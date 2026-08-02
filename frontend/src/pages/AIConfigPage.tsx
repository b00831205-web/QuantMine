import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * AI 配置（阶段 0 占位，仅管理员可修改）。
 * 阶段 7 实现：模型供应商、模型列表、知识库、Skill、外部 API、权限策略、调用日志。
 */
export const AIConfigPage = () => {
  const sections = [
    'Agent 基本设置',
    '模型供应商 / 模型',
    'RAG 知识库',
    'Skill / 工具注册',
    '外部 API',
    '权限与确认策略',
    '调用日志',
  ];
  return (
    <>
      <PageHeader title="AI 配置" subtitle="类似 Dify 的集中配置页 · 仅管理员可改" />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--sp-3)' }}>
        {sections.map((s) => (
          <Card key={s} title={s} minHeight={160}>
            <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 7 接入</div>
          </Card>
        ))}
      </div>
    </>
  );
};
