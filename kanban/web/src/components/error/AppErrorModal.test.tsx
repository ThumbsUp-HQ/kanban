import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React, { useState } from 'react';
import { MemoryRouter, useRouteError } from 'react-router';
import {
  AppErrorModal,
  RouteErrorBoundary,
  GlobalErrorBoundary,
} from './AppErrorModal';

vi.mock('../../utils/uuid', () => ({
  safeCopyToClipboard: vi.fn().mockResolvedValue(true),
  safeRandomUUID: vi.fn().mockReturnValue('11111111-1111-4111-8111-111111111111'),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return {
    ...actual,
    useRouteError: vi.fn(),
  };
});

describe('AppErrorModal, RouteErrorBoundary, and GlobalErrorBoundary', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('AppErrorModal', () => {
    it('renders danger header, message, url, stack trace, and action buttons', () => {
      const error = new Error('Test fatal failure');
      error.stack = 'Error: Test fatal failure\n    at Component.tsx:42';

      render(<AppErrorModal error={error} />);

      expect(screen.getByText('Application Error Detected')).toBeDefined();
      expect(screen.getByTestId('error-message').textContent).toBe('Test fatal failure');
      expect(screen.getByTestId('error-url')).toBeDefined();
      expect(screen.getByTestId('error-trace').textContent).toContain('Error: Test fatal failure');

      const copyBtn = screen.getByTestId('error-copy-btn');
      const reportLink = screen.getByTestId('error-report-link');
      const dismissBtn = screen.getByTestId('error-dismiss-btn');

      expect(copyBtn).toBeDefined();
      expect(reportLink).toBeDefined();
      expect(dismissBtn).toBeDefined();

      const href = reportLink.getAttribute('href') ?? '';
      expect(href).toContain('https://github.com/ThumbsUp-HQ/thumbs-up-kanban/issues/new');
      expect(href).toContain(encodeURIComponent('[Bug]: Application Error: Test fatal failure'));
    });

    it('copies traceback and shows Copied feedback on click', async () => {
      const { safeCopyToClipboard } = await import('../../utils/uuid');
      const error = new Error('Clipboard test error');
      render(<AppErrorModal error={error} />);

      const copyBtn = screen.getByTestId('error-copy-btn');
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(safeCopyToClipboard).toHaveBeenCalled();
        expect(screen.getByText('Copied Traceback!')).toBeDefined();
      });
    });

    it('clears ?peek= search param and invokes onDismiss callback', () => {
      const onDismiss = vi.fn();
      const pushStateSpy = vi.spyOn(window.history, 'replaceState');

      const url = new URL(window.location.href);
      url.searchParams.set('peek', 'KAN-123');
      window.history.pushState({}, '', url.toString());

      render(<AppErrorModal error="Non-Error string failure" onDismiss={onDismiss} />);

      const dismissBtn = screen.getByTestId('error-dismiss-btn');
      fireEvent.click(dismissBtn);

      expect(onDismiss).toHaveBeenCalledTimes(1);
      expect(pushStateSpy).toHaveBeenCalled();
    });

    it('handles non-Error objects and statusText gracefully', () => {
      render(<AppErrorModal error={{ statusText: 'Not Found', status: 404 }} />);
      expect(screen.getByTestId('error-message').textContent).toBe('Not Found');
    });
  });

  describe('RouteErrorBoundary', () => {
    it('renders AppErrorModal with error from useRouteError', () => {
      const mockRouteError = new Error('Route level failure');
      vi.mocked(useRouteError).mockReturnValue(mockRouteError);

      render(
        <MemoryRouter>
          <RouteErrorBoundary />
        </MemoryRouter>,
      );

      expect(screen.getByText('Application Error Detected')).toBeDefined();
      expect(screen.getByTestId('error-message').textContent).toBe('Route level failure');
    });
  });

  describe('GlobalErrorBoundary', () => {
    // Suppress console.error in error boundary tests
    const originalConsoleError = console.error;
    beforeEach(() => {
      console.error = vi.fn();
    });
    afterEach(() => {
      console.error = originalConsoleError;
    });

    function BuggyComponent({ shouldThrow }: { shouldThrow: boolean }): React.JSX.Element {
      if (shouldThrow) {
        throw new Error('Component crashed inside GlobalErrorBoundary');
      }
      return <div>Healthy Child Content</div>;
    }

    it('renders children when no error occurs', () => {
      render(
        <GlobalErrorBoundary>
          <div>Safe Content</div>
        </GlobalErrorBoundary>,
      );

      expect(screen.getByText('Safe Content')).toBeDefined();
    });

    it('catches render errors and recovers on Dismiss click', () => {
      function TestWrapper() {
        const [hasError, setHasError] = useState(false);
        return (
          <div>
            <button
              type="button"
              onClick={() => {
                setHasError(true);
              }}
            >
              Trigger Error
            </button>
            <GlobalErrorBoundary>
              <BuggyComponent shouldThrow={hasError} />
            </GlobalErrorBoundary>
          </div>
        );
      }

      render(<TestWrapper />);
      expect(screen.getByText('Healthy Child Content')).toBeDefined();

      fireEvent.click(screen.getByText('Trigger Error'));

      expect(screen.getByText('Application Error Detected')).toBeDefined();
      expect(screen.getByTestId('error-message').textContent).toBe(
        'Component crashed inside GlobalErrorBoundary',
      );

      // Dismiss recovers
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
    });

    it('catches window error and unhandledrejection events', async () => {
      render(
        <GlobalErrorBoundary>
          <div>Child Area</div>
        </GlobalErrorBoundary>,
      );

      expect(screen.getByText('Child Area')).toBeDefined();

      // Dispatch window error event
      const errorEvent = new ErrorEvent('error', {
        error: new Error('Window level script error'),
      });
      window.dispatchEvent(errorEvent);

      await waitFor(() => {
        expect(screen.getByText('Application Error Detected')).toBeDefined();
        expect(screen.getByTestId('error-message').textContent).toBe(
          'Window level script error',
        );
      });

      // Dismiss recovers back
      fireEvent.click(screen.getByTestId('error-dismiss-btn'));
      await waitFor(() => {
        expect(screen.getByText('Child Area')).toBeDefined();
      });

      // Dispatch unhandled promise rejection event
      const rejectionEvent = new CustomEvent('unhandledrejection', {
        detail: { reason: new Error('Promise rejection error') },
      }) as unknown as PromiseRejectionEvent;
      Object.defineProperty(rejectionEvent, 'reason', {
        value: new Error('Promise rejection error'),
      });
      window.dispatchEvent(rejectionEvent);

      await waitFor(() => {
        expect(screen.getByText('Application Error Detected')).toBeDefined();
        expect(screen.getByTestId('error-message').textContent).toBe(
          'Promise rejection error',
        );
      });
    });
  });
});
