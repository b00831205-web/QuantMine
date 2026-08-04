import { PaginatedTable } from '@/components/common/PaginatedTable';
import type { Column } from '@/components/common/PaginatedTable';
import type { Page } from '@/types/api';
import type { QueryResult } from '@/types/data';

/** 把 QueryResult（columns + rows）渲染成表格：负责数据形态适配和动态列 */
export const QueryResultTable = ({ result }: { result: QueryResult }) => {
  const pageData: Page<Record<string, unknown>> = {
    items: result.rows,
    total: result.rows.length,
    page: 1,
    pageSize: result.rows.length || 1,
  };
  const columns: Column<Record<string, unknown>>[] = result.columns.map((name) => ({
    key: name,
    header: name,
    align: 'left',
    render: (row: Record<string, unknown>) => String(row[name] ?? ''),
  }));
  return (
    <PaginatedTable
      columns={columns}
      page={pageData}
      rowKey={(row) => JSON.stringify(row)}
      emptyHint="无结果"
    />
  );
};
