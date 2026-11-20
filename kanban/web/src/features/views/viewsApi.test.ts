import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchProjectIssues,
  fetchProjectStates,
  createProjectIssue,
  patchProjectIssue,
  deleteProjectIssue,
  ensureCsrfToken,
  extractCsrfFromCookieString,
  normalizeIssueItem,
  normalizeStateKey,
  resolveStateUuid,
  isUuidString,
  extractSavedViews,
  fetchProjectSavedViews,
} from './viewsApi';

describe('viewsApi', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    if (typeof document !== 'undefined') {
      document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    }
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('normalizes state keys and checks UUID strings', () => {
    expect(normalizeStateKey('To Do')).toBe('todo');
    expect(normalizeStateKey('Todo')).toBe('todo');
    expect(normalizeStateKey('In_Progress')).toBe('inprogress');
    expect(isUuidString('01931234-5678-7000-8000-000000000001')).toBe(true);
    expect(isUuidString('state-todo')).toBe(false);
    expect(isUuidString(null)).toBe(false);
  });

  it('normalizes raw backend IssueResponse into IssueItem', () => {
    const item = normalizeIssueItem({
      id: '01931234-5678-7000-8000-000000000010',
      key: 'KANBA-10',
      summary: 'Normalized Issue',
      state: { id: 's-1', name: 'To Do', group: 'unstarted' },
      provenance: { created_by: { id: 'u-1', handle: 'alice' } },
      access_manifest: { explicit_grant_count: 2 },
    });
    expect(item.state.name).toBe('Todo');
    expect(item.created_by_handle).toBe('alice');
    expect(item.created_by_id).toBe('u-1');
    expect(item.has_explicit_acl).toBe(true);
    expect(item.priority.slug).toBe('medium');

    const fallbackItem = normalizeIssueItem({});
    expect(fallbackItem.state.name).toBe('Todo');
    expect(fallbackItem.summary).toBe('');
  });

  it('resolves state UUIDs by exact UUID, normalized name, or group', () => {
    const projectStates = [
      { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog' },
      { id: '01931234-5678-7000-8000-000000000002', name: 'Todo', group: 'unstarted' },
      { id: '01931234-5678-7000-8000-000000000003', name: 'In Progress', group: 'started' },
    ];
    expect(resolveStateUuid(undefined, projectStates)).toBeUndefined();
    expect(
      resolveStateUuid(
        { id: '01931234-5678-7000-8000-000000000099', name: 'Custom', group: 'started' },
        projectStates
      )
    ).toBe('01931234-5678-7000-8000-000000000099');
    expect(
      resolveStateUuid({ id: 'state-todo', name: 'To Do', group: 'unstarted' }, projectStates)
    ).toBe('01931234-5678-7000-8000-000000000002');
    expect(
      resolveStateUuid({ id: 'state-custom', name: 'Working', group: 'started' }, projectStates)
    ).toBe('01931234-5678-7000-8000-000000000003');
  });

  it('bootstraps CSRF token from cookie or /api/v1/auth/session', async () => {
    document.cookie = 'kb_csrf=cookie-csrf-123; path=/';
    expect(await ensureCsrfToken()).toBe('cookie-csrf-123');

    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    const cookieSpy = vi
      .spyOn(document, 'cookie', 'get')
      .mockReturnValueOnce('__Host-kb_csrf=host-csrf-456');
    expect(await ensureCsrfToken()).toBe('host-csrf-456');
    cookieSpy.mockRestore();

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ csrf_token: 'session-csrf-789' }),
    });
    expect(await ensureCsrfToken()).toBe('session-csrf-789');

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
    expect(await ensureCsrfToken()).toBeNull();

    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network error'));
    expect(await ensureCsrfToken()).toBeNull();
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

  it('fetches project states and handles array or object response', async () => {
    const states = [{ id: 's1', name: 'Todo', group: 'unstarted' }];
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: states }),
    });
    expect(await fetchProjectStates('KAN')).toEqual(states);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(states),
    });
    expect(await fetchProjectStates('KAN')).toEqual(states);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Server Error',
    });
    await expect(fetchProjectStates('KAN')).rejects.toThrow(
      'Failed to fetch project states: 500 Server Error'
    );
  });

  it('creates, patches, and deletes a project issue with CSRF token', async () => {
    document.cookie = 'kb_csrf=csrf-tok-99; path=/';
    const createdRaw = {
      id: '01931234-5678-7000-8000-000000000100',
      key: 'KANBA-100',
      summary: 'Created via API',
      state: {
        id: '01931234-5678-7000-8000-000000000002',
        name: 'To Do',
        group: 'unstarted',
      },
      priority: { slug: 'high', label: 'High', emoji: '⚡' },
    };
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(createdRaw),
    });

    const created = await createProjectIssue(
      'KANBA',
      {
        summary: 'Created via API',
        description_markdown: 'Body',
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'high', label: 'High', emoji: '⚡' },
        module_ids: ['01931234-5678-7000-8000-000000000055', 'mod-invalid'],
      },
      [
        {
          id: '01931234-5678-7000-8000-000000000002',
          name: 'Todo',
          group: 'unstarted',
        },
      ]
    );
    expect(created.key).toBe('KANBA-100');
    expect(created.state.name).toBe('Todo');

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
    });
    await expect(createProjectIssue('KANBA', { summary: 'Bad' })).rejects.toThrow(
      'Failed to create issue: 422 Unprocessable Entity'
    );

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ...createdRaw, summary: 'Patched' }),
    });
    const patched = await patchProjectIssue('KANBA-100', { summary: 'Patched' }, '"etag-1"');
    expect(patched.summary).toBe('Patched');

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
    });
    await expect(patchProjectIssue('KANBA-100', { summary: 'Conflict' })).rejects.toThrow(
      'Failed to update issue: 409 Conflict'
    );

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
    });
    await expect(deleteProjectIssue('KANBA-100')).resolves.toBeUndefined();

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
    });
    await expect(deleteProjectIssue('KANBA-100')).rejects.toThrow(
      'Failed to delete issue: 403 Forbidden'
    );
  });

  it('extractCsrfFromCookieString extracts prefix tokens or returns null', () => {
    expect(extractCsrfFromCookieString('')).toBeNull();
    expect(extractCsrfFromCookieString('session=xyz; other=123')).toBeNull();
    expect(extractCsrfFromCookieString('kb_csrf=plain-token; session=xyz')).toBe('plain-token');
    expect(extractCsrfFromCookieString('foo=bar; __Host-kb_csrf=host-token')).toBe('host-token');
    expect(extractCsrfFromCookieString('kb_csrf=encoded%20token')).toBe('encoded token');
  });

  it('ensureCsrfToken covers cookie caching and fetch session error fallbacks', async () => {
    document.cookie = 'kb_csrf=cached-csrf; Path=/';
    const cached = await ensureCsrfToken();
    expect(cached).toBe('cached-csrf');

    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/';
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 500,
    });
    const failedFetch = await ensureCsrfToken();
    expect(failedFetch).toBeNull();

    globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('Network offline'));
    const thrownFetch = await ensureCsrfToken();
    expect(thrownFetch).toBeNull();

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });
    const emptyBody = await ensureCsrfToken();
    expect(emptyBody).toBeNull();
  });

  it('normalizes saved views from items, views, or raw array envelopes', async () => {
    const mockView = {
      id: 'v1',
      name: 'Test View',
      layout: 'board' as const,
      group_by: 'state' as const,
      sub_group_by: 'none' as const,
    };

    expect(extractSavedViews(null)).toEqual([]);
    expect(extractSavedViews(undefined)).toEqual([]);
    expect(extractSavedViews([mockView])).toEqual([mockView]);
    expect(extractSavedViews({ items: [mockView] })).toEqual([mockView]);
    expect(extractSavedViews({ views: [mockView] })).toEqual([mockView]);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: [mockView] }),
    });
    const fromItems = await fetchProjectSavedViews('KAN');
    expect(fromItems).toEqual([mockView]);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ views: [mockView] }),
    });
    const fromViews = await fetchProjectSavedViews('KAN');
    expect(fromViews).toEqual([mockView]);

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Error',
    });
    await expect(fetchProjectSavedViews('KAN')).rejects.toThrow(
      'Failed to fetch project views: 500 Internal Error'
    );

    // Empty project states guard
    const emptyStates = await fetchProjectStates('');
    expect(emptyStates).toEqual([]);

    // fetchProjectIssues with non-empty items array (covers line 306)
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({
        items: [
          {
            id: '01931234-5678-7000-8000-000000000099',
            key: 'KAN-99',
            summary: 'Item map test',
            state: { id: 's-1', name: 'To Do', group: 'unstarted' },
          },
        ],
        total: 1,
      }),
    });
    const issuesRes = await fetchProjectIssues('KAN');
    expect(issuesRes.items).toHaveLength(1);
    expect(issuesRes.total).toBe(1);
  });
});
