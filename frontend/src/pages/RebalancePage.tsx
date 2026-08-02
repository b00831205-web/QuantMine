import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * 调仓收益（阶段 0 占位）。
 * 阶段 3 实现：周期收益、SPY、超额、换手率、持仓与贡献表。
 */
export const RebalancePage = () => {
  return (
    <>
      <PageHeader
        title="调仓收益"
        subtitle="正式策略组合的当前与历史调仓表现"
      />
      <Card title="筛选条件" minHeight={120}>
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          backtest job · variant · factor · holding period · quantile/long-short · rebalance batch
        </div>
      </Card>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--sp-3)' }}>
        <Card title="当前调仓周期" minHeight={200}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            累计净收益 · 同期 SPY · 超额收益 · 换手率 · 持仓数量 · 距下次调仓
          </div>
        </Card>
        <Card title="净值 vs SPY" minHeight={200}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 3 接入图表</div>
        </Card>
        <Card title="当前持仓" minHeight={200}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 3 接入表格</div>
        </Card>
        <Card title="单股收益贡献" minHeight={200}>
          <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 3 接入表格</div>
        </Card>
      </div>
    </>
  );
};
