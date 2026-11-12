import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchProjectIssues } from './viewsApi';

describe('viewsApi', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('fetches project issues with query parameters', async () => {
    const mockData = { items: [], next_cursor: 'cursor123', total: 0 };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockData),
    });

    const result = await fetchProjectIssues('KAN', {
      cursor: 'cur1',
      limit: 25,
      sort_by: 'due_date',
      sort_dir: 'asc',
    });

    expect(result).toEqual(mockData);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/projects/KAN/issues?cursor=cur1&limit=25&sort_by=due_date&sort_dir=asc',
      expect.objectContaining({
        headers: { Accept: 'application/json' },
      })
    );
  });

  it('fetches with default empty params and handles error response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    });

    await expect(fetchProjectIssues('NOT_FOUND')).rejects.toThrow(
      'Failed to fetch project issues: 404 Not Found'
    );
  });
});
