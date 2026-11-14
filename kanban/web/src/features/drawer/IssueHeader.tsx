import React, { type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { EmojiKey } from '../../components/emoji/emojiRegistry';
import { AccessPill } from './AccessPill';
import { useIssueSurfaceSlots, type IssueDetail } from './slots';
import './IssueHeader.css';

export interface IssueHeaderProps {
  issue: IssueDetail;
  mode: 'drawer' | 'full';
  onClose: () => void;
  toggleFullScreen: () => void;
}

function getPriorityEmojiKey(slug: string | undefined): EmojiKey | null {
  if (!slug) return null;
  const normalized = slug.toLowerCase();
  switch (normalized) {
    case 'urgent':
      return 'priorityUrgent';
    case 'high':
      return 'priorityHigh';
    case 'medium':
      return 'priorityMedium';
    case 'low':
      return 'priorityLow';
    default:
      return null;
  }
}

export function IssueHeader({
  issue,
  mode,
  onClose,
  toggleFullScreen,
}: IssueHeaderProps): JSX.Element {
  const slots = useIssueSurfaceSlots();
  const priorityKey = getPriorityEmojiKey(issue.priority?.slug);

  const priorityTooltip = issue.priority
    ? `Priority: ${issue.priority.label} - sort weight ${String(issue.priority.sort_order)}. SLA target: ${issue.priority.sla_target ?? 'not configured'}. Press P to change.`
    : '';

  const SubscribeSlot = slots.subscribe;
  const LinkSlot = slots.link;
  const OverflowSlot = slots.overflow;

  return (
    <header className="surface__header">
      <button
        type="button"
        className="issue-header__btn"
        aria-label="Close issue panel"
        onClick={onClose}
      >
        <span aria-hidden="true" className="issue-header__glyph">→</span>
      </button>

      <button
        type="button"
        className="issue-header__btn"
        aria-label={mode === 'full' ? 'Return to side panel' : 'Open in full screen'}
        aria-keyshortcuts="Meta+Shift+F Control+Shift+F"
        onMouseDown={(e) => { e.preventDefault(); }}
        onClick={toggleFullScreen}
      >
        <span aria-hidden="true" className="issue-header__glyph">↗</span>
      </button>

      {priorityKey && issue.priority && (
        <EmojiHint
          kind={priorityKey}
          variant="tooltip"
          label={`Priority: ${issue.priority.label}`}
          content={priorityTooltip}
          testId="priority-hint"
        />
      )}

      <span className="mono issue-header__key">{issue.key}</span>

      <AccessPill issue={issue} />

      <div className="issue-header__slots">
        {SubscribeSlot && <SubscribeSlot issue={issue} />}
        {LinkSlot && <LinkSlot issue={issue} />}
        {OverflowSlot && (
          <OverflowSlot
            issue={issue}
            mode={mode}
            toggleFullScreen={toggleFullScreen}
          />
        )}
      </div>
    </header>
  );
}
