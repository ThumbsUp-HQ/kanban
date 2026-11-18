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
import { qk } from '../../api/queryKeys';
import { useRealtimeSubscription } from '../../realtime';

export const WORKSPACE_STICKIES_QUERY_KEY = ['stickies', 'workspace'] as const;

export interface WorkspaceStickiesViewProps {
  defaultProjectKey?: string | undefined;
  readOnly?: boolean | undefined;
}

export function WorkspaceStickiesView({
  defaultProjectKey = 'KAN',
  readOnly: propReadOnly,
}: WorkspaceStickiesViewProps = {}): JSX.Element {
  useRealtimeSubscription('workspace:stickies');
  const queryClient = useQueryClient();

  const cachedUser = queryClient.getQueryData<{ workspace_role?: string }>(qk.me());
  const isViewer = propReadOnly ?? (cachedUser?.workspace_role === 'VIEWER' || cachedUser?.workspace_role === 'WORKSPACE_GUEST');

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
    mutationFn: ({
      stickyId,
      payload,
    }: {
      stickyId: string;
      payload?: {
        title?: string;
        parent_doc_id?: string;
        parent_page_id?: string;
        structured_body_markdown?: string;
        expected_sticky_sha256?: string;
      };
    }) => promoteStickyToDoc(stickyId, payload),
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
        readOnly={isViewer}
        onCreateSticky={!isViewer ? () => {
          createMutation.mutate();
        } : undefined}
        onUpdateSticky={async (id, payload, etag) => {
          await updateMutation.mutateAsync({ stickyId: id, payload, etag });
        }}
        onDeleteSticky={async (id) => {
          await deleteMutation.mutateAsync(id);
        }}
        onPromoteSticky={async (id, payload) => {
          await promoteMutation.mutateAsync({ stickyId: id, ...(payload ? { payload } : {}) });
        }}
        onUnarchiveCopy={async (id) => {
          await unarchiveMutation.mutateAsync(id);
        }}
      />
    </div>
  );
}
