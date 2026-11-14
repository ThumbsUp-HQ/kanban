// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, act } from '@testing-library/react';
import { GateActivityRow } from '../GateActivityRow';
import type { GateActivityItem } from '../types';

describe('GateActivityRow (KB-P5-25)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders GATE_APPROVED with latency and copyable hash', () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextMock },
    });

    const item: GateActivityItem = {
      id: 'gate-row-1',
      category: 'AGENT_GATE',
      event_type: 'GATE_APPROVED',
      actor: { display_name: 'sec-audit' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'sec-audit',
        harness: 'cli: agy -p',
        execution_latency_ms: 1250,
        verdict_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      },
    };

    render(<GateActivityRow item={item} />);

    expect(screen.getByText('sec-audit')).not.toBeNull();
    expect(screen.getByText('(cli: agy -p)')).not.toBeNull();
    expect(screen.getByText('Approved transition in 1250 ms')).not.toBeNull();
    expect(screen.getByTestId('activity-verdict-hash').textContent).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );

    const copyBtn = screen.getByTestId('activity-copy-hash-btn');
    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalledWith(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
    expect(copyBtn.textContent).toBe('Copied');

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(copyBtn.textContent).toBe('Copy Hash');
  });

  it('renders GATE_REJECTED with reason and jump-to-comment link', () => {
    const onJumpMock = vi.fn();
    const item: GateActivityItem = {
      id: 'gate-row-2',
      category: 'AGENT_GATE',
      event_type: 'GATE_REJECTED',
      actor: { display_name: 'reality-checker' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'reality-checker',
        harness: 'codex -p',
        reason: 'Missing screenshot artifact in docs/qa/KANBA-8/screenshots/',
        audit_comment_id: 'comment-audit-999',
      },
    };

    render(<GateActivityRow item={item} onJumpToComment={onJumpMock} />);

    expect(screen.getByText('reality-checker')).not.toBeNull();
    expect(screen.getByTestId('gate-activity-reason').textContent).toBe(
      'Missing screenshot artifact in docs/qa/KANBA-8/screenshots/',
    );

    const jumpBtn = screen.getByTestId('jump-comment-btn-gate-row-2');
    fireEvent.click(jumpBtn);
    expect(onJumpMock).toHaveBeenCalledWith('comment-audit-999');
  });

  it('safely renders hostile markdown/script in reason as plain text', () => {
    const item: GateActivityItem = {
      id: 'gate-row-3',
      category: 'AGENT_GATE',
      event_type: 'GATE_REJECTED',
      actor: { display_name: 'guard' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'guard',
        reason: '<script>alert(1)</script><img src=x onerror=alert(2)>',
      },
    };

    render(<GateActivityRow item={item} />);

    const reasonEl = screen.getByTestId('gate-activity-reason');
    expect(reasonEl.textContent).toBe('<script>alert(1)</script><img src=x onerror=alert(2)>');
    expect(reasonEl.querySelectorAll('script').length).toBe(0);
    expect(reasonEl.querySelectorAll('img').length).toBe(0);
  });

  it('renders GATE_ABORTED_STALE for TOCTOU cancel events', () => {
    const item: GateActivityItem = {
      id: 'gate-row-4',
      category: 'AGENT_GATE',
      event_type: 'GATE_ABORTED_STALE',
      actor: { display_name: 'engine' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'engine',
      },
    };

    render(<GateActivityRow item={item} />);
    expect(
      screen.getByText('Transition cancelled (ticket changed while gate was running)'),
    ).not.toBeNull();
  });

  it('renders GATE_FAIL_OPEN_WARN with warning code', () => {
    const item: GateActivityItem = {
      id: 'gate-row-5',
      category: 'AGENT_GATE',
      event_type: 'GATE_FAIL_OPEN_WARN',
      actor: { display_name: 'linter-hook' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'linter-hook',
        warning_code: 'SANDBOX_TIMEOUT',
      },
    };

    render(<GateActivityRow item={item} />);
    expect(screen.getByText('Gate failed open with warning: SANDBOX_TIMEOUT')).not.toBeNull();
  });

  it('renders GATE_PENDING for running gate transitions', () => {
    const item: GateActivityItem = {
      id: 'gate-row-6',
      category: 'AGENT_GATE',
      event_type: 'GATE_PENDING',
      actor: { display_name: 'qa-agent' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'qa-agent',
        harness: 'gemini',
      },
    };

    render(<GateActivityRow item={item} />);
    expect(screen.getByText('Transition gate currently running...')).not.toBeNull();
  });

  it('handles optional fallbacks for hookName, latency, and warningCode', () => {
    const itemWithoutHook: GateActivityItem = {
      id: 'gate-row-7',
      category: 'AGENT_GATE',
      event_type: 'GATE_APPROVED',
      actor: {},
      created_at: '2026-11-14T00:00:00Z',
      payload: {},
    };
    const { unmount } = render(<GateActivityRow item={itemWithoutHook} />);
    expect(screen.getByText('Workflow Gate')).not.toBeNull();
    expect(screen.getByText('Approved transition')).not.toBeNull();
    unmount();

    const itemWarnDefault: GateActivityItem = {
      id: 'gate-row-8',
      category: 'AGENT_GATE',
      event_type: 'GATE_FAIL_OPEN_WARN',
      actor: { display_name: 'Hook' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {},
    };
    render(<GateActivityRow item={itemWarnDefault} />);
    expect(screen.getByText('Gate failed open with warning: TIMEOUT')).not.toBeNull();
  });

  it('renders GATE_VETOED alias with veto row and accessible jump button', () => {
    const onJumpMock = vi.fn();
    const item: GateActivityItem = {
      id: 'gate-row-9',
      category: 'AGENT_GATE',
      event_type: 'GATE_VETOED',
      actor: { display_name: 'veto-guard' },
      created_at: '2026-11-14T00:00:00Z',
      payload: {
        hook_name: 'veto-guard',
        reason: 'Missing test coverage',
        audit_comment_id: 'audit-comm-123',
      },
    };

    render(<GateActivityRow item={item} onJumpToComment={onJumpMock} />);
    expect(screen.getByTestId('gate-vetoed-row')).not.toBeNull();
    const jumpBtn = screen.getByRole('button', { name: 'View audit details' });
    fireEvent.click(jumpBtn);
    expect(onJumpMock).toHaveBeenCalledWith('audit-comm-123');
  });
});
