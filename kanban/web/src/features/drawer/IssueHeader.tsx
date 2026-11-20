import React, { useState, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { EmojiKey } from '../../components/emoji/emojiRegistry';
import { AccessPill } from './AccessPill';
import { useIssueSurfaceSlots, type IssueDetail } from './slots';
import { copyToClipboard } from '../../utils/clipboard';
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

  const [copiedKey, setCopiedKey] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);

  const handleCopyKey = async (): Promise<void> => {
    const ok = await copyToClipboard(issue.key);
    if (ok) {
      setCopiedKey(true);
      setTimeout(() => {
        setCopiedKey(false);
      }, 2000);
    }
  };

  const handleCopyLink = async (): Promise<void> => {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const linkUrl = `${origin}/projects/${issue.project_key}/issues/${issue.key}`;
    const ok = await copyToClipboard(linkUrl);
    if (ok) {
      setCopiedLink(true);
      setTimeout(() => {
        setCopiedLink(false);
      }, 2000);
    }
  };

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

      <div className="issue-header__key-group">
        <span className="mono issue-header__key">{issue.key}</span>
        <button
          type="button"
          className="issue-header__copy-btn"
          data-testid="copy-issue-key-btn"
          aria-label={`Copy issue key ${issue.key}`}
          title={copiedKey ? 'Copied!' : 'Copy issue key'}
          onClick={() => {
            void handleCopyKey();
          }}
        >
          {copiedKey ? 'Copied!' : '📋'}
        </button>
        <button
          type="button"
          className="issue-header__copy-btn"
          data-testid="copy-issue-link-btn"
          aria-label={`Copy issue link for ${issue.key}`}
          title={copiedLink ? 'Copied!' : 'Copy issue link'}
          onClick={() => {
            void handleCopyLink();
          }}
        >
          {copiedLink ? 'Copied!' : '🔗'}
        </button>
      </div>

      <AccessPill
        issue={{
          ...issue,
          object_id: issue.object_id ?? issue.id,
        }}
      />

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
