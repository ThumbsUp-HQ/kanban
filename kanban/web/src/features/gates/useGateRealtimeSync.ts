// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { useEffect, useRef } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { announce } from '../../api/RealtimeStatus';
import { apiFetch } from '../../api/client';
import type { RealtimeClient, RealtimeEvent } from '../../api/realtime';
import type {
  WorkflowGateEventPayload,
  PendingGateInfo,
  LatestGateVerdict,
  GateActivityItem,
} from './types';
import type { BoardIssue } from '../board/boardApi';
import type { IssueDetail } from '../drawer/slots';
import type { ActivityResponse } from '../activity/activityApi';

export interface UseGateRealtimeSyncOptions {
  client?: RealtimeClient | undefined;
  queryClient: QueryClient;
  projectKey?: string | undefined;
  onGateVetoed?: ((event: WorkflowGateEventPayload) => void) | undefined;
  onGateApproved?: ((event: WorkflowGateEventPayload) => void) | undefined;
  onGatePending?: ((event: WorkflowGateEventPayload) => void) | undefined;
  onGateCancelled?: ((event: WorkflowGateEventPayload) => void) | undefined;
  onToast?: ((message: string) => void) | undefined;
}

export function cancelGateTransitionApi(executionId: string): Promise<unknown> {
  return apiFetch('DELETE', '/api/v1/transitions/{execution_id}' as never, {
    params: { execution_id: executionId },
  });
}

export interface CachedStateLike {
  id: string;
  name?: string | undefined;
  group?: string | undefined;
  color_hex?: string | null | undefined;
}

function resolveSyncedState(
  issue: BoardIssue,
  stateId: string,
  fallbackName?: string,
  cachedStates?: CachedStateLike[],
): BoardIssue['state'] {
  if (cachedStates && cachedStates.length > 0) {
    const matched = cachedStates.find((s) => s.id === stateId);
    if (matched) {
      return {
        id: matched.id,
        name: matched.name ?? fallbackName ?? '',
        group: (matched.group ?? 'started') as NonNullable<BoardIssue['state']>['group'],
        color_hex: matched.color_hex ?? null,
      };
    }
  }
  if (issue.state) {
    return {
      id: stateId,
      name: fallbackName ?? (issue.state.id === stateId ? issue.state.name : ''),
      group: issue.state.id === stateId ? issue.state.group : 'started',
      color_hex: issue.state.id === stateId ? issue.state.color_hex : null,
    };
  }
  if (fallbackName) {
    return {
      id: stateId,
      name: fallbackName,
      group: 'started' as NonNullable<BoardIssue['state']>['group'],
      color_hex: null,
    };
  }
  return undefined;
}

export function updateBoardIssueWithGate(
  issue: BoardIssue,
  eventType: string,
  p: WorkflowGateEventPayload,
  cachedStates?: CachedStateLike[],
): BoardIssue {
  if (eventType === 'workflow.gate.pending' || eventType === 'gate.pending') {
    const targetStateId = p.to_state_id ?? issue.state_id;
    const nextState = resolveSyncedState(issue, targetStateId, p.to_state, cachedStates);
    const pendingGate: PendingGateInfo = {
      execution_id: p.execution_id,
      hook_name: p.hook_name,
      agent_slug: p.agent_slug ?? 'agent',
      harness_label:
        p.harness_label ??
        (p.harness_kind === 'in_app_sdk' ? 'in_app_sdk' : (p.harness_kind ?? 'cli: agy -p')),
      started_at: p.started_at ?? new Date().toISOString(),
      repo_mount_ro: p.repo_mount_ro !== false,
      from_state: p.from_state,
      to_state: p.to_state,
      from_state_id: p.from_state_id,
      to_state_id: p.to_state_id,
    };
    return {
      ...issue,
      gate_status: 'pending',
      pending_gate: pendingGate,
      state_id: targetStateId,
      ...(nextState ? { state: nextState } : {}),
    };
  }

  if (eventType === 'workflow.gate.approved' || eventType === 'gate.approved') {
    const targetStateId = p.to_state_id ?? issue.state_id;
    const nextState = resolveSyncedState(issue, targetStateId, p.to_state, cachedStates);
    const verdict: LatestGateVerdict = {
      decision: 'approve',
      hook_name: p.hook_name,
      latency_ms: p.latency_ms,
      verdict_sha256: p.verdict_sha256,
      completed_at: p.completed_at ?? new Date().toISOString(),
    };
    return {
      ...issue,
      gate_status: 'approved',
      pending_gate: null,
      state_id: targetStateId,
      latest_gate_verdict: verdict,
      ...(nextState ? { state: nextState } : {}),
    };
  }

  if (
    eventType === 'workflow.gate.rejected' ||
    eventType === 'workflow.gate.timed_out' ||
    eventType === 'workflow.gate.vetoed' ||
    eventType === 'workflow.gate.failed' ||
    eventType === 'gate.rejected' ||
    eventType === 'gate.vetoed' ||
    eventType === 'gate.failed' ||
    eventType === 'gate.timed_out'
  ) {
    const fromStateId = p.from_state_id ?? issue.pending_gate?.from_state_id ?? issue.state_id;
    const nextState = resolveSyncedState(issue, fromStateId, p.from_state, cachedStates);
    const verdict: LatestGateVerdict = {
      decision: 'reject',
      hook_name: p.hook_name,
      agent_slug: p.agent_slug,
      reason_preview: p.reason_preview,
      audit_comment_id: p.audit_comment_id,
      completed_at: p.completed_at ?? new Date().toISOString(),
    };
    return {
      ...issue,
      gate_status: 'rejected',
      pending_gate: null,
      state_id: fromStateId,
      latest_gate_verdict: verdict,
      ...(nextState ? { state: nextState } : {}),
    };
  }

  if (eventType === 'workflow.gate.cancelled' || eventType === 'gate.cancelled') {
    const fromStateId = p.from_state_id ?? issue.pending_gate?.from_state_id ?? issue.state_id;
    const nextState = resolveSyncedState(issue, fromStateId, p.from_state, cachedStates);
    return {
      ...issue,
      gate_status: null,
      pending_gate: null,
      state_id: fromStateId,
      ...(nextState ? { state: nextState } : {}),
    };
  }

  return issue;
}

