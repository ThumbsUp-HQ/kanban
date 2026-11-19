// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { GateActivityItem } from './types';
import './gates.css';

export interface GateActivityRowProps {
  item: GateActivityItem;
  onJumpToComment?: ((commentId: string) => void) | undefined;
}

export function GateActivityRow({ item, onJumpToComment }: GateActivityRowProps): JSX.Element {
  const [copiedHash, setCopiedHash] = useState(false);
  const payload = item.payload;
  const isRedacted = Boolean(item.actor.redacted);
  const hookName = isRedacted
    ? (item.actor.label ?? 'External Collaborator')
    : (payload.hook_name ?? item.actor.display_name ?? 'Workflow Gate');
  const harness = payload.harness ?? 'cli: agy -p';
  const latency =
    payload.execution_latency_ms !== undefined ? `${String(payload.execution_latency_ms)} ms` : '';
  const hash = payload.verdict_sha256 ?? item.row_hash ?? '';
  const reason = payload.reason ?? 'Transition criteria not satisfied.';
  const auditCommentId = payload.audit_comment_id;

  const formattedDate = new Date(item.created_at).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  if (item.event_type === 'GATE_APPROVED') {
    return (
      <div
        className="gate-activity-row gate-activity-row--approved"
        data-testid={`gate-activity-approved-${item.id}`}
      >
        <div data-testid="gate-approved-row" className="gate-activity-row__inner">
          <EmojiHint
            kind="gateApproved"
            variant="interactive"
            label={`Gate Approved: ${hookName}`}
            content={
              <div className="gate-popover">
                <div className="gate-popover__line1">Gate: {hookName}</div>
                {latency && <div className="gate-popover__line2">Latency: {latency}</div>}
                {hash && (
                  <div className="gate-popover__hash-box">
                    <code className="gate-popover__hash-code">{hash}</code>
                  </div>
                )}
              </div>
            }
            testId={`activity-gate-hint-${item.id}`}
          />
          <div className="gate-activity-row__body">
            <div className="gate-activity-row__header">
              <span className="gate-activity-row__hook">{hookName}</span>
              {!isRedacted && <span className="gate-activity-row__harness">({harness})</span>}
              <time dateTime={item.created_at} className="gate-activity-row__time">
                {formattedDate}
              </time>
            </div>
            <div className="gate-activity-row__detail">
              Approved transition {latency ? `in ${latency}` : ''}
            </div>
            {hash && (
              <div className="gate-activity-row__actions">
                <code className="gate-popover__hash-code" data-testid="activity-verdict-hash">
                  {hash}
                </code>
                <button
                  type="button"
                  className="gate-popover__copy-btn"
                  data-testid="activity-copy-hash-btn"
                  onClick={() => {
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
        </div>
      </div>
    );
  }

  if (item.event_type === 'GATE_REJECTED' || (item.event_type as string) === 'GATE_VETOED') {
    return (
      <div
        className="gate-activity-row gate-activity-row--rejected"
        data-testid={`gate-activity-rejected-${item.id}`}
      >
        <div data-testid="gate-vetoed-row" className="gate-activity-row__inner">
          <EmojiHint
            kind="gateVetoed"
            variant="interactive"
            label={`Gate Vetoed: ${hookName}`}
            content={
              <div className="gate-popover">
                <div className="gate-popover__line1">Vetoed by {hookName}</div>
                <div className="gate-popover__reason">{reason}</div>
              </div>
            }
            testId={`activity-gate-hint-${item.id}`}
          />
          <div className="gate-activity-row__body">
            <div className="gate-activity-row__header">
              <span className="gate-activity-row__hook">{hookName}</span>
              {!isRedacted && <span className="gate-activity-row__harness">({harness})</span>}
              <time dateTime={item.created_at} className="gate-activity-row__time">
                {formattedDate}
              </time>
            </div>
            {/* Anti-XSS: Reason rendered as plain text node */}
            <div className="gate-activity-row__detail" data-testid="gate-activity-reason">
              {reason}
            </div>
            {auditCommentId && onJumpToComment && (
              <div className="gate-activity-row__actions">
                <button
                  type="button"
                  className="gate-popover__jump-link"
                  data-testid={`jump-comment-btn-${item.id}`}
                  aria-label="View audit details"
                  onClick={() => {
                    onJumpToComment(auditCommentId);
                  }}
                >
                  View full gate review comment -&gt;
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (item.event_type === 'GATE_ABORTED_STALE') {
    return (
      <div
        className="gate-activity-row gate-activity-row--stale"
        data-testid={`gate-activity-stale-${item.id}`}
      >
        <div className="gate-activity-row__inner">
          <EmojiHint
            kind="warning"
            variant="tooltip"
            label="Gate Aborted: Stale Snapshot"
            content="Ticket was modified while the agent gate was evaluating (TOCTOU violation)."
            testId={`activity-gate-hint-${item.id}`}
          />
          <div className="gate-activity-row__body">
            <div className="gate-activity-row__header">
              <span className="gate-activity-row__hook">{hookName}</span>
              <time dateTime={item.created_at} className="gate-activity-row__time">
                {formattedDate}
              </time>
            </div>
            <div className="gate-activity-row__detail">
              Transition cancelled (ticket changed while gate was running)
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (item.event_type === 'GATE_FAIL_OPEN_WARN') {
    const warningCode = payload.warning_code ?? 'TIMEOUT';
    return (
      <div
        className="gate-activity-row gate-activity-row--warn"
        data-testid={`gate-activity-warn-${item.id}`}
      >
        <div className="gate-activity-row__inner">
          <EmojiHint
            kind="warning"
            variant="tooltip"
            label="Gate Warning: Fail-Open"
            content={`Gate encountered an error (${warningCode}) but policy permitted proceeding.`}
            testId={`activity-gate-hint-${item.id}`}
          />
          <div className="gate-activity-row__body">
            <div className="gate-activity-row__header">
              <span className="gate-activity-row__hook">{hookName}</span>
              <time dateTime={item.created_at} className="gate-activity-row__time">
                {formattedDate}
              </time>
            </div>
            <div className="gate-activity-row__detail">
              Gate failed open with warning: {warningCode}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Pending
  return (
    <div
      className="gate-activity-row gate-activity-row--pending"
      data-testid={`gate-activity-pending-${item.id}`}
    >
      <div data-testid="gate-pending-row" className="gate-activity-row__inner">
        <EmojiHint
          kind="gatePending"
          variant="tooltip"
          label={`Gate Pending: ${hookName}`}
          content={`Gate evaluation in progress via ${harness}`}
          testId={`activity-gate-hint-${item.id}`}
        />
        <div className="gate-activity-row__body">
          <div className="gate-activity-row__header">
            <span className="gate-activity-row__hook">{hookName}</span>
            {!isRedacted && <span className="gate-activity-row__harness">({harness})</span>}
            <time dateTime={item.created_at} className="gate-activity-row__time">
              {formattedDate}
            </time>
          </div>
          <div className="gate-activity-row__detail">Transition gate currently running...</div>
        </div>
      </div>
    </div>
  );
}
