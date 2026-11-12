/**
 * QueryClient factory configured with project retry policies and staleness timeouts (KB-P3-33).
 */

import { QueryClient } from '@tanstack/react-query';
import { ApiProblem } from './problem.ts';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30000,
        retry: (n: number, e: unknown) => n < 2 && !(e instanceof ApiProblem && e.status < 500),
        refetchOnWindowFocus: true,
      },
    },
  });
}
