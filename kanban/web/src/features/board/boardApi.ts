/**
 * Board API client and cache manipulation functions (KB-P3-37, KB-P3-12, S6.4).
 */

import { apiFetch } from '../../api/client.ts';
import type { PendingGateInfo, LatestGateVerdict } from '../gates/types.ts';

export interface BoardPriority {
  id: string;
  label: string;
  slug: string;
  color_hex?: string;
}

export interface BoardAssignee {
  id: string;
  name?: string;
  display_name?: string;
  handle?: string;
  is_agent?: boolean;
  free_text?: string;
}

export interface BoardCycle {
  id: string;
  name: string;
}

export interface BoardIssueState {
  id: string;
  name: string;
  group: StateGroup;
  color_hex?: string | null | undefined;
  slug?: string | undefined;
}

export interface BoardIssue {
  id: string;
  key: string;
  project_key?: string | null | undefined;
  summary: string;
  state_id: string;
  state?: BoardIssueState | undefined;
  priority?: BoardPriority | null | undefined;
  board_rank: string;
  assignees?: BoardAssignee[] | undefined;
  cycle?: BoardCycle | null | undefined;
  due_date?: string | null | undefined;
  gate_status?: 'pending' | 'rejected' | 'approved' | null | undefined;
  pending_gate?: PendingGateInfo | null | undefined;
  latest_gate_verdict?: LatestGateVerdict | null | undefined;
  has_explicit_acl?: boolean | undefined;
  [key: string]: unknown;
}

export type StateGroup = 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';

export interface BoardWorkflowState {
  id: string;
  name: string;
  slug?: string;
  group: StateGroup;
  sort_order: number;
  wip_soft_limit?: number | null;
  wip_hard_limit?: number | null;
  color_hex?: string | null;
}

export interface IssueMoveParams {
  projectKey: string;
  issueKey: string;
  targetStateId?: string;
  afterIssueKey?: string | null;
  beforeIssueKey?: string | null;
  boardRank?: string;
  wipOverrideReason?: string;
  overrideWip?: boolean;
}

export interface IssueMoveResponse {
  issue_key: string;
  state_id: string;
  board_rank: string;
  rebalance_scheduled: boolean;
  wip_warning?: {
    soft_limit: number;
    resulting_count: number;
  } | null;
}

/**
 * Dispatch POST /api/v1/issues/{issue_ref}/move (KB-P3-12).
 */
export async function moveIssueApi(params: IssueMoveParams): Promise<IssueMoveResponse> {
  const body: Record<string, unknown> = {
    override_wip: params.overrideWip ?? false,
  };
  if (params.targetStateId) {
    body.target_state_id = params.targetStateId;
  }
  if (params.afterIssueKey) {
    body.after_issue = params.afterIssueKey;
  }
  if (params.beforeIssueKey) {
    body.before_issue = params.beforeIssueKey;
  }
  if (params.wipOverrideReason) {
    body.wip_override_reason = params.wipOverrideReason;
  }

  const rawFetch = apiFetch as unknown as (
    method: string,
    path: string,
    options: unknown,
  ) => Promise<IssueMoveResponse>;

  return rawFetch('POST', '/api/v1/issues/{issue_ref}/move', {
    params: { issue_ref: params.issueKey },
    body,
  });
}

export interface AvailableStateRef {
  id: string;
  name?: string | undefined;
  group?: string | undefined;
  color_hex?: string | null | undefined;
}

/**
 * Synchronous 1-row cache updater.
 * Replaces strictly the moved issue object reference in the array or items envelope.
 * Preserves all existing IssueSummary / IssueItem fields (...item) and updates state_id and state.
 * Completes well under the < 12ms budget even on 500+ items.
 */
export function applyOptimisticMove<
  T extends {
    key: string;
    state_id?: string | undefined;
    state?: { id?: string | undefined; name?: string | undefined; group?: string | undefined; color_hex?: string | null | undefined } | undefined;
    board_rank?: string | undefined;
    [key: string]: unknown;
  },
>(
  cache: T[] | undefined,
  params: IssueMoveParams,
  availableStates?: AvailableStateRef[],
): T[];
export function applyOptimisticMove<
  T extends {
    key: string;
    state_id?: string | undefined;
    state?: { id?: string | undefined; name?: string | undefined; group?: string | undefined; color_hex?: string | null | undefined } | undefined;
    board_rank?: string | undefined;
    [key: string]: unknown;
  },
>(
  cache: { items: T[] } | undefined,
  params: IssueMoveParams,
  availableStates?: AvailableStateRef[],
): { items: T[] };
export function applyOptimisticMove<
  T extends {
    key: string;
    state_id?: string | undefined;
    state?: { id?: string | undefined; name?: string | undefined; group?: string | undefined; color_hex?: string | null | undefined } | undefined;
    board_rank?: string | undefined;
    [key: string]: unknown;
  },
>(
  cache: T[] | { items: T[] } | undefined,
  params: IssueMoveParams,
  availableStates?: AvailableStateRef[],
): T[] | { items: T[] } {
  if (!cache) {
    return [];
  }

  const isObjectEnvelope =
    !Array.isArray(cache) &&
    typeof cache === 'object' &&
    'items' in cache &&
    Array.isArray(cache.items);

  const items: T[] = isObjectEnvelope
    ? cache.items
    : Array.isArray(cache)
      ? cache
      : [];

  if (items.length === 0) {
    return isObjectEnvelope ? { ...cache, items: [] } : [];
  }

  const target = items.find((item) => item.key === params.issueKey);
  if (!target) {
    return cache;
  }

  const targetState =
    params.targetStateId && availableStates
      ? availableStates.find((s) => s.id === params.targetStateId)
      : undefined;

  const targetStateId = params.targetStateId ?? target.state_id ?? target.state?.id;

  let updatedState = target.state;
  if (params.targetStateId !== undefined) {
    const rawTargetState = target.state as { name?: string | undefined; group?: string | undefined; color_hex?: string | null | undefined } | undefined;
    updatedState = {
      ...(rawTargetState ?? {}),
      id: params.targetStateId,
      name: targetState?.name ?? rawTargetState?.name ?? '',
      group: targetState?.group ?? rawTargetState?.group ?? 'unstarted',
      color_hex: targetState?.color_hex ?? rawTargetState?.color_hex ?? null,
    };
  }

  const updated: T = {
    ...target,
    ...(targetStateId !== undefined ? { state_id: targetStateId } : {}),
    ...(params.boardRank !== undefined ? { board_rank: params.boardRank } : {}),
    ...(updatedState !== undefined ? { state: updatedState } : {}),
  };

  const updatedItems = items.map((item) => (item.key === params.issueKey ? updated : item));

  if (isObjectEnvelope) {
    return {
      ...cache,
      items: updatedItems,
    };
  }

  return updatedItems;
}
