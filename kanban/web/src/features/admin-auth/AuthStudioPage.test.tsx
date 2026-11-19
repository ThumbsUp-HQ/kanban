import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { AuthStudioPage, formatHandle } from './AuthStudioPage';
import * as client from '../../api/client';
import * as adminAuthApi from './adminAuthApi';
import type { AdminAuthCard } from './adminAuthApi';
import { ApiProblem } from '../../api/problem';

describe('AuthStudioPage (KB-P3-36)', () => {
  const adminUser = {
    id: 'u-admin',
    handle: 'admin',
    is_server_admin: true,
  };

  const memberUser = {
    id: 'u-member',
    handle: 'member',
    is_server_admin: false,
  };

  const mockCards: [AdminAuthCard, AdminAuthCard, AdminAuthCard, AdminAuthCard] = [
    {
      id: 'c-okta',
      provider_kind: 'OIDC',
      slug: 'okta',
      display_name: 'Okta SSO',
      button_subtext: 'Workforce IDP',
      icon_preset: 'shield',
      is_enabled: true,
      sort_rank: '1',
      auto_provision_users: true,
      allowed_email_domains: ['example.com'],
      has_secret: true,
      dek_kid: 'dek-1',
      last_health_status: 'UNVERIFIED',
      last_handshake_at: null,
      check_summary: null,
      latency_ms: null,
      public_config: { issuer_url: 'https://idp.example.com', client_id: 'client-okta' },
    },
    {
      id: 'c-github',
      provider_kind: 'OAUTH2',
      slug: 'github',
      display_name: 'GitHub Enterprise',
      button_subtext: 'Developer accounts',
      icon_preset: 'globe',
      is_enabled: true,
      sort_rank: '2',
      auto_provision_users: true,
      allowed_email_domains: ['github.com'],
      has_secret: true,
      dek_kid: 'dek-2',
      last_health_status: 'HEALTHY',
      last_handshake_at: '2026-11-13T20:00:00Z',
      check_summary: 'OK',
      latency_ms: 55,
      public_config: { issuer_url: 'https://github.com', client_id: 'gh-123' },
    },
    {
      id: 'c-ldap',
      provider_kind: 'LDAP',
      slug: 'corp-ad',
      display_name: 'Corporate Active Directory',
      button_subtext: 'Domain accounts',
      icon_preset: 'lock',
      is_enabled: true,
      sort_rank: '3',
      auto_provision_users: false,
      allowed_email_domains: [],
      has_secret: true,
      dek_kid: 'dek-3',
      last_health_status: 'HEALTHY',
      last_handshake_at: '2026-11-13T20:30:00Z',
      check_summary: 'OK',
      latency_ms: 12,
      public_config: { server_url: 'ldaps://ad.corp', bind_dn: 'cn=admin', base_dn: 'dc=corp' },
    },
    {
      id: 'c-local',
      provider_kind: 'LOCAL_ADMIN',
      slug: 'local-admin',
      display_name: 'Local Administrator',
      button_subtext: 'Break-glass access',
      icon_preset: 'lock',
      is_enabled: true,
      sort_rank: 'z',
      auto_provision_users: false,
      allowed_email_domains: [],
      has_secret: false,
      dek_kid: null,
      last_health_status: 'HEALTHY',
      last_handshake_at: null,
      check_summary: null,
      latency_ms: null,
      public_config: {},
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders 4 cards in sort_rank order with Primary indicator on first enabled external card, and moves card down (Mandatory Test Case 1)', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const reorderSpy = vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockResolvedValue({
      ...mockCards[0],
      sort_rank: '2V',
    });

    render(<AuthStudioPage />);

    // Wait for cards to load
    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
      expect(screen.getByText('Corporate Active Directory')).toBeDefined();
      expect(screen.getByText('Local Administrator')).toBeDefined();
    });

    // Check Primary badge is on Okta SSO
    const rows = screen.getAllByRole('listitem');
    expect(rows.length).toBe(4);
    const row0 = rows[0];
    expect(row0).toBeDefined();
    if (row0) {
      expect(row0.textContent).toContain('Primary');
      expect(row0.textContent).toContain('Okta SSO');
    }

    // Move Okta SSO down
    const moveDownBtn = screen.getByRole('button', { name: /Move Okta SSO down/i });
    fireEvent.click(moveDownBtn);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledTimes(1);
      const callArgs = reorderSpy.mock.calls[0];
      expect(callArgs?.[0]).toBe('c-okta');
      expect(callArgs?.[1]?.before_card_id).toBe('c-ldap');
      expect(callArgs?.[1]?.after_card_id).toBe('c-github');
      expect(/^[0-9A-Za-z]+$/.test(String(callArgs?.[1]?.sort_rank))).toBe(true);
    });
  });

  it('tests handshake and updates status chip from UNVERIFIED to HEALTHY (42 ms) (Mandatory Test Case 1)', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const testSpy = vi.spyOn(adminAuthApi, 'testAuthCardHandshake').mockResolvedValue({
      last_health_status: 'HEALTHY',
      latency_ms: 42,
      check_summary: 'OIDC discovery probe passed',
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByTestId('health-chip-okta').textContent).toContain('UNVERIFIED');
    });

    const testBtn = screen.getAllByRole('button', { name: /Test handshake/i })[0];
    expect(testBtn).toBeDefined();
    if (testBtn) {
      fireEvent.click(testBtn);
    }

    await waitFor(() => {
      expect(testSpy).toHaveBeenCalledWith('c-okta');
      expect(screen.getByTestId('health-chip-okta').textContent).toContain('HEALTHY (42 ms)');
    });
  });

  it('rolls back switch and renders LOCKOUT_PREVENTED alert on 409 HANDSHAKE_STALE_FOR_LOCAL_DISABLE (Mandatory Test Case 4)', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValueOnce(
      new ApiProblem(409, {
        code: 'LOCKOUT_PREVENTED',
        reason_code: 'HANDSHAKE_STALE_FOR_LOCAL_DISABLE',
        detail: 'Cannot disable Local Admin without recent verified handshake.',
      }),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Local Administrator')).toBeDefined();
    });

    const localSwitch = screen.getByRole('switch', { name: /Enable Local Administrator/i });
    expect(localSwitch.getAttribute('aria-checked')).toBe('true');

    // Click to disable
    fireEvent.click(localSwitch);

    await waitFor(() => {
      // Banner rendered with alert
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(
        screen.getByText(
          /Local Administrator cannot be disabled until at least one external Server-Admin identity provider card completes a verified login handshake within the past 15 minutes/i,
        ),
      ).toBeDefined();
      expect(
        screen.getByText('kanban-ctl auth emergency-unlock --enable-local-admin'),
      ).toBeDefined();
    });

    // Verify switch snapped back to true (rolled back)
    expect(localSwitch.getAttribute('aria-checked')).toBe('true');
  });

  it('renders uniform "Not found or no access" for non-server-admin user (Mandatory Test Case 5)', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return memberUser;
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
      expect(
        screen.getByText(
          'The requested page does not exist or you do not have permission to view it.',
        ),
      ).toBeDefined();
    });

    // Zero cards rendered
    expect(screen.queryByText('Authentication Studio')).toBeNull();
  });

  it('renders hostile script and img tags as literal safe text (Mandatory Test Case 5)', async () => {
    const hostileCard: AdminAuthCard = {
      ...mockCards[0],
      id: 'c-hostile',
      slug: 'hostile-xss',
      display_name: '<script>alert(1)</script>',
      check_summary: '<img src=x onerror=alert(1)>',
      last_health_status: 'FAILED',
    };

    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: [hostileCard] };
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('<script>alert(1)</script>')).toBeDefined();
    });

    // Assert no script or img elements were injected
    expect(document.querySelector('script[src="1"]')).toBeNull();
    expect(document.querySelector('img[src="x"]')).toBeNull();
  });

  it('intercepts 403 AAL2_REQUIRED, opens SecondFactorStep modal, and replays mutation (Mandatory Test Case 5)', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const toggleSpy = vi
      .spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled')
      .mockRejectedValueOnce(
        new ApiProblem(403, {
          code: 'AAL2_REQUIRED',
          challenge_id: 'chall-stepup-99',
          methods: ['totp'],
        }),
      )
      .mockResolvedValueOnce({
        ...mockCards[1],
        is_enabled: false,
      });

    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      if ((path as string) === '/api/v1/auth/totp/verify') return { status: 'authenticated' };
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    const ghSwitch = screen.getByRole('switch', { name: /Enable GitHub Enterprise/i });
    fireEvent.click(ghSwitch);

    // Dialog opens with SecondFactorStep
    await waitFor(() => {
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
      expect(screen.getByLabelText(/6-digit Authenticator Code/i)).toBeDefined();
    });

    // Enter 6-digit TOTP code
    const totpInput = screen.getByLabelText<HTMLInputElement>(/6-digit Authenticator Code/i);
    fireEvent.change(totpInput, { target: { value: '123456' } });

    await waitFor(() => {
      // Replay should have called toggleAdminAuthCardEnabled a second time
      expect(toggleSpy).toHaveBeenCalledTimes(2);
      // Dialog should now be closed
      expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
    });
  });

  it('deletes card when delete button is confirmed', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const deleteSpy = vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockResolvedValue(undefined);

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('c-okta');
      expect(screen.queryByText('Okta SSO')).toBeNull();
    });
  });

  it('opens drawer to add a new auth card and appends created card', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const newCard: AdminAuthCard = {
      id: 'c-new',
      provider_kind: 'OIDC',
      slug: 'new-idp',
      display_name: 'New IDP',
      button_subtext: null,
      icon_preset: 'shield',
      is_enabled: true,
      sort_rank: '3',
      auto_provision_users: true,
      allowed_email_domains: [],
      has_secret: false,
      dek_kid: null,
      last_health_status: 'UNVERIFIED',
      last_handshake_at: null,
      check_summary: null,
      latency_ms: null,
      public_config: { issuer_url: 'https://new.example.com' },
    };

    const createSpy = vi.spyOn(adminAuthApi, 'createAdminAuthCard').mockResolvedValue(newCard);

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Authentication Studio')).toBeDefined();
    });

    const addBtn = screen.getByRole('button', { name: /\+ Add auth card/i });
    fireEvent.click(addBtn);

    // Fill form inside drawer
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'new-idp' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'New IDP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i), {
      target: { value: 'https://new.example.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i), {
      target: { value: 'new-client' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalled();
      expect(screen.getByText('New IDP')).toBeDefined();
    });
  });

  it('opens drawer to edit an existing card and updates it', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const updatedCard: AdminAuthCard = {
      ...mockCards[0],
      display_name: 'Renamed Okta SSO',
    };

    const updateSpy = vi.spyOn(adminAuthApi, 'updateAdminAuthCard').mockResolvedValue(updatedCard);

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const editBtns = screen.getAllByRole('button', { name: /^Edit$/i });
    const oktaEditBtn = editBtns[0];
    if (oktaEditBtn) {
      fireEvent.click(oktaEditBtn);
    }

    const nameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i);
    expect(nameInput.value).toBe('Okta SSO');
    fireEvent.change(nameInput, { target: { value: 'Renamed Okta SSO' } });

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith('c-okta', expect.objectContaining({
        display_name: 'Renamed Okta SSO',
      }));
      expect(screen.getByText('Renamed Okta SSO')).toBeDefined();
    });
  });

  it('supports drag-and-drop reordering of auth cards', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const reorderSpy = vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockResolvedValue({
      ...mockCards[0],
      sort_rank: '1V',
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const oktaRow = screen.getByTestId('auth-card-row-okta');
    const githubRow = screen.getByTestId('auth-card-row-github');

    // Drag okta (index 0) over and drop on github (index 1)
    fireEvent.dragStart(oktaRow);
    fireEvent.dragOver(githubRow);
    fireEvent.drop(githubRow);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalled();
    });
  });

  it('handles reorder failure by rolling back and showing error message', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockRejectedValue(new Error('Network error'));

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Corporate Active Directory')).toBeDefined();
    });

    const upBtn = screen.getByRole('button', {
      name: /Move Corporate Active Directory up/i,
    });
    fireEvent.click(upBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to reorder card.')).toBeDefined();
    });

    // Dismiss general error
    const dismissBtn = screen.getByRole('button', { name: /Dismiss error/i });
    fireEvent.click(dismissBtn);
    expect(screen.queryByText('Failed to reorder card.')).toBeNull();
  });

  it('handles handshake failure by updating card status to FAILED', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'testAuthCardHandshake').mockRejectedValue(
      new Error('TLS certificate expired'),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const testBtns = screen.getAllByRole('button', { name: /Test handshake/i });
    const oktaTestBtn = testBtns[0];
    if (oktaTestBtn) {
      fireEvent.click(oktaTestBtn);
    }

    await waitFor(() => {
      const oktaChip = screen.getByTestId('health-chip-okta');
      expect(oktaChip.textContent).toContain('FAILED');
    });
  });

  it('handles LOCKOUT_PREVENTED when deleting a card', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockRejectedValue(
      new ApiProblem(409, {
        code: 'LOCKOUT_PREVENTED',
        reason_code: 'ZERO_ADMIN_CARDS',
        detail: 'Cannot delete the only enabled admin auth card',
      }),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
      expect(
        screen.getByText(
          /disabling or deleting this card would leave zero enabled sign-in cards/i,
        ),
      ).toBeDefined();
    });

    // Dismiss banner
    const dismissAlertBtn = screen.getByRole('button', { name: /Dismiss lockout alert/i });
    fireEvent.click(dismissAlertBtn);
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('handles fetch cards failure: 403 access denied vs general error', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') {
        throw new ApiProblem(403, { code: 'FORBIDDEN' });
      }
      return {};
    });

    const { unmount } = render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });
    unmount();

    // Test generic error loading cards
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') {
        throw new Error('Database connection failed');
      }
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Database connection failed')).toBeDefined();
    });
  });

  it('supports drag-and-drop moving up, and ignores drops on same index or LOCAL_ADMIN', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const reorderSpy = vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockResolvedValue({
      ...mockCards[1],
      sort_rank: '0V',
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    const oktaRow = screen.getByTestId('auth-card-row-okta');
    const githubRow = screen.getByTestId('auth-card-row-github');
    const localAdminRow = screen.getByTestId('auth-card-row-local-admin');

    // 1. Drop on same index does nothing
    fireEvent.dragStart(githubRow);
    fireEvent.drop(githubRow);
    expect(reorderSpy).not.toHaveBeenCalled();

    // 2. Drop on LOCAL_ADMIN does nothing
    fireEvent.dragStart(githubRow);
    fireEvent.drop(localAdminRow);
    expect(reorderSpy).not.toHaveBeenCalled();

    // 3. Drag up: github (index 1) dropped on okta (index 0)
    fireEvent.dragStart(githubRow);
    fireEvent.dragOver(oktaRow);
    fireEvent.drop(oktaRow);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith('c-github', expect.objectContaining({
        before_card_id: 'c-okta',
      }));
    });
  });

  it('handles LOCKOUT_PREVENTED during card update and general error during delete', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'updateAdminAuthCard').mockRejectedValue(
      new ApiProblem(409, {
        code: 'LOCKOUT_PREVENTED',
        reason_code: 'ZERO_ADMIN_CARDS',
        detail: 'Cannot disable the last active card',
      }),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const editBtns = screen.getAllByRole('button', { name: /^Edit$/i });
    if (editBtns[0]) fireEvent.click(editBtns[0]);

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Cannot disable the last active card/i)).toBeDefined();
    });

    // Test delete card general error
    vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockRejectedValue(
      new Error('Foreign key constraint violation'),
    );

    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByText('Foreign key constraint violation')).toBeDefined();
    });
  });

  it('handles AAL2 cancellation and session expiration', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue(
      new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'chall-cancel',
        methods: ['totp'],
      }),
    );

    const { rerender } = render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    const ghSwitch = screen.getByRole('switch', { name: /Enable GitHub Enterprise/i });
    fireEvent.click(ghSwitch);

    await waitFor(() => {
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });

    // Click Cancel in modal
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.queryByText('Admin Verification Required (AAL2)')).toBeNull();
    });

    // Trigger AAL2 on delete and test session expired
    vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockRejectedValueOnce(
      new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'chall-delete',
        methods: ['totp'],
      }),
    );

    rerender(<AuthStudioPage />);
    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });

    // Enter code to replay delete
    const deleteSpy = vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockResolvedValue(undefined);
    const totpInput = screen.getByLabelText<HTMLInputElement>(/6-digit Authenticator Code/i);
    fireEvent.change(totpInput, { target: { value: '654321' } });

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalled();
    });
  });

  it('handles auth/me network failure by denying access', async () => {
    vi.spyOn(client, 'apiFetch').mockRejectedValue(new Error('Network error'));
    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });
  });

  it('handles drag-and-drop reorder network failure', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockRejectedValue(new Error('Reorder failed'));

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const oktaRow = screen.getByTestId('auth-card-row-okta');
    const githubRow = screen.getByTestId('auth-card-row-github');

    fireEvent.dragStart(oktaRow);
    fireEvent.dragOver(githubRow);
    fireEvent.drop(githubRow);

    await waitFor(() => {
      expect(screen.getByText('Failed to reorder card.')).toBeDefined();
    });
  });

  it('handles session/challenge expiration during AAL2 second factor', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      if ((path as string) === '/api/v1/auth/totp/verify') {
        throw new ApiProblem(400, { code: 'CHALLENGE_EXPIRED' });
      }
      return {};
    });

    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue(
      new ApiProblem(403, {
        code: 'AAL2_REQUIRED',
        challenge_id: 'chall-expire',
        methods: ['totp'],
      }),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    const ghSwitch = screen.getByRole('switch', { name: /Enable GitHub Enterprise/i });
    fireEvent.click(ghSwitch);

    await waitFor(() => {
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });

    const totpInput = screen.getByLabelText<HTMLInputElement>(/6-digit Authenticator Code/i);
    fireEvent.change(totpInput, { target: { value: '999999' } });

    await waitFor(() => {
      expect(screen.getByText('Session expired. Please sign in again.')).toBeDefined();
    });
  });

  it('handles moving cards to top and bottom boundaries', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const reorderSpy = vi.spyOn(adminAuthApi, 'reorderAdminAuthCard').mockResolvedValue({
      ...mockCards[1],
      sort_rank: '0V',
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    // Move GitHub (index 1) UP to index 0 (prevPrev is null)
    const upBtn = screen.getByRole('button', { name: /Move GitHub Enterprise up/i });
    fireEvent.click(upBtn);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledWith('c-github', expect.objectContaining({
        before_card_id: 'c-okta',
        after_card_id: null,
      }));
    });

    // Move GitHub DOWN to index 2 (nextNext is null)
    const downBtn = screen.getByRole('button', { name: /Move GitHub Enterprise down/i });
    fireEvent.click(downBtn);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalled();
    });
  });

  it('handles toggle failure with generic Error displaying message', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue(
      new Error('Internal server timeout'),
    );

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('GitHub Enterprise')).toBeDefined();
    });

    const ghSwitch = screen.getByRole('switch', { name: /Enable GitHub Enterprise/i });
    fireEvent.click(ghSwitch);

    await waitFor(() => {
      expect(screen.getByText('Internal server timeout')).toBeDefined();
    });
  });

  it('handles 404 ApiProblem when fetching cards', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') {
        throw new ApiProblem(404, { code: 'NOT_FOUND' });
      }
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Not found or no access')).toBeDefined();
    });
  });

  it('covers edge cases: drag to bottom/top, non-Error exceptions, lockout without reason_code', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    const reorderSpy = vi
      .spyOn(adminAuthApi, 'reorderAdminAuthCard')
      .mockResolvedValueOnce({
        ...mockCards[0],
        sort_rank: '3V',
      })
      .mockResolvedValueOnce({
        ...mockCards[2],
        sort_rank: '0V',
      });

    const { unmount } = render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const oktaRow = screen.getByTestId('auth-card-row-okta');
    const adRow = screen.getByTestId('auth-card-row-corp-ad');

    // 1. Drag okta (index 0) to bottom (index 2) -> beforeCard is undefined
    fireEvent.dragStart(oktaRow);
    fireEvent.dragOver(adRow);
    fireEvent.drop(adRow);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalled();
    });

    // 2. Drag ad (index 2) to top (index 0) -> afterCard is undefined
    fireEvent.dragStart(adRow);
    fireEvent.dragOver(oktaRow);
    fireEvent.drop(oktaRow);

    await waitFor(() => {
      expect(reorderSpy).toHaveBeenCalledTimes(2);
    });

    unmount();

    // 3. Non-Error throw in fetch cards
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('Fatal network disruption');
      }
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load authentication cards.')).toBeDefined();
    });
  });

  it('handles non-Error rejection on handshake, delete, and lockout without reason_code', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    vi.spyOn(adminAuthApi, 'testAuthCardHandshake').mockRejectedValue('Handshake timeout');
    vi.spyOn(adminAuthApi, 'deleteAdminAuthCard').mockRejectedValue('Delete DB error');

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    // Test non-Error handshake
    const testBtns = screen.getAllByRole('button', { name: /Test handshake/i });
    if (testBtns[0]) fireEvent.click(testBtns[0]);

    await waitFor(() => {
      const oktaChip = screen.getByTestId('health-chip-okta');
      expect(oktaChip.textContent).toContain('FAILED');
    });

    // Test non-Error delete
    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to delete card.')).toBeDefined();
    });

    // Test lockout without reason_code
    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue(
      new ApiProblem(409, {
        code: 'LOCKOUT_PREVENTED',
        detail: 'Generic lockout prevention',
      }),
    );

    const oktaSwitch = screen.getByRole('switch', { name: /Enable Okta SSO/i });
    fireEvent.click(oktaSwitch);

    await waitFor(() => {
      expect(screen.getByText('Generic lockout prevention')).toBeDefined();
    });
  });

  it('covers all defensive branches: boundary moves, local admin delete, and update error', async () => {
    vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
      await Promise.resolve();
      if ((path as string) === '/api/v1/auth/me') return adminUser;
      if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
      return {};
    });

    render(<AuthStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    // 1. Move Up on first item (index 0)
    const upBtns = screen.getAllByRole('button', { name: /Move .* up/i });
    if (upBtns[0]) fireEvent.click(upBtns[0]);

    // 2. Move Down on last external item (index 2)
    const downBtns = screen.getAllByRole('button', { name: /Move .* down/i });
    if (downBtns[2]) fireEvent.click(downBtns[2]);

    // 3. Delete on local admin
    const deleteBtns = screen.getAllByRole('button', { name: /Local Admin cannot be deleted/i });
    if (deleteBtns[0]) fireEvent.click(deleteBtns[0]);

    // 4. Update card throwing regular Error (lockout is null)
    vi.spyOn(adminAuthApi, 'updateAdminAuthCard').mockRejectedValue(new Error('Update network failure'));
    const editBtns = screen.getAllByRole('button', { name: /^Edit$/i });
    if (editBtns[0]) fireEvent.click(editBtns[0]);
    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(screen.getByText('Update network failure')).toBeDefined();
    });

    // 5. Toggle failing with string error
    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue('String toggle error');
    const oktaSwitch = screen.getByRole('switch', { name: /Enable Okta SSO/i });
    fireEvent.click(oktaSwitch);
    await waitFor(() => {
      expect(screen.getByText('Failed to update card status.')).toBeDefined();
    });

    // 6. AAL2_REQUIRED without challenge_id or methods
    vi.spyOn(adminAuthApi, 'toggleAdminAuthCardEnabled').mockRejectedValue(
      new ApiProblem(403, { code: 'AAL2_REQUIRED' }),
    );
    fireEvent.click(oktaSwitch);
    await waitFor(() => {
      expect(screen.getByText('Admin Verification Required (AAL2)')).toBeDefined();
    });
  });

  describe('Users & Permissions Tab (KANBA-176)', () => {
    const mockPrincipals = [
      {
        id: 'u-1',
        principal: 'local.user',
        handle: 'local.user',
        display_name: 'Local User',
        type: 'USER' as const,
        status: 'active' as const,
        email: 'local@example.com',
        role: 'SERVER_ADMIN',
        provider: 'LOCAL',
      },
      {
        id: 'u-2',
        principal: 'ldap.engineer',
        handle: 'ldap.engineer',
        display_name: 'LDAP Engineer',
        type: 'USER' as const,
        status: 'active' as const,
        email: 'ldap@example.com',
        role: 'WORKSPACE_MEMBER',
        provider: 'LDAP',
      },
    ];

    beforeEach(() => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        if ((path as string).startsWith('/api/v1/admin/principals')) return mockPrincipals;
        return {};
      });
    });

    it('switches to Users & Permissions tab and renders principals table with badges', async () => {
      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      const usersTab = screen.getByRole('tab', { name: /Users & Permissions/i });
      fireEvent.click(usersTab);

      await waitFor(() => {
        expect(screen.getByText('Local User')).toBeDefined();
        expect(screen.getByText('@local.user')).toBeDefined();
        expect(screen.getByText('local@example.com')).toBeDefined();
        expect(screen.getByText('LDAP Engineer')).toBeDefined();
      });

      expect(screen.getByText('LOCAL')).toBeDefined();
      expect(screen.getByText('LDAP')).toBeDefined();
    });

    it('opens + Add Local User modal and creates user successfully', async () => {
      const createSpy = vi.spyOn(adminAuthApi, 'createLocalUser').mockResolvedValue({
        id: 'u-3',
        principal: 'new.member',
        handle: 'new.member',
        display_name: 'New Member',
        type: 'USER',
        status: 'active',
        email: 'new@example.com',
        role: 'WORKSPACE_MEMBER',
        provider: 'LOCAL',
      });

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      const addBtn = await screen.findByRole('button', { name: /\+ Add Local User/i });
      fireEvent.click(addBtn);

      expect(screen.getByRole('heading', { name: /\+ Add Local User/i })).toBeDefined();

      fireEvent.change(screen.getByLabelText(/Username \/ Handle/i), {
        target: { value: 'new.member' },
      });
      fireEvent.change(screen.getByLabelText(/Display Name/i), {
        target: { value: 'New Member' },
      });
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: 'new@example.com' },
      });
      fireEvent.change(screen.getByLabelText(/^Password/i), {
        target: { value: 'ValidPassword123!' },
      });

      const submitBtn = screen.getByRole('button', { name: /^Create User$/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith({
          handle: 'new.member',
          display_name: 'New Member',
          email: 'new@example.com',
          password: 'ValidPassword123!',
          role: 'WORKSPACE_MEMBER',
        });
      });
    });

    it('updates user role grant via role select dropdown', async () => {
      const roleSpy = vi.spyOn(adminAuthApi, 'updateUserRole').mockResolvedValue(undefined);

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      await waitFor(() => {
        expect(screen.getByText('LDAP Engineer')).toBeDefined();
      });

      const roleSelect = screen.getByLabelText(/Role for @?ldap\.engineer/i);
      fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });

      await waitFor(() => {
        expect(roleSpy).toHaveBeenCalledWith('u-2', 'WORKSPACE_ADMIN', 'WORKSPACE_MEMBER');
      });
    });

    it('opens Reset Password modal and resets user password', async () => {
      const resetSpy = vi.spyOn(adminAuthApi, 'resetUserPassword').mockResolvedValue(undefined);

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      await waitFor(() => {
        expect(screen.getByText('Local User')).toBeDefined();
      });

      const resetBtns = screen.getAllByRole('button', { name: /^Reset Password$/i });
      if (resetBtns[0]) fireEvent.click(resetBtns[0]);

      expect(screen.getByRole('heading', { name: /Reset Password: @local\.user/i })).toBeDefined();

      fireEvent.change(screen.getByLabelText(/^New Password/i), {
        target: { value: 'NewPass12345!' },
      });
      fireEvent.change(screen.getByLabelText(/Confirm New Password/i), {
        target: { value: 'NewPass12345!' },
      });

      const updateBtn = screen.getByRole('button', { name: /^Update Password$/i });
      fireEvent.click(updateBtn);

      await waitFor(() => {
        expect(resetSpy).toHaveBeenCalledWith('u-1', 'NewPass12345!');
      });
    });

    it('filters principals by kind and displays provider badges', async () => {
      const customPrincipals = [
        {
          id: 'u-google',
          principal: 'google.dev',
          display_name: 'Google Dev',
          email: 'dev@google.com',
          provider: 'GOOGLE_WORKSPACE',
          role: 'WORKSPACE_MEMBER',
          created_at: '2026-11-14T00:00:00Z',
        },
        {
          id: 'u-github',
          principal: 'gh.octocat',
          display_name: 'GitHub Octocat',
          email: 'octo@github.com',
          provider: 'GITHUB_ENTERPRISE',
          role: 'WORKSPACE_MEMBER',
          created_at: '2026-11-14T00:00:00Z',
        },
        {
          id: 'u-ad',
          principal: 'corp.user',
          display_name: 'AD User',
          email: 'user@corp.local',
          provider: 'ACTIVE_DIRECTORY',
          role: 'WORKSPACE_MEMBER',
          created_at: '2026-11-14T00:00:00Z',
        },
        {
          id: 'u-other',
          principal: 'custom.user',
          display_name: 'Custom User',
          email: 'custom@idp.com',
          provider: 'CUSTOM_IDP',
          role: 'WORKSPACE_GUEST',
          created_at: '2026-11-14T00:00:00Z',
        },
      ];

      const fetchSpy = vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        if ((path as string).startsWith('/api/v1/admin/principals')) return customPrincipals;
        return {};
      });

      const { container } = render(<AuthStudioPage />);

      await waitFor(() => {
        expect(within(container).getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(within(container).getByRole('tab', { name: /Users & Permissions/i }));

      await waitFor(() => {
        expect(within(container).getByText('Google Dev')).toBeDefined();
      });

      // Provider badges
      expect(within(container).getByText('GOOGLE_WORKSPACE').className).toContain('auth-badge-provider--google');
      expect(within(container).getByText('GITHUB_ENTERPRISE').className).toContain('auth-badge-provider--github');
      expect(within(container).getByText('ACTIVE_DIRECTORY').className).toContain('auth-badge-provider--ad');
      expect(within(container).getByText('CUSTOM_IDP').className).toContain('auth-badge-provider--oauth');

      // Click filter buttons
      fireEvent.click(within(container).getByTestId('filter-user'));
      await waitFor(() => {
        expect(within(container).getByTestId('filter-group')).toBeDefined();
      });
      expect(fetchSpy).toHaveBeenCalledWith('GET', expect.stringContaining('filter=USER'));

      fireEvent.click(within(container).getByTestId('filter-group'));
      await waitFor(() => {
        expect(within(container).getByTestId('filter-agent')).toBeDefined();
      });
      expect(fetchSpy).toHaveBeenCalledWith('GET', expect.stringContaining('filter=GROUP'));

      fireEvent.click(within(container).getByTestId('filter-agent'));
      await waitFor(() => {
        expect(within(container).getByTestId('filter-all')).toBeDefined();
      });
      expect(fetchSpy).toHaveBeenCalledWith('GET', expect.stringContaining('filter=AGENT'));

      fireEvent.click(within(container).getByTestId('filter-all'));
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith('GET', expect.stringContaining('/api/v1/admin/principals'));
      });
    });

    it('renders empty message when no principals exist and dismisses error alert', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') throw new Error('Network failure');
        if ((path as string).startsWith('/api/v1/admin/principals')) return [];
        return {};
      });

      render(<AuthStudioPage />);

      // General error alert appears
      await waitFor(() => {
        expect(screen.getByText('Network failure')).toBeDefined();
      });

      // Dismiss error
      const dismissBtn = screen.getByRole('button', { name: 'Dismiss error' });
      fireEvent.click(dismissBtn);
      expect(screen.queryByText('Network failure')).toBeNull();

      // Check empty principals
      const usersTab = screen.getByRole('tab', { name: /Users & Permissions/i });
      fireEvent.click(usersTab);

      await waitFor(() => {
        expect(screen.getByText('No user principals found.')).toBeDefined();
      });
    });

    it('covers user role update error handling for Error and string rejection', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        if ((path as string).startsWith('/api/v1/admin/principals')) {
          return [
            {
              id: 'u-role-test',
              principal: 'role.user',
              handle: 'role.user',
              display_name: 'Role User',
              email: 'role@example.com',
              role: 'WORKSPACE_MEMBER',
              provider: 'LOCAL',
            },
          ];
        }
        return {};
      });

      const roleSpy = vi.spyOn(adminAuthApi, 'updateUserRole').mockRejectedValueOnce(new Error('Permission denied for role change'));

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      await waitFor(() => {
        expect(screen.getByText('Role User')).toBeDefined();
      });

      const roleSelect = screen.getByLabelText(/Role for @?role\.user/i);
      fireEvent.change(roleSelect, { target: { value: 'WORKSPACE_ADMIN' } });

      await waitFor(() => {
        expect(screen.getByText('Permission denied for role change')).toBeDefined();
      });

      // Now reject with string to trigger fallback
      roleSpy.mockRejectedValueOnce('Unknown failure');
      fireEvent.change(roleSelect, { target: { value: 'SERVER_ADMIN' } });

      await waitFor(() => {
        expect(screen.getByText('Failed to update user role.')).toBeDefined();
      });
    });

    it('covers principal creation for AGENT type, handle validation, and creation errors', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        if ((path as string).startsWith('/api/v1/admin/principals')) return [];
        return {};
      });

      const createSpy = vi.spyOn(adminAuthApi, 'createLocalUser');

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      const addBtn = await screen.findByRole('button', { name: /\+ Add Local User/i });
      fireEvent.click(addBtn);

      // Select Principal Kind: AGENT
      const kindSelect = screen.getByLabelText(/Principal Kind/i);
      fireEvent.change(kindSelect, { target: { value: 'AGENT' } });

      // Submit with empty handle
      const dialog = screen.getByRole('dialog', { name: /\+ Add Local User/i });
      const form = dialog.querySelector('form');
      expect(form).toBeTruthy();
      if (form) fireEvent.submit(form);

      expect(screen.getByText('Handle is required.')).toBeDefined();
      expect(createSpy).not.toHaveBeenCalled();

      // Set handle and mock error with Error instance
      fireEvent.change(screen.getByLabelText(/Username \/ Handle/i), {
        target: { value: 'ci-bot' },
      });
      createSpy.mockRejectedValueOnce(new Error('Agent handle already reserved'));
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByText('Agent handle already reserved')).toBeDefined();
      });

      // Submit again with string reject for fallback error
      createSpy.mockRejectedValueOnce('Backend failure');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByText('Failed to create principal.')).toBeDefined();
      });

      // Submit successfully
      createSpy.mockResolvedValueOnce({
        id: 'p-agent',
        principal: 'ci-bot',
        handle: 'ci-bot',
        display_name: 'ci-bot',
        type: 'AGENT',
        status: 'active',
        role: 'WORKSPACE_MEMBER',
      });
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            handle: 'ci-bot',
            type: 'AGENT',
          }),
        );
        expect(screen.getByText('Principal (AGENT) @ci-bot created successfully.')).toBeDefined();
      });
    });

    it('covers reset password error handling for mismatch, Error instance, and string rejection', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        if ((path as string).startsWith('/api/v1/admin/principals')) {
          return [
            {
              id: 'u-pwd-test',
              principal: 'pwd.user',
              handle: 'pwd.user',
              display_name: 'Pwd User',
              email: 'pwd@example.com',
              role: 'WORKSPACE_MEMBER',
              provider: 'LOCAL',
            },
          ];
        }
        return {};
      });

      const resetSpy = vi.spyOn(adminAuthApi, 'resetUserPassword');

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));

      await waitFor(() => {
        expect(screen.getByText('Pwd User')).toBeDefined();
      });

      const resetBtn = screen.getByRole('button', { name: /^Reset Password$/i });
      fireEvent.click(resetBtn);

      const newPassInput = screen.getByLabelText(/^New Password/i);
      const confirmPassInput = screen.getByLabelText(/Confirm New Password/i);
      const updateBtn = screen.getByRole('button', { name: /^Update Password$/i });

      // Passwords do not match
      fireEvent.change(newPassInput, { target: { value: 'Password12345!' } });
      fireEvent.change(confirmPassInput, { target: { value: 'Mismatch12345!' } });
      fireEvent.click(updateBtn);

      expect(screen.getByText('Passwords do not match or cannot be empty.')).toBeDefined();
      expect(resetSpy).not.toHaveBeenCalled();

      // Matching passwords but resetUserPassword throws Error
      fireEvent.change(confirmPassInput, { target: { value: 'Password12345!' } });
      resetSpy.mockRejectedValueOnce(new Error('Password policy check failed: too common'));
      fireEvent.click(updateBtn);

      await waitFor(() => {
        expect(screen.getByText('Password policy check failed: too common')).toBeDefined();
      });

      // Reset throws non-Error (string)
      resetSpy.mockRejectedValueOnce('Network drop');
      fireEvent.click(updateBtn);

      await waitFor(() => {
        expect(screen.getByText('Failed to reset password.')).toBeDefined();
      });
    });

    it('covers formatHandle permutations in AuthStudioPage', () => {
      expect(formatHandle(null)).toBe('');
      expect(formatHandle(undefined)).toBe('');
      expect(formatHandle('')).toBe('');
      expect(formatHandle('alice')).toBe('@alice');
      expect(formatHandle('@bob')).toBe('@bob');
    });

    it('covers loadUsers error branches (ApiProblem 403 and generic string error)', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation((method, path) => {
        if ((path as string) === '/api/v1/auth/me') return Promise.resolve(adminUser);
        if ((path as string) === '/api/v1/admin/auth-cards') return Promise.resolve({ cards: mockCards });
        return Promise.resolve({});
      });

      vi.spyOn(adminAuthApi, 'fetchAdminPrincipals').mockRejectedValueOnce('Raw string error');

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('tab', { name: /Users & Permissions/i }));
      await waitFor(() => {
        expect(screen.getByText('Failed to load user principals.')).toBeDefined();
      });

      vi.spyOn(adminAuthApi, 'fetchAdminPrincipals').mockRejectedValueOnce(
        new ApiProblem(403, { code: 'FORBIDDEN' }),
      );
      // Trigger loadUsers with filter change to 'USER'
      fireEvent.click(screen.getByTestId('filter-user'));
      await waitFor(() => {
        expect(screen.getByText('Not found or no access')).toBeDefined();
      });
    });

    it('tests handshake from inside drawer for existing card', async () => {
      vi.spyOn(client, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        if ((path as string) === '/api/v1/auth/me') return adminUser;
        if ((path as string) === '/api/v1/admin/auth-cards') return { cards: mockCards };
        return {};
      });

      const testSpy = vi.spyOn(adminAuthApi, 'testAuthCardHandshake').mockResolvedValue({
        last_health_status: 'HEALTHY',
        latency_ms: 22,
        check_summary: 'Probe OK',
      });

      render(<AuthStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Okta SSO')).toBeDefined();
      });

      const editBtns = screen.getAllByRole('button', { name: /^Edit$/i });
      const firstEditBtn = editBtns[0];
      if (firstEditBtn) {
        fireEvent.click(firstEditBtn);
      }

      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-handshake-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('drawer-test-handshake-btn'));

      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith('c-okta');
      });
    });
  });
});
