import React, { type JSX } from 'react';
import { StateProgressRing } from '../icons/KanbanIcons';
import './StateBadge.css';

export type StateGroupKey = 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';

export interface StateObject {
  id?: string;
  name?: string;
  group?: StateGroupKey | (string & {});
}

export const STATE_EMOJI_MAP: Record<StateGroupKey, string> = {
  backlog: '🗂️',
  unstarted: '📋',
  started: '⚙️',
  completed: '✅',
  cancelled: '🚫',
};

export function normalizeStateGroup(groupOrName?: string): StateGroupKey {
  const s = (groupOrName ?? '').toLowerCase().trim().replace(/[\s-]/g, '_');
  if (s.includes('backlog')) return 'backlog';
  if (s.includes('todo') || s.includes('unstarted')) return 'unstarted';
  if (s.includes('progress') || s.includes('review') || s.includes('started')) return 'started';
  if (s.includes('done') || s.includes('complete')) return 'completed';
  if (s.includes('cancel')) return 'cancelled';
  return 'unstarted';
}

export interface StateBadgeProps {
  state?: StateObject | string;
  name?: string;
  group?: StateGroupKey | (string & {});
  showEmoji?: boolean;
  showRing?: boolean;
  showLabel?: boolean;
  className?: string;
  testId?: string;
}

/**
 * Color-coded Workflow State Badge (KB-UX-02).
 * Distinct semantic state emojis (🗂️ Backlog, 📋 Unstarted/Todo, ⚙️ Started/In Progress, ✅ Completed/Done, 🚫 Cancelled)
 * paired with an SVG state progress ring and tokens.css semantic palette.
 * Strict CSP Invariant: Zero inline styles.
 */
export function StateBadge({
  state,
  name,
  group,
  showEmoji = true,
  showRing = true,
  showLabel = true,
  className = '',
  testId,
}: StateBadgeProps): JSX.Element {
  let resolvedGroup: StateGroupKey = 'unstarted';
  let resolvedName = name ?? '';

  if (typeof state === 'string') {
    resolvedGroup = normalizeStateGroup(group ?? state);
    if (!resolvedName) resolvedName = state;
  } else if (state && typeof state === 'object') {
    resolvedGroup = normalizeStateGroup(group ?? state.group ?? state.name);
    if (!resolvedName) resolvedName = state.name ?? resolvedGroup;
  } else if (group) {
    resolvedGroup = normalizeStateGroup(group);
    if (!resolvedName) resolvedName = resolvedGroup;
  }

  if (!resolvedName) {
    resolvedName = resolvedGroup.charAt(0).toUpperCase() + resolvedGroup.slice(1);
  }

  const emoji = STATE_EMOJI_MAP[resolvedGroup];
  const isReview = resolvedName.toLowerCase().includes('review');
  const ringState = isReview ? 'in_review' : resolvedGroup;
  const isCompact = !showLabel;

  const classNames = [
    'state-badge',
    `state-badge--${resolvedGroup}`,
    isCompact ? 'state-badge--compact' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span
      className={classNames}
      data-state-group={resolvedGroup}
      data-testid={testId ?? `state-badge-${resolvedGroup}`}
      title={resolvedName}
    >
      {showEmoji && (
        <span className="state-badge__emoji" aria-hidden="true">
          {emoji}
        </span>
      )}
      {showRing && (
        <StateProgressRing
          state={ringState}
          size={14}
          className="state-badge__ring"
        />
      )}
      {showLabel && (
        <span className="state-badge__label">{resolvedName}</span>
      )}
    </span>
  );
}
