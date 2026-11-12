import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import { useOptimisticMutation } from './optimistic.ts';
import { RealtimeStatus } from './RealtimeStatus.tsx';
import { render } from '@testing-library/react';

interface Issue {
  id: string;
  state: string;
  rank: number;
}

const KEY = ['issues', 'KAN', {}] as const;

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function board(n: number): Issue[] {
  return Array.from({ length: n }, (_, i) => ({ id: `i${String(i)}`, state: 'todo', rank: i }));
}

function moveIssue(cache: Issue[] | undefined, vars: { id: string; state: string }): Issue[] {
  return (cache ?? []).map((i) => (i.id === vars.id ? { ...i, state: vars.state } : i));
}

describe('useOptimisticMutation', () => {
  it('writes apply() synchronously before mutationFn resolves, then settles', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(KEY, board(3));
    let release: (v: string) => void = () => undefined;
    const pending = new Promise<string>((resolve) => {
      release = resolve;
    });
    const { result } = renderHook(
      () =>
        useOptimisticMutation<{ id: string; state: string }, string, Issue[]>({
          mutationFn: () => pending,
          queryKey: KEY,
          apply: moveIssue,
        }),
      { wrapper: makeWrapper(client) },
    );
    act(() => {
      result.current.mutate({ id: 'i1', state: 'done' });
    });
    await waitFor(() => {
      expect(client.getQueryData<Issue[]>(KEY)?.[1]?.state).toBe('done');
    });
    expect(result.current.isSuccess).toBe(false);
    await act(async () => {
      release('ok');
      await pending;
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('restores the deep-equal snapshot and announces on rejection', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const original = board(3);
    client.setQueryData(KEY, original);
    render(<RealtimeStatus />);
    const { result } = renderHook(
      () =>
        useOptimisticMutation<{ id: string; state: string }, string, Issue[]>({
          mutationFn: () => Promise.reject(new Error('veto')),
          queryKey: KEY,
          apply: moveIssue,
          onRollbackMessage: (err) => `Rolled back: ${(err as Error).message}`,
        }),
      { wrapper: makeWrapper(client) },
    );
    await act(async () => {
      result.current.mutate({ id: 'i0', state: 'done' });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(client.getQueryData<Issue[]>(KEY)).toEqual(original);
    expect(document.querySelector('.realtime-live-region')?.textContent).toBe('Rolled back: veto');
  });

  it('uses the default rollback message and handles an empty cache', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<RealtimeStatus />);
    const { result } = renderHook(
      () =>
        useOptimisticMutation<{ id: string; state: string }, string, Issue[]>({
          mutationFn: () => Promise.reject(new Error('x')),
          queryKey: KEY,
          apply: moveIssue,
        }),
      { wrapper: makeWrapper(client) },
    );
    await act(async () => {
      result.current.mutate({ id: 'a', state: 'b' });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(document.querySelector('.realtime-live-region')?.textContent).toBe(
      'Update failed. Changes were reverted.',
    );
  });

  it('500-issue synchronous apply median is under 12ms (20 runs)', () => {
    const cache = board(500);
    const samples: number[] = [];
    for (let run = 0; run < 20; run += 1) {
      const start = performance.now();
      moveIssue(cache, { id: 'i250', state: 'done' });
      samples.push(performance.now() - start);
    }
    samples.sort((a, b) => a - b);
    const median = ((samples[9] ?? 0) + (samples[10] ?? 0)) / 2;
    const line = `runs=20 median_ms=${median.toFixed(4)} max_ms=${(samples[19] ?? 0).toFixed(4)} min_ms=${(samples[0] ?? 0).toFixed(4)}`;
    console.log(`OPTIMISTIC_BENCHMARK ${line}`);
    expect(median).toBeLessThan(12);
  });
});
