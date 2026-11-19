// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export type HarnessKind = 'in_app_sdk' | 'cli_pipe' | 'remote_runner';
export type ProviderKind = 'openai' | 'ollama' | 'gemini' | 'fixture';
export type RepoAccessMode = 'none' | 'bare_git_tools' | 'ro_vfs_mount';

export interface AgentDefinitionResponse {
  id: string;
  workspace_id: string;
  project_id?: string | null;
  principal_id: string;
  slug: string;
  display_name: string;
  harness_kind: HarnessKind;
  provider_kind?: ProviderKind | null;
  model_id?: string | null;
  cli_binary_allowlist_id?: string | null;
  cli_args: string[];
  remote_runner_pool_slug?: string | null;
  repo_access_mode: RepoAccessMode;
  mcp_allowed_tools: string[];
  system_instructions_md: string;
  timeout_ms: number;
}

export interface AgentDefinitionCreate {
  slug: string;
  display_name: string;
  project_id?: string | null;
  harness_kind: HarnessKind;
  provider_kind?: ProviderKind | null;
  model_id?: string | null;
  cli_binary_allowlist_id?: string | null;
  cli_args?: string[];
  remote_runner_pool_slug?: string | null;
  repo_access_mode?: RepoAccessMode;
  mcp_allowed_tools?: string[];
  system_instructions_md?: string;
  timeout_ms?: number;
}

export interface AgentDefinitionPatch {
  display_name?: string;
  provider_kind?: ProviderKind | null;
  model_id?: string | null;
  cli_binary_allowlist_id?: string | null;
  cli_args?: string[];
  remote_runner_pool_slug?: string | null;
  repo_access_mode?: RepoAccessMode;
  mcp_allowed_tools?: string[];
  system_instructions_md?: string;
  timeout_ms?: number;
}

export interface AgentValidationResponse {
  valid: boolean;
  exit_code: number;
  status: string;
  command: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  rendered_context: string;
  tool_trace: string;
  report_text: string;
}

export async function fetchAgentDefinitions(): Promise<AgentDefinitionResponse[]> {
  return (await apiFetch('GET', '/api/v1/admin/agent-definitions' as never)) as AgentDefinitionResponse[];
}

export async function fetchAgentDefinition(agent: string): Promise<AgentDefinitionResponse> {
  return (await apiFetch(
    'GET',
    `/api/v1/admin/agent-definitions/${encodeURIComponent(agent)}` as never,
  )) as AgentDefinitionResponse;
}

export async function createAgentDefinition(payload: AgentDefinitionCreate): Promise<AgentDefinitionResponse> {
  return (await apiFetch('POST', '/api/v1/admin/agent-definitions' as never, {
    body: payload,
  })) as AgentDefinitionResponse;
}

export async function updateAgentDefinition(
  agent: string,
  payload: AgentDefinitionPatch,
): Promise<AgentDefinitionResponse> {
  return (await apiFetch(
    'PATCH',
    `/api/v1/admin/agent-definitions/${encodeURIComponent(agent)}` as never,
    {
      body: payload,
    },
  )) as AgentDefinitionResponse;
}

export async function deleteAgentDefinition(agent: string): Promise<void> {
  await apiFetch('DELETE', `/api/v1/admin/agent-definitions/${encodeURIComponent(agent)}` as never);
}

export async function validateAgentDefinition(agent: string): Promise<AgentValidationResponse> {
  return (await apiFetch(
    'POST',
    `/api/v1/admin/agent-definitions/${encodeURIComponent(agent)}:validate` as never,
  )) as AgentValidationResponse;
}
