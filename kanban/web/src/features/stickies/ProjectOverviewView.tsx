/**
 * Project Overview View (KB-P3-51, S8.1, S8.2).
 *
 * Mounts on /projects/:projectKey/overview and renders the 6-palette stickies grid
 * with real-time optimistic queries and mutations.
 */

import React, { type JSX } from 'react';
import { useParams } from 'react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { StickiesGrid } from './StickiesGrid';
import {
  fetchProjectStickies,
  createSticky,
  updateSticky,
  deleteSticky,
  promoteStickyToDoc,
  unarchiveStickyCopy,
  type StickyItem,
} from './stickiesApi';
import type { StickyColorToken } from './stickyHeuristic';
import { useProjectRouteContext } from '../../app/ProjectRouteContext';
import { useRealtimeSubscription } from '../../realtime';

export function ProjectOverviewView(): JSX.Element {
  const { projectKey = 'KAN' } = useParams<{ projectKey: string }>();
  useRealtimeSubscription(projectKey ? `project:${projectKey}` : null);
  const queryClient = useQueryClient();
  const ctx = useProjectRouteContext();

  const effectiveCaps = ctx.projectKey
    ? ctx.capabilities
    : (ctx.capabilities.length > 0 ? ctx.capabilities : ['EDIT', 'ADMIN']);
  const canEdit = effectiveCaps.includes('EDIT') || effectiveCaps.includes('ADMIN') || ctx.isProjectAdmin;

  const { data: stickies = [], isLoading } = useQuery<StickyItem[]>({
    queryKey: qk.stickies(projectKey),
    queryFn: ({ signal }) => fetchProjectStickies(projectKey, signal),
  });

  const createMutation = useMutation({
    mutationFn: () => createSticky(projectKey, { body_markdown: '', color_token: 'amber' }),
    onSuccess: (newSticky) => {
      queryClient.setQueryData<StickyItem[]>(qk.stickies(projectKey), (old = []) => [
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
      queryClient.setQueryData<StickyItem[]>(qk.stickies(projectKey), (old = []) =>
        old.map((item) => (item.id === updated.id ? updated : item)),
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (stickyId: string) => deleteSticky(stickyId),
    onSuccess: (_, deletedId) => {
      queryClient.setQueryData<StickyItem[]>(qk.stickies(projectKey), (old = []) =>
        old.filter((item) => item.id !== deletedId),
      );
    },
  });

  const promoteMutation = useMutation({
    mutationFn: (stickyId: string) => promoteStickyToDoc(stickyId),
    onSuccess: (promoted) => {
      queryClient.setQueryData<StickyItem[]>(qk.stickies(projectKey), (old = []) =>
        old.map((item) => (item.id === promoted.id ? promoted : item)),
      );
      void queryClient.invalidateQueries({ queryKey: qk.docsTree(projectKey) });
    },
  });

  const unarchiveMutation = useMutation({
    mutationFn: (stickyId: string) => unarchiveStickyCopy(stickyId),
    onSuccess: (newCopy) => {
      queryClient.setQueryData<StickyItem[]>(qk.stickies(projectKey), (old = []) => [
        newCopy,
        ...old,
      ]);
    },
  });

  return (
    <div className="project-overview-page" data-testid="project-overview-page">
      <StickiesGrid
        stickies={stickies}
        projectKey={projectKey}
        title="Project Overview Stickies"
        isLoading={isLoading}
        readOnly={!canEdit}
        onCreateSticky={canEdit ? () => {
          createMutation.mutate();
        } : undefined}
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
