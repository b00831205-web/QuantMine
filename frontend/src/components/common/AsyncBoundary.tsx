import type { AsyncState } from '@/types/api';
import { LoadingView } from './LoadingView';
import { ErrorView } from './ErrorView';
import { EmptyView } from './EmptyView';

interface Props<T> {
  state: AsyncState<T>;
  /** 当 state 处于 success 时使用的渲染函数；children 也可作为函数传入 */
  children: (data: T) => React.ReactNode;
  /** empty 判定：当 data 为空数组或 null 时视为 empty */
  isEmpty?: (data: T) => boolean;
  /** 重试回调，error 时显示 */
  onRetry?: () => void;
  /** empty 文案 */
  emptyTitle?: string;
  emptyHint?: string;
}

/**
 * 异步数据四态边界：
 *   loading | empty | error | success
 *
 * 阶段 0 仅渲染骨架；具体 DOM 结构与样式由对应的 *View 组件承载。
 */
export function AsyncBoundary<T>({
  state,
  children,
  isEmpty,
  onRetry,
  emptyTitle = '暂无数据',
  emptyHint,
}: Props<T>) {
  if (state.status === 'loading' || state.status === 'idle') {
    return <LoadingView />;
  }
  if (state.status === 'error') {
    if (onRetry){
    return <ErrorView error={state.error} onRetry={onRetry} />;
  }
    return <ErrorView error = {state.error}/>;  
}
  if (state.status === 'success') {
    if (isEmpty?.(state.data) === true) {
      if (emptyHint){
      return <EmptyView title={emptyTitle} hint={emptyHint} />;
    }
    return <EmptyView title = {emptyTitle}/>}
    return <>{children(state.data)}</>;
  }
  return null;
}
