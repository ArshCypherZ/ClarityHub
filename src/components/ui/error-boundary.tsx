'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from './button';
import { H2 } from '../typography/h2';
import { Para } from '../typography/para';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-[50vh] flex-col items-center justify-center text-center">
          <H2>Something went wrong</H2>
          <Para className="mt-2 text-gray-600">
            {this.state.error?.message || 'An error occurred while displaying this content'}
          </Para>
          <Button
            className="mt-4"
            onClick={() => this.setState({ hasError: false })}
          >
            Try again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}