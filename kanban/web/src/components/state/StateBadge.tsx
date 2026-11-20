import React, { useEffect, useRef, type JSX } from 'react';
import { StateProgressRing } from '../icons/KanbanIcons';
import './StateBadge.css';

export type StateGroupKey = 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';

export interface StateObject {
  id?: string | undefined;
  name?: string | undefined;
  group?: StateGroupKey | (string & {}) | undefined;
  color_hex?: string | null | undefined;
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
  state?: StateObject | string | undefined;
  name?: string | undefined;
  group?: StateGroupKey | (string & {}) | undefined;
  color_hex?: string | null | undefined;
  colorHex?: string | null | undefined;
  showEmoji?: boolean | undefined;
  showRing?: boolean | undefined;
  showLabel?: boolean | undefined;
  className?: string | undefined;
  testId?: string | undefined;
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
  color_hex,
  colorHex,
  showEmoji = true,
  showRing = true,
  showLabel = true,
  className = '',
  testId,
}: StateBadgeProps): JSX.Element {
  const badgeRef = useRef<HTMLSpanElement | null>(null);

  const rawColorHex =
    colorHex ??
    color_hex ??
    (typeof state === 'object' ? state.color_hex : null);
  const safeHex =
    rawColorHex && /^#[0-9A-Fa-f]{6}$/.test(rawColorHex.trim())
      ? rawColorHex.trim()
      : null;

  useEffect(() => {
    const el = badgeRef.current;
    if (!el) return;
    if (safeHex) {
      el.style.setProperty('--state-custom-fg', safeHex);
    } else {
      el.style.removeProperty('--state-custom-fg');
    }
  }, [safeHex]);

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
    safeHex ? 'state-badge--custom' : '',
    isCompact ? 'state-badge--compact' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span
      ref={badgeRef}
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
          stroke={safeHex ?? undefined}
        />
      )}
      {showLabel && (
        <span className="state-badge__label">{resolvedName}</span>
      )}
    </span>
  );
}
