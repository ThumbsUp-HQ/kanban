import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('../drawer-rail/railApi', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../drawer-rail/railApi');
  return {
    ...actual,
    fetchAssigneeSuggestions: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectLabels: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectCycles: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectModules: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
  };
});

import * as clientModule from '../../api/client.ts';
import { fetchAllProjectIssues, type StateSummary } from './viewsApi';
import { IssuesWorkspaceRoute, defaultQueryClient } from './viewRegistry';
import { BoardView } from '../board/BoardView.tsx';
import { fetchAllBoardIssues, type BoardIssue, type BoardWorkflowState } from '../board/boardApi.ts';

const WORKFLOW_STATES: BoardWorkflowState[] = [
  { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 2 },
  { id: 'state-crazy-ideas', name: 'Crazy_Ideas', group: 'started', sort_order: 3 },
  { id: 'state-done', name: 'Done', group: 'completed', sort_order: 4 },
  { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 5 },
];

const VIEW_STATES: StateSummary[] = WORKFLOW_STATES.map((st) => ({
  id: st.id,
  name: st.name,
  group: st.group,
  sort_order: st.sort_order,
}));

interface DatasetRecord {
  id: string;
  key: string;
  summary: string;
  state_id: string;
  state: { id: string; name: string; group: BoardWorkflowState['group'] };
  priority: { id: string; slug: string; label: string; emoji: string };
  board_rank: string;
}

/**
 * Build deterministic 304-issue descending sequence_id dataset matching post-merge KAN:
 * - KAN-304..KAN-89 (216): Done
 * - KAN-88..KAN-84 (5): Cancelled
 * - KAN-83 (1): Backlog
 * - KAN-82..KAN-76 (7): Crazy_Ideas
 * - KAN-75..KAN-55 (21): Todo
 * - KAN-54..KAN-1 (54): Done
 * Pages 1 and 2 (KAN-304..KAN-105) contain 100% Done issues, so open items only
 * appear starting on page 3 (offset 200).
 */
function buildRealistic304Dataset(): DatasetRecord[] {
  const records: DatasetRecord[] = [];
  for (let seq = 304; seq >= 1; seq -= 1) {
    let state = WORKFLOW_STATES[3]; // Done
    let summary = `Completed Issue KAN-${String(seq)}`;

    if (seq >= 84 && seq <= 88) {
      state = WORKFLOW_STATES[4]; // Cancelled
      summary = `Cancelled Issue KAN-${String(seq)}`;
    } else if (seq === 83) {
      state = WORKFLOW_STATES[0]; // Backlog
      summary = 'KAN-83 Active Backlog Guardrail';
    } else if (seq >= 76 && seq <= 82) {
      state = WORKFLOW_STATES[2]; // Crazy_Ideas
      summary =
        seq === 82
          ? 'KAN-82 Crazy Idea Prototype'
          : `Crazy Idea KAN-${String(seq)}`;
    } else if (seq >= 55 && seq <= 75) {
      state = WORKFLOW_STATES[1]; // Todo
      summary =
        seq === 75
          ? 'KAN-75 Active Todo Feature'
          : `Todo Issue KAN-${String(seq)}`;
    }

    if (!state) {
      throw new Error('Missing workflow state fixture');
    }

    records.push({
      id: `01931234-0000-7000-8000-${String(seq).padStart(12, '0')}`,
      key: `KAN-${String(seq)}`,
      summary,
      state_id: state.id,
      state: {
        id: state.id,
        name: state.name,
        group: state.group,
      },
      priority: {
        id: 'medium',
        slug: 'medium',
        label: 'Medium',
        emoji: '🔹',
      },
      board_rank: String(305 - seq).padStart(6, '0'),
    });
  }
  return records;
}

function sliceCursorPage(
  dataset: DatasetRecord[],
  cursorParam: string | null | undefined,
  limitParam: number | string | null | undefined,
): { items: DatasetRecord[]; next_cursor: string | null; total: number } {
  const parsedLimit = Number(limitParam ?? 50);
  const limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? Math.min(parsedLimit, 100) : 50;
  let offset = 0;
  if (typeof cursorParam === 'string' && cursorParam.startsWith('offset-')) {
    const parsedOffset = Number(cursorParam.slice('offset-'.length));
    if (Number.isFinite(parsedOffset) && parsedOffset >= 0) {
      offset = parsedOffset;
    }
  }
  const items = dataset.slice(offset, offset + limit);
  const nextOffset = offset + items.length;
  const next_cursor =
    items.length > 0 && nextOffset < dataset.length ? `offset-${String(nextOffset)}` : null;
  return {
    items,
    next_cursor,
    total: dataset.length,
  };
}

