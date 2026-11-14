// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

export interface PendingGateInfo {
  execution_id: string;
  hook_name: string;
  agent_slug: string;
  harness_kind?: string | undefined;
  harness_label: string;
  started_at: string;
  deadline_at?: string | undefined;
  repo_mount_ro?: boolean | undefined;
  from_state?: string | undefined;
  to_state?: string | undefined;
  from_state_id?: string | undefined;
  to_state_id?: string | undefined;
  invoking_user_id?: string | undefined;
}

export interface LatestGateVerdict {
  decision: 'approve' | 'reject';
  hook_name: string;
  agent_slug?: string | undefined;
  completed_at?: string | undefined;
  latency_ms?: number | undefined;
  verdict_sha256?: string | undefined;
  reason_preview?: string | undefined;
  audit_comment_id?: string | undefined;
}

export interface GateTransition202Response {
  status: 'pending_agent_gate';
  execution_id: string;
  active_agent: string;
  hook_name: string;
  harness_kind: string;
  harness_label?: string | undefined;
  started_at?: string | undefined;
  repo_mount_ro?: boolean | undefined;
}

export type WorkflowGateEventType =
  | 'workflow.gate.pending'
  | 'workflow.gate.approved'
  | 'workflow.gate.rejected'
  | 'workflow.gate.timed_out'
  | 'workflow.gate.cancelled';

export interface WorkflowGateEventPayload {
  issue_id?: string | undefined;
  issue_key: string;
  execution_id: string;
  hook_name: string;
  agent_slug?: string | undefined;
  harness_kind?: string | undefined;
  harness_label?: string | undefined;
  from_state?: string | undefined;
  from_state_id?: string | undefined;
  to_state?: string | undefined;
  to_state_id?: string | undefined;
  started_at?: string | undefined;
  deadline_at?: string | undefined;
  repo_mount_ro?: boolean | undefined;
  completed_at?: string | undefined;
  latency_ms?: number | undefined;
  verdict_sha256?: string | undefined;
  reason_preview?: string | undefined;
  audit_comment_id?: string | undefined;
  reason?: string | undefined;
  invoking_user_id?: string | undefined;
}

export interface GateActivityItem {
  id: string;
  category: 'AGENT_GATE';
  event_type:
    | 'GATE_APPROVED'
    | 'GATE_REJECTED'
    | 'GATE_VETOED'
    | 'GATE_ABORTED_STALE'
    | 'GATE_FAIL_OPEN_WARN'
    | 'GATE_PENDING';
  actor: {
    type?: string | undefined;
    slug?: string | undefined;
    display_name?: string | undefined;
    handle?: string | undefined;
    redacted?: boolean | undefined;
    label?: string | undefined;
  };
  created_at: string;
  row_hash?: string | undefined;
  payload: {
    hook_name?: string | undefined;
    harness?: string | undefined;
    execution_latency_ms?: number | undefined;
    verdict_sha256?: string | undefined;
    reason?: string | undefined;
    audit_comment_id?: string | undefined;
    repo_mount_ro?: boolean | undefined;
    from_state?: string | undefined;
    to_state?: string | undefined;
    warning_code?: string | undefined;
  };
}
