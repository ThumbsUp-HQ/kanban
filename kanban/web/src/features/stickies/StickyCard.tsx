/**
 * Sticky Card Component (KB-P3-51, S8.1, S8.2).
 *
 * Implements 6-palette color swatches, embedded MarkdownEditor with 1000ms idle debounce,
 * complexity evaluation, 💡📄 promotion banner, and access inspector trigger.
 */

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { MarkdownEditor } from '../../editor/MarkdownEditor';
import {
  evaluateStickyComplexity,
  STICKY_COLOR_TOKENS,
  STICKY_IDLE_DEBOUNCE_MS,
  type StickyColorToken,
  type StickyComplexityEvaluation,
} from './stickyHeuristic';
import { StickyPromotionBanner } from './StickyPromotionBanner';
import type { StickyItem } from './stickiesApi';

export interface StickyCardProps {
  sticky: StickyItem;
  projectKey?: string | undefined;
  readOnly?: boolean | undefined;
  debounceMs?: number | undefined;
  onUpdate: (
    stickyId: string,
    payload: {
      body_markdown?: string | undefined;
      color_token?: StickyColorToken | undefined;
      promotion_snoozed_at_length?: number | null | undefined;
    },
    etag?: string,
  ) => Promise<void> | void;
  onDelete: (stickyId: string) => Promise<void> | void;
  onPromote: (stickyId: string) => Promise<void> | void;
}

