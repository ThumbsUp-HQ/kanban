// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';

export type HookKind = 'sync_validator' | 'sync_mutator' | 'agent_interceptor';
export type FailurePolicy = 'fail_closed' | 'fail_open_warn';
export type HarnessKind = 'in_app_sdk' | 'cli_pipe' | 'remote_runner';
export type StepResultKind = 'allowed' | 'mutated' | 'rejected' | 'error' | 'skipped_async';

export const MUTABLE_FIELD_UNIVERSE = [
  'labels',
  'priority',
  'assignees',
  'start_date',
  'due_date',
  'cycle',
  'custom_fields.risk_rating',
  'custom_fields.qa_status',
  'custom_fields.security_review',
] as const;

export const IMMUTABLE_FIELDS_NOTICE =
  'summary, description_markdown, state, parent, and created_by are immutable to preserve zero-TOCTOU guarantees.';

export interface WorkflowHook {
  id: string;
  name: string;
  from_state: string | null;
  to_state: string;
  hook_kind: HookKind;
  sort_rank: string;
  failure_policy: FailurePolicy;
  manifest_sha256: string;
  is_enabled: boolean;
  description?: string | undefined;
  wasm_module_sha256?: string | undefined;
  wasm_module_name?: string | undefined;
  target_latency_budget?: string | undefined;
  agent_slug?: string | undefined;
  agent_display_name?: string | undefined;
  harness_kind?: HarnessKind | undefined;
  provider_kind?: string | undefined;
  model_id?: string | undefined;
  cli_binary_allowlist_id?: string | undefined;
  cli_args?: string[] | undefined;
  timeout_ms?: number | undefined;
  repo_binding_slug?: string | undefined;
  repo_access_mode?: string | undefined;
  mcp_access_summary?: string | undefined;
  allowed_mutable_fields?: string[] | undefined;
}

export interface TransitionRule {
  from_state: string | null;
  to_state: string;
  active_hook_count: number;
  hooks: WorkflowHook[];
}

export interface CreateWorkflowHookPayload {
  name: string;
  from_state: string | null;
  to_state: string;
  hook_kind: HookKind;
  failure_policy: FailurePolicy;
  wasm_module_sha256?: string | undefined;
  agent?: string | undefined;
  allowed_mutable_fields?: string[] | undefined;
  timeout_ms?: number | undefined;
  description?: string | undefined;
}

export interface UpdateWorkflowHookPayload {
  name?: string | undefined;
  failure_policy?: FailurePolicy | undefined;
  allowed_mutable_fields?: string[] | undefined;
  wasm_module_sha256?: string | undefined;
  agent?: string | undefined;
  timeout_ms?: number | undefined;
}

export interface ReorderHooksPayload {
  transition: {
    from_state: string | null;
    to_state: string;
  };
  ordered_hook_ids: string[];
}

export interface DryRunSampleTicket {
  summary: string;
  description_markdown: string;
  priority: string;
  labels: string[];
}

export interface DryRunPayload {
  from_state: string | null;
  to_state: string;
  issue_key?: string | undefined;
  sample_ticket?: DryRunSampleTicket | undefined;
}

export interface DryRunStepResult {
  order: number;
  name: string;
  hook_kind: HookKind;
  result: StepResultKind;
  reason?: string | undefined;
  field_updates?: Record<string, unknown> | undefined;
  duration_us: number;
  cli_command?: string | undefined;
}

export interface DryRunResponse {
  steps: DryRunStepResult[];
  would_commit: boolean;
}

export interface AgentDefinitionSummary {
  id: string;
  slug: string;
  display_name: string;
  harness_kind: HarnessKind;
  provider_kind?: string | undefined;
  model_id?: string | undefined;
  cli_binary_allowlist_id?: string | undefined;
  cli_args: string[];
  remote_runner_pool_slug?: string | undefined;
  repo_access_mode: string;
  timeout_ms: number;
}

export interface WasmModuleSummary {
  sha256: string;
  name: string;
  description?: string | undefined;
  target_latency_budget?: string | undefined;
}

export interface RepoBindingSummary {
  id: string;
  slug: string;
  remote_url: string;
  access_mode: string;
}

export interface ProjectStateSummary {
  id: string;
  name: string;
}

