/**
 * Stickies Dev Story Harness (KB-P3-51, S8.1, S8.2).
 */

import React, { useState, type JSX } from 'react';
import { StickiesGrid } from '../features/stickies/StickiesGrid';
import type { StickyItem } from '../features/stickies/stickiesApi';
import type { StickyColorToken } from '../features/stickies/stickyHeuristic';
import initialStickiesJson from '../../e2e/fixtures/stickies-kan.json';
import './StickiesStory.css';

export function StickiesStory(): JSX.Element {
  const [stickies, setStickies] = useState<StickyItem[]>(
    initialStickiesJson as unknown as StickyItem[],
  );
  const [isDark, setIsDark] = useState(false);

  const toggleTheme = (): void => {
    const nextDark = !isDark;
    setIsDark(nextDark);
    if (nextDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
    }
  };

  const handleCreateSticky = (): void => {
    const newSticky: StickyItem = {
      id: `sticky-${String(Date.now())}`,
      workspace_id: 'ws-1',
      project_id: 'proj-1',
      body_markdown: 'New rapid triage note...',
      color_token: 'amber',
      sort_rank: String(stickies.length),
      promotion_recommended: false,
      promotion_snoozed_at_length: null,
      promoted_to_doc_id: null,
      is_promoted_stub: false,
      triggers: [],
      capabilities: ['EDIT', 'DELETE', 'PROMOTE'],
    };
    setStickies((prev) => [newSticky, ...prev]);
  };

  const handleUpdateSticky = (
    stickyId: string,
    payload: {
      body_markdown?: string | undefined;
      color_token?: StickyColorToken | undefined;
      promotion_snoozed_at_length?: number | null | undefined;
    },
  ): void => {
    setStickies((prev) =>
      prev.map((s) => {
        if (s.id !== stickyId) return s;
        return {
          ...s,
          body_markdown: payload.body_markdown ?? s.body_markdown,
          color_token: payload.color_token ?? s.color_token,
          promotion_snoozed_at_length:
            payload.promotion_snoozed_at_length !== undefined
              ? payload.promotion_snoozed_at_length
              : s.promotion_snoozed_at_length,
        };
      }),
    );
  };

  const handleDeleteSticky = (stickyId: string): void => {
    setStickies((prev) => prev.filter((s) => s.id !== stickyId));
  };

  const handlePromoteSticky = (stickyId: string): void => {
    setStickies((prev) =>
      prev.map((s) => {
        if (s.id !== stickyId) return s;
        return {
          ...s,
          promoted_to_doc_id: 'doc-promoted-1',
          is_promoted_stub: true,
          promoted_to_doc: {
            id: 'doc-promoted-1',
            canonical_key: 'DOC-PROM',
            title: s.body_markdown.split('\n')[0]?.replace(/^#+\s*/, '') ?? 'Promoted Specification',
          },
        };
      }),
    );
  };

  const handleUnarchiveCopy = (stickyId: string): void => {
    const original = stickies.find((s) => s.id === stickyId);
    if (!original) return;
    const copy: StickyItem = {
      ...original,
      id: `copy-${String(Date.now())}`,
      promoted_to_doc_id: null,
      is_promoted_stub: false,
      promoted_to_doc: null,
    };
    setStickies((prev) => [copy, ...prev]);
  };

  return (
    <div className="stickies-story" data-testid="stickies-story">
      <header className="stickies-story__header">
        <h2 className="stickies-story__title">Stickies 6-Palette & Promotion Dev Story</h2>
        <div className="stickies-story__controls">
          <button
            type="button"
            className="stickies-story__btn"
            onClick={toggleTheme}
            data-testid="toggle-theme-btn"
          >
            {isDark ? '☀️ Light Theme' : '🌙 Dark Theme'}
          </button>
          <button
            type="button"
            className="stickies-story__btn"
            onClick={handleCreateSticky}
            data-testid="story-new-sticky-btn"
          >
            + New Sticky
          </button>
        </div>
      </header>

      <main className="stickies-story__content">
        <StickiesGrid
          stickies={stickies}
          projectKey="KAN"
          title="Project Overview Stickies"
          onCreateSticky={handleCreateSticky}
          onUpdateSticky={handleUpdateSticky}
          onDeleteSticky={handleDeleteSticky}
          onPromoteSticky={handlePromoteSticky}
          onUnarchiveCopy={handleUnarchiveCopy}
        />
      </main>
    </div>
  );
}