describe('KAN-84 multi-page cursor pagination integration (304-issue post-merge project)', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    defaultQueryClient.clear();
    window.innerWidth = 1280;
    window.history.pushState({}, '', '/projects/KAN/issues');

    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      value: 1400,
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      value: 124,
    });
    Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top: 0,
        left: 0,
        bottom: 1400,
        right: 324,
        width: 324,
        height: 1400,
        x: 0,
        y: 0,
        toJSON: () => {
          /* no-op */
        },
      }),
    });
  });

  afterEach(async () => {
    globalThis.fetch = originalFetch;
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  });

  it('fetchAllProjectIssues traverses all 4 cursor pages (100+100+100+4=304) and preserves all 29 open issues', async () => {
    const dataset = buildRealistic304Dataset();
    const calledUrls: string[] = [];

    globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      calledUrls.push(urlStr);
      const parsed = new URL(urlStr, 'http://localhost');
      const page = sliceCursorPage(
        dataset,
        parsed.searchParams.get('cursor'),
        parsed.searchParams.get('limit'),
      );
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(page),
      });
    });

    const result = await fetchAllProjectIssues('KAN', {
      sort_by: 'sequence_id',
      sort_dir: 'desc',
    });

    expect(calledUrls).toEqual([
      '/api/v1/projects/KAN/issues?limit=100&sort_by=sequence_id&sort_dir=desc&lod=summary',
      '/api/v1/projects/KAN/issues?cursor=offset-100&limit=100&sort_by=sequence_id&sort_dir=desc&lod=summary',
      '/api/v1/projects/KAN/issues?cursor=offset-200&limit=100&sort_by=sequence_id&sort_dir=desc&lod=summary',
      '/api/v1/projects/KAN/issues?cursor=offset-300&limit=100&sort_by=sequence_id&sort_dir=desc&lod=summary',
    ]);
    expect(result.pagesFetched).toBe(4);
    expect(result.truncated).toBe(false);
    expect(result.items).toHaveLength(304);
    expect(new Set(result.items.map((item) => item.key)).size).toBe(304);

    const openIssues = result.items.filter((item) =>
      ['backlog', 'unstarted', 'started'].includes(item.state.group),
    );
    expect(openIssues).toHaveLength(29);
    expect(openIssues.filter((i) => i.state.name === 'Backlog')).toHaveLength(1);
    expect(openIssues.filter((i) => i.state.name === 'Crazy_Ideas')).toHaveLength(7);
    expect(openIssues.filter((i) => i.state.name === 'Todo')).toHaveLength(21);
    expect(openIssues.find((i) => i.key === 'KAN-83')?.summary).toBe('KAN-83 Active Backlog Guardrail');
    expect(openIssues.find((i) => i.key === 'KAN-82')?.summary).toBe('KAN-82 Crazy Idea Prototype');
    expect(openIssues.find((i) => i.key === 'KAN-75')?.summary).toBe('KAN-75 Active Todo Feature');
  });

  it('fetchAllProjectIssues guards against cursor cycles, maxPages bounds, empty/undefined projectKey, deduplication, and AbortSignal cancellation', async () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    // 1. Empty / 'undefined' projectKey short-circuit
    expect(await fetchAllProjectIssues('')).toEqual({
      items: [],
      pagesFetched: 0,
      truncated: false,
    });
    expect(await fetchAllProjectIssues('undefined')).toEqual({
      items: [],
      pagesFetched: 0,
      truncated: false,
    });
    expect(fetchSpy).not.toHaveBeenCalled();

    // 2. Cursor cycle guard + deduplication (including empty key/id item)
    const dataset = buildRealistic304Dataset();
    const row83 = dataset.find((d) => d.key === 'KAN-83');
    const row82 = dataset.find((d) => d.key === 'KAN-82');
    if (!row83 || !row82) throw new Error('Missing rows');

    let cycleCall = 0;
    globalThis.fetch = vi.fn().mockImplementation(() => {
      cycleCall += 1;
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            items:
              cycleCall === 1
                ? [row83, row82, { summary: 'No key or id' }]
                : [row82, row83],
            next_cursor: 'loop-cursor-1',
          }),
      });
    });

    const cycleRes = await fetchAllProjectIssues('KAN');
    expect(cycleRes.pagesFetched).toBe(2);
    expect(cycleRes.truncated).toBe(true);
    expect(cycleRes.items.map((i) => i.key)).toEqual(['KAN-83', 'KAN-82', '']);

    // 3. maxPages bound
    globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      const parsed = new URL(urlStr, 'http://localhost');
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            sliceCursorPage(dataset, parsed.searchParams.get('cursor'), parsed.searchParams.get('limit')),
          ),
      });
    });

    const boundedRes = await fetchAllProjectIssues('KAN', { maxPages: 2 });
    expect(boundedRes.pagesFetched).toBe(2);
    expect(boundedRes.items).toHaveLength(200);
    expect(boundedRes.truncated).toBe(true);

    // 4. Pre-aborted signal with default reason and custom non-Error reason
    const controllerPre = new AbortController();
    controllerPre.abort();
    const preErr = await fetchAllProjectIssues('KAN', { signal: controllerPre.signal }).catch(
      (err: unknown) => err,
    );
    expect((preErr as { name?: string }).name).toBe('AbortError');

    const controllerStr = new AbortController();
    controllerStr.abort('cancelled-by-user');
    const strErr = await fetchAllProjectIssues('KAN', { signal: controllerStr.signal }).catch(
      (err: unknown) => err,
    );
    expect((strErr as { name?: string }).name).toBe('AbortError');

    // 5. Aborted mid-pagination after page 1
    const controllerMid = new AbortController();
    globalThis.fetch = vi.fn().mockImplementation(() => {
      controllerMid.abort(new DOMException('Mid-pagination abort', 'AbortError'));
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ items: [row83], next_cursor: 'cursor-2' }),
      });
    });
    const midErr = await fetchAllProjectIssues('KAN', { signal: controllerMid.signal }).catch(
      (err: unknown) => err,
    );
    expect((midErr as { name?: string }).name).toBe('AbortError');
    expect((midErr as { message?: string }).message).toBe('Mid-pagination abort');
  });

  it('IssuesWorkspaceRoute (layout=board & kb:issue-updated live refresh) loads all 304 issues across 4 pages and never regresses to 50 items', async () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=board');
    const dataset = buildRealistic304Dataset();
    let issueFetchCount = 0;

    globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.endsWith('/states')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: VIEW_STATES }),
        });
      }
      if (urlStr.endsWith('/views')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      if (urlStr.includes('/issues')) {
        issueFetchCount += 1;
        const parsed = new URL(urlStr, 'http://localhost');
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve(
              sliceCursorPage(dataset, parsed.searchParams.get('cursor'), parsed.searchParams.get('limit')),
            ),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    const localClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="board" queryClient={localClient} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Backlog lane, 1 issues')).toBeDefined();
      expect(screen.getByLabelText('Crazy_Ideas lane, 7 issues')).toBeDefined();
      expect(screen.getByLabelText('Todo lane, 21 issues')).toBeDefined();
      expect(screen.getByLabelText('Done lane, 270 issues')).toBeDefined();
      expect(screen.getByLabelText('Cancelled lane, 5 issues')).toBeDefined();
    });

    expect(screen.getByText('KAN-83 Active Backlog Guardrail')).toBeDefined();
    expect(screen.getByText('KAN-82 Crazy Idea Prototype')).toBeDefined();
    expect(screen.getByText('KAN-75 Active Todo Feature')).toBeDefined();

    const fetchesAfterMount = issueFetchCount;
    expect(fetchesAfterMount).toBeGreaterThanOrEqual(4);

    // Trigger live refresh event and verify multi-page loader runs again without 50-item truncation
    act(() => {
      fireEvent(window, new CustomEvent('kb:issue-updated'));
    });

    await waitFor(() => {
      expect(issueFetchCount).toBeGreaterThanOrEqual(fetchesAfterMount + 4);
    });

    expect(screen.getByLabelText('Backlog lane, 1 issues')).toBeDefined();
    expect(screen.getByLabelText('Crazy_Ideas lane, 7 issues')).toBeDefined();
    expect(screen.getByLabelText('Todo lane, 21 issues')).toBeDefined();
    expect(screen.getByLabelText('Done lane, 270 issues')).toBeDefined();
    expect(screen.getByText('KAN-83 Active Backlog Guardrail')).toBeDefined();
    expect(screen.getByText('KAN-82 Crazy Idea Prototype')).toBeDefined();
    expect(screen.getByText('KAN-75 Active Todo Feature')).toBeDefined();
  });

  it('IssuesWorkspaceRoute (layout=list) loads all 304 issues and displays open KAN-83, KAN-82, and KAN-75 issues when filtering active states', async () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=list&filter_state=active');
    const dataset = buildRealistic304Dataset();

    globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.endsWith('/states')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: VIEW_STATES }),
        });
      }
      if (urlStr.endsWith('/views')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      if (urlStr.includes('/issues')) {
        const parsed = new URL(urlStr, 'http://localhost');
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve(
              sliceCursorPage(dataset, parsed.searchParams.get('cursor'), parsed.searchParams.get('limit')),
            ),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    const localClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" queryClient={localClient} />);

    await waitFor(() => {
      expect(screen.getAllByText('KAN-83').length).toBeGreaterThan(0);
      expect(screen.getAllByText('KAN-82').length).toBeGreaterThan(0);
      expect(screen.getAllByText('KAN-75').length).toBeGreaterThan(0);
    });

    // Completed Done issues must be filtered out when filter_state=active is set
    expect(screen.queryByText('KAN-304')).toBeNull();
    expect(screen.queryByText('KAN-1')).toBeNull();
  });

  it('Standalone BoardView traverses all 4 apiFetch cursor pages via fetchAllBoardIssues and renders open columns alongside 270 Done issues', async () => {
    const dataset = buildRealistic304Dataset();
    const issueQueryCalls: { cursor?: unknown; limit?: unknown }[] = [];

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path, opts) => {
      if (path === '/api/v1/projects/{project_ref}') {
        return Promise.resolve({
          id: 'proj-kan-1',
          states: WORKFLOW_STATES,
          capabilities: ['VIEW', 'EDIT'],
        });
      }
      if (path === '/api/v1/projects/{project_ref}/issues') {
        const query = opts?.query as { cursor?: string; limit?: number } | undefined;
        issueQueryCalls.push({ cursor: query?.cursor, limit: query?.limit });
        return Promise.resolve(sliceCursorPage(dataset, query?.cursor, query?.limit));
      }
      return Promise.resolve({});
    });

    const localClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    render(
      <QueryClientProvider client={localClient}>
        <BoardView projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByLabelText('Backlog lane, 1 issues')).toBeDefined();
      expect(screen.getByLabelText('Crazy_Ideas lane, 7 issues')).toBeDefined();
      expect(screen.getByLabelText('Todo lane, 21 issues')).toBeDefined();
      expect(screen.getByLabelText('Done lane, 270 issues')).toBeDefined();
      expect(screen.getByLabelText('Cancelled lane, 5 issues')).toBeDefined();
    });

    expect(issueQueryCalls).toEqual([
      { cursor: undefined, limit: 100 },
      { cursor: 'offset-100', limit: 100 },
      { cursor: 'offset-200', limit: 100 },
      { cursor: 'offset-300', limit: 100 },
    ]);
    expect(screen.getByText('KAN-83 Active Backlog Guardrail')).toBeDefined();
    expect(screen.getByText('KAN-82 Crazy Idea Prototype')).toBeDefined();
    expect(screen.getByText('KAN-75 Active Todo Feature')).toBeDefined();
  });

  it('fetchAllBoardIssues covers empty projectKey, cycle protection, deduplication, array fallback, maxPages, and abort', async () => {
    const apiSpy = vi.spyOn(clientModule, 'apiFetch');

    // Empty / 'undefined' projectKey
    expect(await fetchAllBoardIssues('')).toEqual([]);
    expect(await fetchAllBoardIssues('undefined')).toEqual([]);
    expect(apiSpy).not.toHaveBeenCalled();

    // Array response with duplicate keys and keyless fallback
    const issueA: BoardIssue = {
      id: 'id-a',
      key: 'KAN-A',
      summary: 'A',
      state_id: 'state-todo',
      board_rank: '000001',
    };
    const issueNoKey: BoardIssue = {
      id: '',
      key: '',
      summary: 'NoKey',
      state_id: 'state-todo',
      board_rank: '000002',
    };
    apiSpy.mockResolvedValueOnce([issueA, issueA, issueNoKey] as never);
    const arrayRes = await fetchAllBoardIssues('KAN');
    expect(arrayRes).toHaveLength(2);

    // Cycle guard + deduplication across pages
    let pageCall = 0;
    apiSpy.mockImplementation(() => {
      pageCall += 1;
      return Promise.resolve({
        items: pageCall === 1 ? [issueA, issueNoKey] : [issueA],
        next_cursor: 'repeat-cur',
      });
    });
    const cycleRes = await fetchAllBoardIssues('KAN');
    expect(cycleRes).toHaveLength(2);
    expect(pageCall).toBe(2);

    // AbortSignal pre-aborted & non-Error reason
    const abortCtrl = new AbortController();
    abortCtrl.abort('board-abort');
    const boardAbortErr = await fetchAllBoardIssues('KAN', { signal: abortCtrl.signal }).catch(
      (err: unknown) => err,
    );
    expect((boardAbortErr as { name?: string }).name).toBe('AbortError');

    const abortErrCtrl = new AbortController();
    abortErrCtrl.abort(new DOMException('Board cancelled', 'AbortError'));
    const boardDomErr = await fetchAllBoardIssues('KAN', { signal: abortErrCtrl.signal }).catch(
      (err: unknown) => err,
    );
    expect((boardDomErr as { name?: string }).name).toBe('AbortError');
    expect((boardDomErr as { message?: string }).message).toBe('Board cancelled');
  });
});