// Fallback/Default Approved Wasm modules (KB-P5-13 Tier A)
export const DEFAULT_WASM_MODULES: WasmModuleSummary[] = [
  {
    sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    name: 'qa-proof-validator',
    description: 'Ensures description or comments include docs/qa/ proof bundle',
    target_latency_budget: '<2ms',
  },
  {
    sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
    name: 'security-invariant-validator',
    description: 'Checks zero new dependencies and strict security tokens',
    target_latency_budget: '<25ms',
  },
  {
    sha256: 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e',
    name: 'auto-label-mutator',
    description: 'Mutates labels on transition based on issue type',
    target_latency_budget: '<5ms',
  },
];

// Fallback/Default Project States (S6.3)
export const DEFAULT_PROJECT_STATES: ProjectStateSummary[] = [
  { id: 'state-backlog', name: 'Backlog' },
  { id: 'state-in-progress', name: 'In Progress' },
  { id: 'state-in-review', name: 'In Review' },
  { id: 'state-done', name: 'Done' },
  { id: 'state-cancelled', name: 'Cancelled' },
];

// Default S14.4 Wireframe Mock Rules for immediate initial state
export const DEFAULT_S14_4_RULES: TransitionRule[] = [
  {
    from_state: 'In Review',
    to_state: 'Done',
    active_hook_count: 3,
    hooks: [
      {
        id: 'hook-1',
        name: 'require-qa-proof-link',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        sort_rank: '0000000000000001',
        failure_policy: 'fail_closed',
        manifest_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        is_enabled: true,
        wasm_module_name: 'qa-proof-validator',
        wasm_module_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        target_latency_budget: '<2ms',
        description: 'Ensures description or comments include `docs/qa/KAN-*/` proof bundle before invoking AI.',
      },
      {
        id: 'hook-2',
        name: 'forensic-code-check',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '0000000000000002',
        failure_policy: 'fail_closed',
        manifest_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
        is_enabled: true,
        agent_slug: 'forensic-code-check',
        agent_display_name: 'Forensic Code Check',
        harness_kind: 'cli_pipe',
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        timeout_ms: 60000,
        repo_binding_slug: 'kanban-main',
        repo_access_mode: 'ro_vfs_mount',
        mcp_access_summary: 'Read-Only (KAN)',
        allowed_mutable_fields: ['labels'],
        description: 'Repo: `kanban-main` (:ro mount) | MCP: Read-Only (`KAN`) | Mutable Fields: `[labels]`',
      },
      {
        id: 'hook-3',
        name: 'sec-invariant-scan',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '0000000000000003',
        failure_policy: 'fail_closed',
        manifest_sha256: '7b52009b64fd0a2a49e6d8a939753077792b055425eee527861182c611383145',
        is_enabled: true,
        agent_slug: 'sec-invariant-scan',
        agent_display_name: 'Security Invariant Scanner',
        harness_kind: 'in_app_sdk',
        provider_kind: 'ollama',
        model_id: 'ollama/qwen2.5-coder',
        timeout_ms: 30000,
        repo_binding_slug: 'kanban-main',
        repo_access_mode: 'ro_vfs_mount',
        mcp_access_summary: 'Read-Only (KAN)',
        allowed_mutable_fields: [],
        description: 'Verifies RLS policy tests & zero new unapproved dependencies in `uv.lock` / `pnpm-lock.yaml`.',
      },
    ],
  },
];

