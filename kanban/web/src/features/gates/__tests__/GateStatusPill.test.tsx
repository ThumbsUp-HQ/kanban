// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, act } from '@testing-library/react';
import {
  GateStatusPill,
  formatElapsedSeconds,
  useElapsedGateTimer,
} from '../GateStatusPill';
import type { PendingGateInfo, LatestGateVerdict } from '../types';

function TimerProbe({ startedAt }: { startedAt?: string }) {
  const { elapsedSeconds, formattedElapsed } = useElapsedGateTimer(startedAt);
  return (
    <div data-testid="timer-probe">
      <span data-testid="probe-seconds">{elapsedSeconds}</span>
      <span data-testid="probe-formatted">{formattedElapsed}</span>
    </div>
  );
}

describe('GateStatusPill & useElapsedGateTimer (KB-P5-25)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('formatElapsedSeconds', () => {
    it('formats seconds into MM:SS correctly', () => {
      expect(formatElapsedSeconds(0)).toBe('00:00');
      expect(formatElapsedSeconds(14)).toBe('00:14');
      expect(formatElapsedSeconds(65)).toBe('01:05');
      expect(formatElapsedSeconds(3600)).toBe('60:00');
      expect(formatElapsedSeconds(-5)).toBe('00:00');
    });
  });

  describe('useElapsedGateTimer', () => {
    it('returns 00:00 when startedAt is undefined or invalid', () => {
      const { rerender } = render(<TimerProbe />);
      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:00');

      rerender(<TimerProbe startedAt="invalid-date-string" />);
      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:00');
    });

    it('advances timer every 1000ms', () => {
      const start = new Date(Date.now() - 2000).toISOString();
      render(<TimerProbe startedAt={start} />);

      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:02');

      act(() => {
        vi.advanceTimersByTime(3000);
      });

      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:05');
    });

    it('pauses on document visibility hidden and resumes on visible', () => {
      const start = new Date(Date.now()).toISOString();
      render(<TimerProbe startedAt={start} />);

      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:00');

      // Hide document
      Object.defineProperty(document, 'hidden', { value: true, configurable: true });
      fireEvent(document, new Event('visibilitychange'));

      act(() => {
        vi.advanceTimersByTime(5000);
      });

      // Show document
      Object.defineProperty(document, 'hidden', { value: false, configurable: true });
      fireEvent(document, new Event('visibilitychange'));

      // Additional visible event when timer is already running
      fireEvent(document, new Event('visibilitychange'));

      expect(screen.getByTestId('probe-formatted').textContent).toBe('00:05');
    });
  });

  describe('GateStatusPill: Pending State', () => {
    const pendingGate: PendingGateInfo = {
      execution_id: 'exec-123',
      hook_name: 'sec-review',
      agent_slug: 'security-agent',
      harness_label: 'cli: agy -p',
      started_at: new Date(Date.now() - 14000).toISOString(),
      repo_mount_ro: true,
    };

    it('renders ⏳🤖 and opens interactive popover with live timer and :ro badge', () => {
      render(
        <GateStatusPill
          status="pending"
          pendingGate={pendingGate}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-pending-KAN-8');
      expect(trigger).not.toBeNull();

      act(() => {
        trigger.focus();
      });

      expect(screen.getByTestId('gate-pending-popover')).not.toBeNull();
      expect(screen.getByText('Gate: sec-review (cli: agy -p)')).not.toBeNull();
      expect(screen.getByTestId('gate-elapsed-timer').textContent).toContain('Elapsed: 00:14');
      expect(screen.getByTestId('gate-repo-ro-badge').textContent).toBe(':ro repo mounted');
    });

    it('renders without :ro badge when repo_mount_ro is false', () => {
      render(
        <GateStatusPill
          status="pending"
          pendingGate={{ ...pendingGate, repo_mount_ro: false }}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-pending-KAN-8');
      act(() => {
        trigger.focus();
      });

      expect(screen.queryByTestId('gate-repo-ro-badge')).toBeNull();
    });

    it('shows Cancel gate button only when canCancel is true', () => {
      const onCancelMock = vi.fn();
      const { rerender } = render(
        <GateStatusPill
          status="pending"
          pendingGate={pendingGate}
          issueKey="KAN-8"
          canCancel={false}
          onCancelGate={onCancelMock}
        />,
      );

      const trigger = screen.getByTestId('gate-pending-KAN-8');
      act(() => {
        trigger.focus();
      });

      // Security invariant: non-privileged users cannot cancel
      expect(screen.queryByTestId('cancel-gate-button')).toBeNull();

      rerender(
        <GateStatusPill
          status="pending"
          pendingGate={pendingGate}
          issueKey="KAN-8"
          canCancel={true}
          onCancelGate={onCancelMock}
        />,
      );

      act(() => {
        trigger.focus();
      });

      const cancelBtn = screen.getByTestId('cancel-gate-btn-KAN-8');
      expect(cancelBtn).not.toBeNull();

      fireEvent.click(cancelBtn);
      expect(onCancelMock).toHaveBeenCalledWith('exec-123');
    });

    it('uses fallback values when pendingGate is omitted', () => {
      render(<GateStatusPill status="pending" />);
      const trigger = screen.getByTestId('gate-pending-pill');
      act(() => {
        trigger.focus();
      });
      expect(screen.getByText('Gate: Workflow Gate (cli: agy -p)')).not.toBeNull();
    });
  });

  describe('GateStatusPill: Rejected / Vetoed State', () => {
    const latestVerdict: LatestGateVerdict = {
      decision: 'reject',
      hook_name: 'forensic-code-check',
      agent_slug: 'reality-checker',
      completed_at: '2026-11-14T00:00:00Z',
      reason_preview: 'Verification proof missing required logcat trace. Aborting transition.',
      audit_comment_id: 'comment-uuid-456',
    };

    it('renders 🛑🤖 and displays hook name and 2-line reason preview', () => {
      render(
        <GateStatusPill
          status="rejected"
          latestVerdict={latestVerdict}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-vetoed-KAN-8');
      expect(trigger).not.toBeNull();

      act(() => {
        trigger.focus();
      });

      expect(screen.getByTestId('gate-vetoed-popover')).not.toBeNull();
      expect(screen.getByText(/Vetoed by forensic-code-check \(reality-checker\)/)).not.toBeNull();
      expect(screen.getByTestId('gate-veto-reason').textContent).toBe(
        'Verification proof missing required logcat trace. Aborting transition.',
      );
    });

    it('safely renders hostile reason_preview as plain text nodes (Anti-XSS)', () => {
      const hostileVerdict: LatestGateVerdict = {
        decision: 'reject',
        hook_name: 'sec-guard',
        reason_preview: '<img src=x onerror=alert(1)> and <script>alert(2)</script>',
      };

      render(
        <GateStatusPill
          status="rejected"
          latestVerdict={hostileVerdict}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-vetoed-KAN-8');
      act(() => {
        trigger.focus();
      });

      const reasonEl = screen.getByTestId('gate-veto-reason');
      expect(reasonEl.textContent).toContain('<img src=x onerror=alert(1)>');
      expect(reasonEl.querySelectorAll('img').length).toBe(0);
      expect(reasonEl.querySelectorAll('script').length).toBe(0);
    });

    it('truncates reason_preview exceeding 280 chars with ellipsis', () => {
      const longReason = 'A'.repeat(300);
      render(
        <GateStatusPill
          status="rejected"
          latestVerdict={{ ...latestVerdict, reason_preview: longReason }}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-vetoed-KAN-8');
      act(() => {
        trigger.focus();
      });

      const reasonEl = screen.getByTestId('gate-veto-reason');
      expect(reasonEl.textContent.length).toBe(280);
      expect(reasonEl.textContent.endsWith('...')).toBe(true);
    });

    it('invokes onJumpToComment when clicking jump link', () => {
      const onJumpMock = vi.fn();
      render(
        <GateStatusPill
          status="rejected"
          latestVerdict={latestVerdict}
          issueKey="KAN-8"
          onJumpToComment={onJumpMock}
        />,
      );

      const trigger = screen.getByTestId('gate-vetoed-KAN-8');
      act(() => {
        trigger.focus();
      });

      const jumpBtn = screen.getByTestId('jump-to-comment-link');
      fireEvent.click(jumpBtn);
      expect(onJumpMock).toHaveBeenCalledWith('comment-uuid-456');

      // Without onJumpToComment callback, clicking jump link does not throw
      const { unmount } = render(
        <GateStatusPill
          status="rejected"
          latestVerdict={latestVerdict}
          issueKey="KAN-8"
        />,
      );
      const triggers = screen.getAllByTestId('gate-vetoed-KAN-8');
      const trigger2 = triggers[triggers.length - 1];
      if (trigger2) {
        act(() => {
          trigger2.focus();
        });
      }
      const jumpBtns = screen.getAllByTestId('jump-to-comment-link');
      const lastJumpBtn = jumpBtns[jumpBtns.length - 1];
      if (lastJumpBtn) {
        expect(() => {
          fireEvent.click(lastJumpBtn);
        }).not.toThrow();
      }
      unmount();
    });

    it('uses fallback values when latestVerdict is undefined', () => {
      render(<GateStatusPill status="rejected" />);
      const trigger = screen.getByTestId('gate-vetoed-pill');
      act(() => {
        trigger.focus();
      });
      expect(screen.getByText(/Vetoed by Workflow Gate \(agent\)/)).not.toBeNull();
    });
  });

  describe('GateStatusPill: Approved State', () => {
    const approvedVerdict: LatestGateVerdict = {
      decision: 'approve',
      hook_name: 'architecture-audit',
      latency_ms: 1420,
      verdict_sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      completed_at: '2026-11-14T00:00:00Z',
    };

    it('renders ✅🤖 and displays latency and copyable verdict hash', () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      render(
        <GateStatusPill
          status="approved"
          latestVerdict={approvedVerdict}
          issueKey="KAN-8"
        />,
      );

      const trigger = screen.getByTestId('gate-approved-KAN-8');
      expect(trigger).not.toBeNull();

      act(() => {
        trigger.focus();
      });

      expect(screen.getByTestId('gate-approved-popover')).not.toBeNull();
      expect(screen.getByText('Gate: architecture-audit')).not.toBeNull();
      expect(screen.getByTestId('gate-latency').textContent).toBe('Latency: 1420 ms');
      expect(screen.getByTestId('verdict-sha256-code').textContent).toBe(
        '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      );

      const copyBtn = screen.getByTestId('copy-verdict-hash-btn');
      fireEvent.click(copyBtn);
      expect(writeTextMock).toHaveBeenCalledWith(
        '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      );
      expect(copyBtn.textContent).toBe('Copied');

      act(() => {
        vi.advanceTimersByTime(2100);
      });
      expect(copyBtn.textContent).toBe('Copy Hash');
    });

    it('uses fallback values when latestVerdict is undefined', () => {
      render(<GateStatusPill status="approved" />);
      const trigger = screen.getByTestId('gate-approved-pill');
      act(() => {
        trigger.focus();
      });
      expect(screen.getByText('Gate: Workflow Gate')).not.toBeNull();
    });
  });
});
