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
  timeout_ms?: number | null | undefined;
  effective_timeout_ms?: number | undefined;
  repo_binding_slug?: string | null | undefined;
  repo_access_mode?: string | null | undefined;
  mcp_access_summary?: string | undefined;
  allowed_mutable_fields?: string[] | undefined;
  last_execution_log?: string | undefined;
  last_execution_status?: string | undefined;
  inherited_from_template_id?: string | null | undefined;
  inherited_from_scope?: 'system' | 'workspace' | null | undefined;
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
  timeout_ms?: number | null | undefined;
  description?: string | undefined;
}

export interface UpdateWorkflowHookPayload {
  name?: string | undefined;
  failure_policy?: FailurePolicy | undefined;
  allowed_mutable_fields?: string[] | undefined;
  wasm_module_sha256?: string | undefined;
  agent?: string | undefined;
  timeout_ms?: number | null | undefined;
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

export interface RepoBindingDetail {
  id: string;
  workspace_id?: string | undefined;
  project_id?: string | undefined;
  slug: string;
  remote_url: string;
  default_ref: string;
  access_mode: 'bare_git_tools' | 'ro_vfs_mount';
  last_fetched_commit?: string | null | undefined;
  last_fetched_at?: string | null | undefined;
  last_fetch_error?: string | null | undefined;
  created_by?: string | undefined;
  created_at?: string | undefined;
}

export type RepoBindingSummary = RepoBindingDetail;

export interface CreateRepoBindingPayload {
  slug: string;
  remote_url: string;
  default_ref?: string | undefined;
  access_mode: 'bare_git_tools' | 'ro_vfs_mount';
  credential?: string | undefined;
}

export interface ProjectStateSummary {
  id: string;
  name: string;
}

export function validateGitRemoteUrl(url: string): { valid: boolean; error?: string } {
  const trimmed = url.trim();
  if (!trimmed) {
    return { valid: false, error: 'Repository URL is required.' };
  }
  if (trimmed.length > 2048) {
    return { valid: false, error: 'Repository URL exceeds 2048 characters.' };
  }
  const disallowed = ['file://', 'ext::', 'fd::', 'git://', 'http://', 'ftp://', 'ftps://'];
  for (const prefix of disallowed) {
    if (trimmed.toLowerCase().startsWith(prefix)) {
      return {
        valid: false,
        error: `Insecure URL scheme rejected: '${prefix}'. Only HTTPS or SSH URLs are permitted.`,
      };
    }
  }
  const isHttps = trimmed.startsWith('https://');
  const isSsh =
    trimmed.startsWith('ssh://') ||
    /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+:[a-zA-Z0-9._/~-]+$/.test(trimmed);
  if (!isHttps && !isSsh) {
    return {
      valid: false,
      error: 'URL must start with https://, ssh://, or use git@host:path SSH syntax.',
    };
  }
  // SSRF check for loopback, localhost, and internal subnets
  const lower = trimmed.toLowerCase();
  if (
    lower.includes('localhost') ||
    lower.includes('127.0.0.1') ||
    lower.includes('[::1]') ||
    lower.includes('169.254.') ||
    lower.includes('0.0.0.0') ||
    /\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/.test(lower) ||
    /\b192\.168\.\d{1,3}\.\d{1,3}\b/.test(lower) ||
    /\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b/.test(lower)
  ) {
    return {
      valid: false,
      error:
        'SSRF hazard rejected: Localhost, private IP ranges, and internal network addresses are forbidden.',
    };
  }
  return { valid: true };
}

// Fallback/Default Approved Wasm modules (KB-P5-13 Tier A)
export const DEFAULT_WASM_MODULES: WasmModuleSummary[] = [
  {
    sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
    name: 'qa-proof-validator',
    description: 'Ensures description or comments include docs/qa/ proof bundle',
    target_latency_budget: '<2ms',
  },
  {
    sha256: '7982de041f00a867a3f839e6172865450d0159fa77c288ec57440ceb87571874',
    name: 'security-invariant-validator',
    description: 'Checks zero new dependencies and strict security tokens',
    target_latency_budget: '<25ms',
  },
  {
    sha256: '2e7db622992707370042a3c5e15eda145d995048ef4f69f6c746f33dc43f93e9',
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
        manifest_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
        is_enabled: true,
        wasm_module_name: 'qa-proof-validator',
        wasm_module_sha256: '92d31f66098dd8194837346df091aace6d7db8ef63106181c0910ad85463f968',
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

export async function fetchAgentDefinitions(
  workspace = 'kanban',
  fallbackOnCatch = true,
): Promise<AgentDefinitionSummary[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/workspaces/${encodeURIComponent(workspace)}/agent-definitions` as never,
    )) as AgentDefinitionSummary[];
    return Array.isArray(data) ? data : [];
  } catch (err: unknown) {
    if (err instanceof ApiProblem && err.status === 404) {
      return [];
    }
    if (!fallbackOnCatch) {
      return [];
    }
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

export async function fetchRepoBindings(projectKey: string): Promise<RepoBindingDetail[]> {
  try {
    const data = (await apiFetch(
      'GET',
      `/api/v1/projects/${encodeURIComponent(projectKey)}/repo-bindings` as never,
    )) as RepoBindingDetail[];
    return Array.isArray(data) ? data : [];
  } catch {
    return [
      {
        id: 'repo-1',
        slug: 'kanban-main',
        remote_url: 'https://github.com/ThumbsUp-HQ/kanban.git',
        default_ref: 'main',
        access_mode: 'ro_vfs_mount',
      },
    ];
  }
}

export async function createRepoBinding(
  projectKey: string,
  payload: CreateRepoBindingPayload,
): Promise<RepoBindingDetail> {
  const res = (await apiFetch(
    'POST',
    `/api/v1/projects/${encodeURIComponent(projectKey)}/repo-bindings` as never,
    { body: payload },
  )) as RepoBindingDetail;
  return res;
}

export async function refreshRepoBinding(bindingId: string): Promise<RepoBindingDetail> {
  const res = (await apiFetch(
    'POST',
    `/api/v1/repo-bindings/${encodeURIComponent(bindingId)}/refresh` as never,
  )) as RepoBindingDetail;
  return res;
}

export async function deleteRepoBinding(bindingId: string): Promise<void> {
  await apiFetch(
    'DELETE',
    `/api/v1/repo-bindings/${encodeURIComponent(bindingId)}` as never,
  );
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

export async function fetchApprovedWasmModules(projectKey?: string): Promise<WasmModuleSummary[]> {
  try {
    if (!projectKey) return DEFAULT_WASM_MODULES;
    const data = (await apiFetch(
      'GET',
      `/api/v1/projects/${encodeURIComponent(projectKey)}/approved-wasm-modules` as never,
    )) as WasmModuleSummary[];
    return Array.isArray(data) && data.length > 0 ? data : DEFAULT_WASM_MODULES;
  } catch {
    return DEFAULT_WASM_MODULES;
  }
}

export type DefaultHookScopeKind = 'system' | 'workspace';

export interface DefaultWorkflowHook {
  id: string;
  scope_kind: DefaultHookScopeKind;
  workspace_id?: string | null;
  name: string;
  from_state_name?: string | null;
  to_state_name: string;
  hook_kind: string;
  sort_rank: number;
  is_enabled: boolean;
  wasm_module_sha256?: string | null;
  agent_definition_id?: string | null;
  agent_slug?: string | null;
  allowed_mutable_fields: string[];
  failure_policy: FailurePolicy;
  timeout_ms?: number | null;
  max_rework_attempts: number;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateDefaultWorkflowHookPayload {
  name: string;
  scope_kind: DefaultHookScopeKind;
  workspace_id?: string | null | undefined;
  from_state_name?: string | null | undefined;
  to_state_name: string;
  hook_kind?: string | undefined;
  sort_rank?: number | undefined;
  is_enabled?: boolean | undefined;
  wasm_module_sha256?: string | null | undefined;
  agent?: string | null | undefined;
  agent_definition_id?: string | null | undefined;
  agent_slug?: string | null | undefined;
  allowed_mutable_fields?: string[] | undefined;
  failure_policy?: FailurePolicy | undefined;
  timeout_ms?: number | null | undefined;
  max_rework_attempts?: number | undefined;
}

export interface UpdateDefaultWorkflowHookPayload {
  name?: string | undefined;
  from_state_name?: string | null | undefined;
  to_state_name?: string | undefined;
  hook_kind?: string | undefined;
  sort_rank?: number | undefined;
  is_enabled?: boolean | undefined;
  wasm_module_sha256?: string | null | undefined;
  agent?: string | null | undefined;
  agent_definition_id?: string | null | undefined;
  agent_slug?: string | null | undefined;
  allowed_mutable_fields?: string[] | undefined;
  failure_policy?: FailurePolicy | undefined;
  timeout_ms?: number | null | undefined;
  max_rework_attempts?: number | undefined;
}

export async function fetchDefaultWorkflowHooks(
  scopeKind?: DefaultHookScopeKind,
  workspaceId?: string,
): Promise<DefaultWorkflowHook[]> {
  const params = new URLSearchParams();
  if (scopeKind) params.set('scope_kind', scopeKind);
  if (workspaceId && scopeKind !== 'system') params.set('workspace_id', workspaceId);
  const qs = params.toString();
  const endpoint =
    workspaceId && scopeKind !== 'system'
      ? `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/default-workflow-hooks${scopeKind ? `?include_system=false` : ''}`
      : `/api/v1/admin/default-workflow-hooks${qs ? `?${qs}` : ''}`;
  const data = (await apiFetch('GET', endpoint as never)) as DefaultWorkflowHook[];
  if (!Array.isArray(data)) return [];
  if (scopeKind) {
    return data.filter((t) => t.scope_kind === scopeKind);
  }
  return data;
}

export async function createDefaultWorkflowHook(
  payload: CreateDefaultWorkflowHookPayload,
  workspaceId?: string,
): Promise<DefaultWorkflowHook> {
  const endpoint =
    payload.scope_kind === 'workspace' && workspaceId
      ? `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/default-workflow-hooks`
      : '/api/v1/admin/default-workflow-hooks';
  const res = (await apiFetch('POST', endpoint as never, {
    body: payload,
  })) as DefaultWorkflowHook;
  return res;
}

export async function updateDefaultWorkflowHook(
  hookId: string,
  payload: UpdateDefaultWorkflowHookPayload,
  workspaceId?: string,
): Promise<DefaultWorkflowHook> {
  const endpoint = workspaceId
    ? `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/default-workflow-hooks/${encodeURIComponent(hookId)}`
    : `/api/v1/admin/default-workflow-hooks/${encodeURIComponent(hookId)}`;
  const res = (await apiFetch('PATCH', endpoint as never, {
    body: payload,
  })) as DefaultWorkflowHook;
  return res;
}

export async function deleteDefaultWorkflowHook(
  hookId: string,
  workspaceId?: string,
): Promise<void> {
  const endpoint = workspaceId
    ? `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/default-workflow-hooks/${encodeURIComponent(hookId)}`
    : `/api/v1/admin/default-workflow-hooks/${encodeURIComponent(hookId)}`;
  await apiFetch('DELETE', endpoint as never);
}

export async function syncDefaultWorkflowHooks(
  projectKey: string,
): Promise<WorkflowHook[]> {
  const res = (await apiFetch(
    'POST',
    `/api/v1/projects/${encodeURIComponent(projectKey)}/workflow-hooks/sync-defaults` as never,
  )) as WorkflowHook[];
  return Array.isArray(res) ? res : [];
}
