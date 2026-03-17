import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      let errorMessage = this.state.error?.message || 'An unexpected error occurred.';
      let parsedError = null;

      try {
        parsedError = JSON.parse(errorMessage);
        errorMessage = parsedError.error || errorMessage;
      } catch (e) {
        // Not a JSON string, use as is
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-200 p-4">
          <div className="max-w-md w-full bg-zinc-900 border border-zinc-800 rounded-xl p-6 shadow-xl">
            <h2 className="text-xl font-semibold text-red-400 mb-4">Something went wrong</h2>
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-800 overflow-auto max-h-64">
              <p className="text-sm font-mono text-zinc-400 whitespace-pre-wrap">
                {errorMessage}
              </p>
              {parsedError && parsedError.path && (
                <p className="text-xs text-zinc-500 mt-2">Path: {parsedError.path}</p>
              )}
            </div>
            <button
              className="mt-6 w-full py-2 px-4 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition-colors"
              onClick={() => window.location.reload()}
            >
              Reload Application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
