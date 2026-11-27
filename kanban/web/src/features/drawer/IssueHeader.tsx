import React, { useState, useMemo, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { EmojiKey } from '../../components/emoji/emojiRegistry';
import { StateBadge } from '../../components/state/StateBadge';
import { AccessPill } from './AccessPill';
import { useIssueSurfaceSlots, type IssueDetail } from './slots';
import { copyToClipboard } from '../../utils/clipboard';
import { patchIssue } from '../drawer-rail/railApi';
import type { StateSummary } from '../views/viewsApi';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './IssueHeader.css';

export interface IssueHeaderProps {
  issue: IssueDetail;
  mode: 'drawer' | 'full';
  onClose: () => void;
  toggleFullScreen: () => void;
  projectStates?: StateSummary[] | undefined;
  onStateChange?: ((stateId: string) => Promise<void>) | undefined;
  currentUserCapabilities?: string[] | undefined;
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
  projectStates,
  onStateChange,
  currentUserCapabilities,
}: IssueHeaderProps): JSX.Element {
  const slots = useIssueSurfaceSlots();
  const priorityKey = getPriorityEmojiKey(issue.priority?.slug);

  const capabilities = currentUserCapabilities ?? issue.capabilities ?? ['EDIT', 'TRANSITION'];
  const canTransition =
    capabilities.includes('TRANSITION') ||
    capabilities.includes('EDIT') ||
    capabilities.includes('ADMIN');

  const availableStates = useMemo(() => {
    if (projectStates && projectStates.length > 0) {
      const list = [...projectStates];
      if (issue.state && !list.some((s) => s.id === issue.state?.id)) {
        list.push({
          id: issue.state.id ?? 'state-current',
          name: issue.state.name,
          group: issue.state.group,
        });
      }
      return list;
    }
    const defaultStates = [
      { id: 'state-backlog', name: 'Backlog', group: 'backlog' as const },
      { id: 'state-todo', name: 'Todo', group: 'unstarted' as const },
      { id: 'state-in-progress', name: 'In Progress', group: 'started' as const },
      { id: 'state-in-review', name: 'In Review', group: 'started' as const },
      { id: 'state-done', name: 'Done', group: 'completed' as const },
      { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled' as const },
    ];
    if (issue.state && !defaultStates.some((s) => s.id === issue.state?.id)) {
      defaultStates.push({
        id: issue.state.id ?? 'state-current',
        name: issue.state.name,
        group: issue.state.group as 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled',
      });
    }
    return defaultStates;
  }, [projectStates, issue.state]);

  const [isTransitioning, setIsTransitioning] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  const handleStateSelect = async (stateId: string): Promise<void> => {
    setIsTransitioning(true);
    setTransitionError(null);
    try {
      if (onStateChange) {
        await onStateChange(stateId);
      } else {
        await patchIssue(issue.key, { state_id: stateId }, issue.etag);
      }
    } catch (err: unknown) {
      const errObj = typeof err === 'object' && err !== null ? (err as Record<string, unknown>) : null;
      const msg =
        err instanceof Error
          ? err.message
          : typeof errObj?.detail === 'string'
            ? errObj.detail
            : typeof errObj?.message === 'string'
              ? errObj.message
              : 'State transition failed';
      setTransitionError(msg);
    } finally {
      setIsTransitioning(false);
    }
  };

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
        className="issue-header__btn issue-header__back-btn"
        data-testid="issue-back-to-list-btn"
        aria-label={mode === 'full' ? 'Back to issues list' : 'Close issue panel'}
        title={mode === 'full' ? 'Back to list' : 'Close issue panel'}
        onClick={onClose}
      >
        <span aria-hidden="true" className="issue-header__glyph">
          {mode === 'full' ? '←' : '→'}
        </span>
        {mode === 'full' && <span className="issue-back-to-list-text"> Back to list</span>}
      </button>

      <button
        type="button"
        className={`issue-header__btn ${mode === 'full' ? 'issue-header__fullscreen-toggle--active' : ''}`}
        data-testid="issue-header-fullscreen-toggle"
        aria-label={mode === 'full' ? 'Return to side panel' : 'Open in full screen'}
        title={mode === 'full' ? 'Return to side panel (Meta+Shift+F)' : 'Open in full screen (Meta+Shift+F)'}
        aria-keyshortcuts="Meta+Shift+F Control+Shift+F"
        onMouseDown={(e) => { e.preventDefault(); }}
        onClick={toggleFullScreen}
      >
        <span aria-hidden="true" className="issue-header__glyph">
          {mode === 'full' ? '↙' : '↗'}
        </span>
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

      {canTransition ? (
        <select
          data-testid="header-state-select"
          className="header-state-select"
          aria-label="Workflow State"
          value={issue.state?.id ?? ''}
          disabled={isTransitioning}
          onChange={(e) => {
            void handleStateSelect(e.target.value);
          }}
        >
          {availableStates.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      ) : (
        <StateBadge state={issue.state ?? undefined} testId="header-state-badge" />
      )}
      {transitionError && (
        <div
          role="alert"
          className="header-state-error"
          data-testid="header-state-error"
        >
          {transitionError}
        </div>
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
        <StudioDocLink
          href="/docs/ticket-screen-and-work-item-features#the-960px-ticket-peek-drawer-peek"
          label="Ticket Guide ->"
          testId="issue-header-doc-link"
        />
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
