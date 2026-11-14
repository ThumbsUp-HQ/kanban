/**
 * Non-Modal Sticky Promotion Banner (KB-P3-51, S8.2).
 *
 * Renders in sticky card footer when complexity heuristics trigger, offering
 * 1-click Doc promotion or snooze without modal interruption.
 */

import React, { type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';

export interface StickyPromotionBannerProps {
  reasons: string[];
  isPromoting?: boolean | undefined;
  onPromote: () => void;
  onSnooze: () => void;
}

export function StickyPromotionBanner({
  reasons,
  isPromoting = false,
  onPromote,
  onSnooze,
}: StickyPromotionBannerProps): JSX.Element {
  const reasonsText = reasons.length > 0 ? reasons.join(', ') : 'complexity threshold exceeded';
  const hintContent = `Exceeded Sticky complexity (${reasonsText}) - click Promote to Doc to convert while preserving exact ACLs`;

  return (
    <footer
      className="sticky-promotion-banner"
      role="region"
      aria-label="Sticky promotion recommendation"
      data-testid="sticky-promotion-banner"
    >
      <div className="sticky-promotion-banner__left">
        <EmojiHint
          kind="stickyPromotion"
          variant="interactive"
          content={hintContent}
          testId="sticky-promotion-hint"
        />
        <span className="sticky-promotion-banner__label">Growing into a spec</span>
      </div>
      <div className="sticky-promotion-banner__actions">
        <button
          type="button"
          className="sticky-promotion-banner__promote-btn"
          onClick={onPromote}
          disabled={isPromoting}
          aria-label="Promote to Doc"
          data-testid="promote-to-doc-btn"
        >
          {isPromoting ? 'Promoting...' : 'Promote to Doc ->'}
        </button>
        <button
          type="button"
          className="sticky-promotion-banner__snooze-btn"
          onClick={onSnooze}
          disabled={isPromoting}
          aria-label="Snooze promotion"
          data-testid="snooze-promotion-btn"
        >
          Snooze
        </button>
      </div>
    </footer>
  );
}
