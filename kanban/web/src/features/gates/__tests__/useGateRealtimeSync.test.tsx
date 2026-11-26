// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import {
  useGateRealtimeSync,
  handleGateEvent,
  cancelGateTransitionApi,
} from '../useGateRealtimeSync';
import type { WorkflowGateEventPayload } from '../types';
import type { BoardIssue } from '../../board/boardApi';
import type { IssueDetail } from '../../drawer/slots';
import type { ActivityResponse } from '../../activity/activityApi';
import { qk } from '../../../api/queryKeys';
import * as clientModule from '../../../api/client';

describe('useGateRealtimeSync & handleGateEvent (KB-P5-25)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  afterEach(() => {
    queryClient.clear();
    vi.restoreAllMocks();
  });

  describe('handleGateEvent', () => {
    it('handles workflow.gate.pending and updates issues and issue caches', () => {
      const initialIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Sliding-window rate limiter',
        state_id: 'state-in-progress',
        board_rank: '0|hzzzzz:',
      };

      queryClient.setQueryData(qk.issues('KAN', {}), [initialIssue]);

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Sliding-window rate limiter',
        state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const onGatePending = vi.fn();
      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-1',
        hook_name: 'sec-review',
        agent_slug: 'security-agent',
        harness_label: 'cli: agy -p',
        from_state: 'In Progress',
        from_state_id: 'state-in-progress',
        to_state: 'In Review',
        to_state_id: 'state-in-review',
        started_at: '2026-11-14T00:00:00Z',
      };

      handleGateEvent('workflow.gate.pending', payload, queryClient, {
        projectKey: 'KAN',
        onGatePending,
      });

      expect(onGatePending).toHaveBeenCalledWith(payload);

      // Verify board issue cache
      const boardIssues = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(boardIssues?.[0]?.gate_status).toBe('pending');
      expect(boardIssues?.[0]?.state_id).toBe('state-in-review');
      expect(boardIssues?.[0]?.pending_gate?.execution_id).toBe('exec-1');

      // Verify issue detail cache
      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate?.hook_name).toBe('sec-review');
      expect(detail?.state?.name).toBe('In Review');
    });

    it('handles workflow.gate.approved and updates activity cache with verdict hash', () => {
      const pendingIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 'state-in-review',
        board_rank: '0|hzzzzz:',
        gate_status: 'pending',
        pending_gate: {
          execution_id: 'exec-1',
          hook_name: 'sec-review',
          agent_slug: 'sec',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };

      queryClient.setQueryData(qk.issues('KAN', {}), { items: [pendingIssue] });

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Sliding-window rate limiter',
        state: { id: 'state-in-review', name: 'In Review', group: 'started' },
        pending_gate: {
          execution_id: 'exec-1',
          hook_name: 'sec-review',
          agent_slug: 'sec',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const initialActivity: ActivityResponse = {
        items: [],
        counts: { all: 0, comments: 0, history: 0, gates: 0 },
        next_cursor: null,
      };
      queryClient.setQueryData(qk.activity('KAN-8', 'gates'), initialActivity);

      const onGateApproved = vi.fn();
      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-1',
        hook_name: 'sec-review',
        to_state: 'Done',
        to_state_id: 'state-done',
        latency_ms: 1420,
        verdict_sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      };

      handleGateEvent('workflow.gate.approved', payload, queryClient, {
        projectKey: 'KAN',
        onGateApproved,
      });

      expect(onGateApproved).toHaveBeenCalledWith(payload);

      // Board issue committed to Done
      const cached = queryClient.getQueryData<{ items: BoardIssue[] }>(qk.issues('KAN', {}));
      expect(cached?.items[0]?.gate_status).toBe('approved');
      expect(cached?.items[0]?.state_id).toBe('state-done');
      expect(cached?.items[0]?.pending_gate).toBeNull();
      expect(cached?.items[0]?.latest_gate_verdict?.verdict_sha256).toBe(
        '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      );

      // Issue detail cache updated
      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate).toBeNull();
      expect(detail?.latest_gate_verdict?.decision).toBe('approve');
      expect(detail?.state?.name).toBe('Done');

      // Activity cache contains GATE_APPROVED record
      const activity = queryClient.getQueryData<ActivityResponse>(qk.activity('KAN-8', 'gates'));
      expect(activity?.counts.gates).toBe(1);
      expect(activity?.items.length).toBe(1);
      expect(activity?.items[0]?.event_type).toBe('GATE_APPROVED');

      // Boundary: duplicate event is idempotent
      handleGateEvent('workflow.gate.approved', payload, queryClient, { projectKey: 'KAN' });
      const activityAfterDup = queryClient.getQueryData<ActivityResponse>(
        qk.activity('KAN-8', 'gates'),
      );
      expect(activityAfterDup?.items.length).toBe(1);
    });

    it('handles workflow.gate.rejected, reverts state, and announces polite veto', () => {
      const pendingIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 'state-in-review',
        board_rank: '0|hzzzzz:',
        gate_status: 'pending',
      };

      queryClient.setQueryData(qk.issues('KAN', {}), [pendingIssue]);

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Task',
        state: { id: 'state-in-review', name: 'In Review', group: 'started' },
        pending_gate: {
          execution_id: 'exec-1',
          hook_name: 'forensic-code-check',
          agent_slug: 'reality-checker',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const onGateVetoed = vi.fn();
      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-1',
        hook_name: 'forensic-code-check',
        agent_slug: 'reality-checker',
        from_state: 'In Progress',
        from_state_id: 'state-in-progress',
        to_state: 'In Review',
        to_state_id: 'state-in-review',
        reason_preview: 'Verification proof rejected: missing test results.',
        audit_comment_id: 'comment-123',
      };

      handleGateEvent('workflow.gate.rejected', payload, queryClient, {
        projectKey: 'KAN',
        onGateVetoed,
      });

      expect(onGateVetoed).toHaveBeenCalledWith(payload);

      const boardIssues = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(boardIssues?.[0]?.gate_status).toBe('rejected');
      expect(boardIssues?.[0]?.state_id).toBe('state-in-progress');
      expect(boardIssues?.[0]?.latest_gate_verdict?.reason_preview).toBe(
        'Verification proof rejected: missing test results.',
      );

      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate).toBeNull();
      expect(detail?.latest_gate_verdict?.decision).toBe('reject');
      expect(detail?.state?.name).toBe('In Progress');
    });

    it('handles issue.transition_rejected event and snaps back state cleanly', () => {
      const pendingIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 'state-in-review',
        board_rank: '0|hzzzzz:',
        gate_status: 'pending',
      };
      queryClient.setQueryData(qk.issues('KAN', {}), [pendingIssue]);

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Task',
        state: { id: 'state-in-review', name: 'In Review', group: 'started' },
        pending_gate: {
          execution_id: 'exec-trans-1',
          hook_name: 'forensic-code-check',
          agent_slug: 'reality-checker',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const onGateVetoed = vi.fn();
      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-trans-1',
        hook_name: 'forensic-code-check',
        agent_slug: 'reality-checker',
        from_state: 'In Progress',
        from_state_id: 'state-in-progress',
        to_state: 'In Review',
        to_state_id: 'state-in-review',
        reason_preview: 'Transition rejected: gate vetoed.',
      };

      handleGateEvent('issue.transition_rejected', payload, queryClient, {
        projectKey: 'KAN',
        onGateVetoed,
      });

      expect(onGateVetoed).toHaveBeenCalledWith(payload);

      const boardIssues = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(boardIssues?.[0]?.gate_status).toBe('rejected');
      expect(boardIssues?.[0]?.state_id).toBe('state-in-progress');

      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate).toBeNull();
      expect(detail?.latest_gate_verdict?.decision).toBe('reject');
      expect(detail?.state?.name).toBe('In Progress');
    });

    it('handles workflow.gate.timed_out, resets state, and updates caches', () => {
      const pendingIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 'state-in-review',
        board_rank: '0|hzzzzz:',
        gate_status: 'pending',
      };
      queryClient.setQueryData(qk.issues('KAN', {}), [pendingIssue]);

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Task',
        state: { id: 'state-in-review', name: 'In Review', group: 'started' },
        pending_gate: {
          execution_id: 'exec-1',
          hook_name: 'forensic-code-check',
          agent_slug: 'reality-checker',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const onGateVetoed = vi.fn();
      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-1',
        hook_name: 'forensic-code-check',
        reason_preview: 'Timeout waiting for agent verdict (30000ms exceeded).',
      };

      handleGateEvent('workflow.gate.timed_out', payload, queryClient, {
        projectKey: 'KAN',
        onGateVetoed,
      });

      expect(onGateVetoed).toHaveBeenCalledWith(payload);

      const boardIssues = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(boardIssues?.[0]?.gate_status).toBe('rejected');
      expect(boardIssues?.[0]?.pending_gate).toBeNull();

      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate).toBeNull();
      expect(detail?.latest_gate_verdict?.decision).toBe('reject');
    });

    it('handles workflow.gate.cancelled with STALE_SNAPSHOT and shows toast', () => {
      const pendingIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 'state-in-review',
        board_rank: '0|hzzzzz:',
        gate_status: 'pending',
      };
      queryClient.setQueryData(qk.issues('KAN', {}), [pendingIssue]);

      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Task',
        state: { id: 'state-in-review', name: 'In Review', group: 'started' },
        pending_gate: {
          execution_id: 'exec-1',
          hook_name: 'engine',
          agent_slug: 'engine',
          harness_label: 'cli: agy -p',
          started_at: '2026-11-14T00:00:00Z',
        },
      };
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      const onToast = vi.fn();
      const onGateCancelled = vi.fn();

      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-1',
        hook_name: 'engine',
        from_state: 'In Progress',
        from_state_id: 'state-in-progress',
        reason: 'STALE_SNAPSHOT',
      };

      handleGateEvent('workflow.gate.cancelled', payload, queryClient, {
        projectKey: 'KAN',
        onToast,
        onGateCancelled,
      });

      expect(onToast).toHaveBeenCalledWith(
        'Transition cancelled (ticket changed while gate was running)',
      );
      expect(onGateCancelled).toHaveBeenCalledWith(payload);

      const boardIssues = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(boardIssues?.[0]?.gate_status).toBeNull();
      expect(boardIssues?.[0]?.state_id).toBe('state-in-progress');

      const detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.pending_gate).toBeNull();
      expect(detail?.state?.name).toBe('In Progress');
    });

    it('handles workflow.gate.cancelled with USER_OVERRIDE reason (not stale snapshot)', () => {
      const onToast = vi.fn();
      const onGateCancelled = vi.fn();

      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-user-override',
        hook_name: 'engine',
        reason: 'USER_OVERRIDE',
      };

      handleGateEvent('workflow.gate.cancelled', payload, queryClient, {
        onToast,
        onGateCancelled,
      });

      expect(onToast).not.toHaveBeenCalled();
      expect(onGateCancelled).toHaveBeenCalledWith(payload);
    });

    it('returns early when payload has no issue_key', () => {
      // @ts-expect-error missing issue_key
      const payload: WorkflowGateEventPayload = {
        execution_id: 'exec-no-key',
        hook_name: 'engine',
      };
      // Should not throw
      expect(() => {
        handleGateEvent('workflow.gate.pending', payload, queryClient);
      }).not.toThrow();
    });

    it('handles unknown gate events and unrecognized query cache shapes gracefully', () => {
      const issueItem: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Sliding-window rate limiter',
        state_id: 'state-in-progress',
        board_rank: '0|hzzzzz:',
      };
      queryClient.setQueryData(qk.issues('KAN', {}), [issueItem]);
      queryClient.setQueryData(qk.issues('KAN-OTHER', {}), [issueItem]);
      queryClient.setQueryData(qk.issue('KAN-8'), {
        key: 'KAN-8',
        state: { id: 'state-1', name: 'Original', group: 'started' },
      });

      const payload: WorkflowGateEventPayload = {
        issue_key: 'KAN-8',
        execution_id: 'exec-unk',
        hook_name: 'unknown',
      };

      // With projectKey filter
      handleGateEvent('workflow.gate.unrecognized', payload, queryClient, { projectKey: 'KAN' });
      // Without projectKey filter
      handleGateEvent('workflow.gate.unrecognized', payload, queryClient);

      const cache = queryClient.getQueryData<BoardIssue[]>(qk.issues('KAN', {}));
      expect(cache?.[0]?.state_id).toBe('state-in-progress');
    });

    it('covers optional state and timestamp branches when updating issue details', () => {
      const initialDetail: IssueDetail = {
        key: 'KAN-8',
        project_key: 'KAN',
        summary: 'Task',
        state: { id: 's-original', name: 'Original', group: 'started' },
      };
      const boardIssue: BoardIssue = {
        id: 'issue-1',
        key: 'KAN-8',
        summary: 'Task',
        state_id: 's-original',
        board_rank: '0|hzzzzz:',
      };
      queryClient.setQueryData(qk.issues('KAN', {}), [boardIssue]);
      queryClient.setQueryData(qk.issue('KAN-8'), initialDetail);

      // 1. Pending without to_state
      handleGateEvent(
        'workflow.gate.pending',
        {
          issue_key: 'KAN-8',
          execution_id: 'exec-1',
          hook_name: 'hook',
        },
        queryClient,
      );
      let detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.state?.name).toBe('Original');

      // 2. Approved without to_state or to_state_id, with completed_at
      handleGateEvent(
        'workflow.gate.approved',
        {
          issue_key: 'KAN-8',
          execution_id: 'exec-1',
          hook_name: 'hook',
          completed_at: '2026-11-14T01:00:00Z',
        },
        queryClient,
      );
      detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.state?.name).toBe('Original');

      // 3. Rejected without from_state or from_state_id, with completed_at
      handleGateEvent(
        'workflow.gate.rejected',
        {
          issue_key: 'KAN-8',
          execution_id: 'exec-1',
          hook_name: 'hook',
          completed_at: '2026-11-14T01:00:00Z',
        },
        queryClient,
      );
      detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.state?.name).toBe('Original');

      // 4. Cancelled without from_state or from_state_id
      handleGateEvent(
        'workflow.gate.cancelled',
        {
          issue_key: 'KAN-8',
          execution_id: 'exec-1',
          hook_name: 'hook',
        },
        queryClient,
      );
      detail = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-8'));
      expect(detail?.state?.name).toBe('Original');
    });
  });

  describe('useGateRealtimeSync Hook', () => {
    it('subscribes to realtime events and ignores non-gate events', () => {
      let listener: ((evt: { type: string; payload: unknown; id: string }) => void) | null = null;
      const fakeClient = {
        onEvent: vi.fn((cb: (evt: { type: string; payload: unknown; id: string }) => void) => {
          listener = cb;
          return () => {
            listener = null;
          };
        }),
      };

      const onGatePending = vi.fn();
      renderHook(() => {
        useGateRealtimeSync({
          // @ts-expect-error Mock client interface
          client: fakeClient,
          queryClient,
          projectKey: 'KAN',
          onGatePending,
        });
      });

      expect(fakeClient.onEvent).toHaveBeenCalled();

      // Non-gate event ignored
      act(() => {
        listener?.({ id: 'evt-0', type: 'issue.updated', payload: { key: 'KAN-8' } });
      });
      expect(onGatePending).not.toHaveBeenCalled();

      // Gate event processed
      act(() => {
        listener?.({
          id: 'evt-1',
          type: 'workflow.gate.pending',
          payload: {
            issue_key: 'KAN-8',
            execution_id: 'exec-1',
            hook_name: 'sec',
          },
        });
      });
      expect(onGatePending).toHaveBeenCalledTimes(1);

      // Duplicate event with same dedupeKey is ignored
      act(() => {
        listener?.({
          id: 'evt-1',
          type: 'workflow.gate.pending',
          payload: {
            issue_key: 'KAN-8',
            execution_id: 'exec-1',
            hook_name: 'sec',
          },
        });
      });
      expect(onGatePending).toHaveBeenCalledTimes(1);

      // Over 1000 events clears deduplication cache safely
      for (let i = 0; i <= 1005; i++) {
        act(() => {
          listener?.({
            id: `evt-bulk-${String(i)}`,
            type: 'workflow.gate.pending',
            payload: {
              issue_key: 'KAN-8',
              execution_id: `exec-bulk-${String(i)}`,
              hook_name: 'sec',
            },
          });
        });
      }
      expect(onGatePending).toHaveBeenCalledTimes(1007);
    });

    it('dispatches all gate callbacks (approved, vetoed, cancelled) from realtime events', () => {
      let listener: ((evt: { type: string; payload: unknown; id: string }) => void) | null = null;
      const fakeClient = {
        onEvent: vi.fn((cb: (evt: { type: string; payload: unknown; id: string }) => void) => {
          listener = cb;
          return () => {
            listener = null;
          };
        }),
      };

      const onGateApproved = vi.fn();
      const onGateVetoed = vi.fn();
      const onGateCancelled = vi.fn();
      const onToast = vi.fn();

      renderHook(() => {
        useGateRealtimeSync({
          // @ts-expect-error Mock client interface
          client: fakeClient,
          queryClient,
          projectKey: 'KAN',
          onGateApproved,
          onGateVetoed,
          onGateCancelled,
          onToast,
        });
      });

      act(() => {
        listener?.({
          id: 'evt-approved-1',
          type: 'workflow.gate.approved',
          payload: {
            issue_key: 'KAN-8',
            execution_id: 'exec-app-1',
            hook_name: 'test-hook',
          },
        });
      });
      expect(onGateApproved).toHaveBeenCalled();

      act(() => {
        listener?.({
          id: 'evt-vetoed-1',
          type: 'workflow.gate.rejected',
          payload: {
            issue_key: 'KAN-8',
            execution_id: 'exec-vet-1',
            hook_name: 'test-hook',
            reason_preview: 'vetoed',
          },
        });
      });
      expect(onGateVetoed).toHaveBeenCalled();

      act(() => {
        listener?.({
          id: 'evt-cancelled-1',
          type: 'workflow.gate.cancelled',
          payload: {
            issue_key: 'KAN-8',
            execution_id: 'exec-can-1',
            hook_name: 'test-hook',
            reason: 'STALE_SNAPSHOT',
          },
        });
      });
      expect(onGateCancelled).toHaveBeenCalled();
      expect(onToast).toHaveBeenCalledWith(
        'Transition cancelled (ticket changed while gate was running)',
      );
    });

    it('returns early when client is undefined', () => {
      const { result } = renderHook(() => {
        useGateRealtimeSync({
          client: undefined,
          queryClient,
        });
      });
      expect(result.current).toBeUndefined();
    });
  });

  describe('cancelGateTransitionApi', () => {
    it('calls DELETE /api/v1/transitions/{execution_id}', async () => {
      const apiFetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({});
      await cancelGateTransitionApi('exec-abc');

      expect(apiFetchSpy).toHaveBeenCalledWith(
        'DELETE',
        '/api/v1/transitions/{execution_id}',
        expect.objectContaining({
          params: { execution_id: 'exec-abc' },
        }),
      );
    });
  });
});
