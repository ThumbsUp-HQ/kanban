/**
 * Schedule mutation helper and optimistic reschedule hook (KB-P3-39, S7.2 8e).
 * Sends PATCH /api/v1/issues/{issue_ref} and provides rollback on 412 / 422 errors.
 */

import { useCallback, useState } from 'react';
import type { IssueItem } from '../views/viewsApi';

export interface SchedulePatch {
  startDate?: string | null;
  dueDate?: string | null;
}

export interface UseRescheduleIssueOptions {
  onOptimisticUpdate?: (key: string, patch: SchedulePatch) => void;
  onRollback?: (key: string, original: { startDate: string | null; dueDate: string | null }) => void;
  onSuccess?: (key: string, updated: IssueItem) => void;
  onError?: (key: string, error: Error) => void;
}

/**
 * Direct PATCH API call to update an issue's schedule dates.
 */
export async function patchIssueSchedule(
  issueKey: string,
  patch: SchedulePatch,
  etag?: string,
): Promise<IssueItem> {
  const body: Record<string, string | null> = {};
  if (patch.startDate !== undefined) {
    body.start_date = patch.startDate;
  }
  if (patch.dueDate !== undefined) {
    body.due_date = patch.dueDate;
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (etag) {
    headers['If-Match'] = etag;
  }

  const res = await fetch(`/api/v1/issues/${encodeURIComponent(issueKey)}`, {
    method: 'PATCH',
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    let errorText = '';
    try {
      errorText = await res.text();
    } catch {
      // ignore
    }
    let errorCode = `HTTP_${String(res.status)}`;
    try {
      const parsed = JSON.parse(errorText) as { code?: string };
      if (parsed.code) {
        errorCode = parsed.code;
      }
    } catch {
      // Non-JSON response
    }
    const err = new Error(`Reschedule failed (${String(res.status)} ${errorCode}): ${errorText}`);
    (err as unknown as { status: number; code: string }).status = res.status;
    (err as unknown as { status: number; code: string }).code = errorCode;
    throw err;
  }

  return (await res.json()) as IssueItem;
}

/**
 * Hook providing optimistic reschedule execution with live announcement and rollback on failure.
 */
export function useRescheduleIssue(options: UseRescheduleIssueOptions = {}) {
  const [announcement, setAnnouncement] = useState<string>('');
  const [isPending, setIsPending] = useState<boolean>(false);

  const reschedule = useCallback(
    async (
      issueOrTarget:
        | (Pick<IssueItem, 'key' | 'start_date' | 'due_date'> & { etag?: string })
        | {
            issueRef: string;
            dueDate?: string | null | undefined;
            startDate?: string | null | undefined;
            etag?: string | undefined;
          },
      optionalPatch?: SchedulePatch,
    ): Promise<boolean> => {
      let key: string;
      let patch: SchedulePatch;
      let originalDates: { startDate: string | null; dueDate: string | null };
      let etag: string | undefined;

      if (optionalPatch) {
        const iss = issueOrTarget as Pick<IssueItem, 'key' | 'start_date' | 'due_date'> & {
          etag?: string;
        };
        key = iss.key;
        patch = optionalPatch;
        originalDates = {
          startDate: iss.start_date ?? null,
          dueDate: iss.due_date ?? null,
        };
        etag = iss.etag;
      } else {
        const target = issueOrTarget as {
          issueRef: string;
          dueDate?: string | null;
          startDate?: string | null;
          etag?: string;
        };
        key = target.issueRef;
        patch = {};
        if (target.startDate !== undefined) {
          patch.startDate = target.startDate;
        }
        if (target.dueDate !== undefined) {
          patch.dueDate = target.dueDate;
        }
        originalDates = {
          startDate: target.startDate ?? null,
          dueDate: target.dueDate ?? null,
        };
        etag = target.etag;
      }

      // 1. Optimistic apply
      options.onOptimisticUpdate?.(key, patch);
      setIsPending(true);

      try {
        const updated = await patchIssueSchedule(key, patch, etag);
        setAnnouncement(`Rescheduled ${key} successfully.`);
        options.onSuccess?.(key, updated);
        return true;
      } catch (err) {
        // 2. Rollback on failure (412 ETag mismatch, 422 date validation error, etc.)
        options.onRollback?.(key, originalDates);
        const errorMsg = err instanceof Error ? err.message : String(err);
        setAnnouncement(`Reschedule failed for ${key}, rolled back to previous schedule.`);
        options.onError?.(key, err instanceof Error ? err : new Error(errorMsg));
        return false;
      } finally {
        setIsPending(false);
      }
    },
    [options],
  );

  return {
    reschedule,
    announcement,
    isPending,
  };
}
