/**
 * Unit Tests for draftsStore (KANBA-212, KB-P3-40).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  getDrafts,
  saveDraft,
  deleteDraft,
  useDrafts,
  DRAFTS_STORAGE_KEY,
  DRAFTS_CHANGED_EVENT,
  type DraftInput,
} from './draftsStore';

describe('draftsStore', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('getDrafts returns empty array when window is undefined', () => {
    vi.stubGlobal('window', undefined);
    try {
      expect(getDrafts()).toEqual([]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('getDrafts returns empty array when storage is empty, corrupted, or not an array', () => {
    expect(getDrafts()).toEqual([]);

    window.localStorage.setItem(DRAFTS_STORAGE_KEY, 'not-valid-json');
    expect(getDrafts()).toEqual([]);

    window.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify({ not: 'an-array' }));
    expect(getDrafts()).toEqual([]);
  });

  it('saveDraft saves a new draft with auto-generated id and emits drafts changed event', () => {
    const listener = vi.fn();
    window.addEventListener(DRAFTS_CHANGED_EVENT, listener);

    const input: DraftInput = {
      projectKey: 'KAN',
      summary: 'New task draft',
      description: 'Task description',
      stateId: 'state-todo',
      prioritySlug: 'high',
      moduleIds: ['mod-1'],
    };

    const saved = saveDraft(input);
    expect(saved.id).toBeDefined();
    expect(saved.summary).toBe('New task draft');
    expect(saved.createdAt).toBeDefined();
    expect(saved.updatedAt).toBe(saved.createdAt);
    expect(listener).toHaveBeenCalled();

    const stored = getDrafts();
    expect(stored).toHaveLength(1);
    expect(stored[0]?.id).toBe(saved.id);

    window.removeEventListener(DRAFTS_CHANGED_EVENT, listener);
  });

  it('saveDraft updates an existing draft preserving original createdAt', () => {
    // Seed two drafts to exercise the map branch where d.id !== input.id
    const draft1 = saveDraft({
      id: 'custom-draft-1',
      projectKey: 'KAN',
      summary: 'Initial draft',
      stateId: 'state-todo',
      prioritySlug: 'medium',
    });
    saveDraft({
      id: 'custom-draft-2',
      projectKey: 'KAN',
      summary: 'Second draft',
      stateId: 'state-todo',
      prioritySlug: 'low',
    });

    const updated = saveDraft({
      id: 'custom-draft-1',
      projectKey: 'KAN',
      summary: 'Updated draft summary',
      stateId: 'state-done',
      prioritySlug: 'urgent',
    });

    expect(updated.id).toBe('custom-draft-1');
    expect(updated.summary).toBe('Updated draft summary');
    expect(updated.createdAt).toBe(draft1.createdAt);

    const all = getDrafts();
    expect(all).toHaveLength(2);
    expect(all.find((d) => d.id === 'custom-draft-1')?.summary).toBe('Updated draft summary');

    // Test updating a legacy draft missing createdAt to hit the ?? now branch
    window.localStorage.setItem(
      DRAFTS_STORAGE_KEY,
      JSON.stringify([{ id: 'legacy-draft', projectKey: 'KAN', summary: 'Legacy' }]),
    );
    const updatedLegacy = saveDraft({
      id: 'legacy-draft',
      projectKey: 'KAN',
      summary: 'Updated legacy',
      stateId: 'state-todo',
      prioritySlug: 'medium',
    });
    expect(updatedLegacy.createdAt).toBeDefined();
  });

  it('deleteDraft removes draft by id and emits event', () => {
    const listener = vi.fn();
    window.addEventListener(DRAFTS_CHANGED_EVENT, listener);

    saveDraft({
      id: 'draft-to-delete',
      projectKey: 'KAN',
      summary: 'Temporary',
      stateId: 'state-todo',
      prioritySlug: 'low',
    });
    expect(getDrafts()).toHaveLength(1);

    deleteDraft('draft-to-delete');
    expect(getDrafts()).toHaveLength(0);
    expect(listener).toHaveBeenCalled();

    window.removeEventListener(DRAFTS_CHANGED_EVENT, listener);
  });

  it('saveDraft and deleteDraft handle SSR and storage quota exceptions gracefully', () => {
    // Test saveDraft with brand new explicit id
    const savedWithId = saveDraft({
      id: 'explicit-new-id',
      projectKey: 'KAN',
      summary: 'Brand new draft with explicit id',
      stateId: 'state-todo',
      prioritySlug: 'low',
    });
    expect(savedWithId.id).toBe('explicit-new-id');

    // Test storage setItem exception (quota exceeded)
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });

    expect(() => {
      saveDraft({
        projectKey: 'KAN',
        summary: 'Draft with storage failure',
        stateId: 'state-todo',
        prioritySlug: 'low',
      });
    }).not.toThrow();

    expect(() => {
      deleteDraft('explicit-new-id');
    }).not.toThrow();

    setItemSpy.mockRestore();

    // Test SSR environment where window is undefined
    vi.stubGlobal('window', undefined);
    try {
      expect(() => {
        saveDraft({
          projectKey: 'KAN',
          summary: 'SSR draft',
          stateId: 'state-todo',
          prioritySlug: 'low',
        });
      }).not.toThrow();
      expect(() => {
        deleteDraft('any-id');
      }).not.toThrow();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('useDrafts hook reacts to drafts-changed and storage events', () => {
    const { result } = renderHook(() => useDrafts());
    expect(result.current).toEqual([]);

    act(() => {
      saveDraft({
        projectKey: 'KAN',
        summary: 'Reacted draft',
        stateId: 'state-todo',
        prioritySlug: 'medium',
      });
    });

    expect(result.current).toHaveLength(1);
    expect(result.current[0]?.summary).toBe('Reacted draft');

    // Simulate storage event from another tab
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: DRAFTS_STORAGE_KEY }));
    });
    expect(result.current).toHaveLength(1);

    // Unrelated storage event does not trigger update
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'other-key' }));
    });
    expect(result.current).toHaveLength(1);
  });
});
