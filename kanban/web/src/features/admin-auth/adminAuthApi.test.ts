import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as client from '../../api/client';
import {
  fetchAdminAuthCards,
  createAdminAuthCard,
  updateAdminAuthCard,
  toggleAdminAuthCardEnabled,
  reorderAdminAuthCard,
  testAuthCardHandshake,
  deleteAdminAuthCard,
  sanitizeAdminAuthCard,
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
          secret_input: 'super-secret',
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
      body: { display_name: 'Updated Okta' },
    });
    expect(res.id).toBe('card-1');
  });

  it('toggleAdminAuthCardEnabled calls PATCH /api/v1/admin/auth-cards/{id}/enabled', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      ...rawCard,
      is_enabled: false,
    });
    const res = await toggleAdminAuthCardEnabled('card-1', false);

    expect(apiSpy).toHaveBeenCalledWith(
      'PATCH',
      '/api/v1/admin/auth-cards/card-1/enabled',
      { body: { is_enabled: false } },
    );
    expect(res.is_enabled).toBe(false);
  });

  it('reorderAdminAuthCard calls POST /api/v1/admin/auth-cards/{id}/reorder', async () => {
    const apiSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      ...rawCard,
      sort_rank: '1V',
    });
    const res = await reorderAdminAuthCard('card-1', {
      before_card_id: 'card-0',
      after_card_id: 'card-2',
      sort_rank: '1V',
    });

    expect(apiSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/admin/auth-cards/card-1/reorder',
      { body: { before_card_id: 'card-0', after_card_id: 'card-2', sort_rank: '1V' } },
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
    );
  });

  it('fetchAdminAuthCards handles response without cards property gracefully', async () => {
    vi.spyOn(client, 'apiFetch').mockResolvedValue({});
    const res = await fetchAdminAuthCards();
    expect(res.cards).toEqual([]);
  });
});
