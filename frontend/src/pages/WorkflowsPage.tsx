import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * Airflow 工作流（阶段 0 占位）。
 * 阶段 4 实现：状态、节点拓扑、历史运行、日志摘要、确认触发/重跑。
 */
export const WorkflowsPage = () => {
  return (
    <>
      <PageHeader
        title="Airflow 工作流"
        subtitle="DAG 整体状态 · 不复制完整 Airflow 管理后台"
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--sp-3)' }}>
        <Card title="DAG 状态" minHeight={140}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            当前状态 · 最近 run · 数据日期 · 总耗时 · 下次计划
          </div>
        </Card>
        <Card title="节点拓扑" minHeight={140}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            下载/清洗/因子/IC/入库/回测 节点状态、耗时、重试次数
          </div>
        </Card>
        <Card title="历史运行" minHeight={140}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 4 接入表格</div>
        </Card>
        <Card title="日志摘要" minHeight={140}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 4 接入</div>
        </Card>
      </div>
    </>
  );
};