export function handleGateEvent(
  eventType: string,
  payload: WorkflowGateEventPayload,
  queryClient: QueryClient,
  options: {
    projectKey?: string | undefined;
    onGateVetoed?: ((event: WorkflowGateEventPayload) => void) | undefined;
    onGateApproved?: ((event: WorkflowGateEventPayload) => void) | undefined;
    onGatePending?: ((event: WorkflowGateEventPayload) => void) | undefined;
    onGateCancelled?: ((event: WorkflowGateEventPayload) => void) | undefined;
    onToast?: ((message: string) => void) | undefined;
  } = {},
): void {
  const { issue_key } = payload;
  if (!issue_key) return;

  // 1. Update Board / Issues List caches
  queryClient.setQueriesData<unknown>(
    {
      predicate: (q) =>
        q.queryKey[0] === 'issues' &&
        (options.projectKey === undefined || q.queryKey[1] === options.projectKey),
    },
    (oldData: unknown) => {
      if (!oldData) return oldData;
      if (Array.isArray(oldData)) {
        return oldData.map((item: BoardIssue) =>
          item.key === issue_key ? updateBoardIssueWithGate(item, eventType, payload) : item,
        );
      }
      if (typeof oldData === 'object' && 'items' in oldData && Array.isArray((oldData as { items: unknown[] }).items)) {
        const obj = oldData as { items: BoardIssue[] };
        return {
          ...obj,
          items: obj.items.map((item) =>
            item.key === issue_key ? updateBoardIssueWithGate(item, eventType, payload) : item,
          ),
        };
      }
      return oldData;
    },
  );

  // 2. Update single issue detail cache
  queryClient.setQueryData<IssueDetail>(qk.issue(issue_key), (oldIssue) => {
    if (!oldIssue) return oldIssue;
    if (eventType === 'workflow.gate.pending' || eventType === 'gate.pending') {
      const pendingGate: PendingGateInfo = {
        execution_id: payload.execution_id,
        hook_name: payload.hook_name,
        agent_slug: payload.agent_slug ?? 'agent',
        harness_label:
          payload.harness_label ??
          (payload.harness_kind === 'in_app_sdk' ? 'in_app_sdk' : (payload.harness_kind ?? 'cli: agy -p')),
        started_at: payload.started_at ?? new Date().toISOString(),
        repo_mount_ro: payload.repo_mount_ro !== false,
        from_state: payload.from_state,
        to_state: payload.to_state,
        from_state_id: payload.from_state_id,
        to_state_id: payload.to_state_id,
      };
      return {
        ...oldIssue,
        pending_gate: pendingGate,
        gate_status: 'pending',
        state: payload.to_state
          ? {
              id: payload.to_state_id ?? oldIssue.state?.id,
              name: payload.to_state,
              group: 'started',
            }
          : oldIssue.state,
      };
    }
    if (eventType === 'workflow.gate.approved' || eventType === 'gate.approved') {
      return {
        ...oldIssue,
        pending_gate: null,
        gate_status: 'approved',
        latest_gate_verdict: {
          decision: 'approve',
          hook_name: payload.hook_name,
          latency_ms: payload.latency_ms,
          verdict_sha256: payload.verdict_sha256,
          completed_at: payload.completed_at ?? new Date().toISOString(),
        },
        state: payload.to_state
          ? {
              id: payload.to_state_id ?? oldIssue.state?.id,
              name: payload.to_state,
              group: 'completed',
            }
          : oldIssue.state,
      };
    }
    if (
      eventType === 'workflow.gate.rejected' ||
      eventType === 'workflow.gate.timed_out' ||
      eventType === 'workflow.gate.vetoed' ||
      eventType === 'workflow.gate.failed' ||
      eventType === 'gate.rejected' ||
      eventType === 'gate.vetoed' ||
      eventType === 'gate.failed' ||
      eventType === 'gate.timed_out'
    ) {
      const fromStateId =
        payload.from_state_id ?? oldIssue.pending_gate?.from_state_id ?? oldIssue.state?.id;
      const fromStateName =
        payload.from_state ?? oldIssue.pending_gate?.from_state ?? oldIssue.state?.name;
      return {
        ...oldIssue,
        pending_gate: null,
        gate_status: 'rejected',
        latest_gate_verdict: {
          decision: 'reject',
          hook_name: payload.hook_name,
          agent_slug: payload.agent_slug,
          reason_preview: payload.reason_preview,
          audit_comment_id: payload.audit_comment_id,
          completed_at: payload.completed_at ?? new Date().toISOString(),
        },
        state: fromStateId
          ? {
              id: fromStateId,
              name: fromStateName ?? 'In Progress',
              group: 'started',
            }
          : oldIssue.state,
      };
    }
    if (eventType === 'workflow.gate.cancelled' || eventType === 'gate.cancelled') {
      const fromStateId =
        payload.from_state_id ?? oldIssue.pending_gate?.from_state_id ?? oldIssue.state?.id;
      const fromStateName =
        payload.from_state ?? oldIssue.pending_gate?.from_state ?? oldIssue.state?.name;
      return {
        ...oldIssue,
        pending_gate: null,
        gate_status: null,
        state: fromStateId
          ? {
              id: fromStateId,
              name: fromStateName ?? 'In Progress',
              group: 'started',
            }
          : oldIssue.state,
      };
    }
    return oldIssue;
  });

  // 3. Update Activity Feed Cache (idempotent injection)
  const activityEventMap: Record<string, GateActivityItem['event_type']> = {
    'workflow.gate.approved': 'GATE_APPROVED',
    'gate.approved': 'GATE_APPROVED',
    'workflow.gate.rejected': 'GATE_REJECTED',
    'gate.rejected': 'GATE_REJECTED',
    'workflow.gate.vetoed': 'GATE_REJECTED',
    'gate.vetoed': 'GATE_REJECTED',
    'workflow.gate.failed': 'GATE_REJECTED',
    'gate.failed': 'GATE_REJECTED',
    'workflow.gate.timed_out': 'GATE_REJECTED',
    'gate.timed_out': 'GATE_REJECTED',
    'workflow.gate.cancelled':
      payload.reason === 'STALE_SNAPSHOT' ? 'GATE_ABORTED_STALE' : 'GATE_REJECTED',
    'gate.cancelled':
      payload.reason === 'STALE_SNAPSHOT' ? 'GATE_ABORTED_STALE' : 'GATE_REJECTED',
  };

  const activityEventType = activityEventMap[eventType];
  if (activityEventType) {
    const activityItemId = `gate-evt-${payload.execution_id}-${payload.hook_name}-${activityEventType}`;
    const newActivityItem: GateActivityItem = {
      id: activityItemId,
      category: 'AGENT_GATE',
      event_type: activityEventType,
      actor: {
        type: 'AGENT',
        slug: payload.agent_slug,
        display_name: payload.hook_name,
      },
      created_at: payload.completed_at ?? new Date().toISOString(),
      row_hash: payload.verdict_sha256,
      payload: {
        hook_name: payload.hook_name,
        harness: payload.harness_label ?? payload.harness_kind,
        execution_latency_ms: payload.latency_ms,
        verdict_sha256: payload.verdict_sha256,
        reason: payload.reason_preview,
        audit_comment_id: payload.audit_comment_id,
        from_state: payload.from_state,
        to_state: payload.to_state,
      },
    };

    // Update all matching activity queries for this issue
    queryClient.setQueriesData<ActivityResponse>(
      {
        predicate: (q) => q.queryKey[0] === 'activity' && q.queryKey[1] === issue_key,
      },
      (oldActivity) => {
        if (!oldActivity) return oldActivity;
        const exists = oldActivity.items.some(
          (it) =>
            it.id === activityItemId ||
            (it.payload &&
              (it.payload as { verdict_sha256?: string }).verdict_sha256 ===
                payload.verdict_sha256 &&
              payload.verdict_sha256 !== undefined),
        );
        if (exists) {
          return oldActivity;
        }

        const counts = {
          ...oldActivity.counts,
          all: oldActivity.counts.all + 1,
          gates: oldActivity.counts.gates + 1,
        };

        return {
          ...oldActivity,
          items: [newActivityItem as unknown as ActivityResponse['items'][number], ...oldActivity.items],
          counts,
        };
      },
    );
  }

  // 4. Notifications & Callbacks
  const isVetoOrReject =
    eventType === 'workflow.gate.rejected' ||
    eventType === 'workflow.gate.timed_out' ||
    eventType === 'workflow.gate.vetoed' ||
    eventType === 'workflow.gate.failed' ||
    eventType === 'gate.rejected' ||
    eventType === 'gate.vetoed' ||
    eventType === 'gate.failed' ||
    eventType === 'gate.timed_out';

  if (
    eventType === 'workflow.gate.approved' ||
    eventType === 'gate.approved' ||
    isVetoOrReject ||
    eventType === 'workflow.gate.cancelled' ||
    eventType === 'gate.cancelled'
  ) {
    void queryClient.invalidateQueries({ queryKey: ['comments', issue_key] });
    void queryClient.invalidateQueries({
      predicate: (q) => q.queryKey[0] === 'activity' && q.queryKey[1] === issue_key,
    });
  }

  if (eventType === 'workflow.gate.pending' || eventType === 'gate.pending') {
    options.onGatePending?.(payload);
  } else if (eventType === 'workflow.gate.approved' || eventType === 'gate.approved') {
    options.onGateApproved?.(payload);
  } else if (isVetoOrReject) {
    const msg = `Gate ${payload.hook_name} vetoed transition ${issue_key}`;
    announce(msg);
    options.onGateVetoed?.(payload);
  } else if (eventType === 'workflow.gate.cancelled' || eventType === 'gate.cancelled') {
    if (payload.reason === 'STALE_SNAPSHOT') {
      const msg = 'Transition cancelled (ticket changed while gate was running)';
      options.onToast?.(msg);
      announce(msg);
    }
    options.onGateCancelled?.(payload);
  }
}

