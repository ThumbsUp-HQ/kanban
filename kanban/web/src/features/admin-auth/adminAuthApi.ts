/**
 * Typed API client wrappers and validation helpers for Admin Auth Studio (KB-P3-36, S4.1, S4.2, S4.3).
 */

import { apiFetch } from '../../api/client';

export type ProviderKind = 'OIDC' | 'OAUTH2' | 'LDAP' | 'LOCAL_ADMIN';

export type HealthStatus = 'HEALTHY' | 'FAILED' | 'UNVERIFIED';

export interface OidcPublicConfig {
  issuer_url: string;
  client_id: string;
  scopes?: string[];
  pkce_method?: 'S256';
  token_auth_method?: 'client_secret_basic' | 'private_key_jwt';
}

export interface LdapPublicConfig {
  server_url: string;
  bind_dn: string;
  base_dn: string;
  user_filter?: string;
  start_tls?: boolean;
  ca_pem?: string;
  spki_sha256_pin?: string;
}

export interface LocalAdminPublicConfig {
  recovery_policy?: string;
}

export interface AdminAuthCard {
  id: string;
  provider_kind: ProviderKind;
  slug: string;
  display_name: string;
  button_subtext: string | null;
  icon_preset: string;
  is_enabled: boolean;
  sort_rank: string;
  auto_provision_users: boolean;
  allowed_email_domains: string[];
  has_secret: boolean;
  dek_kid: string | null;
  last_health_status: HealthStatus;
  last_handshake_at: string | null;
  check_summary: string | null;
  latency_ms: number | null;
  public_config: Record<string, unknown>;
}

export interface AdminAuthCardsResponse {
  cards: AdminAuthCard[];
}

export interface CreateAuthCardPayload {
  provider_kind: ProviderKind;
  slug: string;
  display_name: string;
  button_subtext?: string | null;
  icon_preset: string;
  auto_provision_users: boolean;
  allowed_email_domains: string[];
  public_config: Record<string, unknown>;
  secret_input?: string;
}

export interface UpdateAuthCardPayload {
  display_name?: string;
  button_subtext?: string | null;
  icon_preset?: string;
  auto_provision_users?: boolean;
  allowed_email_domains?: string[];
  public_config?: Record<string, unknown>;
  secret_input?: string;
}

export interface ReorderAuthCardPayload {
  before_card_id: string | null;
  after_card_id: string | null;
  sort_rank: string;
}

export interface TestHandshakeResult {
  last_health_status: 'HEALTHY' | 'FAILED';
  latency_ms: number;
  check_summary: string;
}

const FORBIDDEN_SECRET_KEYS = [
  'client_secret',
  'bind_dn_password',
  'encrypted_secret_blob',
  'wrapped_dek',
] as const;

/**
 * Defensively strips raw secrets from auth card responses (Security Invariant KB-P3-36).
 */
export function sanitizeAdminAuthCard(card: AdminAuthCard): AdminAuthCard {
  const sanitizedRecord: Record<string, unknown> = { ...card };
  for (const key of FORBIDDEN_SECRET_KEYS) {
    Reflect.deleteProperty(sanitizedRecord, key);
  }
  const config: Record<string, unknown> = { ...card.public_config };
  for (const key of FORBIDDEN_SECRET_KEYS) {
    Reflect.deleteProperty(config, key);
  }
  return {
    ...sanitizedRecord,
    public_config: config,
  } as unknown as AdminAuthCard;
}

export async function fetchAdminAuthCards(): Promise<AdminAuthCardsResponse> {
  const result = (await apiFetch(
    'GET',
    '/api/v1/admin/auth-cards' as never,
  )) as Partial<AdminAuthCardsResponse>;
  return {
    cards: (result.cards ?? []).map(sanitizeAdminAuthCard),
  };
}

export async function createAdminAuthCard(
  payload: CreateAuthCardPayload,
): Promise<AdminAuthCard> {
  const result = (await apiFetch(
    'POST',
    '/api/v1/admin/auth-cards' as never,
    { body: payload },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function updateAdminAuthCard(
  cardId: string,
  payload: UpdateAuthCardPayload,
): Promise<AdminAuthCard> {
  const result = (await apiFetch(
    'PATCH',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}` as never,
    { body: payload },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function toggleAdminAuthCardEnabled(
  cardId: string,
  isEnabled: boolean,
): Promise<AdminAuthCard> {
  const result = (await apiFetch(
    'PATCH',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/enabled` as never,
    { body: { is_enabled: isEnabled } },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function reorderAdminAuthCard(
  cardId: string,
  payload: ReorderAuthCardPayload,
): Promise<AdminAuthCard> {
  const result = (await apiFetch(
    'POST',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/reorder` as never,
    { body: payload },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function testAuthCardHandshake(
  cardId: string,
): Promise<TestHandshakeResult> {
  const result = (await apiFetch(
    'POST',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/test-handshake` as never,
    { body: {} },
  )) as TestHandshakeResult;
  return result;
}

export async function deleteAdminAuthCard(cardId: string): Promise<void> {
  await apiFetch(
    'DELETE',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}` as never,
  );
}
