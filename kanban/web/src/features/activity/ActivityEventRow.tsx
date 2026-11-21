/**
 * Activity Event Row rendering HISTORY and AGENT_GATE ledger items with EmojiHints (KB-P3-44, S7.1, S7.2 8j).
 */

import React, { useState, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type {
  ActivityItem,
  GatePayload,
  CreatorOverridePayload,
} from './activityApi';

export interface ActivityEventRowProps {
  readonly item: ActivityItem;
  readonly onJumpToComment?: (commentId: string) => void;
}

export function formatActorName(actor: ActivityItem['actor']): string {
  if (actor.redacted) {
    return actor.label ?? '1 External Collaborator';
  }
  if (actor.type === 'AGENT') {
    return actor.display_name ?? actor.slug ?? 'Agent';
  }
  if (actor.handle) {
    return `@${actor.handle.replace(/^@/, '')}`;
  }
  return actor.display_name ?? 'System';
}

export function formatEventSummary(item: ActivityItem): string {
  const payload: Record<string, unknown> = (item.payload ?? {}) as Record<string, unknown>;

  switch (item.event_type) {
    case 'CREATOR_OVERRIDDEN': {
      const p = payload as CreatorOverridePayload;
      return `Creator overridden: ${p.old_created_by ?? 'Unknown'} -> ${p.new_created_by ?? 'Unknown'}`;
    }
    case 'STATE_CHANGED': {
      const fromState = typeof payload.from_state === 'string' ? payload.from_state : '';
      const toState = typeof payload.to_state === 'string' ? payload.to_state : '';
      return `changed State from ${fromState} to ${toState}`;
    }
    case 'PRIORITY_CHANGED': {
      const fromPrio = typeof payload.from_priority === 'string' ? payload.from_priority : '';
      const toPrio = typeof payload.to_priority === 'string' ? payload.to_priority : '';
      return `changed Priority from ${fromPrio} to ${toPrio}`;
    }
    case 'ASSIGNEE_ADDED': {
      const assignee = typeof payload.assignee_handle === 'string'
        ? payload.assignee_handle
        : typeof payload.assignee_name === 'string'
          ? payload.assignee_name
          : '';
      return `assigned ${assignee}`;
    }
    case 'ASSIGNEE_REMOVED': {
      const unassignee = typeof payload.assignee_handle === 'string'
        ? payload.assignee_handle
        : typeof payload.assignee_name === 'string'
          ? payload.assignee_name
          : '';
      return `unassigned ${unassignee}`;
    }
    case 'TITLE_CHANGED':
      return 'updated issue summary';
    case 'DESCRIPTION_CHANGED':
      return 'updated issue description';
    case 'LABEL_ADDED': {
      const label = typeof payload.label_name === 'string' ? payload.label_name : '';
      return `added label ${label}`;
    }
    case 'LABEL_REMOVED': {
      const label = typeof payload.label_name === 'string' ? payload.label_name : '';
      return `removed label ${label}`;
    }
    case 'GATE_PENDING': {
      const hookName = typeof payload.hook_name === 'string' ? payload.hook_name : '';
      return `Transition gate pending: ${hookName}`;
    }
    case 'GATE_APPROVED': {
      const hookName = typeof payload.hook_name === 'string' ? payload.hook_name : '';
      return `Transition gate approved: ${hookName}`;
    }
    case 'GATE_VETOED':
    case 'GATE_REJECTED': {
      const hookName = typeof payload.hook_name === 'string' ? payload.hook_name : '';
      return `Transition gate vetoed: ${hookName}`;
    }
    default:
      return item.event_type.toLowerCase().replace(/_/g, ' ');
  }
}

export function ActivityEventRow({
  item,
  onJumpToComment,
}: ActivityEventRowProps): JSX.Element {
  const [copiedHash, setCopiedHash] = useState(false);
  const payload: Record<string, unknown> = (item.payload ?? {}) as Record<string, unknown>;
  const actorName = formatActorName(item.actor);
  const eventSummary = formatEventSummary(item);

  const formattedDate = new Date(item.created_at).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  // Render Gate Pending
  if (item.event_type === 'GATE_PENDING') {
    const gp = payload as GatePayload;
    const hookName = gp.hook_name ?? 'Workflow Gate';
    const rawHarness = gp.harness_label ?? gp.harness ?? 'cli: agy -p';
    const isInAppSdk =
      rawHarness.startsWith('in_app_sdk') ||
      gp.harness_kind === 'in_app_sdk' ||
      ['ollama', 'gemini', 'openai'].includes(gp.provider_kind ?? '') ||
      rawHarness === 'sdk';

    let displayHarness = rawHarness;
    if (isInAppSdk) {
      if (!displayHarness.startsWith('in_app_sdk (')) {
        const prov =
          gp.provider_kind ??
          (rawHarness !== 'in_app_sdk' && rawHarness !== 'sdk' ? rawHarness : 'ollama');
        const mod = gp.model_id ? `/${gp.model_id}` : '';
        displayHarness = `in_app_sdk (${prov}${mod})`;
      }
    }

    const ro = gp.repo_mount_ro !== false ? ':ro' : ':rw';
    const summaryText = isInAppSdk
      ? `evaluating gate via ${displayHarness}`
      : `evaluating gate via ${rawHarness} (${ro})`;
    const tooltipText = `Gate: ${hookName} | Harness: ${displayHarness} | Repo mount: ${ro} | Status: Pending`;

    return (
      <div className="activity-event-row activity-event-row--gate-pending" data-testid="gate-pending-row">
        <EmojiHint
          kind="gatePending"
          variant="tooltip"
          label={`Gate Pending: ${hookName}`}
          content={tooltipText}
        />
        <div className="event-row__content">
          <span className="event-row__actor">{hookName}</span>
          <span className="event-row__summary">
            {summaryText}
          </span>
          <time dateTime={item.created_at} className="event-row__time">
            {formattedDate}
          </time>
        </div>
      </div>
    );
  }

  // Render Gate Approved
  if (item.event_type === 'GATE_APPROVED') {
    const gp = payload as GatePayload;
    const hookName = gp.hook_name ?? 'Workflow Gate';
    const latency = gp.execution_latency_ms !== undefined ? `${String(gp.execution_latency_ms)} ms` : '';
    const hash = gp.verdict_sha256 ?? item.row_hash ?? '';
    const tooltipContent = (
      <div className="gate-tooltip">
        <div className="gate-tooltip__header">
          <strong>{hookName}</strong> {latency ? `(${latency})` : ''}
        </div>
        <div className="gate-tooltip__status">Status: APPROVED</div>
        {hash && (
          <div className="gate-tooltip__hash">
            <span>SHA-256: {hash.slice(0, 16)}...</span>
            <button
              type="button"
              className="gate-tooltip__copy-btn"
              onClick={() => {
                void navigator.clipboard.writeText(hash);
                setCopiedHash(true);
                setTimeout(() => { setCopiedHash(false); }, 2000);
              }}
            >
              {copiedHash ? 'Copied' : 'Copy Hash'}
            </button>
          </div>
        )}
      </div>
    );

    return (
      <div className="activity-event-row activity-event-row--gate-approved" data-testid="gate-approved-row">
        <EmojiHint
          kind="gateApproved"
          variant="tooltip"
          label={`Gate Approved: ${hookName}`}
          content={tooltipContent}
        />
        <div className="event-row__content">
          <span className="event-row__actor">{hookName}</span>
          <span className="event-row__summary">
            approved transition {latency ? `in ${latency}` : ''}
          </span>
          <time dateTime={item.created_at} className="event-row__time">
            {formattedDate}
          </time>
        </div>
      </div>
    );
  }

  // Render Gate Vetoed
  if (item.event_type === 'GATE_VETOED' || item.event_type === 'GATE_REJECTED') {
    const gp = payload as GatePayload;
    const hookName = gp.hook_name ?? 'Workflow Gate';
    const reason = gp.reason ?? 'Transition criteria not satisfied.';
    const auditCommentId = gp.audit_comment_id;

    const tooltipContent = (
      <div className="gate-tooltip gate-tooltip--vetoed">
        <div className="gate-tooltip__header">
          <strong>{hookName}</strong>
        </div>
        <div className="gate-tooltip__reason">{reason}</div>
        {auditCommentId && (
          <button
            type="button"
            className="gate-tooltip__jump-btn"
            onClick={() => { onJumpToComment?.(auditCommentId); }}
          >
            Jump to comment
          </button>
        )}
      </div>
    );

    return (
      <div className="activity-event-row activity-event-row--gate-vetoed" data-testid="gate-vetoed-row">
        <EmojiHint
          kind="gateVetoed"
          variant="interactive"
          label={`Gate Vetoed: ${hookName}`}
          content={tooltipContent}
          {...(auditCommentId
            ? {
                activateLabel: 'Jump to comment',
                onActivate: () => {
                  onJumpToComment?.(auditCommentId);
                },
              }
            : {})}
        />
        <div className="event-row__content">
          <span className="event-row__actor">{hookName}</span>
          <span className="event-row__summary">vetoed transition: {reason.slice(0, 60)}</span>
          {auditCommentId && (
            <button
              type="button"
              className="event-row__jump-link"
              onClick={() => { onJumpToComment?.(auditCommentId); }}
            >
              View audit details
            </button>
          )}
          <time dateTime={item.created_at} className="event-row__time">
            {formattedDate}
          </time>
        </div>
      </div>
    );
  }

  // Render Creator Override
  if (item.event_type === 'CREATOR_OVERRIDDEN') {
    const cp = payload as CreatorOverridePayload;
    const oldCreator = cp.old_created_by ?? 'Unknown';
    const newCreator = cp.new_created_by ?? 'Unknown';
    const reason = cp.reason ?? 'Administrative adjustment';
    const hash = cp.row_hash ?? item.row_hash ?? '';
    const tooltipText = `Creator Overridden: ${oldCreator} -> ${newCreator} | Reason: ${reason}${hash ? ` | Hash: ${hash.slice(0, 12)}...` : ''}`;

    return (
      <div className="activity-event-row activity-event-row--creator-override" data-testid="creator-override-row">
        <EmojiHint
          kind="creatorOverride"
          variant="tooltip"
          label="Creator Overridden"
          content={tooltipText}
        />
        <div className="event-row__content">
          <span className="event-row__actor">{actorName}</span>
          <span className="event-row__summary">
            changed Created by from {oldCreator} to {newCreator} ({reason})
          </span>
          <time dateTime={item.created_at} className="event-row__time">
            {formattedDate}
          </time>
        </div>
      </div>
    );
  }

  // Standard History Row
  return (
    <div className="activity-event-row activity-event-row--history" data-testid="history-row">
      {item.actor.type === 'AGENT' ? (
        <EmojiHint kind="agent" variant="tooltip" label={`Agent: ${actorName}`} content={actorName} />
      ) : (
        <span className="event-row__bullet" aria-hidden="true">•</span>
      )}
      <div className="event-row__content">
        <span className="event-row__actor">{actorName}</span>
        <span className="event-row__summary">{eventSummary}</span>
        <time dateTime={item.created_at} className="event-row__time">
          {formattedDate}
        </time>
      </div>
    </div>
  );
}
