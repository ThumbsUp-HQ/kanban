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

  it('covers testDraftAuthCardHandshake fallback status and check_summary branches', async () => {
    const dummyPayload = {
      provider_kind: 'OIDC' as const,
      slug: 'test',
      display_name: 'Test',
      button_subtext: null,
      icon_preset: 'key',
      is_enabled: true,
      auto_provision_users: false,
      allowed_email_domains: [],
      public_config: {},
    };

    // 1. status: 'OK', ok: undefined, check_summary undefined
    vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({
      status: 'OK',
    });
    const res1 = await testDraftAuthCardHandshake(dummyPayload);
    expect(res1.last_health_status).toBe('HEALTHY');
    expect(res1.check_summary).toBe('Probe failed');

    // 2. ok: true, check_summary undefined
    vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({
      ok: true,
    });
    const res2 = await testDraftAuthCardHandshake(dummyPayload);
    expect(res2.last_health_status).toBe('HEALTHY');
    expect(res2.check_summary).toBe('Probe successful');

    // 3. ok: false, error_code: 'CERT_EXPIRED', check_summary undefined
    vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({
      ok: false,
      error_code: 'CERT_EXPIRED',
    });
    const res3 = await testDraftAuthCardHandshake(dummyPayload);
    expect(res3.last_health_status).toBe('FAILED');
    expect(res3.check_summary).toBe('CERT_EXPIRED');

    // 4. deleteAdminAuthCard with explicit confirmSlug
    const deleteSpy = vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({});
    await deleteAdminAuthCard('c-1', 'confirmed-c1');
    expect(deleteSpy).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/admin/auth-cards/c-1',
      { body: { confirm_slug: 'confirmed-c1' } },
    );

    // 5. fetchAdminPrincipals filter queries
    const principalsSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue([]);
    await fetchAdminPrincipals('USER');
    expect(principalsSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?filter=USER&limit=100');

    await fetchAdminPrincipals('ALL');
    expect(principalsSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?limit=100');

    await fetchAdminPrincipals();
    expect(principalsSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/principals?limit=100');

    // 6. createLocalUser with and without optional fields
    const createSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({ id: 'u-1' });
    await createLocalUser({
      handle: 'alice',
      display_name: 'Alice',
      email: 'alice@corp.com',
      password: 'pwd',
      role: 'ADMIN',
    });
    expect(createSpy).toHaveBeenCalledWith('POST', '/api/v1/admin/principals', {
      body: {
        type: 'USER',
        handle: 'alice',
        display_name: 'Alice',
        email: 'alice@corp.com',
        password: 'pwd',
        role: 'ADMIN',
      },
    });

    await createLocalUser({
      handle: 'bob',
      display_name: 'Bob',
    });
    expect(createSpy).toHaveBeenCalledWith('POST', '/api/v1/admin/principals', {
      body: {
        type: 'USER',
        handle: 'bob',
        display_name: 'Bob',
      },
    });
  });
});
