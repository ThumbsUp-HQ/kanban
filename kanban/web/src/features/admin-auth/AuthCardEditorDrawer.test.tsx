import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthCardEditorDrawer, type AuthCardEditorDrawerProps } from './AuthCardEditorDrawer';
import type { AdminAuthCard, CreateAuthCardPayload } from './adminAuthApi';

describe('AuthCardEditorDrawer (KB-P3-36)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  const existingOidcCard: AdminAuthCard = {
    id: 'c-oidc',
    provider_kind: 'OIDC',
    slug: 'okta-workforce',
    display_name: 'Okta SSO',
    button_subtext: 'Workforce IDP',
    icon_preset: 'shield',
    is_enabled: true,
    sort_rank: '1',
    auto_provision_users: true,
    allowed_email_domains: ['corp.example.com'],
    has_secret: true,
    dek_kid: 'dek-oidc-99',
    last_health_status: 'HEALTHY',
    last_handshake_at: '2026-11-13T20:00:00Z',
    check_summary: 'OK',
    latency_ms: 38,
    public_config: {
      issuer_url: 'https://okta.corp.example.com',
      client_id: 'client-abc-123',
      scopes: ['openid', 'profile', 'email'],
      pkce_method: 'S256',
      token_auth_method: 'client_secret_basic',
    },
  };

  it('renders write-only secret field empty on edit, omits secret_input unless replace checked (Mandatory Test Case 2)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={existingOidcCard}
        onClose={onClose}
        onSave={onSave}
      />,
    );

    const secretInput = screen.getByLabelText<HTMLInputElement>(/Client Secret/i);
    // Write-only: value is empty, disabled, placeholder has dek_kid
    expect(secretInput.value).toBe('');
    expect(secretInput.hasAttribute('disabled')).toBe(true);
    expect(secretInput.getAttribute('placeholder')).toContain('dek-oidc-99');

    // 1. Submit without checking Replace Stored Secret -> secret_input is omitted
    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'Okta SSO',
        }),
        true,
      );
    });

    const payload = onSave.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(payload).toBeDefined();
    expect('secret_input' in payload).toBe(false);

    // 2. Check Replace Stored Secret -> unlocks input and sends new secret
    const replaceBox = screen.getByLabelText<HTMLInputElement>(/Replace Stored Secret/i);
    fireEvent.click(replaceBox);
    expect(secretInput.hasAttribute('disabled')).toBe(false);

    fireEvent.change(secretInput, { target: { value: 'NewSecretValue12345!' } });
    expect(secretInput.value).toBe('NewSecretValue12345!');

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          secret: 'NewSecretValue12345!',
        }),
        true,
      );
    });

    const secondPayload = onSave.mock.calls[1]?.[0] as Record<string, unknown>;
    expect(secondPayload).toBeDefined();
    expect('secret_input' in secondPayload).toBe(false);

    // Password value in DOM input must be cleared
    expect(secretInput.value).toBe('');
  });

  it('displays authorized redirect URI and copies dynamically on click', () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={existingOidcCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    const callbackInput = screen.getByTestId<HTMLInputElement>('oauth-callback-url');
    expect(callbackInput.value).toBe(
      `${window.location.origin}/api/v1/auth/oidc/okta-workforce/callback`,
    );
    expect(callbackInput.readOnly).toBe(true);

    const originDisplay = screen.getByTestId('oauth-js-origin');
    expect(originDisplay.textContent).toBe(window.location.origin);

    const copyBtn = screen.getByTestId('copy-callback-url-btn');
    expect(copyBtn.textContent).toBe('Copy');
    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalledWith(
      `${window.location.origin}/api/v1/auth/oidc/okta-workforce/callback`,
    );
  });

  it('rejects OIDC with http:// URL and invalid slug before network call (Mandatory Test Case 3)', () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    const slugInput = screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i);
    const nameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i);
    const issuerInput = screen.getByLabelText<HTMLInputElement>(/Issuer URL/i);
    const clientIdInput = screen.getByLabelText<HTMLInputElement>(/Client ID/i);

    // Invalid slug (uppercase & underscore)
    fireEvent.change(slugInput, { target: { value: 'Bad_Slug' } });
    fireEvent.change(nameInput, { target: { value: 'Insecure IDP' } });
    // Insecure HTTP URL
    fireEvent.change(issuerInput, { target: { value: 'http://idp.example.com' } });
    fireEvent.change(clientIdInput, { target: { value: 'client-1' } });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    expect(screen.getByText(/Slug must be 3-48 lowercase alphanumeric/i)).toBeDefined();
    expect(screen.getByText(/Issuer URL must use HTTPS/i)).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('forces StartTLS = true when LDAP server_url starts with ldap:// and rejects 63-hex SPKI pin', () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    // Select LDAP
    const kindSelect = screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i);
    fireEvent.change(kindSelect, { target: { value: 'LDAP' } });

    const serverInput = screen.getByLabelText<HTMLInputElement>(/Server URL/i);
    const startTlsBox = screen.getByLabelText<HTMLInputElement>(/StartTLS/i);

    // Enter ldap://
    fireEvent.change(serverInput, { target: { value: 'ldap://dc01.corp.example.com' } });
    expect(startTlsBox.checked).toBe(true);
    expect(startTlsBox.hasAttribute('disabled')).toBe(true);

    // Test invalid SPKI pin (63 hex chars, should be 64)
    const spkiInput = screen.getByLabelText<HTMLInputElement>(/SPKI SHA-256 Pin/i);
    fireEvent.change(spkiInput, { target: { value: 'a'.repeat(63) } });

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'corp-ad' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Corp AD' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i), {
      target: { value: 'cn=admin,dc=corp' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i), {
      target: { value: 'dc=corp' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    expect(
      screen.getByText(/SPKI pin must be exactly 64 hexadecimal characters/i),
    ).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('closes drawer on Escape key press', () => {
    const onClose = vi.fn();
    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={onClose}
        onSave={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    // Non-Escape keys do not trigger onClose
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders null when isOpen is false and handles close button click', () => {
    const onClose = vi.fn();
    const { rerender, container } = render(
      <AuthCardEditorDrawer
        isOpen={false}
        card={null}
        onClose={onClose}
        onSave={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={onClose}
        onSave={vi.fn()}
      />,
    );
    const closeBtn = screen.getByRole('button', { name: /Close drawer/i });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('supports OAuth2 provider configuration with issuer_url', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i), {
      target: { value: 'OAUTH2' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'github-oauth' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'GitHub' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i), {
      target: { value: 'https://github.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i), {
      target: { value: 'gh-client-id' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_kind: 'OAUTH2',
          slug: 'github-oauth',
          display_name: 'GitHub',
        }),
        false,
      );
    });
  });

  it('renders LOCAL_ADMIN policy view when editing local-admin card', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const localAdminCard: AdminAuthCard = {
      ...existingOidcCard,
      id: 'c-local',
      provider_kind: 'LOCAL_ADMIN',
      slug: 'local-admin',
      display_name: 'Local Administrator',
    };

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={localAdminCard}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    expect(screen.getByText('Local Administrator Security Policy')).toBeDefined();
    expect(screen.getByText(/Argon2id hashing/i)).toBeDefined();

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'Local Administrator',
        }),
        true,
      );
    });
  });

  it('validates required LDAP fields: empty serverUrl, wrong protocol, missing DNs', () => {
    const onSave = vi.fn();
    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'ldap-test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'LDAP Test' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    expect(screen.getByText('Server URL is required.')).toBeDefined();
    expect(screen.getByText('Bind DN is required.')).toBeDefined();
    expect(screen.getByText('Base DN is required.')).toBeDefined();

    // Invalid protocol
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i), {
      target: { value: 'http://ldap.example.com' },
    });
    fireEvent.click(createBtn);
    expect(screen.getByText('Server URL must start with ldaps:// or ldap://')).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('displays form error when onSave throws an error', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Slug already exists'));

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'valid-slug' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Valid Name' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i), {
      target: { value: 'https://issuer.example.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i), {
      target: { value: 'client-id' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText('Slug already exists')).toBeDefined();
    });
  });

  it('edits an LDAP card with CA PEM, user filter, and replaces bind DN password', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const ldapCard: AdminAuthCard = {
      id: 'c-ldap',
      provider_kind: 'LDAP',
      slug: 'corp-ldap',
      display_name: 'Corp Directory',
      button_subtext: 'Domain login',
      icon_preset: 'lock',
      is_enabled: true,
      sort_rank: '2',
      auto_provision_users: false,
      allowed_email_domains: ['example.com'],
      has_secret: true,
      dek_kid: 'dek-ldap-1',
      last_health_status: 'HEALTHY',
      last_handshake_at: '2026-11-13T20:00:00Z',
      check_summary: 'OK',
      latency_ms: 50,
      public_config: {
        server_url: 'ldaps://ldap.example.com',
        start_tls: false,
        bind_dn: 'cn=admin,dc=example,dc=com',
        base_dn: 'ou=users,dc=example,dc=com',
        user_filter: '(mail={username})',
        ca_pem: '-----BEGIN CERTIFICATE-----TEST-----END CERTIFICATE-----',
        spki_sha256_pin: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
      },
    };

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={ldapCard}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    const userFilterInput = screen.getByLabelText<HTMLInputElement>(/User Filter/i);
    expect(userFilterInput.value).toBe('(mail={username})');
    fireEvent.change(userFilterInput, { target: { value: '(uid={username})' } });

    const caPemInput = screen.getByLabelText<HTMLTextAreaElement>(/CA Certificate/i);
    expect(caPemInput.value).toContain('TEST');
    fireEvent.change(caPemInput, { target: { value: '-----BEGIN CERTIFICATE-----UPDATED-----END CERTIFICATE-----' } });

    const replaceSecretBox = screen.getByLabelText<HTMLInputElement>(/Replace Stored Secret/i);
    fireEvent.click(replaceSecretBox);

    const bindPwdInput = screen.getByLabelText<HTMLInputElement>(/Bind DN Password/i);
    fireEvent.change(bindPwdInput, { target: { value: 'new-bind-password-secret' } });

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'Corp Directory',
          secret: 'new-bind-password-secret',
          public_config: expect.objectContaining({
            user_search_filter: '(uid={username})',
            ca_cert_pem: '-----BEGIN CERTIFICATE-----UPDATED-----END CERTIFICATE-----',
          }) as unknown,
        }),
        true,
      );
    });
  });

  it('updates metadata fields: icon preset, button subtext, auto-provision, domains, and scopes', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'full-test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Full Test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Button Subtext/i), {
      target: { value: 'Custom subtext' },
    });
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Icon Preset/i), {
      target: { value: 'globe' },
    });
    fireEvent.click(screen.getByLabelText<HTMLInputElement>(/Auto-provision Users/i));
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Allowed Email Domains/i), {
      target: { value: 'corp.com, partner.org' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i), {
      target: { value: 'https://idp.fulltest.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i), {
      target: { value: 'full-client-id' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Scopes/i), {
      target: { value: 'openid, email' },
    });
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Token Auth Method/i), {
      target: { value: 'private_key_jwt' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'full-test',
          display_name: 'Full Test',
          button_subtext: 'Custom subtext',
          icon_preset: 'globe',
          auto_provision_users: false,
          allowed_email_domains: ['corp.com', 'partner.org'],
          public_config: expect.objectContaining({
            scopes: ['openid', 'email'],
            client_auth: 'private_key_jwt',
          }) as unknown,
        }),
        false,
      );
    });
  });

  it('validates maximum lengths for display name and button subtext', () => {
    const onSave = vi.fn();

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'valid-slug' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'a'.repeat(81) },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Button Subtext/i), {
      target: { value: 'b'.repeat(121) },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    expect(
      screen.getByText('Display name must be between 1 and 80 characters.'),
    ).toBeDefined();
    expect(screen.getByText('Subtext must not exceed 120 characters.')).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('closes when clicking backdrop, but not when clicking inside dialog', () => {
    const onClose = vi.fn();

    const { container } = render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={onClose}
        onSave={vi.fn()}
      />,
    );

    const dialog = screen.getByRole('dialog');
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();

    const backdrop = container.querySelector('.auth-drawer-backdrop');
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onClose).toHaveBeenCalledTimes(1);
    }
  });

  it('validates empty slug on create and allows typing secret on create', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    // Empty slug submit
    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);
    expect(screen.getByText('Slug is required.')).toBeDefined();

    // Fill valid fields and secret
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'secret-card' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Secret Card' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i), {
      target: { value: 'https://issuer.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i), {
      target: { value: 'client-1' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client Secret/i), {
      target: { value: 'super-create-secret' },
    });

    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'secret-card',
          secret: 'super-create-secret',
        }),
        false,
      );
    });
  });

  it('handles non-Error rejection and toggles StartTLS on ldaps://', async () => {
    const onSave = vi.fn().mockRejectedValue('Generic error string');

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    // Switch to LDAP with ldaps://
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i), {
      target: { value: 'ldaps://secure-ldap.example.com' },
    });
    const startTlsBox = screen.getByLabelText<HTMLInputElement>(/StartTLS/i);
    expect(startTlsBox.checked).toBe(false);
    fireEvent.click(startTlsBox);
    expect(startTlsBox.checked).toBe(true);

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'secure-ldap' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Secure LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i), {
      target: { value: 'cn=admin' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i), {
      target: { value: 'dc=example' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText('Failed to save authentication card.')).toBeDefined();
    });
  });

  it('loads card with string scopes, private_key_jwt, and null dek_kid', () => {
    const customCard: AdminAuthCard = {
      ...existingOidcCard,
      button_subtext: null,
      dek_kid: null,
      public_config: {
        issuer_url: 'https://jwt.example.com',
        client_id: 'jwt-client',
        scopes: 'openid email',
        token_auth_method: 'private_key_jwt',
      },
    };

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={customCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLSelectElement>(/Token Auth Method/i).value).toBe(
      'private_key_jwt',
    );
    expect(screen.getByLabelText<HTMLInputElement>(/Scopes/i).value).toBe('openid email');
  });

  it('creates an LDAP card with ldap:// scheme forcing start_tls true', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i), {
      target: { value: 'insecure-ldap' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i), {
      target: { value: 'Insecure LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i), {
      target: { value: 'ldap://plain.example.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i), {
      target: { value: 'cn=admin' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i), {
      target: { value: 'dc=plain' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({
          slug: 'insecure-ldap',
          public_config: expect.objectContaining({
            transport_mode: 'starttls',
          }) as unknown,
        }),
        false,
      );
    });
  });

  it('rejects ldap:// without StartTLS when editing an existing LDAP card with start_tls false', () => {
    const onSave = vi.fn();
    const insecureCard: AdminAuthCard = {
      ...existingOidcCard,
      id: 'c-insecure',
      provider_kind: 'LDAP',
      slug: 'insecure-ldap-card',
      display_name: 'Insecure LDAP',
      public_config: {
        server_url: 'ldap://legacy.corp.internal',
        start_tls: false,
        bind_dn: 'cn=bind',
        base_dn: 'dc=corp',
      },
    };

    render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={insecureCard}
        onClose={vi.fn()}
        onSave={onSave}
      />,
    );

    const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    expect(
      screen.getByText('ldap:// requires StartTLS to be enabled.'),
    ).toBeDefined();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('handles empty public_config gracefully when loading OIDC and LDAP cards', () => {
    const emptyOidcCard: AdminAuthCard = {
      ...existingOidcCard,
      display_name: '',
      public_config: {},
    };

    const { rerender } = render(
      <AuthCardEditorDrawer
        isOpen={true}
        card={emptyOidcCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i).value).toBe('');
    expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i).value).toBe('');

    const emptyLdapCard: AdminAuthCard = {
      ...existingOidcCard,
      provider_kind: 'LDAP',
      public_config: {},
    };

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={emptyLdapCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i).value).toBe('');
    expect(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i).value).toBe('');

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={existingOidcCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i).value).toBe('okta-workforce');

    const ldapCard: AdminAuthCard = {
      ...existingOidcCard,
      id: 'c-ldap-test',
      provider_kind: 'LDAP',
      slug: 'corp-ad',
      public_config: {
        server_url: 'ldaps://ad.corp.com:636',
        start_tls: false,
        bind_dn: 'cn=admin,dc=corp',
        base_dn: 'dc=corp',
        user_filter: '(sAMAccountName={username})',
        ca_pem: '-----BEGIN CERT-----',
        spki_sha256_pin: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
      },
    };

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={ldapCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i).value).toBe('corp-ad');

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i).value).toBe('');
  });

  describe('Google OAuth JSON Importer (KB-AUTH-JSON / KANBA-185)', () => {
    const validGoogleWebJson = JSON.stringify({
      web: {
        client_id: '1234567890-testclientid.apps.googleusercontent.com',
        project_id: 'test-google-project',
        auth_uri: 'https://accounts.google.com/o/oauth2/auth',
        token_uri: 'https://oauth2.googleapis.com/token',
        auth_provider_x509_cert_url: 'https://www.googleapis.com/oauth2/v1/certs',
        client_secret: 'GOCSPX-supersecretkey1234567890',
        redirect_uris: [
          'http://localhost:3000/api/v1/auth/oidc/google-oauth/callback',
        ],
        javascript_origins: ['http://localhost:3000'],
      },
    });

    const mismatchGoogleWebJson = JSON.stringify({
      web: {
        client_id: '1234567890-mismatch.apps.googleusercontent.com',
        project_id: 'test-google-project',
        auth_uri: 'https://accounts.google.com/o/oauth2/auth',
        token_uri: 'https://oauth2.googleapis.com/token',
        client_secret: 'GOCSPX-supersecretkey1234567890',
        redirect_uris: [
          'https://other-domain.example.com/oauth2callback',
        ],
      },
    });

    const installedClientJson = JSON.stringify({
      installed: {
        client_id: 'desktop-client-id.apps.googleusercontent.com',
        project_id: 'desktop-project',
        client_secret: 'GOCSPX-desktopsecret',
        redirect_uris: ['http://localhost'],
      },
    });

    it('renders Google JSON dropzone and paste toggle for OIDC provider', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByTestId('google-json-import-section')).toBeDefined();
      expect(screen.getByTestId('google-json-dropzone')).toBeDefined();
      expect(screen.getByTestId('google-json-upload-btn')).toBeDefined();
      expect(screen.getByTestId('google-json-paste-toggle')).toBeDefined();
    });

    it('toggles paste textarea and parses valid Google JSON with matched redirect URI', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const pasteToggle = screen.getByTestId('google-json-paste-toggle');
      fireEvent.click(pasteToggle);

      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      fireEvent.change(textarea, { target: { value: validGoogleWebJson } });

      const applyBtn = screen.getByTestId('google-json-apply-btn');
      fireEvent.click(applyBtn);

      await waitFor(() => {
        expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i).value).toBe(
          '1234567890-testclientid.apps.googleusercontent.com',
        );
      });

      expect(screen.getByLabelText<HTMLInputElement>(/Client Secret/i).value).toBe(
        'GOCSPX-supersecretkey1234567890',
      );
      expect(screen.getByTestId('google-json-redirect-ok')).toBeDefined();
    });

    it('shows warning and details when redirect URI does not match expected callback', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      fireEvent.change(textarea, { target: { value: mismatchGoogleWebJson } });
      fireEvent.click(screen.getByTestId('google-json-apply-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('google-json-redirect-warning')).toBeDefined();
      });

      expect(screen.getByText(/Authorized Redirect URI mismatch/i)).toBeDefined();
      expect(screen.getByText(/URIs found in Google JSON \(1\)/i)).toBeDefined();
    });

    it('rejects installed client JSON with informative error message', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      fireEvent.change(textarea, { target: { value: installedClientJson } });
      fireEvent.click(screen.getByTestId('google-json-apply-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('google-json-error')).toBeDefined();
      });

      expect(screen.getByTestId('google-json-error').textContent).toContain(
        'Google OAuth JSON is for an Installed/Desktop client',
      );
    });

    it('rejects oversized JSON exceeding 32KB payload limit', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const hugePayload = ' '.repeat(35000);
      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      fireEvent.change(textarea, { target: { value: hugePayload } });
      fireEvent.click(screen.getByTestId('google-json-apply-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('google-json-error')).toBeDefined();
      });

      expect(screen.getByTestId('google-json-error').textContent).toContain(
        'exceeds maximum allowed size of 32,768 bytes',
      );
    });

    it('handles invalid Google JSON structures: missing web, missing client_id/secret, untrusted endpoints', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      const applyBtn = screen.getByTestId('google-json-apply-btn');

      // 1. Missing web object
      fireEvent.change(textarea, { target: { value: JSON.stringify({ other: true }) } });
      fireEvent.click(applyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('google-json-error').textContent).toContain("must contain a top-level 'web'");
      });

      // 2. Missing client_id
      fireEvent.change(textarea, { target: { value: JSON.stringify({ web: { client_secret: 'sec' } }) } });
      fireEvent.click(applyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('google-json-error').textContent).toContain("'client_id' is missing or invalid");
      });

      // 3. Missing client_secret
      fireEvent.change(textarea, { target: { value: JSON.stringify({ web: { client_id: 'cid' } }) } });
      fireEvent.click(applyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('google-json-error').textContent).toContain("'client_secret' is missing or invalid");
      });

      // 4. Untrusted auth_uri
      fireEvent.change(textarea, {
        target: {
          value: JSON.stringify({
            web: { client_id: 'cid', client_secret: 'sec', auth_uri: 'https://evil.com/auth' },
          }),
        },
      });
      fireEvent.click(applyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('google-json-error').textContent).toContain("does not match allowed Google authorization endpoints");
      });

      // 5. Untrusted token_uri
      fireEvent.change(textarea, {
        target: {
          value: JSON.stringify({
            web: {
              client_id: 'cid',
              client_secret: 'sec',
              auth_uri: 'https://accounts.google.com/o/oauth2/auth',
              token_uri: 'https://evil.com/token',
            },
          }),
        },
      });
      fireEvent.click(applyBtn);
      await waitFor(() => {
        expect(screen.getByTestId('google-json-error').textContent).toContain("does not match allowed Google token endpoints");
      });
    });

    it('supports drag/drop and file input for Google JSON client secrets', async () => {
      const validJson = JSON.stringify({
        web: {
          client_id: 'file-client-id.apps.googleusercontent.com',
          client_secret: 'file-secret-value',
          auth_uri: 'https://accounts.google.com/o/oauth2/auth',
          token_uri: 'https://oauth2.googleapis.com/token',
          redirect_uris: [`${window.location.origin}/api/v1/auth/oidc/google-oauth/callback`],
        },
      });

      vi.spyOn(FileReader.prototype, 'readAsText').mockImplementation(function (this: FileReader) {
        Object.defineProperty(this, 'result', { value: validJson, configurable: true });
        this.onload?.({ target: this } as ProgressEvent<FileReader>);
      });

      const { container } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));

      const dropzone = screen.getByTestId('google-json-dropzone');
      // Drag over activates
      fireEvent.dragOver(dropzone);
      expect(dropzone.className).toContain('auth-google-json-dropzone--active');

      // Drag leave deactivates
      fireEvent.dragLeave(dropzone);
      expect(dropzone.className).not.toContain('auth-google-json-dropzone--active');

      // Drop file
      const fakeFile = new File(['content'], 'client_secret.json', { type: 'application/json' });
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [fakeFile],
        },
      });

      await waitFor(() => {
        expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i).value).toBe(
          'file-client-id.apps.googleusercontent.com',
        );
      });

      // File input change
      const fileInput = container.querySelector('input[type="file"]');
      expect(fileInput).toBeTruthy();
      if (fileInput) {
        fireEvent.change(fileInput, { target: { files: [fakeFile] } });
      }

      await waitFor(() => {
        expect(screen.getByLabelText<HTMLInputElement>(/Client Secret/i).value).toBe('file-secret-value');
      });
    });

    it('copies expected callback URL on mismatch warning', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      const mismatchJson = JSON.stringify({
        web: {
          client_id: 'mismatch-id',
          client_secret: 'mismatch-sec',
          auth_uri: 'https://accounts.google.com/o/oauth2/auth',
          token_uri: 'https://oauth2.googleapis.com/token',
          redirect_uris: ['https://other-domain.com/callback'],
        },
      });

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const textarea = screen.getByLabelText(/Paste Google Cloud Console client JSON/i);
      fireEvent.change(textarea, { target: { value: mismatchJson } });
      fireEvent.click(screen.getByTestId('google-json-apply-btn'));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Copy Expected Callback URL/i })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: /Copy Expected Callback URL/i }));
      expect(writeTextMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/auth/oidc/google-oauth/callback'),
      );
    });

    it('handles keyboard escape and tab key focus trap', () => {
      const onClose = vi.fn();
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={onClose}
          onSave={vi.fn()}
        />,
      );

      // Escape key closes drawer
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalled();

      // Tab key navigation wraps
      fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
      fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    });

    it('edits and saves LOCAL_ADMIN card preserving config', async () => {
      const localAdminCard: AdminAuthCard = {
        id: 'c-local',
        provider_kind: 'LOCAL_ADMIN',
        slug: 'local-admin',
        display_name: 'Local Root Admin',
        button_subtext: 'Break-glass access',
        icon_preset: 'key',
        is_enabled: true,
        sort_rank: '0',
        auto_provision_users: false,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: 0,
        public_config: {
          require_totp: true,
        },
      };

      const onSave = vi.fn<AuthCardEditorDrawerProps['onSave']>().mockResolvedValue(undefined);
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={localAdminCard}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      expect(screen.getByText('Local Administrator Security Policy')).toBeDefined();

      const saveBtn = screen.getByRole('button', { name: /Save Changes/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalled();
      });
      const firstCall = onSave.mock.calls[0];
      expect(firstCall).toBeDefined();
      if (firstCall) {
        const [savedCard, isSecretReplaced] = firstCall;
        expect(savedCard.display_name).toBe('Local Root Admin');
        const localConfig = savedCard.public_config as { require_totp?: boolean } | undefined;
        expect(localConfig?.require_totp).toBe(true);
        expect(isSecretReplaced).toBe(true);
      }
    });

    it('creates LDAP card with ldap:// scheme, startTls, and restricted groups', async () => {
      const onSave = vi.fn<AuthCardEditorDrawerProps['onSave']>().mockResolvedValue(undefined);
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      // Change provider to LDAP
      fireEvent.change(screen.getByLabelText(/Provider Kind/i), { target: { value: 'LDAP' } });

      fireEvent.change(screen.getByLabelText(/Slug Identifier/i), { target: { value: 'corp-ad' } });
      fireEvent.change(screen.getByLabelText(/Display Name/i), { target: { value: 'Active Directory' } });
      fireEvent.change(screen.getByLabelText(/Server URL/i), { target: { value: 'ldap://ad.corp.example.com:389' } });
      fireEvent.change(screen.getByLabelText(/^Bind DN$/i), { target: { value: 'cn=bind,dc=example,dc=com' } });
      fireEvent.change(screen.getByLabelText(/^Base DN$/i), { target: { value: 'dc=example,dc=com' } });
      fireEvent.change(screen.getByLabelText(/Bind DN Password/i), { target: { value: 'SuperSecretPass123!' } });

      // Change access policy to restricted
      fireEvent.change(screen.getByLabelText(/Access Policy/i), { target: { value: 'restricted' } });
      fireEvent.change(screen.getByLabelText(/Admin Groups/i), { target: { value: 'Admins, SuperUsers' } });
      fireEvent.change(screen.getByLabelText(/User Groups/i), { target: { value: 'Engineers, Product' } });

      const saveBtn = screen.getByRole('button', { name: /Create Card/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalled();
      });
      const ldapCall = onSave.mock.calls[0];
      expect(ldapCall).toBeDefined();
      if (ldapCall) {
        const [savedLdap, isSecretReplaced] = ldapCall;
        const ldapPayload = savedLdap as CreateAuthCardPayload;
        expect(ldapPayload.provider_kind).toBe('LDAP');
        expect(ldapPayload.slug).toBe('corp-ad');
        expect(ldapPayload.secret).toBe('SuperSecretPass123!');
        const ldapConfig = ldapPayload.public_config as {
          kind?: string;
          transport_mode?: string;
          access_mode?: string;
          admin_groups?: string[];
          user_groups?: string[];
        };
        expect(ldapConfig.kind).toBe('LDAP');
        expect(ldapConfig.transport_mode).toBe('starttls');
        expect(ldapConfig.access_mode).toBe('group_restricted');
        expect(ldapConfig.admin_groups).toEqual(['Admins', 'SuperUsers']);
        expect(ldapConfig.user_groups).toEqual(['Engineers', 'Product']);
        expect(isSecretReplaced).toBe(false);
      }
    });

    it('initializes restricted mode and allowlists from existing card config', () => {
      const restrictedCard: AdminAuthCard = {
        id: 'c-restricted',
        provider_kind: 'OIDC',
        slug: 'restricted-oidc',
        display_name: 'Restricted OIDC',
        button_subtext: null,
        icon_preset: 'shield',
        is_enabled: true,
        sort_rank: '2',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: 10,
        public_config: {
          access_mode: 'group_restricted',
          admin_allowlist: ['admin@example.com'],
          user_allowlist: ['dev1@example.com', 'dev2@example.com'],
          admin_groups: ['CorpAdmins'],
          user_groups: ['CorpUsers'],
        },
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={restrictedCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const accessPolicySelect = screen.getByLabelText<HTMLSelectElement>(/Access Policy/i);
      expect(accessPolicySelect.value).toBe('restricted');
      expect(screen.getByLabelText<HTMLInputElement>(/Admin Allowlist/i).value).toBe('admin@example.com');
      expect(screen.getByLabelText<HTMLInputElement>(/User Allowlist/i).value).toBe('dev1@example.com, dev2@example.com');
    });

    it('traps Tab and Shift+Tab navigation between first and last focusable elements', () => {
      const { container } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const focusable = container.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      expect(focusable.length).toBeGreaterThan(1);

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      // Shift+Tab from first element wraps to last
      if (first) {
        first.focus();
        fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
        expect(document.activeElement).toBe(last);
      }

      // Tab from last element wraps to first
      if (last) {
        last.focus();
        fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
        expect(document.activeElement).toBe(first);
      }
    });

    it('initializes fallback field names for OIDC issuer_url and LDAP server_url/bind_dn', () => {
      const fallbackOidcCard: AdminAuthCard = {
        id: 'c-fallback-oidc',
        provider_kind: 'OIDC',
        slug: 'fallback-oidc',
        display_name: 'Fallback OIDC',
        button_subtext: null,
        icon_preset: 'key',
        is_enabled: true,
        sort_rank: '3',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: '',
        latency_ms: null,
        public_config: {
          issuer_url: 'https://fallback.auth.com',
          client_id: 'cid-999',
        },
      };

      const { unmount } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={fallbackOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i).value).toBe('https://fallback.auth.com');
      unmount();

      const fallbackLdapCard: AdminAuthCard = {
        id: 'c-fallback-ldap',
        provider_kind: 'LDAP',
        slug: 'fallback-ldap',
        display_name: 'Fallback LDAP',
        button_subtext: null,
        icon_preset: 'directory',
        is_enabled: true,
        sort_rank: '4',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: '',
        latency_ms: null,
        public_config: {
          server_url: 'ldaps://corp.example.internal:636',
          bind_dn: 'cn=svc,dc=corp,dc=internal',
        },
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={fallbackLdapCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i).value).toBe('ldaps://corp.example.internal:636');
      expect(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i).value).toBe('cn=svc,dc=corp,dc=internal');
    });

    it('copies OAuth callback URL to clipboard and handles unchecking replace secret', () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      const oidcCardWithSecret: AdminAuthCard = {
        id: 'c-secret',
        provider_kind: 'OIDC',
        slug: 'corp-oidc',
        display_name: 'Corp OIDC',
        button_subtext: null,
        icon_preset: 'shield',
        is_enabled: true,
        sort_rank: '1',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: true,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: '',
        latency_ms: null,
        public_config: {
          client_id: 'corp-client-1',
          issuer: 'https://auth.corp.com',
        },
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={oidcCardWithSecret}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const copyBtn = screen.getByTestId('copy-callback-url-btn');
      fireEvent.click(copyBtn);
      expect(writeTextMock).toHaveBeenCalledWith(
        `${window.location.origin}/api/v1/auth/oidc/corp-oidc/callback`
      );

      // Uncheck replace secret clears secret input
      const replaceSecretCheckbox = screen.getByLabelText(/Replace Stored Secret/i);
      fireEvent.click(replaceSecretCheckbox);
      expect(replaceSecretCheckbox.getAttribute('checked')).toBeNull();
    });

    it('covers restricted access policy mode and LDAP submission with custom attributes and CA PEM', async () => {
      const saveMock = vi.fn().mockResolvedValue(undefined);
      const restrictedLdapCard: AdminAuthCard = {
        id: 'c-rest-ldap',
        provider_kind: 'LDAP',
        slug: 'rest-ldap',
        display_name: 'Restricted LDAP',
        button_subtext: 'Internal corp only',
        icon_preset: 'directory',
        is_enabled: true,
        sort_rank: '2',
        auto_provision_users: false,
        allowed_email_domains: ['corp.internal'],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: '',
        latency_ms: null,
        public_config: {
          access_mode: 'group_restricted',
          admin_groups: ['Domain Admins'],
          user_groups: ['Corp Users'],
          url: 'ldap://ldap.corp.internal:389',
          transport_mode: 'starttls',
          service_bind_dn: 'cn=admin,dc=corp,dc=internal',
          base_dn: 'dc=corp,dc=internal',
          user_search_filter: '(sAMAccountName={username})',
          subject_attribute: 'entryUUID',
          email_attribute: 'userPrincipalName',
          display_name_attribute: 'cn',
          ca_cert_pem: '-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----',
          spki_sha256_pins: ['a'.repeat(64)],
        },
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={restrictedLdapCard}
          onClose={vi.fn()}
          onSave={saveMock}
        />,
      );

      // Access policy mode is restricted
      const policySelect = screen.getByLabelText<HTMLSelectElement>(/Access Policy/i);
      expect(policySelect.value).toBe('restricted');

      // Submit edit
      const form = screen.getByRole('dialog').querySelector('form');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(saveMock).toHaveBeenCalled();
      });
    });

    it('covers editing LOCAL_ADMIN card policy view and save', async () => {
      const saveMock = vi.fn().mockResolvedValue(undefined);
      const localAdminCard: AdminAuthCard = {
        id: 'c-local-admin',
        provider_kind: 'LOCAL_ADMIN',
        slug: 'local-admin',
        display_name: 'Local Administrator',
        button_subtext: 'Emergency Break-Glass',
        icon_preset: 'key',
        is_enabled: true,
        sort_rank: '0',
        auto_provision_users: false,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: '',
        latency_ms: null,
        public_config: {},
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={localAdminCard}
          onClose={vi.fn()}
          onSave={saveMock}
        />,
      );

      expect(screen.getByText('Local Administrator Security Policy')).toBeDefined();
      const form = screen.getByRole('dialog').querySelector('form');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(saveMock).toHaveBeenCalled();
      });
    });
  });
});
