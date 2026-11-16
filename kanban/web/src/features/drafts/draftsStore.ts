/**
 * Reactive Client-side Drafts Store for Work Items.
 * Backed by localStorage key `kb.drafts.v1` and dispatched events.
 */

import { useState, useEffect } from 'react';
import { safeRandomUUID } from '../../utils/uuid';

export const DRAFTS_STORAGE_KEY = 'kb.drafts.v1';
export const DRAFTS_CHANGED_EVENT = 'kb:drafts-changed';

export interface IssueDraft {
  readonly id: string;
  readonly projectKey: string;
  readonly summary: string;
  readonly description?: string | undefined;
  readonly stateId: string;
  readonly prioritySlug: string;
  readonly moduleIds?: string[] | undefined;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export type DraftInput = Omit<IssueDraft, 'id' | 'createdAt' | 'updatedAt'> & {
  id?: string | undefined;
};

/**
 * Loads all drafts from localStorage.
 */
export function getDrafts(): IssueDraft[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed as IssueDraft[];
  } catch {
    return [];
  }
}

/**
 * Saves or updates a draft in localStorage and emits `kb:drafts-changed`.
 */
export function saveDraft(input: DraftInput): IssueDraft {
  const now = new Date().toISOString();
  const existingDrafts = getDrafts();

  let targetDraft: IssueDraft;
  let nextDrafts: IssueDraft[];

  if (input.id && existingDrafts.some((d) => d.id === input.id)) {
    targetDraft = {
      ...input,
      id: input.id,
      createdAt:
        existingDrafts.find((d) => d.id === input.id)?.createdAt ?? now,
      updatedAt: now,
    };
    nextDrafts = existingDrafts.map((d) =>
      d.id === input.id ? targetDraft : d,
    );
  } else {
    targetDraft = {
      ...input,
      id: input.id ?? safeRandomUUID(),
      createdAt: now,
      updatedAt: now,
    };
    nextDrafts = [targetDraft, ...existingDrafts];
  }

  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(
        DRAFTS_STORAGE_KEY,
        JSON.stringify(nextDrafts),
      );
    } catch {
      // Ignore quota errors in constrained environments
    }
    window.dispatchEvent(new CustomEvent(DRAFTS_CHANGED_EVENT));
  }

  return targetDraft;
}

/**
 * Deletes a draft by id and emits `kb:drafts-changed`.
 */
export function deleteDraft(id: string): void {
  const existingDrafts = getDrafts();
  const nextDrafts = existingDrafts.filter((d) => d.id !== id);

  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(
        DRAFTS_STORAGE_KEY,
        JSON.stringify(nextDrafts),
      );
    } catch {
      // Ignore
    }
    window.dispatchEvent(new CustomEvent(DRAFTS_CHANGED_EVENT));
  }
}

/**
 * React hook for reactive subscription to saved drafts.
 */
export function useDrafts(): IssueDraft[] {
  const [drafts, setDrafts] = useState<IssueDraft[]>(() => getDrafts());

  useEffect(() => {
    const handleUpdate = (): void => {
      setDrafts(getDrafts());
    };

    window.addEventListener(DRAFTS_CHANGED_EVENT, handleUpdate);
    window.addEventListener('storage', handleUpdate);

    return () => {
      window.removeEventListener(DRAFTS_CHANGED_EVENT, handleUpdate);
      window.removeEventListener('storage', handleUpdate);
    };
  }, []);

  return drafts;
}
