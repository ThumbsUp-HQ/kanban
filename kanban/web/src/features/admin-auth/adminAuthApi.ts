/**
 * Typed API client wrappers and validation helpers for Admin Auth Studio (KB-P3-36, KB-UX-06).
 */

import { apiFetch } from '../../api/client';

export type ProviderKind = 'OIDC' | 'OAUTH2' | 'LDAP' | 'LOCAL_ADMIN';

export type HealthStatus = 'HEALTHY' | 'FAILED' | 'UNVERIFIED';

export interface OidcPublicConfig {
  kind?: 'OIDC' | 'OAUTH2';
  issuer?: string;
  authorization_endpoint?: string;
  token_endpoint?: string;
  userinfo_endpoint?: string;
  jwks_uri?: string;
  client_id: string;
  scopes?: string[];
  admin_allowlist?: string[];
  user_allowlist?: string[];
  token_auth_method?: 'client_secret_basic' | 'private_key_jwt';
}

export interface LdapPublicConfig {
  kind?: 'LDAP';
  url: string;
  transport_mode: 'ldaps' | 'starttls';
  base_dn: string;
  service_bind_dn?: string;
  user_search_filter?: string;
  subject_attribute?: string;
  email_attribute?: string;
  display_name_attribute?: string;
  access_mode?: 'any_user' | 'group_restricted';
  admin_groups?: string[];
  user_groups?: string[];
  ca_cert_pem?: string;
  spki_sha256_pins?: string[];
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
  last_admin_handshake_at?: string | null;
  last_handshake_at?: string | null;
  check_summary?: string | null;
  latency_ms?: number | null;
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
  is_enabled?: boolean;
  auto_provision_users: boolean;
  allowed_email_domains: string[];
  public_config: Record<string, unknown>;
  secret?: string | null;
  secret_input?: string;
}

export interface UpdateAuthCardPayload {
  display_name?: string;
  button_subtext?: string | null;
  icon_preset?: string;
  is_enabled?: boolean;
  auto_provision_users?: boolean;
  allowed_email_domains?: string[];
  public_config?: Record<string, unknown>;
  secret?: string | null;
  secret_input?: string;
}

export interface ReorderAuthCardPayload {
  after?: string | null;
  before_card_id?: string | null;
  after_card_id?: string | null;
  sort_rank?: string;
}

export interface TestHandshakeResult {
  ok?: boolean;
  status?: string;
  last_health_status?: 'HEALTHY' | 'FAILED';
  latency_ms: number;
  check_summary?: string;
  error_code?: string | null;
}

export interface AdminUserPrincipal {
  id: string;
  principal: string;
  handle?: string;
  display_name: string;
  type: 'USER' | 'GROUP' | 'AGENT';
  status: 'active' | 'deactivated' | 'disabled';
  email?: string | null;
  role?: string;
  provider?: string;
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
  const { secret_input, ...rest } = payload;
  const normalized = {
    ...rest,
    secret: payload.secret ?? secret_input ?? null,
  };
  const result = (await apiFetch(
    'POST',
    '/api/v1/admin/auth-cards' as never,
    { body: normalized },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function updateAdminAuthCard(
  cardId: string,
  payload: UpdateAuthCardPayload,
): Promise<AdminAuthCard> {
  const { secret_input, ...rest } = payload;
  const normalized = {
    ...rest,
    secret: payload.secret ?? secret_input ?? null,
  };
  const result = (await apiFetch(
    'PATCH',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}` as never,
    { body: normalized },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function toggleAdminAuthCardEnabled(
  cardId: string,
  isEnabled: boolean,
): Promise<AdminAuthCard> {
  const endpoint = isEnabled
    ? `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/enable`
    : `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/disable`;
  const result = (await apiFetch(
    'POST',
    endpoint as never,
    { body: {} },
  )) as AdminAuthCard;
  return sanitizeAdminAuthCard(result);
}

export async function reorderAdminAuthCard(
  cardId: string,
  payload: ReorderAuthCardPayload,
): Promise<AdminAuthCard> {
  const afterValue = payload.after !== undefined ? payload.after : (payload.after_card_id ?? null);
  const result = (await apiFetch(
    'POST',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}/reorder` as never,
    { body: { after: afterValue } },
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
  return {
    ...result,
    last_health_status: (result.ok ?? (result.status === 'OK' || result.last_health_status === 'HEALTHY'))
      ? 'HEALTHY'
      : 'FAILED',
    check_summary: result.check_summary ?? (result.ok ? 'Probe successful' : (result.error_code ?? 'Probe failed')),
  };
}

export async function deleteAdminAuthCard(cardId: string, confirmSlug?: string): Promise<void> {
  await apiFetch(
    'DELETE',
    `/api/v1/admin/auth-cards/${encodeURIComponent(cardId)}` as never,
    { body: { confirm_slug: confirmSlug ?? cardId } },
  );
}

// User & Permission Management APIs (KB-UX-06)

export async function fetchAdminPrincipals(filter = 'USER'): Promise<AdminUserPrincipal[]> {
  const result = (await apiFetch(
    'GET',
    `/api/v1/admin/principals?filter=${encodeURIComponent(filter)}&limit=100` as never,
  )) as AdminUserPrincipal[];
  return result;
}

export async function createLocalUser(payload: {
  handle: string;
  display_name: string;
  email: string;
  password?: string;
  role?: string;
}): Promise<AdminUserPrincipal> {
  const result = (await apiFetch(
    'POST',
    '/api/v1/admin/principals' as never,
    {
      body: {
        type: 'USER',
        handle: payload.handle,
        display_name: payload.display_name,
        email: payload.email,
        ...(payload.password ? { password: payload.password } : {}),
        ...(payload.role ? { role: payload.role } : {}),
      },
    },
  )) as AdminUserPrincipal;
  return result;
}

export async function resetUserPassword(principalId: string, password: string): Promise<void> {
  await apiFetch(
    'POST',
    `/api/v1/admin/principals/${encodeURIComponent(principalId)}/password` as never,
    { body: { password } },
  );
}

export async function updateUserRole(
  principalId: string,
  newRole: string,
  previousRole?: string,
): Promise<void> {
  if (previousRole && previousRole !== newRole) {
    try {
      await apiFetch(
        'DELETE',
        '/api/v1/admin/role-bindings' as never,
        {
          body: {
            principal_id: principalId,
            role: previousRole,
            scope_type: previousRole === 'SERVER_ADMIN' ? 'server' : 'workspace',
          },
        },
      );
    } catch {
      // Ignored if previously not bound
    }
  }

  await apiFetch(
    'POST',
    '/api/v1/admin/role-bindings' as never,
    {
      body: {
        principal_id: principalId,
        role: newRole,
        scope_type: newRole === 'SERVER_ADMIN' ? 'server' : 'workspace',
      },
    },
  );
}
