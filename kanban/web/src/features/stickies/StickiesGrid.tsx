/**
 * Stickies Grid Component (KB-P3-51, S8.1, S8.2).
 *
 * Implements responsive CSS Grid of 6-palette cards with + New Sticky composer.
 */

import React, { useState, type JSX } from 'react';
import { StickyCard } from './StickyCard';
import { PromotedStickyStub } from './PromotedStickyStub';
import type { StickyColorToken } from './stickyHeuristic';
import type { StickyItem } from './stickiesApi';
import './StickiesGrid.css';

export interface StickiesGridProps {
  stickies: StickyItem[];
  projectKey?: string | undefined;
  title?: string | undefined;
  readOnly?: boolean | undefined;
  isLoading?: boolean | undefined;
  onCreateSticky?: (() => void) | undefined;
  onUpdateSticky: (
    stickyId: string,
    payload: {
      body_markdown?: string | undefined;
      color_token?: StickyColorToken | undefined;
      promotion_snoozed_at_length?: number | null | undefined;
    },
    etag?: string,
  ) => Promise<void> | void;
  onDeleteSticky: (stickyId: string) => Promise<void> | void;
  onPromoteSticky: (
    stickyId: string,
    payload?: {
      title?: string;
      parent_doc_id?: string;
      parent_page_id?: string;
      structured_body_markdown?: string;
      expected_sticky_sha256?: string;
    },
  ) => Promise<void> | void;
  onUnarchiveCopy: (stickyId: string) => Promise<void> | void;
  onMoveSticky?: (
    stickyId: string,
    direction: 'up' | 'down' | 'left' | 'right',
  ) => Promise<void> | void;
}

export function StickiesGrid({
  stickies,
  projectKey,
  title = 'Stickies',
  readOnly = false,
  isLoading = false,
  onCreateSticky,
  onUpdateSticky,
  onDeleteSticky,
  onPromoteSticky,
  onUnarchiveCopy,
  onMoveSticky,
}: StickiesGridProps): JSX.Element {
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [reorderedStickies, setReorderedStickies] = useState<StickyItem[] | null>(null);
  const displayedStickies = reorderedStickies ?? stickies;

  const handleKeyboardMove = (
    stickyId: string,
    direction: 'up' | 'down' | 'left' | 'right',
  ): void => {
    const currentIndex = displayedStickies.findIndex((s) => s.id === stickyId);
    const targetIndex =
      direction === 'left' || direction === 'up'
        ? Math.max(0, currentIndex - 1)
        : Math.min(displayedStickies.length - 1, currentIndex + 1);

    if (currentIndex >= 0 && targetIndex !== currentIndex) {
      const nextList = [...displayedStickies];
      const moved = nextList.splice(currentIndex, 1)[0];
      if (moved) {
        nextList.splice(targetIndex, 0, moved);
        setReorderedStickies(nextList);
      }
      setAnnouncement(
        `Moved sticky note ${direction} to position ${String(targetIndex + 1)} of ${String(displayedStickies.length)}.`,
      );
      if (onMoveSticky) {
        void onMoveSticky(stickyId, direction);
      }
      requestAnimationFrame(() => {
        const el = document.querySelector<HTMLElement>(`[data-testid="sticky-card-${stickyId}"]`);
        el?.focus();
      });
    }
  };

  const handleSpatialNavigate = (
    stickyId: string,
    direction: 'up' | 'down' | 'left' | 'right',
  ): void => {
    const currentIndex = displayedStickies.findIndex((s) => s.id === stickyId);
    const targetIndex =
      direction === 'left' || direction === 'up'
        ? Math.max(0, currentIndex - 1)
        : Math.min(displayedStickies.length - 1, currentIndex + 1);

    if (currentIndex >= 0 && targetIndex !== currentIndex) {
      const target = displayedStickies[targetIndex];
      if (target) {
        const el = document.querySelector<HTMLElement>(
          `[data-testid="sticky-card-${target.id}"], [data-testid="promoted-sticky-stub-${target.id}"]`,
        );
        el?.focus();
      }
    }
  };

  const handleUpdate = async (
    stickyId: string,
    payload: {
      body_markdown?: string | undefined;
      color_token?: StickyColorToken | undefined;
      promotion_snoozed_at_length?: number | null | undefined;
    },
    etag?: string,
  ): Promise<void> => {
    if (payload.color_token) {
      setAnnouncement(`Sticky note color changed to ${payload.color_token}.`);
    }
    await onUpdateSticky(stickyId, payload, etag);
  };

  const handlePromote = async (
    stickyId: string,
    payload?: {
      title?: string;
      parent_doc_id?: string;
      parent_page_id?: string;
      structured_body_markdown?: string;
      expected_sticky_sha256?: string;
    },
  ): Promise<void> => {
    await onPromoteSticky(stickyId, payload);
    setAnnouncement('Promoted sticky to Doc - exact ACLs and object links preserved.');
  };

  const handleUnarchive = async (stickyId: string): Promise<void> => {
    await onUnarchiveCopy(stickyId);
    setAnnouncement('Created editable copy of sticky note.');
  };

  return (
    <section
      className="stickies-container"
      aria-label={title}
      data-testid="stickies-container"
    >
      <header className="stickies-container__header">
        <h1 className="stickies-container__title">{title}</h1>
        {!readOnly && onCreateSticky ? (
          <button
            type="button"
            className="stickies-container__new-btn"
            onClick={onCreateSticky}
            aria-label="Create new sticky note"
            data-testid="new-sticky-btn"
          >
            <span aria-hidden="true">+</span> New Sticky
          </button>
        ) : null}
      </header>

      {/* Accessible Live Region for Announcements */}
      {announcement ? (
        <div
          role="status"
          aria-live="polite"
          className="stickies-announcement visually-hidden"
          data-testid="stickies-announcement"
        >
          {announcement}
        </div>
      ) : null}

      <div className="stickies-grid" data-testid="stickies-grid">
        {isLoading && stickies.length === 0 ? (
          <div className="stickies-loading" data-testid="stickies-loading">
            Loading stickies...
          </div>
        ) : stickies.length === 0 ? (
          <div className="stickies-empty" data-testid="stickies-empty">
            <h2 className="stickies-empty__title">No stickies yet</h2>
            <p className="stickies-empty__desc">
              Capture quick thoughts, triage scratchpads, or architecture notes.
            </p>
            {!readOnly && onCreateSticky ? (
              <button
                type="button"
                className="stickies-container__new-btn"
                onClick={onCreateSticky}
              >
                + Create your first sticky
              </button>
            ) : null}
          </div>
        ) : (
          displayedStickies.map((sticky) =>
            sticky.is_promoted_stub || sticky.promoted_to_doc_id !== null ? (
              <PromotedStickyStub
                key={sticky.id}
                sticky={sticky}
                projectKey={projectKey}
                onUnarchiveCopy={() => {
                  void handleUnarchive(sticky.id);
                }}
              />
            ) : (
              <StickyCard
                key={sticky.id}
                sticky={sticky}
                projectKey={projectKey}
                readOnly={readOnly}
                onUpdate={handleUpdate}
                onDelete={onDeleteSticky}
                onPromote={handlePromote}
                onAnnounce={setAnnouncement}
                onKeyboardMove={handleKeyboardMove}
                onSpatialNavigate={handleSpatialNavigate}
              />
            ),
          )
        )}
      </div>
    </section>
  );
}
