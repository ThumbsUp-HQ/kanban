import { describe, expect, it } from 'vitest';
import { qk } from './queryKeys.ts';
import { createQueryClient } from './queryClient.ts';
import { ApiProblem } from './problem.ts';

describe('qk', () => {
  it('builds the exact key tuples', () => {
    expect(qk.me()).toEqual(['me']);
    expect(qk.systemStatus()).toEqual(['system', 'status']);
    expect(qk.projects()).toEqual(['projects']);
    expect(qk.savedViews('KAN')).toEqual(['views', 'KAN']);
    expect(qk.notifications()).toEqual(['notifications', false]);
    expect(qk.notifications(true)).toEqual(['notifications', true]);
    expect(qk.project('KAN')).toEqual(['project', 'KAN']);
    expect(qk.issues('KAN', { state: 'open' })).toEqual(['issues', 'KAN', { state: 'open' }]);
    expect(qk.issue('KAN-1')).toEqual(['issue', 'KAN-1']);
    expect(qk.activity('KAN-1', 'gates')).toEqual(['activity', 'KAN-1', 'gates']);
    expect(qk.access('obj')).toEqual(['access', 'obj']);
    expect(qk.authCards()).toEqual(['auth', 'cards']);
    expect(qk.docsTree('KAN')).toEqual(['docs', 'tree', 'KAN']);
    expect(qk.page('p1')).toEqual(['docs', 'page', 'p1']);
    expect(qk.stickies('KAN')).toEqual(['stickies', 'KAN']);
    expect(qk.subscription('KAN-1')).toEqual(['subscription', 'KAN-1']);
    expect(qk.objectLinks('KAN-1')).toEqual(['objectLinks', 'KAN-1']);
    expect(qk.canonicalUrl('KAN-1')).toEqual(['canonicalUrl', 'KAN-1']);
    expect(qk.deletePreview('KAN-1')).toEqual(['deletePreview', 'KAN-1']);
  });
});

describe('createQueryClient', () => {
  it('applies staleness, focus refetch and the retry policy', () => {
    const defaults = createQueryClient().getDefaultOptions().queries;
    expect(defaults?.staleTime).toBe(30000);
    expect(defaults?.refetchOnWindowFocus).toBe(true);
    const retry = defaults?.retry as (n: number, e: unknown) => boolean;
    expect(retry(0, new Error('net'))).toBe(true);
    expect(retry(2, new Error('net'))).toBe(false);
    expect(retry(0, new ApiProblem(404))).toBe(false);
    expect(retry(0, new ApiProblem(503))).toBe(true);
  });
});
