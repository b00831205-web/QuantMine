import { useParams, useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/common/Card';

/**
 * 第二页（DAG 详情：图/网格视图 + 概览/运行/任务/代码 标签页）占位。
 * 第一页评审通过后再实现。此处仅保证列表页点击不 404。
 */
export const WorkflowDetailPage = () => {
  const { dagId } = useParams<{ dagId: string }>();
  const navigate = useNavigate();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <PageHeader
        title={dagId ?? 'DAG'}
        subtitle="DAG 详情页（第二页）"
        actions={
          <button type="button" onClick={() => navigate('/workflows')}>
            ← 返回列表
          </button>
        }
      />
      <Card title="开发中">
        <div style={{ color: 'var(--text-muted)', padding: 'var(--sp-5)', lineHeight: 1.6 }}>
          第二页（图视图 + 概览/运行记录/任务/代码 标签页，节点按状态着色）将在第一页评审通过后实现。
        </div>
      </Card>
    </div>
  );
};
