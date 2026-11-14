/**
 * Unit Tests for Stickies REST API Client (KB-P3-51, KB-P3-15).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchProjectStickies,
  fetchWorkspaceStickies,
  createSticky,
  updateSticky,
  deleteSticky,
  snoozeStickyPromotion,
  promoteStickyToDoc,
  unarchiveStickyCopy,
  type StickyItem,
} from './stickiesApi';

const mockSticky: StickyItem = {
  id: '01918a22-0001-7000-8000-000000000001',
  workspace_id: 'ws-1',
  project_id: 'proj-1',
  body_markdown: 'Triage note',
  color_token: 'amber',
  sort_rank: '0',
  promotion_recommended: false,
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: null,
  is_promoted_stub: false,
  triggers: [],
  etag: '"etag-1"',
  capabilities: ['EDIT', 'DELETE'],
};

describe('stickiesApi', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('fetchProjectStickies returns items from paginated object or direct array', async () => {
    // 1. Paginated object response
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: [mockSticky] }),
    });

    const items = await fetchProjectStickies('KAN');
    expect(items).toEqual([mockSticky]);

    // 2. Direct array response
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([mockSticky]),
    });

    const itemsArr = await fetchProjectStickies('KAN');
    expect(itemsArr).toEqual([mockSticky]);
  });

  it('fetchWorkspaceStickies returns items from /api/v1/stickies', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: [mockSticky] }),
    });

    const items = await fetchWorkspaceStickies();
    expect(items).toEqual([mockSticky]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/stickies',
      expect.objectContaining({ credentials: 'same-origin' }),
    );

    // Direct array response
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve([mockSticky]),
    });

    const itemsArray = await fetchWorkspaceStickies();
    expect(itemsArray).toEqual([mockSticky]);
  });

  it('createSticky posts to /api/v1/projects/:key/stickies', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockSticky),
    });

    const result = await createSticky('KAN', {
      body_markdown: 'New note',
      color_token: 'mint',
    });
    expect(result).toEqual(mockSticky);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/projects/KAN/stickies',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          body_markdown: 'New note',
          color_token: 'mint',
        }),
      }),
    );

    // Call with empty payload for defaults
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockSticky),
    });
    await createSticky('KAN', {});
  });

  it('updateSticky patches /api/v1/stickies/:id with ETag or without ETag', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...mockSticky, body_markdown: 'Updated' }),
    });

    const result = await updateSticky(
      mockSticky.id,
      { body_markdown: 'Updated' },
      '"etag-1"',
    );
    expect(result.body_markdown).toBe('Updated');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `/api/v1/stickies/${mockSticky.id}`,
      expect.objectContaining({
        method: 'PATCH',
        headers: expect.objectContaining({
          'If-Match': '"etag-1"',
        }) as unknown as Record<string, string>,
      }),
    );

    // Update without ETag
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...mockSticky, body_markdown: 'No etag' }),
    });
    const result2 = await updateSticky(mockSticky.id, { body_markdown: 'No etag' });
    expect(result2.body_markdown).toBe('No etag');
  });

  it('deleteSticky calls DELETE /api/v1/stickies/:id', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ deleted: true }),
    });

    await deleteSticky(mockSticky.id);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `/api/v1/stickies/${mockSticky.id}`,
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('snoozeStickyPromotion calls /snooze-promotion or falls back to PATCH', async () => {
    // 1. Success on POST endpoint
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...mockSticky, promotion_snoozed_at_length: 650 }),
    });

    const res1 = await snoozeStickyPromotion(mockSticky.id, 650);
    expect(res1.promotion_snoozed_at_length).toBe(650);

    // 2. Fallback to PATCH on network error
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ ...mockSticky, promotion_snoozed_at_length: 650 }),
      });

    const res2 = await snoozeStickyPromotion(mockSticky.id, 650, '"etag-1"');
    expect(res2.promotion_snoozed_at_length).toBe(650);

    // 3. Fallback to PATCH when POST returns 404
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ ...mockSticky, promotion_snoozed_at_length: 700 }),
      });

    const res3 = await snoozeStickyPromotion(mockSticky.id, 700);
    expect(res3.promotion_snoozed_at_length).toBe(700);
  });

  it('promoteStickyToDoc calls POST /api/v1/stickies/:id/promote-to-doc', async () => {
    const promotedResponse = {
      ...mockSticky,
      promoted_to_doc_id: 'doc-123',
      is_promoted_stub: true,
    };
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(promotedResponse),
    });

    const result = await promoteStickyToDoc(mockSticky.id, { title: 'Spec Doc' });
    expect(result.promoted_to_doc_id).toBe('doc-123');
    expect(result.is_promoted_stub).toBe(true);

    // Promote without options
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(promotedResponse),
    });
    const result2 = await promoteStickyToDoc(mockSticky.id);
    expect(result2.promoted_to_doc_id).toBe('doc-123');
  });

  it('unarchiveStickyCopy calls POST /api/v1/stickies/:id/unarchive-copy', async () => {
    const copyResponse = {
      ...mockSticky,
      id: '01918a22-0002-7000-8000-000000000002',
    };
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(copyResponse),
    });

    const result = await unarchiveStickyCopy(mockSticky.id);
    expect(result.id).toBe('01918a22-0002-7000-8000-000000000002');
  });

  it('handles HTTP error responses and surfaces error messages', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: () => Promise.resolve({ detail: 'Sticky note not found' }),
    });

    await expect(fetchProjectStickies('KAN')).rejects.toThrow('Sticky note not found');

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Forbidden to delete this sticky' }),
    });

    await expect(deleteSticky('s-forbidden')).rejects.toThrow('Forbidden to delete this sticky');

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error('Not JSON')),
    });

    await expect(deleteSticky('missing')).rejects.toThrow('HTTP 500');
  });
});