/**
 * Realtime hook synchronizing async agent gate events with TanStack Query caches.
 */
export function useGateRealtimeSync({
  client,
  queryClient,
  projectKey,
  onGateVetoed,
  onGateApproved,
  onGatePending,
  onGateCancelled,
  onToast,
}: UseGateRealtimeSyncOptions): void {
  const processedEventsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!client) return undefined;

    const handler = (event: RealtimeEvent): void => {
      const normalizedType = event.type.toLowerCase();
      const isGateEvent =
        normalizedType.startsWith('workflow.gate.') ||
        normalizedType.startsWith('gate.') ||
        [
          'workflow.gate.pending',
          'workflow.gate.approved',
          'workflow.gate.rejected',
          'workflow.gate.timed_out',
          'workflow.gate.cancelled',
          'workflow.gate.vetoed',
          'workflow.gate.failed',
          'gate.pending',
          'gate.approved',
          'gate.rejected',
          'gate.vetoed',
          'gate.failed',
        ].includes(normalizedType);
      if (!isGateEvent) {
        return;
      }

      // Deduplicate event processing by event.id or execution+type
      const p = event.payload as unknown as WorkflowGateEventPayload;
      const dedupeKey = `${event.id}:${p.execution_id}:${event.type}`;
      if (processedEventsRef.current.has(dedupeKey)) {
        return;
      }
      processedEventsRef.current.add(dedupeKey);
      if (processedEventsRef.current.size > 1000) {
        processedEventsRef.current.clear();
      }

      handleGateEvent(event.type, p, queryClient, {
        projectKey,
        onGateVetoed,
        onGateApproved,
        onGatePending,
        onGateCancelled,
        onToast,
      });
    };

    return client.onEvent(handler);
  }, [
    client,
    queryClient,
    projectKey,
    onGateVetoed,
    onGateApproved,
    onGatePending,
    onGateCancelled,
    onToast,
  ]);
}
