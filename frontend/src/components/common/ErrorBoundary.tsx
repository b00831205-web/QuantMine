import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ErrorView } from './ErrorView';
import type { ApiError } from '@/types/api';

interface Props {
  children: ReactNode;
}

interface State {
  error: ApiError | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return {
      error: {
        status: 500,
        code: 'INTERNAL_ERROR',
        title: '页面渲染异常',
        detail: error.message,
      },
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 阶段 0 仅 console；阶段 8 接入真实审计上报
    console.error('[ErrorBoundary]', error, info);
  }

  handleRetry = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      return <ErrorView error={this.state.error} onRetry={this.handleRetry} />;
    }
    return this.props.children;
  }
}
