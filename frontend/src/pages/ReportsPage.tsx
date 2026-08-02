import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * PDF 报告（阶段 0 占位）。
 * 阶段 6 实现：异步生成任务、状态查询、预览、下载、历史记录。
 */
export const ReportsPage = () => {
  return (
    <>
      <PageHeader
        title="PDF 报告"
        subtitle="可打印 · 可下载 · 可追溯的研究报告"
      />
      <Card title="新建报告" minHeight={140}>
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          research run · variants · tests · backtest jobs · 章节选择
        </div>
      </Card>
      <Card title="报告历史" minHeight={240} extra={<button disabled>刷新</button>}>
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>阶段 6 接入分页表格 + 状态徽标 + 下载按钮</div>
      </Card>
    </>
  );
};
