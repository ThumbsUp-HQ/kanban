// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import {
  BRAND_TITLE,
  stripLeadingThumb,
  formatDocumentTitle,
  useDocumentTitle,
} from '../documentTitle';

describe('documentTitle module', () => {
  const originalTitle = document.title;

  beforeEach(() => {
    document.title = originalTitle;
  });

  afterEach(() => {
    document.title = originalTitle;
    vi.restoreAllMocks();
  });

  describe('BRAND_TITLE', () => {
    it('equals "kanban"', () => {
      expect(BRAND_TITLE).toBe('kanban');
    });
  });

  describe('stripLeadingThumb', () => {
    it('returns empty string for null, undefined, or empty input', () => {
      expect(stripLeadingThumb('')).toBe('');
      expect(stripLeadingThumb(null as unknown as string)).toBe('');
      expect(stripLeadingThumb(undefined as unknown as string)).toBe('');
    });

    it('returns empty string when input consists only of thumbs or whitespace', () => {
      expect(stripLeadingThumb('👍')).toBe('');
      expect(stripLeadingThumb('  👍  ')).toBe('');
      expect(stripLeadingThumb('👍👍')).toBe('');
      expect(stripLeadingThumb('   ')).toBe('');
    });

    it('strips leading thumb touching text directly', () => {
      expect(stripLeadingThumb('👍kanban')).toBe('kanban');
      expect(stripLeadingThumb('👍BugFix')).toBe('BugFix');
    });

    it('strips leading thumb with whitespace', () => {
      expect(stripLeadingThumb('👍 Critical Bug Fix')).toBe('Critical Bug Fix');
      expect(stripLeadingThumb('  👍   Issue Title   ')).toBe('Issue Title');
    });

    it('strips multiple leading thumbs and handles variation selector-16', () => {
      expect(stripLeadingThumb('👍 👍 KAN-42')).toBe('KAN-42');
      expect(stripLeadingThumb('👍\uFE0F Refactor Auth')).toBe('Refactor Auth');
    });

    it('preserves text without thumbs', () => {
      expect(stripLeadingThumb('Normal Title')).toBe('Normal Title');
      expect(stripLeadingThumb('kanban')).toBe('kanban');
    });

    it('preserves thumbs located in the middle or end of text', () => {
      expect(stripLeadingThumb('Feature with 👍 emoji')).toBe('Feature with 👍 emoji');
      expect(stripLeadingThumb('Thumbs at end 👍')).toBe('Thumbs at end 👍');
    });
  });

  describe('formatDocumentTitle', () => {
    it('returns BRAND_TITLE when parts array is empty or contains only null/undefined/empty', () => {
      expect(formatDocumentTitle([])).toBe(BRAND_TITLE);
      expect(formatDocumentTitle([null, undefined, '', '   '])).toBe(BRAND_TITLE);
    });

    it('appends BRAND_TITLE when not already present at the end', () => {
      expect(formatDocumentTitle(['Login'])).toBe('Login - kanban');
      expect(formatDocumentTitle(['Docs', 'System Overview'])).toBe('Docs - System Overview - kanban');
    });

    it('does not duplicate BRAND_TITLE if already present at the end', () => {
      expect(formatDocumentTitle(['kanban'])).toBe('kanban');
      expect(formatDocumentTitle(['Docs', 'kanban'])).toBe('Docs - kanban');
      expect(formatDocumentTitle(['About', 'Kanban'])).toBe('About - Kanban');
    });

    it('strips leading thumbs from each part', () => {
      expect(formatDocumentTitle(['👍 Work Items', '👍 Alpha Project'])).toBe(
        'Work Items - Alpha Project - kanban',
      );
      expect(formatDocumentTitle(['👍kanban'])).toBe('kanban');
    });

    it('filters out null, undefined, and blank parts while joining remaining parts', () => {
      expect(formatDocumentTitle(['Work Items', null, '  ', undefined, 'Project X'])).toBe(
        'Work Items - Project X - kanban',
      );
    });
  });

  describe('useDocumentTitle hook', () => {
    it('sets document.title and restores previous title on unmount', () => {
      document.title = 'Initial Page Title';

      const { unmount } = renderHook(() => {
        useDocumentTitle('Custom Page');
      });
      expect(document.title).toBe('Custom Page - kanban');

      unmount();
      expect(document.title).toBe('Initial Page Title');
    });

    it('does not double-append brand title if title already ends with BRAND_TITLE', () => {
      document.title = 'Initial Title';

      const { unmount } = renderHook(() => {
        useDocumentTitle('Dashboard - kanban');
      });
      expect(document.title).toBe('Dashboard - kanban');

      unmount();
      expect(document.title).toBe('Initial Title');
    });

    it('falls back to BRAND_TITLE when given empty or null title', () => {
      document.title = 'Previous Title';

      const { rerender, unmount } = renderHook(
        ({ title }: { title: string | null | undefined }) => {
          useDocumentTitle(title);
        },
        { initialProps: { title: undefined as string | null | undefined } },
      );
      expect(document.title).toBe('kanban');

      rerender({ title: null });
      expect(document.title).toBe('kanban');

      rerender({ title: 'New Title' });
      expect(document.title).toBe('New Title - kanban');

      unmount();
      expect(document.title).toBe('Previous Title');
    });

    it('strips leading thumbs when formatting through useDocumentTitle', () => {
      document.title = 'Base Title';

      const { unmount } = renderHook(() => {
        useDocumentTitle('👍 Settings');
      });
      expect(document.title).toBe('Settings - kanban');

      unmount();
      expect(document.title).toBe('Base Title');
    });

    it('updates document.title when title prop changes', () => {
      document.title = 'Base Title';

      const { rerender, unmount } = renderHook(
        ({ title }: { title: string }) => {
          useDocumentTitle(title);
        },
        { initialProps: { title: 'First Section' } },
      );
      expect(document.title).toBe('First Section - kanban');

      rerender({ title: 'Second Section' });
      expect(document.title).toBe('Second Section - kanban');

      unmount();
      expect(document.title).toBe('Base Title');
    });
  });
});
