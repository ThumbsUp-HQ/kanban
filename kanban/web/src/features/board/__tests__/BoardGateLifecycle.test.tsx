// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type ReactNode } from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BoardView } from '../BoardView';
import { BoardColumn } from '../BoardColumn';
import * as boardApiModule from '../boardApi';
import type { BoardIssue, BoardWorkflowState } from '../boardApi';
import type { RealtimeClient, RealtimeEvent, RealtimeEventHandler } from '../../../api/realtime';
import { QuickCreateIssueModal } from '../../views/QuickCreateIssueModal';
import { StatePriorityRows } from '../../drawer-rail/StatePriorityRows';
import { handleGateEvent } from '../../gates/useGateRealtimeSync';
import { qk } from '../../../api/queryKeys';
import type { IssueDetail } from '../../drawer/slots';
import { IssuesWorkspaceRoute } from '../../views/viewRegistry';
import { RealtimeProvider } from '../../../realtime/context';

const mockStates: BoardWorkflowState[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
  { id: 'st-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
  { id: 'st-progress', name: 'In Progress', group: 'started', sort_order: 3, wip_soft_limit: 5 },
  { id: 'st-done', name: 'Done', group: 'completed', sort_order: 4 },
];

function createMockRealtime(): {
  client: RealtimeClient;
  emit: (event: RealtimeEvent) => void;
} {
  const handlers = new Set<RealtimeEventHandler>();
  const client = {
    state: 'open' as const,
    connect: vi.fn(),
    close: vi.fn(),
    onStateChange: vi.fn(() => () => {
      /* no-op */
    }),
    subscribe: vi.fn((_channel: string, handler: RealtimeEventHandler) => {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    }),
    onEvent: vi.fn((handler: RealtimeEventHandler) => {
      handlers.add(handler);
      return () => {
        handlers.delete(handler);
      };
    }),
    setSession: vi.fn(),
  } as unknown as RealtimeClient;

  return {
    client,
    emit: (event: RealtimeEvent) => {
      handlers.forEach((h) => { h(event); });
    },
  };
}

function renderWithClient(ui: ReactNode, customClient?: QueryClient) {
  const client =
    customClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  return {
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
    queryClient: client,
  };
}

describe('BoardGateLifecycle & Lane Default Integration (KAN-432)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      value: 900,
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
        bottom: 900,
        right: 324,
        width: 324,
        height: 900,
        x: 0,
        y: 0,
        toJSON: () => null,
      }),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Positive Gate Case: HTTP 202 Accepted renders ⏳🤖 pending indicator and transitions cleanly to Done on WebSocket approved event', async () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-progress',
      board_rank: '01',
      rebalance_scheduled: false,
      gate_status: 'pending',
      execution_id: 'exec-101',
      hook_name: 'Security Gate',
      from_state_id: null, // triggers fallback to previousIssues.find
      to_state_id: 'st-done',
      status_code: 202,
    });

    const initialIssues: BoardIssue[] = [
      {
        id: 'i1',
        key: 'KAN-1',
        summary: 'Sliding window rate limiter',
        state_id: 'st-progress',
        board_rank: '01',
      },
      {
        id: 'i99',
        key: 'KAN-99',
        summary: 'Unrelated background task',
        state_id: 'st-todo',
        board_rank: '00',
      },
    ];

    const testClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    testClient.setQueryData(qk.issue('KAN-1'), {
      key: 'KAN-1',
      summary: 'Sliding window rate limiter',
      state: { id: 'st-progress', name: 'In Progress' },
    });
    testClient.setQueryData(qk.issues('KAN', {}), initialIssues);

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={initialIssues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
      testClient,
    );

    const card = screen.getByTestId('board-card-KAN-1');
    expect(card).toBeDefined();

    // Trigger keyboard move towards st-done (alt + ArrowRight)
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(1);
    });

    // 1. Pending Gate Hold: card should have data-gate-pending="true" and render pending gate indicator
    await waitFor(() => {
      const updatedCard = screen.getByTestId('board-card-KAN-1');
      expect(updatedCard.getAttribute('data-gate-pending')).toBe('true');
    });

    const pendingPill = screen.getByTestId('gate-pending-KAN-1');
    expect(pendingPill).toBeDefined();

    // 2. Gate Resolution: Emit live WebSocket approved event
    act(() => {
      emit({
        id: 'evt-approved-1',
        type: 'workflow.gate.approved',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-1',
          execution_id: 'exec-101',
          hook_name: 'Security Gate',
          to_state_id: 'st-done',
          to_state: 'Done',
          completed_at: new Date().toISOString(),
          latency_ms: 120,
          verdict_sha256: 'abc123sha',
        },
      });
    });

    // Card should now be finalized in Done without pending gate
    await waitFor(() => {
      const doneCol = screen.getByTestId('board-column-st-done');
      expect(doneCol.querySelector('[data-testid="board-card-KAN-1"]')).not.toBeNull();
      const approvedPill = screen.getByTestId('gate-approved-KAN-1');
      expect(approvedPill).toBeDefined();
    });
  });

  it('Negative Veto Snap-Back Case: WebSocket vetoed/rejected event snaps card back to In Progress with 🛑🤖 feedback without page reload', async () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-2',
      state_id: 'st-progress',
      board_rank: '02',
      rebalance_scheduled: false,
      gate_status: 'pending',
      execution_id: 'exec-202',
      hook_name: 'Security Gate',
      from_state_id: 'st-progress',
      to_state_id: 'st-done',
      status_code: 202,
    });

    const initialIssues: BoardIssue[] = [
      {
        id: 'i2',
        key: 'KAN-2',
        summary: 'Authentication bypass audit',
        state_id: 'st-progress',
        board_rank: '02',
      },
      {
        id: 'i98',
        key: 'KAN-98',
        summary: 'Another issue',
        state_id: 'st-todo',
        board_rank: '00',
      },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={initialIssues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-2');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    await waitFor(() => {
      const updatedCard = screen.getByTestId('board-card-KAN-2');
      expect(updatedCard.getAttribute('data-gate-pending')).toBe('true');
    });

    // Live WebSocket veto event arrives from GateWorker
    act(() => {
      emit({
        id: 'evt-vetoed-2',
        type: 'workflow.gate.vetoed',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-2',
          execution_id: 'exec-202',
          hook_name: 'Security Gate',
          agent_slug: 'security-agent',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
          reason_preview: 'Critical SAST vulnerability detected in diff',
          completed_at: new Date().toISOString(),
        },
      });
    });

    // Automatic Veto Snap-Back: Card snaps back to st-progress column with 🛑🤖 feedback
    await waitFor(() => {
      const progressCol = screen.getByTestId('board-column-st-progress');
      expect(progressCol.querySelector('[data-testid="board-card-KAN-2"]')).not.toBeNull();
      const vetoedPill = screen.getByTestId('gate-vetoed-KAN-2');
      expect(vetoedPill).toBeDefined();
    });
  });

  it('Live WebSocket gate.pending event updates board issue when received asynchronously', async () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    const initialIssues: BoardIssue[] = [
      {
        id: 'i5',
        key: 'KAN-5',
        summary: 'Async gate testing',
        state_id: 'st-progress',
        board_rank: '05',
      },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={initialIssues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
    );

    // Emit live gate.pending event
    act(() => {
      emit({
        id: 'evt-pending-5',
        type: 'workflow.gate.pending',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-5',
          execution_id: 'exec-505',
          hook_name: 'Code Review Gate',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
          started_at: new Date().toISOString(),
        },
      });
    });

    await waitFor(() => {
      const card = screen.getByTestId('board-card-KAN-5');
      expect(card.getAttribute('data-gate-pending')).toBe('true');
    });
  });

  it('Issue Detail View Gate Veto: Realtime sync clears Gate Pending and updates to Gate Vetoed without reload', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const initialDetail: IssueDetail = {
      key: 'KAN-3',
      project_key: 'KAN',
      summary: 'Strict lone-surrogate sanitizer',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
      pending_gate: {
        execution_id: 'exec-303',
        hook_name: 'Reality Checker QA Gate',
        agent_slug: 'reality-checker',
        harness_label: 'cli: agy -p',
        started_at: new Date().toISOString(),
        from_state_id: 'st-progress',
        to_state_id: 'st-done',
      },
    };

    queryClient.setQueryData(qk.issue('KAN-3'), initialDetail);

    // Exercise handleGateEvent with items container structure and non-array fallback
    queryClient.setQueryData(['issues', 'KAN', 'filter'], { items: [initialDetail] });
    queryClient.setQueryData(['issues', 'KAN', 'primitive'], 'invalid-raw-string');

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <StatePriorityRows
          issue={initialDetail}
          projectStates={mockStates}
          canEdit={true}
          canTransition={true}
          onStateChange={vi.fn()}
          onPriorityChange={vi.fn()}
        />
      </QueryClientProvider>,
    );

    // Initial state: drawer-gate-pending is visible
    expect(screen.getByTestId('drawer-gate-pending')).toBeDefined();
    expect(screen.queryByTestId('drawer-gate-vetoed')).toBeNull();

    // Fire realtime veto event via handleGateEvent
    act(() => {
      handleGateEvent(
        'workflow.gate.rejected',
        {
          issue_key: 'KAN-3',
          execution_id: 'exec-303',
          hook_name: 'Reality Checker QA Gate',
          agent_slug: 'reality-checker',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
          reason_preview: 'Unit test coverage dropped below 95%',
          completed_at: new Date().toISOString(),
        },
        queryClient,
        { projectKey: 'KAN' },
      );
    });

    // Query cache updated; render with updated data
    const updatedIssue = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-3'));
    expect(updatedIssue?.pending_gate).toBeNull();
    expect(updatedIssue?.latest_gate_verdict?.decision).toBe('reject');
    if (!updatedIssue) {
      throw new Error('Expected updatedIssue to be defined');
    }

    rerender(
      <QueryClientProvider client={queryClient}>
        <StatePriorityRows
          issue={updatedIssue}
          projectStates={mockStates}
          canEdit={true}
          canTransition={true}
          onStateChange={vi.fn()}
          onPriorityChange={vi.fn()}
        />
      </QueryClientProvider>,
    );

    // Gate Pending cleared, Gate Vetoed (🛑🤖) rendered
    expect(screen.queryByTestId('drawer-gate-pending')).toBeNull();
    expect(screen.getByTestId('drawer-gate-vetoed')).toBeDefined();
  });

  it('Lane State Default: Clicking + New work item in In Progress passes column state.id and initializes modal State selector', () => {
    const handleNewItem = vi.fn();
    const progressState = mockStates[2];
    if (!progressState) {
      throw new Error('Expected progressState to be defined');
    }

    render(
      <BoardColumn
        state={progressState}
        issues={[]}
        projectKey="KAN"
        onNewItem={handleNewItem}
      />,
    );

    const newBtn = screen.getByTestId('new-item-st-progress');
    fireEvent.click(newBtn);

    expect(handleNewItem).toHaveBeenCalledTimes(1);
    expect(handleNewItem).toHaveBeenCalledWith('st-progress');

    // Render QuickCreateIssueModal with defaultStateId="st-progress"
    render(
      <QuickCreateIssueModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={vi.fn()}
        projectKey="KAN"
        defaultStateId="st-progress"
        states={mockStates}
      />,
    );

    const select = screen.getByLabelText('State');
    expect((select as HTMLSelectElement).value).toBe('st-progress');
  });

  it('Gate Cancellation: WebSocket cancelled event resets pending state and snaps card back', async () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-4',
      state_id: 'st-progress',
      board_rank: '04',
      rebalance_scheduled: false,
      gate_status: 'pending',
      execution_id: 'exec-404',
      hook_name: 'Security Gate',
      from_state_id: 'st-progress',
      to_state_id: 'st-done',
      status_code: 202,
    });

    const initialIssues: BoardIssue[] = [
      {
        id: 'i4',
        key: 'KAN-4',
        summary: 'Passkey WebAuthn relying party audit',
        state_id: 'st-progress',
        board_rank: '04',
      },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={initialIssues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-4');
    fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

    await waitFor(() => {
      const updatedCard = screen.getByTestId('board-card-KAN-4');
      expect(updatedCard.getAttribute('data-gate-pending')).toBe('true');
    });

    // Emit live WebSocket cancelled event (e.g. stale snapshot cancellation)
    act(() => {
      emit({
        id: 'evt-cancel-4',
        type: 'workflow.gate.cancelled',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-4',
          execution_id: 'exec-404',
          hook_name: 'Security Gate',
          from_state_id: 'st-progress',
          reason: 'STALE_SNAPSHOT',
        },
      });
    });

    await waitFor(() => {
      const progressCol = screen.getByTestId('board-column-st-progress');
      expect(progressCol.querySelector('[data-testid="board-card-KAN-4"]')).not.toBeNull();
      const updatedCard = screen.getByTestId('board-card-KAN-4');
      expect(updatedCard.getAttribute('data-gate-pending')).toBeNull();
    });
  });

  it('handles gate cancelled fallback branches in handleGateEvent without from_state and with null activity', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const issueDetail: IssueDetail = {
      key: 'KAN-FALLBACK',
      project_key: 'KAN',
      summary: 'Fallback test issue',
      state: { id: 'st-todo', name: 'To Do', group: 'unstarted' },
    };

    queryClient.setQueryData(qk.issue('KAN-FALLBACK'), issueDetail);
    queryClient.setQueryData(['activity', 'KAN-FALLBACK'], null);

    handleGateEvent(
      'workflow.gate.cancelled',
      {
        issue_key: 'KAN-FALLBACK',
        execution_id: 'exec-fb',
        hook_name: 'Hook',
        from_state_id: undefined,
        from_state: undefined,
        reason: 'STALE_SNAPSHOT',
      },
      queryClient,
    );

    const updated = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-FALLBACK'));
    expect(updated?.pending_gate).toBeNull();
    expect(updated?.gate_status).toBeNull();
  });

  it('handles onGateVetoed and onGateCancelled when card element is not in DOM', () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    const initialIssues: BoardIssue[] = [
      {
        id: 'i-absent',
        key: 'KAN-ABSENT',
        summary: 'Card will not be in DOM query',
        state_id: 'st-progress',
        board_rank: '09',
      },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={initialIssues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
    );

    // Emit veto for a non-existent card key
    act(() => {
      emit({
        id: 'evt-vetoed-absent',
        type: 'workflow.gate.vetoed',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-NONEXISTENT',
          execution_id: 'exec-absent',
          hook_name: 'Hook',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
        },
      });
    });

    // Emit cancel for non-existent card key
    act(() => {
      emit({
        id: 'evt-cancel-absent',
        type: 'workflow.gate.cancelled',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-NONEXISTENT',
          execution_id: 'exec-absent',
          hook_name: 'Hook',
          from_state_id: 'st-progress',
        },
      });
    });

    // Verify BoardView remains healthy
    expect(screen.getByTestId('board-column-st-progress')).toBeDefined();
  });

  it('covers null query cache and existing activity in handleGateEvent', () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['issues', 'KAN', 'null-test'], null);
    queryClient.setQueryData(['activity', 'KAN-NULL'], {
      items: [
        {
          id: 'activity-existing',
          category: 'AGENT_GATE',
          event_type: 'GATE_APPROVED',
          actor: { type: 'AGENT' },
          created_at: new Date().toISOString(),
          payload: { verdict_sha256: 'matched-hash' },
        },
      ],
    });

    handleGateEvent(
      'workflow.gate.approved',
      {
        issue_key: 'KAN-NULL',
        execution_id: 'exec-n',
        hook_name: 'Hook',
        verdict_sha256: 'matched-hash',
      },
      queryClient,
      { projectKey: 'KAN' },
    );
  });

  it('covers toast notification and missing query cache', async () => {
    const { client: realtimeClient, emit } = createMockRealtime();

    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-TOAST',
      state_id: 'st-progress',
      board_rank: '01',
      rebalance_scheduled: false,
      gate_status: 'pending',
      execution_id: 'exec-toast',
      hook_name: 'Security Gate',
      to_state_id: 'st-done',
      status_code: 202,
    });

    const issues: BoardIssue[] = [
      { id: 'it', key: 'KAN-TOAST', summary: 'Toast item', state_id: 'st-progress', board_rank: '01' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['ADMIN']}
        realtimeClient={realtimeClient}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-TOAST');
    act(() => {
      fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });
    });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledTimes(1);
    });

    // Emit cancelled event with STALE_SNAPSHOT to trigger toast
    act(() => {
      emit({
        id: 'evt-toast',
        type: 'workflow.gate.cancelled',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-TOAST',
          execution_id: 'exec-toast',
          hook_name: 'Security Gate',
          reason: 'STALE_SNAPSHOT',
        },
      });
    });

    expect(screen.getByRole('alert')).toBeDefined();
  });

  it('covers minimal 202 response fallbacks in BoardView', async () => {
    const moveSpy = vi.spyOn(boardApiModule, 'moveIssueApi').mockResolvedValue({
      issue_key: 'KAN-MIN',
      state_id: 'st-progress',
      board_rank: '01',
      rebalance_scheduled: false,
      status_code: 202,
      // execution_id, hook_name, from_state_id, to_state_id omitted
    });

    const issues: BoardIssue[] = [
      { id: 'imin', key: 'KAN-MIN', summary: 'Minimal 202', state_id: 'st-progress', board_rank: '01' },
      { id: 'imin2', key: 'KAN-OTHER2', summary: 'Other 2', state_id: 'st-todo', board_rank: '02' },
    ];

    renderWithClient(
      <BoardView
        projectKey="KAN"
        states={mockStates}
        issues={issues}
        currentUserCapabilities={['ADMIN']}
      />,
    );

    const card = screen.getByTestId('board-card-KAN-MIN');
    act(() => {
      fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });
    });

    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalled();
    });

    const updatedCard = screen.getByTestId('board-card-KAN-MIN');
    expect(updatedCard.getAttribute('data-gate-pending')).toBe('true');
  });

  it('covers partial state fallbacks in veto and cancel handleGateEvent', () => {
    const queryClient = new QueryClient();

    // 1. Veto with only from_state_id
    const issue1: IssueDetail = {
      key: 'KAN-PARTIAL1',
      project_key: 'KAN',
      summary: 'Partial state issue 1',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
    };
    queryClient.setQueryData(qk.issue('KAN-PARTIAL1'), issue1);

    handleGateEvent(
      'workflow.gate.rejected',
      {
        issue_key: 'KAN-PARTIAL1',
        execution_id: 'exec-p1',
        hook_name: 'Hook',
        from_state_id: 'st-progress',
        from_state: undefined,
      },
      queryClient,
    );

    const res1 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL1'));
    expect(res1?.state?.id).toBe('st-progress');

    // 2. Veto with only from_state
    const issue2: IssueDetail = {
      key: 'KAN-PARTIAL2',
      project_key: 'KAN',
      summary: 'Partial state issue 2',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
    };
    queryClient.setQueryData(qk.issue('KAN-PARTIAL2'), issue2);

    handleGateEvent(
      'workflow.gate.rejected',
      {
        issue_key: 'KAN-PARTIAL2',
        execution_id: 'exec-p2',
        hook_name: 'Hook',
        from_state_id: undefined,
        from_state: 'In Progress',
      },
      queryClient,
    );

    const res2 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL2'));
    expect(res2?.state?.name).toBe('In Progress');

    // 3. Cancel with only from_state
    const issue3: IssueDetail = {
      key: 'KAN-PARTIAL3',
      project_key: 'KAN',
      summary: 'Partial state issue 3',
      state: { id: 'st-done', name: 'Done', group: 'completed' },
    };
    queryClient.setQueryData(qk.issue('KAN-PARTIAL3'), issue3);

    handleGateEvent(
      'workflow.gate.cancelled',
      {
        issue_key: 'KAN-PARTIAL3',
        execution_id: 'exec-p3',
        hook_name: 'Hook',
        from_state_id: undefined,
        from_state: 'In Progress',
      },
      queryClient,
    );

    const res3 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL3'));
    expect(res3?.state?.name).toBe('In Progress');

    // 4. Veto fallback where fromStateName defaults to 'In Progress'
    const issue4 = {
      key: 'KAN-PARTIAL4',
      project_key: 'KAN',
      summary: 'Partial state issue 4',
      state: { id: 'st-done', group: 'completed' },
    } as unknown as IssueDetail;
    queryClient.setQueryData(qk.issue('KAN-PARTIAL4'), issue4);
    handleGateEvent(
      'workflow.gate.rejected',
      {
        issue_key: 'KAN-PARTIAL4',
        execution_id: 'exec-p4',
        hook_name: 'Hook',
        from_state_id: 'st-custom',
      },
      queryClient,
    );
    const res4 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL4'));
    expect(res4?.state?.name).toBe('In Progress');

    // 5. Cancel fallback where fromStateName defaults to 'In Progress'
    const issue5 = {
      key: 'KAN-PARTIAL5',
      project_key: 'KAN',
      summary: 'Partial state issue 5',
      state: { id: 'st-done', group: 'completed' },
    } as unknown as IssueDetail;
    queryClient.setQueryData(qk.issue('KAN-PARTIAL5'), issue5);
    handleGateEvent(
      'workflow.gate.cancelled',
      {
        issue_key: 'KAN-PARTIAL5',
        execution_id: 'exec-p5',
        hook_name: 'Hook',
        from_state_id: 'st-custom',
      },
      queryClient,
    );
    const res5 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL5'));
    expect(res5?.state?.name).toBe('In Progress');

    // 6. Pending fallback where to_state_id is omitted and falls back to oldIssue.state.id
    const issue6 = {
      key: 'KAN-PARTIAL6',
      project_key: 'KAN',
      summary: 'Partial state issue 6',
      state: { id: 'st-fallback-id', name: 'Original', group: 'unstarted' },
    } as unknown as IssueDetail;
    queryClient.setQueryData(qk.issue('KAN-PARTIAL6'), issue6);
    handleGateEvent(
      'workflow.gate.pending',
      {
        issue_key: 'KAN-PARTIAL6',
        execution_id: 'exec-p6',
        hook_name: 'Hook',
        to_state: 'Target State',
        to_state_id: undefined,
      },
      queryClient,
    );
    const res6 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL6'));
    expect(res6?.state?.id).toBe('st-fallback-id');

    // 7. Approved fallback where to_state_id is omitted and falls back to oldIssue.state.id
    const issue7 = {
      key: 'KAN-PARTIAL7',
      project_key: 'KAN',
      summary: 'Partial state issue 7',
      state: { id: 'st-fallback-id-7', name: 'Original', group: 'unstarted' },
    } as unknown as IssueDetail;
    queryClient.setQueryData(qk.issue('KAN-PARTIAL7'), issue7);
    handleGateEvent(
      'workflow.gate.approved',
      {
        issue_key: 'KAN-PARTIAL7',
        execution_id: 'exec-p7',
        hook_name: 'Hook',
        to_state: 'Target State 7',
        to_state_id: undefined,
      },
      queryClient,
    );
    const res7 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL7'));
    expect(res7?.state?.id).toBe('st-fallback-id-7');

    // 8. Veto and cancel where fromStateId is undefined and retains oldIssue.state
    const issue8 = {
      key: 'KAN-PARTIAL8',
      project_key: 'KAN',
      summary: 'Partial state issue 8',
      state: { id: 'st-keep-id', name: 'Keep', group: 'started' },
    } as unknown as IssueDetail;
    queryClient.setQueryData(qk.issue('KAN-PARTIAL8'), issue8);
    handleGateEvent(
      'workflow.gate.rejected',
      {
        issue_key: 'KAN-PARTIAL8',
        execution_id: 'exec-p8',
        hook_name: 'Hook',
        from_state_id: undefined,
      },
      queryClient,
    );
    const res8 = queryClient.getQueryData<IssueDetail>(qk.issue('KAN-PARTIAL8'));
    expect(res8?.state?.id).toBe('st-keep-id');
  });

  it('loads states from project query when states prop is omitted', () => {
    const testClient = new QueryClient();
    testClient.setQueryData(qk.project('KAN-FETCH'), {
      id: 'proj-1',
      object_id: 'obj-1',
      states: mockStates,
    });

    renderWithClient(
      <BoardView projectKey="KAN-FETCH" issues={[]} />,
      testClient,
    );

    expect(screen.getByTestId('board-column-st-progress')).toBeDefined();
  });

  it('mounts IssuesWorkspaceRoute without realtimeClient prop, receives live RealtimeProvider context, holds ⏳🤖 and veto snaps back to In Progress', async () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=board');
    const mockRt = createMockRealtime();
    const testClient = new QueryClient();

    testClient.setQueryData(['states', 'KAN'], mockStates);
    testClient.setQueryData(qk.project('KAN'), {
      id: 'proj-kan',
      key: 'KAN',
      name: 'Core Project',
      states: mockStates,
    });

    const routeIssues = [
      {
        id: 'iss-route-1',
        key: 'KAN-432-RT',
        project_key: 'KAN',
        summary: 'Routed Board Gate Issue',
        state_id: 'st-progress',
        state: { id: 'st-progress', name: 'In Progress', group: 'started' },
        priority: { slug: 'high', label: 'High' },
        board_rank: '000001',
      },
    ];

    act(() => {
      render(
        <QueryClientProvider client={testClient}>
          <RealtimeProvider client={mockRt.client} autoConnect={false} bindInvalidation={false}>
            <IssuesWorkspaceRoute
              projectKey="KAN"
              modulesEnabled={false}
              initialIssues={routeIssues as never}
              queryClient={testClient}
            />
          </RealtimeProvider>
        </QueryClientProvider>,
      );
    });

    // Initial render in In Progress lane
    expect(screen.getByTestId('board-card-KAN-432-RT')).toBeDefined();
    const progressCol = screen.getByTestId('board-column-st-progress');
    expect(progressCol.contains(screen.getByTestId('board-card-KAN-432-RT'))).toBe(true);

    // 1. Live WebSocket pending gate event
    act(() => {
      mockRt.emit({
        id: 'evt-pending-route',
        type: 'workflow.gate.pending',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-432-RT',
          execution_id: 'exec-route-1',
          hook_name: 'Security Gatekeeper',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
        },
      });
    });

    expect(screen.getByTestId('gate-pending-KAN-432-RT')).toBeDefined();

    // 2. Live WebSocket veto/rejection event
    act(() => {
      mockRt.emit({
        id: 'evt-rejected-route',
        type: 'workflow.gate.rejected',
        channel: 'project:KAN',
        payload: {
          issue_key: 'KAN-432-RT',
          execution_id: 'exec-route-1',
          hook_name: 'Security Gatekeeper',
          from_state_id: 'st-progress',
          to_state_id: 'st-done',
          reason_preview: 'Automated test suite gate rejected',
        },
      });
    });

    // Card automatically returned/snapped back to In Progress column with veto feedback
    await waitFor(() => {
      const col = screen.getByTestId('board-column-st-progress');
      expect(col.contains(screen.getByTestId('board-card-KAN-432-RT'))).toBe(true);
      expect(screen.getByTestId('gate-vetoed-KAN-432-RT')).toBeDefined();
    });
  });
});
