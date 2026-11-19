import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as client from '../../api/client';
import {
  fetchAdminAuthCards,
  createAdminAuthCard,
  updateAdminAuthCard,
  toggleAdminAuthCardEnabled,
  reorderAdminAuthCard,
  testAuthCardHandshake,
  testDraftAuthCardHandshake,
  parseGoogleOAuthJson,
  deleteAdminAuthCard,
  sanitizeAdminAuthCard,
  fetchAdminPrincipals,
  createLocalUser,
  resetUserPassword,
  updateUserRole,
  type AdminAuthCard,
} from './adminAuthApi';

describe('adminAuthApi (KB-P3-36)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const rawCard: AdminAuthCard = {
    id: 'card-1',
    provider_kind: 'OIDC',
    slug: 'okta',
    display_name: 'Okta SSO',
    button_subtext: 'Workforce',
    icon_preset: 'shield',
    is_enabled: true,
    sort_rank: '1',
    auto_provision_users: true,
    allowed_email_domains: ['example.com'],
    has_secret: true,
    dek_kid: 'dek-123',
    last_health_status: 'HEALTHY',
    last_handshake_at: '2026-11-13T20:00:00Z',
    check_summary: 'OK',
    latency_ms: 42,
    public_config: { issuer_url: 'https://idp.example.com' },
  };

  it('sanitizes forbidden secret keys from card response (Mandatory Test Case 2)', () => {
    const leakedCard = {
      ...rawCard,
      client_secret: 'leaked-secret-123',
      bind_dn_password: 'leaked-password-456',
      public_config: {
        issuer_url: 'https://idp.example.com',
        client_secret: 'leaked-secret-nested',
      },
    } as unknown as AdminAuthCard;

    const sanitized = sanitizeAdminAuthCard(leakedCard);
    expect('client_secret' in sanitized).toBe(false);
    expect('bind_dn_password' in sanitized).toBe(false);
    expect('client_secret' in sanitized.public_config).toBe(false);
    expect(sanitized.public_config.issuer_url).toBe('https://idp.example.com');
  });

  it('fetchAdminAuthCards calls GET /api/v1/admin/auth-cards and prunes secrets', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      cards: [
        {
          ...rawCard,
          client_secret: 'leak',
        },
      ],
    });

    const res = await fetchAdminAuthCards();
    expect(apiSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/auth-cards');
    expect(res.cards.length).toBe(1);
    const card0 = res.cards[0];
    expect(card0).toBeDefined();
    if (card0) {
      expect('client_secret' in card0).toBe(false);
      expect(card0.display_name).toBe('Okta SSO');
    }
  });

  it('createAdminAuthCard calls POST /api/v1/admin/auth-cards', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(rawCard);
    const res = await createAdminAuthCard({
      provider_kind: 'OIDC',
      slug: 'okta',
      display_name: 'Okta SSO',
      icon_preset: 'shield',
      auto_provision_users: true,
      allowed_email_domains: ['example.com'],
      public_config: { issuer_url: 'https://idp.example.com' },
      secret_input: 'super-secret',
    });

    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/auth-cards',
      expect.objectContaining({
        body: expect.objectContaining({
          slug: 'okta',
          secret: 'super-secret',
        }) as unknown,
      }),
    );
    expect(res.id).toBe('card-1');
  });

  it('updateAdminAuthCard calls PATCH /api/v1/admin/auth-cards/{id}', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(rawCard);
    const res = await updateAdminAuthCard('card-1', {
      display_name: 'Updated Okta',
    });

    expect(apiSpy).toHaveBeenCalledWith('PATCH', '/api/v1/admin/auth-cards/card-1', {
      body: { display_name: 'Updated Okta', secret: null },
    });
    expect(res.id).toBe('card-1');
  });

  it('toggleAdminAuthCardEnabled calls POST /api/v1/admin/auth-cards/{id}/disable', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      ...rawCard,
      is_enabled: false,
    });
    const res = await toggleAdminAuthCardEnabled('card-1', false);

    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/auth-cards/card-1/disable',
      { body: {} },
    );
    expect(res.is_enabled).toBe(false);
  });

  it('reorderAdminAuthCard calls POST /api/v1/admin/auth-cards/{id}/reorder', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      ...rawCard,
      sort_rank: '1V',
    });
    const res = await reorderAdminAuthCard('card-1', {
      after_card_id: 'card-2',
    });

    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/auth-cards/card-1/reorder',
      { body: { after: 'card-2' } },
    );
    expect(res.sort_rank).toBe('1V');
  });

  it('testAuthCardHandshake calls POST /api/v1/admin/auth-cards/{id}/test-handshake', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      last_health_status: 'HEALTHY',
      latency_ms: 42,
      check_summary: 'OIDC discovery successful',
    });
    const res = await testAuthCardHandshake('card-1');

    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/auth-cards/card-1/test-handshake',
      { body: {} },
    );
    expect(res.last_health_status).toBe('HEALTHY');
    expect(res.latency_ms).toBe(42);
  });

  it('deleteAdminAuthCard calls DELETE /api/v1/admin/auth-cards/{id}', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(undefined);
    await deleteAdminAuthCard('card-1');

    expect(apiSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/admin/auth-cards/card-1',
      { body: { confirm_slug: 'card-1' } },
    );
  });

  it('fetchAdminAuthCards handles response without cards property gracefully', async () => {
    vi.spyOn(client, 'apiFetch').mockResolvedValue({});
    const res = await fetchAdminAuthCards();
    expect(res.cards).toEqual([]);
  });

  it('covers testDraftAuthCardHandshake and parseGoogleOAuthJson API calls', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation((_method, path) => {
      const pathStr = path as string;
      if (pathStr.includes('/api/v1/admin/auth-cards/test-handshake')) {
        return Promise.resolve({ ok: true, check_summary: 'Draft probe passed' });
      }
      if (pathStr.includes('/api/v1/admin/auth-cards/parse-google-json')) {
        return Promise.resolve({ client_id: 'client-123', client_secret: 'sec-456' });
      }
      return Promise.resolve({});
    });

    const draftRes = await testDraftAuthCardHandshake({
      provider_kind: 'OIDC',
      slug: 'test-draft',
      display_name: 'Test Draft',
      button_subtext: null,
      icon_preset: 'google',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: { issuer_url: 'https://accounts.google.com' },
    });

    expect(draftRes.last_health_status).toBe('HEALTHY');
    expect(draftRes.check_summary).toBe('Draft probe passed');

    const googleRes = await parseGoogleOAuthJson({
      google_oauth_json: '{"web":{}}',
    });
    expect(googleRes.client_id).toBe('client-123');
  });

  it('covers testDraftAuthCardHandshake fallback branches for status and error codes', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch');

    // 1. ok is false with error_code
    apiSpy.mockResolvedValueOnce({ ok: false, error_code: 'ERR_TIMEOUT' });
    const r1 = await testDraftAuthCardHandshake({
      provider_kind: 'OIDC',
      slug: 'd1',
      display_name: 'D1',
      button_subtext: null,
      icon_preset: 'shield',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: {},
    });
    expect(r1.last_health_status).toBe('FAILED');
    expect(r1.check_summary).toBe('ERR_TIMEOUT');

    // 2. ok is false without error_code, status is 'ERR'
    apiSpy.mockResolvedValueOnce({ ok: false });
    const r2 = await testDraftAuthCardHandshake({
      provider_kind: 'OIDC',
      slug: 'd2',
      display_name: 'D2',
      button_subtext: null,
      icon_preset: 'shield',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: {},
    });
    expect(r2.last_health_status).toBe('FAILED');
    expect(r2.check_summary).toBe('Probe failed');

    // 3. status is 'OK' with ok undefined
    apiSpy.mockResolvedValueOnce({ status: 'OK' });
    const r3 = await testDraftAuthCardHandshake({
      provider_kind: 'OIDC',
      slug: 'd3',
      display_name: 'D3',
      button_subtext: null,
      icon_preset: 'shield',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: {},
    });
    expect(r3.last_health_status).toBe('HEALTHY');
    expect(r3.check_summary).toBe('Probe failed');

    // 4. last_health_status is 'HEALTHY' with ok undefined and check_summary present
    apiSpy.mockResolvedValueOnce({ last_health_status: 'HEALTHY', check_summary: 'Already healthy' });
    const r4 = await testDraftAuthCardHandshake({
      provider_kind: 'OIDC',
      slug: 'd4',
      display_name: 'D4',
      button_subtext: null,
      icon_preset: 'shield',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: {},
    });
    expect(r4.last_health_status).toBe('HEALTHY');
    expect(r4.check_summary).toBe('Already healthy');

    // 5. deleteAdminAuthCard with custom confirmSlug
    apiSpy.mockResolvedValueOnce(undefined);
    await deleteAdminAuthCard('card-x', 'custom-confirm');
    expect(apiSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/admin/auth-cards/card-x',
      { body: { confirm_slug: 'custom-confirm' } },
    );
  });

  it('covers fetchAdminPrincipals, createLocalUser, resetUserPassword, updateUserRole branches', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch');

    // 1. fetchAdminPrincipals with filter=ALL or spaces
    apiSpy.mockResolvedValueOnce([]);
    await fetchAdminPrincipals('ALL');
    expect(apiSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?limit=100');

    apiSpy.mockResolvedValueOnce([]);
    await fetchAdminPrincipals('   ');
    expect(apiSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?limit=100');

    apiSpy.mockResolvedValueOnce([]);
    await fetchAdminPrincipals('AGENT');
    expect(apiSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?filter=AGENT&limit=100');

    // 2. createLocalUser with and without optional fields
    apiSpy.mockResolvedValueOnce({ id: 'u-1', handle: 'alice', display_name: 'Alice' });
    await createLocalUser({
      handle: 'alice',
      display_name: 'Alice',
      email: 'alice@example.com',
      password: 'secretPassword1',
      role: 'WORKSPACE_MEMBER',
    });
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/principals',
      expect.objectContaining({
        body: expect.objectContaining({
          type: 'USER',
          email: 'alice@example.com',
          password: 'secretPassword1',
          role: 'WORKSPACE_MEMBER',
        }),
      }),
    );

    apiSpy.mockResolvedValueOnce({ id: 'u-2', handle: 'bob', display_name: 'Bob' });
    await createLocalUser({
      handle: 'bob',
      display_name: 'Bob',
      type: 'AGENT',
    });
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/principals',
      expect.objectContaining({
        body: {
          type: 'AGENT',
          handle: 'bob',
          display_name: 'Bob',
        },
      }),
    );

    // 3. resetUserPassword
    apiSpy.mockResolvedValueOnce(undefined);
    await resetUserPassword('u-1', 'newPass123!');
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/principals/u-1/password',
      { body: { password: 'newPass123!' } },
    );

    // 4. updateUserRole with previousRole SERVER_ADMIN and newRole WORKSPACE_MEMBER
    apiSpy.mockRejectedValueOnce(new Error('Ignore unbind failure'));
    apiSpy.mockResolvedValueOnce(undefined);
    await updateUserRole('u-1', 'WORKSPACE_MEMBER', 'SERVER_ADMIN');
    expect(apiSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/admin/role-bindings',
      {
        body: {
          principal_id: 'u-1',
          role: 'SERVER_ADMIN',
          scope_type: 'server',
        },
      },
    );
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/role-bindings',
      {
        body: {
          principal_id: 'u-1',
          role: 'WORKSPACE_MEMBER',
          scope_type: 'workspace',
        },
      },
    );

    // 5. updateUserRole with previousRole WORKSPACE_MEMBER and newRole SERVER_ADMIN
    apiSpy.mockResolvedValueOnce(undefined);
    apiSpy.mockResolvedValueOnce(undefined);
    await updateUserRole('u-1', 'SERVER_ADMIN', 'WORKSPACE_MEMBER');
    expect(apiSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/admin/role-bindings',
      {
        body: {
          principal_id: 'u-1',
          role: 'WORKSPACE_MEMBER',
          scope_type: 'workspace',
        },
      },
    );
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/role-bindings',
      {
        body: {
          principal_id: 'u-1',
          role: 'SERVER_ADMIN',
          scope_type: 'server',
        },
      },
    );

    // 6. updateUserRole with same previousRole and newRole (no DELETE called)
    apiSpy.mockResolvedValueOnce(undefined);
    await updateUserRole('u-1', 'WORKSPACE_MEMBER', 'WORKSPACE_MEMBER');
    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/role-bindings',
      {
        body: {
          principal_id: 'u-1',
          role: 'WORKSPACE_MEMBER',
          scope_type: 'workspace',
        },
      },
    );
  });
});
