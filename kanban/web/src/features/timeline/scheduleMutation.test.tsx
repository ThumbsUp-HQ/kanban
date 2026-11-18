import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { patchIssueSchedule, useRescheduleIssue } from './scheduleMutation';

describe('scheduleMutation', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=test-csrf-token-123; Path=/';
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    document.cookie = 'kb_csrf=; Path=/; Max-Age=0';
  });

  it('patchIssueSchedule sends PATCH request with JSON body, X-CSRF-Token, credentials, and If-Match header', async () => {
    const mockResponse = {
      id: 'issue-142',
      key: 'KAN-142',
      summary: 'Task 142',
      start_date: '2026-11-12',
      due_date: '2026-11-20',
      state: { id: 's1', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'medium', label: 'Medium' },
    };

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockResponse),
    });
    globalThis.fetch = mockFetch;

    const result = await patchIssueSchedule(
      'KAN-142',
      { startDate: '2026-11-12', dueDate: '2026-11-20' },
      '"etag-abc"',
    );

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/issues/KAN-142', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-CSRF-Token': 'test-csrf-token-123',
        'If-Match': '"etag-abc"',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ start_date: '2026-11-12', due_date: '2026-11-20' }),
    });
    expect(result.due_date).toBe('2026-11-20');
  });

  it('patchIssueSchedule parses error codes from failed responses', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      text: () => Promise.resolve(JSON.stringify({ code: 'DATE_RANGE_INVALID' })),
    });
    globalThis.fetch = mockFetch;

    await expect(
      patchIssueSchedule('KAN-142', { startDate: '2026-11-25', dueDate: '2026-11-20' }),
    ).rejects.toThrow('DATE_RANGE_INVALID');
  });

  it('useRescheduleIssue hook performs optimistic update and rolls back on failure', async () => {
    const onOptimistic = vi.fn();
    const onRollback = vi.fn();
    const onSuccess = vi.fn();
    const onError = vi.fn();

    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 412,
      text: () => Promise.resolve(JSON.stringify({ code: 'PRECONDITION_FAILED' })),
    });
    globalThis.fetch = mockFetch;

    const { result } = renderHook(() =>
      useRescheduleIssue({
        onOptimisticUpdate: onOptimistic,
        onRollback: onRollback,
        onSuccess: onSuccess,
        onError: onError,
      }),
    );

    const issue = {
      key: 'KAN-142',
      start_date: '2026-11-10',
      due_date: '2026-11-18',
    };

    let success = false;
    await act(async () => {
      success = await result.current.reschedule(issue, { dueDate: '2026-11-22' });
    });

    expect(success).toBe(false);
    expect(onOptimistic).toHaveBeenCalledWith('KAN-142', { dueDate: '2026-11-22' });
    expect(onRollback).toHaveBeenCalledWith('KAN-142', {
      startDate: '2026-11-10',
      dueDate: '2026-11-18',
    });
    expect(onError).toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.announcement).toContain('rolled back');
  });

  it('useRescheduleIssue announces success on valid 200 response', async () => {
    const onSuccess = vi.fn();
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ key: 'KAN-142', due_date: '2026-11-20' }),
    });
    globalThis.fetch = mockFetch;

    const { result } = renderHook(() =>
      useRescheduleIssue({
        onSuccess,
      }),
    );

    const issue = {
      key: 'KAN-142',
      start_date: '2026-11-10',
      due_date: '2026-11-18',
    };

    let success = false;
    await act(async () => {
      success = await result.current.reschedule(issue, { dueDate: '2026-11-20' });
    });

    expect(success).toBe(true);
    expect(onSuccess).toHaveBeenCalled();
    expect(result.current.announcement).toContain('Rescheduled KAN-142 successfully');
  });

  it('supports single-target reschedule signature and non-JSON error handling', async () => {
    // Non-JSON error
    const mockErrorFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('Internal Server Error HTML'),
    });
    globalThis.fetch = mockErrorFetch;

    await expect(
      patchIssueSchedule('KAN-99', { dueDate: '2026-11-20' }),
    ).rejects.toThrow('HTTP_500');

    // Single-target reschedule call with both dates
    const mockOkFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ key: 'KAN-99', due_date: '2026-11-20' }),
    });
    globalThis.fetch = mockOkFetch;

    const { result } = renderHook(() => useRescheduleIssue());
    let ok = false;
    await act(async () => {
      ok = await result.current.reschedule({
        issueRef: 'KAN-99',
        startDate: '2026-11-15',
        dueDate: '2026-11-20',
      });
    });
    expect(ok).toBe(true);
  });

  it('handles issues with null dates, single-target with partial/no dates, and non-Error rejections', async () => {
    const onError = vi.fn();
    const onRollback = vi.fn();
    const { result } = renderHook(() =>
      useRescheduleIssue({
        onError,
        onRollback,
      }),
    );

    // 1. Issue with null start_date and null due_date
    const mockOkFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ key: 'KAN-NULL', due_date: '2026-11-20' }),
    });
    globalThis.fetch = mockOkFetch;

    await act(async () => {
      await result.current.reschedule(
        { key: 'KAN-NULL', start_date: null, due_date: null },
        { dueDate: '2026-11-20' },
      );
    });

    // 2. Single-target with only startDate
    await act(async () => {
      await result.current.reschedule({
        issueRef: 'KAN-PARTIAL1',
        startDate: '2026-11-10',
      });
    });

    // 3. Single-target with only dueDate
    await act(async () => {
      await result.current.reschedule({
        issueRef: 'KAN-PARTIAL2',
        dueDate: '2026-11-25',
      });
    });

    // 4. Single-target with neither date
    await act(async () => {
      await result.current.reschedule({
        issueRef: 'KAN-PARTIAL3',
      });
    });

    // 5. Non-Error throw in fetch to test String(err) fallback and genuine rollback to null
    globalThis.fetch = vi.fn().mockRejectedValueOnce('raw network failure string');
    let failResult = true;
    await act(async () => {
      failResult = await result.current.reschedule({
        issueRef: 'KAN-ERR',
        dueDate: '2026-11-25',
      });
    });

    expect(failResult).toBe(false);
    expect(onError).toHaveBeenCalledWith('KAN-ERR', expect.any(Error));
    expect(onRollback).toHaveBeenCalledWith('KAN-ERR', { startDate: null, dueDate: null });
    expect(result.current.announcement).toContain('rolled back');

    // 6. Genuine rollback to explicitly provided pre-mutation dates
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: () => Promise.resolve(JSON.stringify({ code: 'CSRF_REJECTED' })),
    });
    let failOriginal = true;
    await act(async () => {
      failOriginal = await result.current.reschedule({
        issueRef: 'KAN-ERR-2',
        startDate: '2026-11-20',
        dueDate: '2026-11-25',
        originalStartDate: '2026-11-05',
        originalDueDate: '2026-11-12',
      });
    });
    expect(failOriginal).toBe(false);
    expect(onRollback).toHaveBeenCalledWith('KAN-ERR-2', {
      startDate: '2026-11-05',
      dueDate: '2026-11-12',
    });
  });

  it('dispatches kb:issue-updated CustomEvent on window on successful reschedule', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const mockResponse = {
      id: 'issue-142',
      key: 'KAN-142',
      start_date: '2026-11-12',
      due_date: '2026-11-20',
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useRescheduleIssue());
    await act(async () => {
      await result.current.reschedule({
        issueRef: 'KAN-142',
        startDate: '2026-11-12',
        dueDate: '2026-11-20',
      });
    });

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'kb:issue-updated',
      }),
    );
  });
});
