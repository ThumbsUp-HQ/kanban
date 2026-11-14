// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useRef, type JSX, type ReactNode } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { PendingGateInfo, LatestGateVerdict } from './types';
import './gates.css';

export interface UseElapsedGateTimerResult {
  elapsedSeconds: number;
  formattedElapsed: string;
}

export function formatElapsedSeconds(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const mins = Math.floor(safeSeconds / 60);
  const secs = safeSeconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * Live 1s elapsed timer hook that tracks time elapsed since startedAt.
 * Pauses interval updates when the document is hidden and cleans up on unmount.
 */
export function useElapsedGateTimer(startedAt: string | undefined): UseElapsedGateTimerResult {
  const [now, setNow] = useState<number>(() => Date.now());
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!startedAt) {
      return undefined;
    }

    const startMs = new Date(startedAt).getTime();
    if (Number.isNaN(startMs)) {
      return undefined;
    }

    const startInterval = (): void => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
      timerRef.current = setInterval(() => {
        setNow(Date.now());
      }, 1000);
    };

    const stopInterval = (): void => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    const handleVisibilityChange = (): void => {
      if (document.hidden) {
        stopInterval();
      } else {
        setNow(Date.now());
        startInterval();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    startInterval();

    return () => {
      stopInterval();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [startedAt]);

  if (!startedAt) {
    return { elapsedSeconds: 0, formattedElapsed: '00:00' };
  }

  const startMs = new Date(startedAt).getTime();
  if (Number.isNaN(startMs)) {
    return { elapsedSeconds: 0, formattedElapsed: '00:00' };
  }

  const diffSeconds = Math.max(0, Math.floor((now - startMs) / 1000));
  return {
    elapsedSeconds: diffSeconds,
    formattedElapsed: formatElapsedSeconds(diffSeconds),
  };
}

export interface GateStatusPillProps {
  status: 'pending' | 'rejected' | 'approved';
  pendingGate?: PendingGateInfo | null | undefined;
  latestVerdict?: LatestGateVerdict | null | undefined;
  issueKey?: string | undefined;
  canCancel?: boolean | undefined;
  onCancelGate?: ((executionId: string) => void | Promise<void>) | undefined;
  onJumpToComment?: ((commentId: string) => void) | undefined;
  testId?: string | undefined;
}

export function GateStatusPill({
  status,
  pendingGate,
  latestVerdict,
  issueKey,
  canCancel = false,
  onCancelGate,
  onJumpToComment,
  testId,
}: GateStatusPillProps): JSX.Element {
  const [copiedHash, setCopiedHash] = useState(false);
  const timer = useElapsedGateTimer(status === 'pending' ? pendingGate?.started_at : undefined);

  if (status === 'pending') {
    const hookName = pendingGate?.hook_name ?? 'Workflow Gate';
    const harness = pendingGate?.harness_label ?? pendingGate?.harness_kind ?? 'cli: agy -p';
    const isRo = pendingGate?.repo_mount_ro !== false;
    const executionId = pendingGate?.execution_id ?? '';

    const popoverContent = (): ReactNode => (
      <div className="gate-popover" data-testid="gate-pending-popover">
        <div className="gate-popover__line1">
          Gate: {hookName} ({harness})
        </div>
        <div className="gate-popover__line2">
          <span className="gate-popover__timer" data-testid="gate-elapsed-timer">
            Elapsed: {timer.formattedElapsed}
          </span>
          {isRo && (
            <span className="gate-popover__repo-ro" data-testid="gate-repo-ro-badge">
              :ro repo mounted
            </span>
          )}
        </div>
        {canCancel && executionId && onCancelGate && (
          <button
            type="button"
            className="gate-popover__cancel-btn"
            data-testid={issueKey ? `cancel-gate-btn-${issueKey}` : 'cancel-gate-button'}
            onClick={(e) => {
              e.stopPropagation();
              void onCancelGate(executionId);
            }}
          >
            Cancel gate
          </button>
        )}
      </div>
    );

    return (
      <EmojiHint
        kind="gatePending"
        variant="interactive"
        label={`Gate Pending: ${hookName}`}
        content={popoverContent}
        testId={testId ?? (issueKey ? `gate-pending-${issueKey}` : 'gate-pending-pill')}
      />
    );
  }

  if (status === 'rejected') {
    const hookName = latestVerdict?.hook_name ?? 'Workflow Gate';
    const agentSlug = latestVerdict?.agent_slug ?? 'agent';
    const reasonRaw = latestVerdict?.reason_preview ?? 'Transition criteria not satisfied.';
    // Ensure <= 280 chars
    const reasonPreview = reasonRaw.length > 280 ? `${reasonRaw.slice(0, 277)}...` : reasonRaw;
    const auditCommentId = latestVerdict?.audit_comment_id;

    const formattedTime = latestVerdict?.completed_at
      ? new Date(latestVerdict.completed_at).toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
        })
      : '';

    const popoverContent = (): ReactNode => (
      <div className="gate-popover" data-testid="gate-vetoed-popover">
        <div className="gate-popover__line1">
          Vetoed by {hookName} ({agentSlug}) {formattedTime ? `at ${formattedTime}` : ''}
        </div>
        <div className="gate-popover__reason" data-testid="gate-veto-reason">
          {reasonPreview}
        </div>
        {auditCommentId && (
          <button
            type="button"
            className="gate-popover__jump-link"
            data-testid="jump-to-comment-link"
            onClick={(e) => {
              e.stopPropagation();
              onJumpToComment?.(auditCommentId);
            }}
          >
            View full gate review comment -&gt;
          </button>
        )}
      </div>
    );

    return (
      <EmojiHint
        kind="gateVetoed"
        variant="interactive"
        label={`Gate Vetoed: ${hookName}`}
        content={popoverContent}
        testId={testId ?? (issueKey ? `gate-vetoed-${issueKey}` : 'gate-vetoed-pill')}
      />
    );
  }

  // Approved
  const hookName = latestVerdict?.hook_name ?? 'Workflow Gate';
  const latencyMs = latestVerdict?.latency_ms !== undefined ? `${String(latestVerdict.latency_ms)} ms` : '';
  const hash = latestVerdict?.verdict_sha256 ?? '';

  const popoverContent = (): ReactNode => (
    <div className="gate-popover" data-testid="gate-approved-popover">
      <div className="gate-popover__line1">Gate: {hookName}</div>
      {latencyMs && (
        <div className="gate-popover__line2" data-testid="gate-latency">
          Latency: {latencyMs}
        </div>
      )}
      {hash && (
        <div className="gate-popover__hash-box">
          <code className="gate-popover__hash-code" data-testid="verdict-sha256-code">
            {hash}
          </code>
          <button
            type="button"
            className="gate-popover__copy-btn"
            data-testid="copy-verdict-hash-btn"
            onClick={(e) => {
              e.stopPropagation();
              void navigator.clipboard.writeText(hash);
              setCopiedHash(true);
              setTimeout(() => {
                setCopiedHash(false);
              }, 2000);
            }}
          >
            {copiedHash ? 'Copied' : 'Copy Hash'}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <EmojiHint
      kind="gateApproved"
      variant="interactive"
      label={`Gate Approved: ${hookName}`}
      content={popoverContent}
      testId={testId ?? (issueKey ? `gate-approved-${issueKey}` : 'gate-approved-pill')}
    />
  );
}
