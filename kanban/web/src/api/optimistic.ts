/**
 * Optimistic mutation hook with synchronous cache updates and deterministic rollback (KB-P3-33).
 */

import {
  useMutation,
  useQueryClient,
  type QueryKey,
  type UseMutationResult,
} from '@tanstack/react-query';
import { announce } from './RealtimeStatus.tsx';

export interface UseOptimisticMutationOptions<TVars, TData, TCache> {
  mutationFn: (vars: TVars) => Promise<TData>;
  queryKey: QueryKey;
  apply: (cache: TCache | undefined, vars: TVars) => TCache;
  onRollbackMessage?: (err: unknown) => string;
}

interface OptimisticContext<TCache> {
  snapshot: TCache | undefined;
}

export function useOptimisticMutation<TVars, TData, TCache>(
  options: UseOptimisticMutationOptions<TVars, TData, TCache>,
): UseMutationResult<TData, unknown, TVars, OptimisticContext<TCache>> {
  const queryClient = useQueryClient();
  const { mutationFn, queryKey, apply, onRollbackMessage } = options;

  return useMutation<TData, unknown, TVars, OptimisticContext<TCache>>({
    mutationFn,
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey });
      const snapshot = queryClient.getQueryData<TCache>(queryKey);
      queryClient.setQueryData<TCache>(queryKey, apply(snapshot, vars));
      return { snapshot };
    },
    onError: (err, _vars, context) => {
      if (context) {
        queryClient.setQueryData<TCache>(queryKey, context.snapshot);
      }
      announce(onRollbackMessage ? onRollbackMessage(err) : 'Update failed. Changes were reverted.');
    },
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
  });
}