export function StickyCard({
  sticky,
  readOnly = false,
  debounceMs = STICKY_IDLE_DEBOUNCE_MS,
  onUpdate,
  onDelete,
  onPromote,
}: StickyCardProps): JSX.Element {
  const [body, setBody] = useState(sticky.body_markdown);
  const [evaluatedBody, setEvaluatedBody] = useState(sticky.body_markdown);
  const [color, setColor] = useState<StickyColorToken>(sticky.color_token);
  const [snoozedAt, setSnoozedAt] = useState<number | null>(
    sticky.promotion_snoozed_at_length,
  );
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isPromoting, setIsPromoting] = useState(false);

  const effectiveCaps = sticky.capabilities ?? (readOnly ? ['VIEW'] : ['EDIT', 'DELETE', 'ADMIN']);
  const canEdit = !readOnly && (effectiveCaps.includes('EDIT') || effectiveCaps.includes('ADMIN'));
  const canDelete = !readOnly && (effectiveCaps.includes('DELETE') || effectiveCaps.includes('ADMIN'));

  // Complexity evaluation runs on debounced evaluatedBody
  const evaluation: StickyComplexityEvaluation = evaluateStickyComplexity(
    evaluatedBody,
    snoozedAt,
    sticky.promoted_to_doc_id,
  );

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushSave = useCallback(
    (nextBody: string) => {
      if (nextBody !== sticky.body_markdown) {
        void onUpdate(
          sticky.id,
          { body_markdown: nextBody },
          sticky.etag,
        );
      }
    },
    [sticky.id, sticky.body_markdown, sticky.etag, onUpdate],
  );

  const handleBodyChange = (nextMarkdown: string): void => {
    setBody(nextMarkdown);

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      setEvaluatedBody(nextMarkdown);
      flushSave(nextMarkdown);
    }, debounceMs);
  };

  const handleBodyBlur = (currentMarkdown: string): void => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    setEvaluatedBody(currentMarkdown);
    flushSave(currentMarkdown);
  };

  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleColorSelect = (nextColor: StickyColorToken): void => {
    setColor(nextColor);
    void onUpdate(
      sticky.id,
      { color_token: nextColor },
      sticky.etag,
    );
  };

  const handleColorKeyDown = (
    e: KeyboardEvent<HTMLDivElement>,
    currentColor: StickyColorToken,
  ): void => {
    const currentIndex = STICKY_COLOR_TOKENS.indexOf(currentColor);
    let nextIndex = currentIndex;

    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % STICKY_COLOR_TOKENS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      nextIndex =
        (currentIndex - 1 + STICKY_COLOR_TOKENS.length) %
        STICKY_COLOR_TOKENS.length;
    }

    if (nextIndex !== currentIndex) {
      const nextColor = STICKY_COLOR_TOKENS[nextIndex];
      if (typeof nextColor === 'string') {
        handleColorSelect(nextColor);
      }
    }
  };

  const handleSnooze = (): void => {
    setSnoozedAt(evaluation.charLength);
    void onUpdate(
      sticky.id,
      { promotion_snoozed_at_length: evaluation.charLength },
      sticky.etag,
    );
  };

  const handlePromote = async (): Promise<void> => {
    setIsPromoting(true);
    try {
      await onPromote(sticky.id);
    } finally {
      setIsPromoting(false);
    }
  };

  const handleAccessClick = (): void => {
    window.dispatchEvent(
      new CustomEvent('kb:open-access-inspector', {
        detail: { objectId: sticky.id, objectKind: 'sticky' },
      }),
    );
  };

  return (
    <article
      className={`sticky-card sticky-card--${color}`}
      aria-label={`Sticky note in ${color}`}
      data-testid={`sticky-card-${sticky.id}`}
      data-sticky-id={sticky.id}
    >
      <header className="sticky-card__header">
        {/* 6-swatch palette radiogroup */}
        {canEdit && (
          <div
            role="radiogroup"
            aria-label="Sticky color"
            className="sticky-card__palette"
            onKeyDown={(e) => { handleColorKeyDown(e, color); }}
          >
            {STICKY_COLOR_TOKENS.map((token) => {
              const isSelected = token === color;
              return (
                <button
                  key={token}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  aria-label={`Color ${token}`}
                  className={`sticky-swatch sticky-swatch--${token}${isSelected ? ' sticky-swatch--selected' : ''}`}
                  onClick={() => { handleColorSelect(token); }}
                  tabIndex={isSelected ? 0 : -1}
                  data-testid={`color-swatch-${token}`}
                />
              );
            })}
          </div>
        )}

        <div className="sticky-card__actions">
          {/* Access Inspector 🛡️ */}
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

          {/* ⋯ Overflow menu */}
          {(canEdit || canDelete) && (
            <div className="sticky-card__menu-container">
              <button
                type="button"
                className="sticky-card__menu-trigger"
                onClick={() => { setIsMenuOpen((prev) => !prev); }}
                aria-label="Sticky actions"
                aria-haspopup="menu"
                aria-expanded={isMenuOpen}
                data-testid={`sticky-menu-trigger-${sticky.id}`}
              >
                ⋯
              </button>
              {isMenuOpen ? (
                <div
                  className="sticky-card__menu"
                  role="menu"
                  aria-label="Sticky actions"
                >
                  {canEdit && (
                    <button
                      type="button"
                      role="menuitem"
                      className="sticky-card__menu-item"
                      onClick={() => {
                        setIsMenuOpen(false);
                        void handlePromote();
                      }}
                      data-testid="convert-to-doc-menuitem"
                    >
                      Convert to Doc
                    </button>
                  )}
                  {canDelete && (
                    <button
                      type="button"
                      role="menuitem"
                      className="sticky-card__menu-item sticky-card__menu-item--danger"
                      onClick={() => {
                        setIsMenuOpen(false);
                        void onDelete(sticky.id);
                      }}
                      data-testid="delete-sticky-menuitem"
                    >
                      Delete Sticky
                    </button>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </header>

      {/* Embedded ProseMirror Markdown Editor */}
      <div className="sticky-card__editor-wrapper">
        <MarkdownEditor
          surface="sticky"
          value={body}
          onChange={handleBodyChange}
          onBlur={handleBodyBlur}
          readOnly={readOnly || !canEdit}
          maxBytes={65536}
          ariaLabel="Sticky markdown content"
          testId={`sticky-editor-${sticky.id}`}
        />
      </div>

      {/* 💡📄 Non-modal promotion banner */}
      {canEdit && evaluation.shouldShowBanner ? (
        <StickyPromotionBanner
          reasons={evaluation.reasons}
          isPromoting={isPromoting}
          onPromote={() => { void handlePromote(); }}
          onSnooze={handleSnooze}
        />
      ) : null}
    </article>
  );
}
