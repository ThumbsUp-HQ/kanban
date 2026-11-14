/**
 * Promoted Sticky Stub Component (KB-P3-51, S8.2).
 *
 * Renders compact placeholder card for stickies that have graduated into permanent Docs.
 */

import React, { type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { StickyItem } from './stickiesApi';

export interface PromotedStickyStubProps {
  sticky: StickyItem;
  projectKey?: string | undefined;
  isUnarchiving?: boolean | undefined;
  onUnarchiveCopy: () => void;
  onOpenAccessInspector?: (() => void) | undefined;
}

export function PromotedStickyStub({
  sticky,
  projectKey,
  isUnarchiving = false,
  onUnarchiveCopy,
  onOpenAccessInspector,
}: PromotedStickyStubProps): JSX.Element {
  // Derive 2-line preview from body_markdown
  const previewText = sticky.body_markdown
    .replace(/^#+\s+/gm, '')
    .replace(/[`*_[\]]/g, '')
    .trim()
    .slice(0, 160);

  const docTitle = sticky.promoted_to_doc?.title ?? 'Promoted Specification';
  const docId = sticky.promoted_to_doc_id ?? sticky.promoted_to_doc?.id ?? '';
  const docLink = projectKey
    ? `/projects/${encodeURIComponent(projectKey)}/docs/${encodeURIComponent(docId)}`
    : `/docs/${encodeURIComponent(docId)}`;

  const handleAccessClick = (): void => {
    if (onOpenAccessInspector) {
      onOpenAccessInspector();
    } else {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId: sticky.id, objectKind: 'sticky' },
        }),
      );
    }
  };

  return (
    <article
      className={`sticky-card sticky-card--${sticky.color_token} sticky-card--promoted`}
      aria-label={`Promoted sticky: ${docTitle}`}
      data-testid={`promoted-sticky-stub-${sticky.id}`}
      data-sticky-id={sticky.id}
    >
      <header className="sticky-card__header">
        <div className="promoted-stub__header-left">
          <span className="promoted-stub__badge" aria-label="Promoted to Doc">
            <span aria-hidden="true">📄</span> Promoted to Doc
          </span>
          <span className="sticky-card__access-btn">
            <EmojiHint
              kind="access"
              variant="interactive"
              label="Inspect effective access"
              content="Inspect explicit ACLs, group inheritances, and agent restrictions"
              onActivate={handleAccessClick}
              testId={`access-hint-${sticky.id}`}
            />
          </span>
        </div>
      </header>

      <div className="promoted-stub__body">
        <h3 className="promoted-stub__title">{docTitle}</h3>
        {previewText ? (
          <p className="promoted-stub__preview">{previewText}</p>
        ) : null}
      </div>

      <footer className="promoted-stub__footer">
        <a
          href={docLink}
          className="promoted-stub__open-link"
          aria-label={`Open Doc: ${docTitle}`}
          data-testid="open-doc-link"
        >
          <span aria-hidden="true">📄</span> Open Doc
        </a>
        <button
          type="button"
          className="promoted-stub__unarchive-btn"
          onClick={onUnarchiveCopy}
          disabled={isUnarchiving}
          aria-label="Unarchive editable sticky copy"
          data-testid="unarchive-copy-btn"
        >
          {isUnarchiving ? 'Copying...' : 'Unarchive Copy'}
        </button>
      </footer>
    </article>
  );
}
