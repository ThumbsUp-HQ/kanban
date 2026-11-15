/**
 * Workspace Stickies View (KB-P3-51, S8.1, S8.2).
 *
 * Mounts on /stickies and renders all stickies across the workspace with
 * cross-project palette filtering and promotion stubs.
 */

import React, { type JSX } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { StickiesGrid } from './StickiesGrid';
import {
  fetchWorkspaceStickies,
  createSticky,
  updateSticky,
  deleteSticky,
  promoteStickyToDoc,
  unarchiveStickyCopy,
  type StickyItem,
} from './stickiesApi';
import type { StickyColorToken } from './stickyHeuristic';

export const WORKSPACE_STICKIES_QUERY_KEY = ['stickies', 'workspace'] as const;

export function WorkspaceStickiesView({
  defaultProjectKey = 'KAN',
}: {
  defaultProjectKey?: string | undefined;
} = {}): JSX.Element {
  const queryClient = useQueryClient();

  const { data: stickies = [], isLoading } = useQuery<StickyItem[]>({
    queryKey: WORKSPACE_STICKIES_QUERY_KEY,
    queryFn: ({ signal }) => fetchWorkspaceStickies(signal),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createSticky(defaultProjectKey, { body_markdown: '', color_token: 'amber' }),
    onSuccess: (newSticky) => {
      queryClient.setQueryData<StickyItem[]>(WORKSPACE_STICKIES_QUERY_KEY, (old = []) => [
        newSticky,
        ...old,
      ]);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      stickyId,
      payload,
      etag,
    }: {
      stickyId: string;
      payload: {
        body_markdown?: string | undefined;
        color_token?: StickyColorToken | undefined;
        promotion_snoozed_at_length?: number | null | undefined;
      };
      etag?: string | undefined;
    }) => updateSticky(stickyId, payload, etag),
    onSuccess: (updated) => {
      queryClient.setQueryData<StickyItem[]>(WORKSPACE_STICKIES_QUERY_KEY, (old = []) =>
        old.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (stickyId: string) => deleteSticky(stickyId),
    onSuccess: (_, deletedId) => {
      queryClient.setQueryData<StickyItem[]>(WORKSPACE_STICKIES_QUERY_KEY, (old = []) =>
        old.filter((item) => item.id !== deletedId),
      );
    },
  });

  const promoteMutation = useMutation({
    mutationFn: (stickyId: string) => promoteStickyToDoc(stickyId),
    onSuccess: (promoted) => {
      queryClient.setQueryData<StickyItem[]>(WORKSPACE_STICKIES_QUERY_KEY, (old = []) =>
        old.map((item) => (item.id === promoted.id ? promoted : item)),
      );
    },
  });

  const unarchiveMutation = useMutation({
    mutationFn: (stickyId: string) => unarchiveStickyCopy(stickyId),
    onSuccess: (newCopy) => {
      queryClient.setQueryData<StickyItem[]>(WORKSPACE_STICKIES_QUERY_KEY, (old = []) => [
        newCopy,
        ...old,
      ]);
    },
  });

  return (
    <div className="workspace-stickies-page" data-testid="workspace-stickies-page">
      <StickiesGrid
        stickies={stickies}
        title="Workspace Stickies"
        isLoading={isLoading}
        onCreateSticky={() => {
          createMutation.mutate();
        }}
        onUpdateSticky={async (id, payload, etag) => {
          await updateMutation.mutateAsync({ stickyId: id, payload, etag });
        }}
        onDeleteSticky={async (id) => {
          await deleteMutation.mutateAsync(id);
        }}
        onPromoteSticky={async (id) => {
          await promoteMutation.mutateAsync(id);
        }}
        onUnarchiveCopy={async (id) => {
          await unarchiveMutation.mutateAsync(id);
        }}
      />
    </div>
  );
}
