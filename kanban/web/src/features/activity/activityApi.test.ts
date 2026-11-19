import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  fetchActivity,
  fetchComments,
  createComment,
  patchComment,
  deleteComment,
  addReaction,
  removeReaction,
  fetchAssigneeSuggestions,
} from './activityApi';
import { ApiProblem } from '../../api/problem';

describe('activityApi', () => {

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchActivity', () => {
    it('fetches activity with tab and cursor query params', async () => {
      const mockData = { items: [], next_cursor: null, counts: { all: 0, comments: 0, history: 0, gates: 0 } };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const res = await fetchActivity('KAN-142', 'gates', 'cur-1');
      expect(res).toEqual(mockData);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/issues/KAN-142/activity?tab=gates&cursor=cur-1',
        expect.objectContaining({ headers: { Accept: 'application/json' } }),
      );
    });

    it('throws ApiProblem when request fails with non-JSON response body', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: () => Promise.reject(new Error('Bad gateway HTML')),
      });

      await expect(fetchActivity('KAN-142')).rejects.toThrow(ApiProblem);
    });
  });

  describe('fetchComments', () => {
    it('fetches comments list with optional cursor', async () => {
      const mockComments = { items: [], next_cursor: null };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockComments),
      });

      const res = await fetchComments('KAN-142', 'c-cursor');
      expect(res).toEqual(mockComments);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/issues/KAN-142/comments?cursor=c-cursor',
        expect.anything(),
      );
    });

    it('throws ApiProblem on failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Server error' }),
      });

      await expect(fetchComments('KAN-142')).rejects.toThrow(ApiProblem);
    });
  });

  describe('createComment', () => {
    it('posts comment with markdown body and optional parent/mentions', async () => {
      const mockResult = { id: 'c-1', body_markdown: 'Hello' };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const res = await createComment('KAN-142', {
        body_markdown: 'Hello',
        parent_comment_id: 'p-1',
        acknowledge_mentions: ['m-1'],
      });
      expect(res).toEqual(mockResult);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/issues/KAN-142/comments',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            body_markdown: 'Hello',
            parent_comment_id: 'p-1',
            acknowledge_mentions: ['m-1'],
          }),
        }),
      );
    });

    it('throws ApiProblem on failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: () => Promise.resolve({ code: 'MENTION_ACCESS_WARNING' }),
      });

      await expect(createComment('KAN-142', { body_markdown: 'test' })).rejects.toThrow(ApiProblem);
    });
  });

  describe('patchComment', () => {
    it('sends PATCH with If-Match header when etag is provided', async () => {
      const mockResult = { id: 'c-1', body_markdown: 'Updated' };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResult),
      });

      const res = await patchComment('c-1', { body_markdown: 'Updated' }, '"etag-1"');
      expect(res).toEqual(mockResult);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/comments/c-1',
        expect.objectContaining({
          method: 'PATCH',
          headers: expect.objectContaining({ 'If-Match': '"etag-1"' }) as unknown as Record<string, string>,
        }),
      );
    });

    it('throws ApiProblem on failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 412,
        json: () => Promise.resolve({ code: 'PRECONDITION_FAILED' }),
      });

      await expect(patchComment('c-1', { body_markdown: 'fail' })).rejects.toThrow(ApiProblem);
    });
  });

  describe('deleteComment', () => {
    it('sends DELETE request and handles 204 No Content', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 204,
      });

      await expect(deleteComment('c-1')).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/comments/c-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });

    it('throws ApiProblem on failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: 'Forbidden' }),
      });

      await expect(deleteComment('c-1')).rejects.toThrow(ApiProblem);
    });
  });

  describe('addReaction & removeReaction', () => {
    it('PUTs reaction with URL-encoded emoji', async () => {
      const mockReaction = { emoji: '🚀', count: 1, reacted_by_me: true };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockReaction),
      });

      const res = await addReaction('c-1', '🚀');
      expect(res).toEqual(mockReaction);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/comments/c-1/reactions/%F0%9F%9A%80',
        expect.objectContaining({ method: 'PUT' }),
      );
    });

    it('throws ApiProblem on addReaction failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Invalid reaction' }),
      });

      await expect(addReaction('c-1', '🚀')).rejects.toThrow(ApiProblem);
    });

    it('DELETEs reaction with URL-encoded emoji and handles 204', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 204,
      });

      await expect(removeReaction('c-1', '🚀')).resolves.toBeUndefined();
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/comments/c-1/reactions/%F0%9F%9A%80',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });

    it('throws ApiProblem on removeReaction failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' }),
      });

      await expect(removeReaction('c-1', '🚀')).rejects.toThrow(ApiProblem);
    });
  });

  describe('fetchAssigneeSuggestions', () => {
    it('queries assignee suggestions with q and limit=10', async () => {
      const mockSuggestions = { items: [{ id: 'u-1', handle: 'adam', display_name: 'Adam' }] };
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSuggestions),
      });

      const res = await fetchAssigneeSuggestions('KAN', 'ada');
      expect(res).toEqual(mockSuggestions);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/projects/KAN/assignee-suggestions?q=ada&limit=10',
        expect.anything(),
      );
    });

    it('throws ApiProblem on failure', async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Error' }),
      });

      await expect(fetchAssigneeSuggestions('KAN', 'ada')).rejects.toThrow(ApiProblem);
    });

    it('covers preflight fallback response with body error when mutation returns undefined', async () => {
      global.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/csrf-preflight')) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: () => Promise.reject(new Error('Preflight json parse error')),
          });
        }
        return Promise.resolve(undefined);
      });

      await expect(createComment('KAN-1', { body_markdown: 'hello' })).rejects.toThrow(ApiProblem);
    });
  });
});
