// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface ProviderConfigPublic {
  id: string;
  provider_kind: string;
  display_name: string;
  base_url?: string | null;
  model_allowlist: string[];
  residency_tier: string;
  priority: number;
  settings: Record<string, unknown>;
  api_key_set: boolean;
  is_enabled: boolean;
  project_id?: string | null;
}

export interface ProviderConfigCreate {
  provider_kind: string;
  display_name: string;
  model_allowlist?: string[];
  residency_tier?: string;
  base_url?: string | null;
  priority?: number;
  settings?: Record<string, unknown>;
  project_id?: string | null;
  is_enabled?: boolean;
  api_key?: string | null;
}

export interface ProviderConfigUpdate {
  display_name?: string;
  model_allowlist?: string[];
  residency_tier?: string;
  base_url?: string | null;
  priority?: number;
  settings?: Record<string, unknown>;
  is_enabled?: boolean;
  api_key?: string | null;
}

export interface BudgetRecord {
  period_kind: 'daily' | 'monthly';
  period_start: string;
  token_cap: number;
  tokens_used: number;
  tokens_reserved: number;
}

export interface BudgetSetRequest {
  provider_config_id: string;
  project_id?: string | null | undefined;
  period_kind: 'daily' | 'monthly';
  token_cap: number;
}

export async function fetchAiProviders(projectId?: string): Promise<ProviderConfigPublic[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  return (await apiFetch('GET', `/api/v1/admin/ai/providers${query}` as never)) as ProviderConfigPublic[];
}

export async function fetchAiProvider(providerId: string): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'GET',
    `/api/v1/admin/ai/providers/${encodeURIComponent(providerId)}` as never,
  )) as ProviderConfigPublic;
}

export async function createAiProvider(payload: ProviderConfigCreate): Promise<ProviderConfigPublic> {
  return (await apiFetch('POST', '/api/v1/admin/ai/providers' as never, { body: payload })) as ProviderConfigPublic;
}

export async function updateAiProvider(
  providerId: string,
  payload: ProviderConfigUpdate,
): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'PATCH',
    `/api/v1/admin/ai/providers/${encodeURIComponent(providerId)}` as never,
    {
      body: payload,
    },
  )) as ProviderConfigPublic;
}

export async function disableAiProvider(providerId: string): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'POST',
    `/api/v1/admin/ai/providers/${encodeURIComponent(providerId)}:disable` as never,
  )) as ProviderConfigPublic;
}

export async function deleteAiProvider(providerId: string): Promise<void> {
  await apiFetch('DELETE', `/api/v1/admin/ai/providers/${encodeURIComponent(providerId)}` as never);
}

export async function fetchBudgets(providerConfigId: string): Promise<BudgetRecord[]> {
  return (await apiFetch(
    'GET',
    `/api/v1/admin/ai/budgets?provider_config_id=${encodeURIComponent(providerConfigId)}` as never,
  )) as BudgetRecord[];
}

export async function setBudget(payload: BudgetSetRequest): Promise<BudgetRecord> {
  return (await apiFetch('PUT', '/api/v1/admin/ai/budgets' as never, { body: payload })) as BudgetRecord;
}

export async function fetchAirGapMode(): Promise<boolean> {
  try {
    const settings = (await apiFetch('GET', '/api/v1/workspaces/settings' as never)) as {
      air_gap_mode?: boolean;
    };
    return Boolean(settings.air_gap_mode);
  } catch {
    return false;
  }
}
