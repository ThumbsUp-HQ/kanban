/**
 * Blatant, Dismissible On-Screen Error Modal & Boundaries.
 * Strict CSP Compliant (style-src 'self', zero inline style attributes).
 */

import React, {
  Component,
  useState,
  useCallback,
  type ErrorInfo,
  type ReactNode,
  type JSX,
} from 'react';
import { useLocation, useNavigate, useRouteError } from 'react-router';
import { safeCopyToClipboard } from '../../utils/uuid';
import { ErrorHelpHint } from '../help/ErrorHelpHint';
import './AppErrorModal.css';

export interface AppErrorModalProps {
  readonly error: unknown;
  readonly errorInfo?: { componentStack?: string | null | undefined } | null | undefined;
  readonly onDismiss?: () => void;
}

export function AppErrorModal({
  error,
  errorInfo,
  onDismiss,
}: AppErrorModalProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  let errorMessage = 'An unexpected application error occurred.';
  if (error instanceof Error) {
    errorMessage = error.message;
  } else if (typeof error === 'string') {
    errorMessage = error;
  } else if (typeof error === 'object' && error !== null && 'statusText' in error) {
    errorMessage = String(error.statusText);
  }

  let stackTrace = 'No stack trace available.';
  if (error instanceof Error && error.stack) {
    stackTrace = error.stack;
  } else if (typeof error === 'string') {
    stackTrace = error;
  } else if (
    typeof error === 'number' ||
    typeof error === 'boolean' ||
    typeof error === 'bigint'
  ) {
    stackTrace = error.toString();
  } else if (typeof error === 'object' && error !== null) {
    stackTrace = JSON.stringify(error, null, 2);
  }

  const componentStack = errorInfo?.componentStack ?? '';
  const fullTrace = componentStack
    ? `${stackTrace}\n\nComponent Stack:\n${componentStack}`
    : stackTrace;

  const currentUrl = window.location.href;

  const handleCopy = useCallback(async (): Promise<void> => {
    const textToCopy = `Error: ${errorMessage}\nURL: ${currentUrl}\n\nTraceback:\n${fullTrace}`;
    const success = await safeCopyToClipboard(textToCopy);
    if (success) {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  }, [errorMessage, currentUrl, fullTrace]);

  const handleDismiss = useCallback((): void => {
    const url = new URL(window.location.href);
    if (url.searchParams.has('peek')) {
      url.searchParams.delete('peek');
      window.history.replaceState({}, '', url.toString());
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
    onDismiss?.();
  }, [onDismiss]);

  const reportTitle = `[Bug]: Application Error: ${errorMessage.slice(0, 80)}`;
  const reportBody = `### Application Error Detected\n\n**URL:** ${currentUrl}\n**Error:** ${errorMessage}\n\n\`\`\`\n${fullTrace}\n\`\`\``;
  const baseUrl =
    (import.meta.env.VITE_ISSUE_REPORT_URL as string | undefined) ??
    'https://github.com/ThumbsUp-HQ/kanban/issues/new';
  const reportUrl = `${baseUrl}?title=${encodeURIComponent(reportTitle)}&body=${encodeURIComponent(reportBody)}`;

  return (
    <div
      className="app-error-backdrop"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="app-error-title"
      aria-describedby="app-error-message"
    >
      <div className="app-error-modal" data-testid="app-error-modal">
        <header className="app-error-modal__header">
          <span className="app-error-modal__icon" aria-hidden="true">
            🚨
          </span>
          <h2 id="app-error-title" className="app-error-modal__title">
            Application Error Detected
          </h2>
        </header>

        <div className="app-error-modal__body">
          <div
            id="app-error-message"
            className="app-error-modal__message"
            data-testid="error-message"
          >
            {errorMessage}
          </div>

          <div className="app-error-modal__help-row">
            <ErrorHelpHint error={error ?? errorMessage} testId="app-error-help" />
          </div>

          <div className="app-error-modal__url" data-testid="error-url">
            <span className="app-error-modal__label">URL:</span>
            <code>{currentUrl}</code>
          </div>

          <div className="app-error-modal__trace-wrapper">
            <span className="app-error-modal__label">Stack Trace:</span>
            <pre className="app-error-modal__trace" data-testid="error-trace">
              {fullTrace}
            </pre>
          </div>
        </div>

        <footer className="app-error-modal__actions">
          <button
            type="button"
            className="app-error-modal__btn app-error-modal__btn--copy"
            onClick={() => {
              void handleCopy();
            }}
            data-testid="error-copy-btn"
          >
            {copied ? 'Copied Traceback!' : 'Copy Traceback'}
          </button>

          <a
            href={reportUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="app-error-modal__btn app-error-modal__btn--report"
            data-testid="error-report-link"
          >
            Report to ThumbsUp-HQ
          </a>

          <button
            type="button"
            className="app-error-modal__btn app-error-modal__btn--dismiss"
            onClick={handleDismiss}
            data-testid="error-dismiss-btn"
          >
            Dismiss / Recover
          </button>
        </footer>
      </div>
    </div>
  );
}

/**
 * Route-level error boundary for React Router route `errorElement`.
 */
export function RouteErrorBoundary(): JSX.Element {
  const error = useRouteError();
  const navigate = useNavigate();
  const location = useLocation();

  const handleDismiss = useCallback((): void => {
    const params = new URLSearchParams(location.search);
    if (params.has('peek')) {
      params.delete('peek');
      const qs = params.toString();
      void navigate(`${location.pathname}${qs ? `?${qs}` : ''}`, {
        replace: true,
      });
    } else {
      window.location.reload();
    }
  }, [location.pathname, location.search, navigate]);

  return <AppErrorModal error={error} onDismiss={handleDismiss} />;
}

interface GlobalErrorBoundaryProps {
  readonly children: ReactNode;
}

interface GlobalErrorBoundaryState {
  readonly error: unknown;
  readonly errorInfo: { componentStack?: string | null | undefined } | null;
}

/**
 * Top-level application error boundary that wraps `<App />` and catches
 * render errors as well as unhandled window errors and promise rejections.
 */
export class GlobalErrorBoundary extends Component<
  GlobalErrorBoundaryProps,
  GlobalErrorBoundaryState
> {
  constructor(props: GlobalErrorBoundaryProps) {
    super(props);
    this.state = {
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: unknown): Partial<GlobalErrorBoundaryState> {
    return { error };
  }

  override componentDidCatch(error: unknown, errorInfo: ErrorInfo): void {
    this.setState({
      error,
      errorInfo: { componentStack: errorInfo.componentStack },
    });
  }

  override componentDidMount(): void {
    window.addEventListener('error', this.handleWindowError);
    window.addEventListener('unhandledrejection', this.handleUnhandledRejection);
  }

  override componentWillUnmount(): void {
    window.removeEventListener('error', this.handleWindowError);
    window.removeEventListener('unhandledrejection', this.handleUnhandledRejection);
  }

  private readonly handleWindowError = (event: ErrorEvent): void => {
    // Only capture unhandled runtime script errors
    if (event.error) {
      this.setState({
        error: event.error,
        errorInfo: null,
      });
    } else if (event.message) {
      this.setState({
        error: new Error(event.message),
        errorInfo: null,
      });
    }
  };

  private readonly handleUnhandledRejection = (
    event: PromiseRejectionEvent,
  ): void => {
    this.setState({
      error: event.reason ?? new Error('Unhandled Promise Rejection'),
      errorInfo: null,
    });
  };

  private readonly handleDismiss = (): void => {
    this.setState({
      error: null,
      errorInfo: null,
    });
  };

  override render(): ReactNode {
    if (this.state.error !== null) {
      return (
        <AppErrorModal
          error={this.state.error}
          errorInfo={this.state.errorInfo}
          onDismiss={this.handleDismiss}
        />
      );
    }

    return this.props.children;
  }
}
