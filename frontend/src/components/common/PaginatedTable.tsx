import { useTranslation } from 'react-i18next';
import type { Page as PageT } from '@/types/api';
import styles from './PaginatedTable.module.css';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: 'left' | 'center' |'right';
  width?: number | string;
}

interface Props<T> {
  columns: Column<T>[];
  page: PageT<T>;
  onPageChange?: (page: number) => void;
  rowKey: (row: T) => string;
  emptyHint?: string;
  onRowClick?:(row: T) =>void;
  onRowDoubleClick?:(row: T) =>void;
  // 显式 | undefined：exactOptionalPropertyTypes 下调用方会条件式传入 undefined
  selectedRowKey?: string | undefined;
}

export function PaginatedTable<T>({
  columns,
  page,
  onPageChange,
  rowKey,
  emptyHint,
  onRowClick,
  onRowDoubleClick,
  selectedRowKey,
}: Props<T>) {
  const { t } = useTranslation();
  if (page.items.length === 0) {
    return <div className={styles.empty}>{emptyHint ?? t('common.noMatch')}</div>;
  }
  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align ?? 'left' }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.items.map((row) => {
            const key = rowKey(row);
            const isSelected = selectedRowKey !== undefined && selectedRowKey === key;
            return (
              <tr
                key={key}
                className={isSelected ? styles.selected : undefined}
                onClick={() => onRowClick?.(row)}
                onDoubleClick={() => onRowDoubleClick?.(row)}
              >
                {columns.map((c) => (
                  <td key={c.key} style={{ textAlign: c.align ?? 'left' }}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <footer className={styles.footer}>
        <span>
          {t('common.pagination', {
            total: page.total,
            page: page.page,
            pages: Math.max(1, Math.ceil(page.total / page.pageSize)),
          })}
        </span>
        <div className={styles.pager}>
          <button
            disabled={page.page <= 1}
            onClick={() => onPageChange?.(page.page - 1)}
            className={styles.btn}
          >
            {t('common.prevPage')}
          </button>
          <button
            disabled={page.page * page.pageSize >= page.total}
            onClick={() => onPageChange?.(page.page + 1)}
            className={styles.btn}
          >
            {t('common.nextPage')}
          </button>
        </div>
      </footer>
    </div>
  );
}
