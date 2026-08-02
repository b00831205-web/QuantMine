import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * 数据库速查（阶段 0 占位）。
 * 阶段 5 实现：白名单表/字段、结构化筛选、服务端分页、CSV 导出。
 * 严禁任意 SQL、任意 join、任意写入。
 */
export const DataExplorerPage = () => {
  return (
    <>
      <PageHeader
        title="数据库速查"
        subtitle="白名单业务对象 · 服务端筛选/排序/分页 · CSV 导出"
      />
      <Card title="资源目录" minHeight={120}>
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          market_latest · market_bars · research_runs · test_results · backtest_results · backtest_metrics · IC/test/backtest artifacts
        </div>
      </Card>
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 'var(--sp-3)', marginTop: 'var(--sp-3)' }}>
        <Card title="字段说明" minHeight={300}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 5 接入字段说明面板</div>
        </Card>
        <Card title="结果" minHeight={300}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 5 接入分页表格 + 导出</div>
        </Card>
      </div>
    </>
  );
};