export async function fetchWorkflowHooks(projectKey: string): Promise<TransitionRule[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks` as never,
    )) as { rules?: TransitionRule[] } | TransitionRule[];

    if (Array.isArray(data)) {
      return data;
    }
    if ('rules' in data && Array.isArray(data.rules)) {
      return data.rules;
    }
    return DEFAULT_S14_4_RULES;
  } catch (err: unknown) {
    if (err instanceof ApiProblem && (err.status === 404 || err.status === 403)) {
      throw err;
    }
    // Return default wireframe mock rules for preview/offline resilience
    return DEFAULT_S14_4_RULES;
  }
}

export async function createWorkflowHook(
  projectKey: string,
  payload: CreateWorkflowHookPayload,
): Promise<WorkflowHook> {
  const res = (await apiFetch(
    'POST',
    `/api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks` as never,
    { body: payload },
  )) as WorkflowHook;
  return res;
}

export async function updateWorkflowHook(
  hookId: string,
  payload: UpdateWorkflowHookPayload,
): Promise<WorkflowHook> {
  const res = (await apiFetch(
    'PATCH',
    `/api/v1/workflow-hooks/${encodeURIComponent(hookId)}` as never,
    { body: payload },
  )) as WorkflowHook;
  return res;
}

export async function enableWorkflowHook(hookId: string): Promise<void> {
  await apiFetch(
    'POST',
    `/api/v1/workflow-hooks/${encodeURIComponent(hookId)}/enable` as never,
  );
}

export async function disableWorkflowHook(hookId: string): Promise<void> {
  await apiFetch(
    'POST',
    `/api/v1/workflow-hooks/${encodeURIComponent(hookId)}/disable` as never,
  );
}

export async function deleteWorkflowHook(hookId: string): Promise<void> {
  await apiFetch(
    'DELETE',
    `/api/v1/workflow-hooks/${encodeURIComponent(hookId)}` as never,
  );
}

export async function reorderWorkflowHooks(
  projectKey: string,
  payload: ReorderHooksPayload,
): Promise<void> {
  await apiFetch(
    'POST',
    `/api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks/reorder` as never,
    { body: payload },
  );
}

export async function dryRunWorkflowHooks(
  projectKey: string,
  payload: DryRunPayload,
): Promise<DryRunResponse> {
  const res = (await apiFetch(
    'POST',
    `/api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks/dry-run` as never,
    { body: payload },
  )) as DryRunResponse;
  return res;
}

export async function fetchAgentDefinitions(workspace = 'kanban'): Promise<AgentDefinitionSummary[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/workspaces/${encodeURIComponent(workspace)}/agent-definitions` as never,
    )) as AgentDefinitionSummary[];
    return Array.isArray(data) ? data : [];
  } catch {
    return [
      {
        id: 'agent-1',
        slug: 'forensic-code-check',
        display_name: 'Forensic Code Check',
        harness_kind: 'cli_pipe',
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        repo_access_mode: 'ro_vfs_mount',
        timeout_ms: 60000,
      },
      {
        id: 'agent-2',
        slug: 'sec-invariant-scan',
        display_name: 'Security Invariant Scanner',
        harness_kind: 'in_app_sdk',
        provider_kind: 'ollama',
        model_id: 'ollama/qwen2.5-coder',
        cli_args: [],
        repo_access_mode: 'ro_vfs_mount',
        timeout_ms: 30000,
      },
      {
        id: 'agent-3',
        slug: 'codex-readonly-reviewer',
        display_name: 'Codex Read-Only Reviewer',
        harness_kind: 'cli_pipe',
        cli_binary_allowlist_id: 'codex',
        cli_args: ['-p', '-s', 'read-only'],
        repo_access_mode: 'bare_git_tools',
        timeout_ms: 60000,
      },
      {
        id: 'agent-4',
        slug: 'remote-wss-verifier',
        display_name: 'Remote WSS Verifier',
        harness_kind: 'remote_runner',
        remote_runner_pool_slug: 'gpu-pool-1',
        cli_args: [],
        repo_access_mode: 'ro_vfs_mount',
        timeout_ms: 90000,
      },
    ];
  }
}

export async function fetchRepoBindings(projectKey: string): Promise<RepoBindingSummary[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/projects/${encodeURIComponent(projectKey)}/repo-bindings` as never,
    )) as RepoBindingSummary[];
    return Array.isArray(data) ? data : [];
  } catch {
    return [
      {
        id: 'repo-1',
        slug: 'kanban-main',
        remote_url: 'https://github.com/adamoutler/kanban.git',
        access_mode: 'ro_vfs_mount',
      },
    ];
  }
}

export async function fetchProjectStates(projectKey: string): Promise<ProjectStateSummary[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/projects/${encodeURIComponent(projectKey)}/states` as never,
    )) as ProjectStateSummary[];
    return Array.isArray(data) && data.length > 0 ? data : DEFAULT_PROJECT_STATES;
  } catch {
    return DEFAULT_PROJECT_STATES;
  }
}

export function fetchApprovedWasmModules(): Promise<WasmModuleSummary[]> {
  return Promise.resolve(DEFAULT_WASM_MODULES);
}
