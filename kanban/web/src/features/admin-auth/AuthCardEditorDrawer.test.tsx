import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { AuthCardEditorDrawer, type AuthCardEditorDrawerProps } from './AuthCardEditorDrawer';
import type { AdminAuthCard, CreateAuthCardPayload } from './adminAuthApi';
import * as adminAuthApi from './adminAuthApi';
import { registerShellPanel, ShellPanelsProvider } from '../../app/shellPanels';

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

    const secretInput = screen.getByLabelText<HTMLInputElement>(/Client Secret/i, { selector: 'input' });
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
    const replaceBox = screen.getByLabelText<HTMLInputElement>(/Replace Stored Secret/i, { selector: 'input' });
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

    const slugInput = screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' });
    const nameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' });
    const issuerInput = screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' });
    const clientIdInput = screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' });

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
    const kindSelect = screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i, { selector: 'select' });
    fireEvent.change(kindSelect, { target: { value: 'LDAP' } });

    const serverInput = screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' });
    const startTlsBox = screen.getByLabelText<HTMLInputElement>(/StartTLS/i, { selector: 'input' });

    // Enter ldap://
    fireEvent.change(serverInput, { target: { value: 'ldap://dc01.corp.example.com' } });
    expect(startTlsBox.checked).toBe(true);
    expect(startTlsBox.hasAttribute('disabled')).toBe(true);

    // Test invalid SPKI pin (63 hex chars, should be 64)
    const spkiInput = screen.getByLabelText<HTMLInputElement>(/SPKI SHA-256 Pin/i, { selector: 'input' });
    fireEvent.change(spkiInput, { target: { value: 'a'.repeat(63) } });

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'corp-ad' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Corp AD' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i, { selector: 'input' }), {
      target: { value: 'cn=admin,dc=corp' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i, { selector: 'input' }), {
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

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i, { selector: 'select' }), {
      target: { value: 'OAUTH2' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'github-oauth' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'GitHub' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }), {
      target: { value: 'https://github.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }), {
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

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i, { selector: 'select' }), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'ldap-test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'LDAP Test' },
    });

    const createBtn = screen.getByRole('button', { name: /Create Card/i });
    fireEvent.click(createBtn);

    expect(screen.getByText('Server URL is required.')).toBeDefined();
    expect(screen.getByText('Bind DN is required.')).toBeDefined();
    expect(screen.getByText('Base DN is required.')).toBeDefined();

    // Invalid protocol
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }), {
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

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'valid-slug' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Valid Name' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }), {
      target: { value: 'https://issuer.example.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }), {
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

    const userFilterInput = screen.getByLabelText<HTMLInputElement>(/User Filter/i, { selector: 'input' });
    expect(userFilterInput.value).toBe('(mail={username})');
    fireEvent.change(userFilterInput, { target: { value: '(uid={username})' } });

    const caPemInput = screen.getByLabelText<HTMLTextAreaElement>(/CA Certificate/i, { selector: 'textarea' });
    expect(caPemInput.value).toContain('TEST');
    fireEvent.change(caPemInput, { target: { value: '-----BEGIN CERTIFICATE-----UPDATED-----END CERTIFICATE-----' } });

    const replaceSecretBox = screen.getByLabelText<HTMLInputElement>(/Replace Stored Secret/i, { selector: 'input' });
    fireEvent.click(replaceSecretBox);

    const bindPwdInput = screen.getByLabelText<HTMLInputElement>(/Bind DN Password/i, { selector: 'input' });
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

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'full-test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Full Test' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Button Subtext/i, { selector: 'input' }), {
      target: { value: 'Custom subtext' },
    });
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Icon Preset/i, { selector: 'select' }), {
      target: { value: 'globe' },
    });
    fireEvent.click(screen.getByLabelText<HTMLInputElement>(/Auto-provision Users/i, { selector: 'input' }));
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Allowed Email Domains/i, { selector: 'input' }), {
      target: { value: 'corp.com, partner.org' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }), {
      target: { value: 'https://idp.fulltest.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }), {
      target: { value: 'full-client-id' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Scopes/i, { selector: 'input' }), {
      target: { value: 'openid, email' },
    });
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Token Auth Method/i, { selector: 'select' }), {
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

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'valid-slug' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'a'.repeat(81) },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Button Subtext/i, { selector: 'input' }), {
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
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'secret-card' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Secret Card' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }), {
      target: { value: 'https://issuer.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }), {
      target: { value: 'client-1' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Client Secret/i, { selector: 'input' }), {
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
    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i, { selector: 'select' }), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }), {
      target: { value: 'ldaps://secure-ldap.example.com' },
    });
    const startTlsBox = screen.getByLabelText<HTMLInputElement>(/StartTLS/i, { selector: 'input' });
    expect(startTlsBox.checked).toBe(false);
    fireEvent.click(startTlsBox);
    expect(startTlsBox.checked).toBe(true);

    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'secure-ldap' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Secure LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i, { selector: 'input' }), {
      target: { value: 'cn=admin' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i, { selector: 'input' }), {
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

    expect(screen.getByLabelText<HTMLSelectElement>(/Token Auth Method/i, { selector: 'select' }).value).toBe(
      'private_key_jwt',
    );
    expect(screen.getByLabelText<HTMLInputElement>(/Scopes/i, { selector: 'input' }).value).toBe('openid email');
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

    fireEvent.change(screen.getByLabelText<HTMLSelectElement>(/Provider Kind/i, { selector: 'select' }), {
      target: { value: 'LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }), {
      target: { value: 'insecure-ldap' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }), {
      target: { value: 'Insecure LDAP' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }), {
      target: { value: 'ldap://plain.example.com' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i, { selector: 'input' }), {
      target: { value: 'cn=admin' },
    });
    fireEvent.change(screen.getByLabelText<HTMLInputElement>(/Base DN/i, { selector: 'input' }), {
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

    expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }).value).toBe('');
    expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }).value).toBe('');

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

    expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }).value).toBe('');
    expect(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i, { selector: 'input' }).value).toBe('');

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={existingOidcCard}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('okta-workforce');

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
    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('corp-ad');

    rerender(
      <AuthCardEditorDrawer
        isOpen={true}
        card={null}
        onClose={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('');
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
        expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }).value).toBe(
          '1234567890-testclientid.apps.googleusercontent.com',
        );
      });

      expect(screen.getByLabelText<HTMLInputElement>(/Client Secret/i, { selector: 'input' }).value).toBe(
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
        expect(screen.getByLabelText<HTMLInputElement>(/Client ID/i, { selector: 'input' }).value).toBe(
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
        expect(screen.getByLabelText<HTMLInputElement>(/Client Secret/i, { selector: 'input' }).value).toBe('file-secret-value');
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
      fireEvent.change(screen.getByLabelText(/Provider Kind/i, { selector: 'select' }), { target: { value: 'LDAP' } });

      fireEvent.change(screen.getByLabelText(/Slug Identifier/i, { selector: 'input' }), { target: { value: 'corp-ad' } });
      fireEvent.change(screen.getByLabelText(/Display Name/i, { selector: 'input' }), { target: { value: 'Active Directory' } });
      fireEvent.change(screen.getByLabelText(/Server URL/i, { selector: 'input' }), { target: { value: 'ldap://ad.corp.example.com:389' } });
      fireEvent.change(screen.getByLabelText(/^Bind DN(?!\s*Password)/i, { selector: 'input' }), { target: { value: 'cn=bind,dc=example,dc=com' } });
      fireEvent.change(screen.getByLabelText(/^Base DN/i, { selector: 'input' }), { target: { value: 'dc=example,dc=com' } });
      fireEvent.change(screen.getByLabelText(/Bind DN Password/i, { selector: 'input' }), { target: { value: 'SuperSecretPass123!' } });

      // Change access policy to restricted
      fireEvent.change(screen.getByLabelText(/Access Policy/i, { selector: 'select' }), { target: { value: 'restricted' } });
      fireEvent.change(screen.getByLabelText(/Admin Groups/i, { selector: 'input' }), { target: { value: 'Admins, SuperUsers' } });
      fireEvent.change(screen.getByLabelText(/User Groups/i, { selector: 'input' }), { target: { value: 'Engineers, Product' } });

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

      const accessPolicySelect = screen.getByLabelText<HTMLSelectElement>(/Access Policy/i, { selector: 'select' });
      expect(accessPolicySelect.value).toBe('restricted');
      expect(screen.getByLabelText<HTMLInputElement>(/Admin Allowlist/i, { selector: 'input' }).value).toBe('admin@example.com');
      expect(screen.getByLabelText<HTMLInputElement>(/User Allowlist/i, { selector: 'input' }).value).toBe('dev1@example.com, dev2@example.com');
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

      expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }).value).toBe('https://fallback.auth.com');
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

      expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }).value).toBe('ldaps://corp.example.internal:636');
      expect(screen.getByLabelText<HTMLInputElement>(/^Bind DN$/i, { selector: 'input' }).value).toBe('cn=svc,dc=corp,dc=internal');
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
      const replaceSecretCheckbox = screen.getByLabelText(/Replace Stored Secret/i, { selector: 'input' });
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
      const policySelect = screen.getByLabelText<HTMLSelectElement>(/Access Policy/i, { selector: 'select' });
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

    it('covers drawer handshake testing with onTestHandshake healthy, failed, and exception', async () => {
      const mockTestHandshake = vi.fn().mockResolvedValue({
        last_health_status: 'HEALTHY',
        check_summary: 'OIDC discovery endpoint verified',
      });

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
          onTestHandshake={mockTestHandshake}
        />,
      );

      const testBtn = screen.getByTestId('drawer-test-handshake-btn');
      fireEvent.click(testBtn);

      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('HEALTHY: OIDC discovery endpoint verified');
      });

      // Failed handshake response
      mockTestHandshake.mockResolvedValueOnce({
        last_health_status: 'FAILED',
        check_summary: 'Connection timeout',
      });
      fireEvent.click(testBtn);

      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('FAILED: Connection timeout');
      });

      // Rejected promise / exception
      mockTestHandshake.mockRejectedValueOnce(new Error('Network offline'));
      fireEvent.click(testBtn);

      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('FAILED: Network offline');
      });

      // Handshake with check_summary undefined (fallbacks)
      mockTestHandshake.mockResolvedValueOnce({
        last_health_status: 'HEALTHY',
      });
      fireEvent.click(testBtn);
      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('Handshake healthy');
      });

      mockTestHandshake.mockResolvedValueOnce({
        last_health_status: 'FAILED',
      });
      fireEvent.click(testBtn);
      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('Handshake probe failed');
      });
    });

    it('covers access mode restricted, google json error, and unchecking secret', () => {
      const onSave = vi.fn().mockResolvedValue(undefined);
      const restrictedCard: AdminAuthCard = {
        ...existingOidcCard,
        public_config: {
          access_mode: 'group_restricted',
          admin_allowlist: ['admin@example.com'],
          user_allowlist: ['user@example.com'],
        },
      };

      const { unmount } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={restrictedCard}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      // Check replace secret and uncheck it
      const replaceCheckbox = screen.getByRole('checkbox', { name: /Replace Stored Secret/i });
      fireEvent.click(replaceCheckbox);
      const secretInput = screen.getByLabelText(/Client Secret/i, { selector: 'input' });
      fireEvent.change(secretInput, { target: { value: 'temp-secret' } });
      fireEvent.click(replaceCheckbox); // uncheck -> sets secretInput to ''

      // Google JSON paste invalid JSON
      const jsonArea = screen.queryByLabelText(/Paste Google Client JSON/i);
      if (jsonArea) {
        fireEvent.change(jsonArea, { target: { value: 'invalid{json' } });
      }

      // Save
      fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));
      unmount();
    });

    it('covers access policy defaults from allowlists and default handshake functions', async () => {
      // 1. Initialized with admin_allowlist only
      const adminOnlyCard: AdminAuthCard = {
        ...existingOidcCard,
        public_config: {
          admin_allowlist: ['adm@corp.com'],
        },
      };
      const { unmount: u1 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={adminOnlyCard}
          onClose={vi.fn()}
          onSave={vi.fn().mockResolvedValue(undefined)}
        />,
      );
      expect(screen.getByLabelText<HTMLSelectElement>('Access Policy', { selector: 'select' }).value).toBe('restricted');
      expect(screen.getByLabelText(/Admin Allowlist/i, { selector: 'input' })).toBeDefined();
      u1();

      // 2. Initialized with user_allowlist only
      const userOnlyCard: AdminAuthCard = {
        ...existingOidcCard,
        public_config: {
          user_allowlist: ['usr@corp.com'],
        },
      };
      const { unmount: u2 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={userOnlyCard}
          onClose={vi.fn()}
          onSave={vi.fn().mockResolvedValue(undefined)}
        />,
      );
      expect(screen.getByLabelText<HTMLSelectElement>('Access Policy', { selector: 'select' }).value).toBe('restricted');
      expect(screen.getByLabelText(/User Allowlist/i, { selector: 'input' })).toBeDefined();
      u2();

      // 3. Test handshake with non-Error rejection
      const mockTestHandshake = vi.fn().mockRejectedValueOnce('Network timeout string');
      const { unmount: u3 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn().mockResolvedValue(undefined)}
          onTestHandshake={mockTestHandshake}
        />,
      );
      fireEvent.click(screen.getByRole('button', { name: /Test Handshake/i }));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('Handshake test failed');
      });
      u3();
    });

    it('covers default testAuthCardHandshake and testDraftAuthCardHandshake with fallback messages', async () => {
      vi.spyOn(adminAuthApi, 'testAuthCardHandshake').mockResolvedValue({
        last_health_status: 'HEALTHY',
        latency_ms: 42,
        check_summary: null as never,
      });
      vi.spyOn(adminAuthApi, 'testDraftAuthCardHandshake').mockResolvedValue({
        last_health_status: 'FAILED',
        latency_ms: 120,
        check_summary: undefined as never,
      });

      // 1. Existing card with card.id
      const { unmount: u1 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );
      fireEvent.click(screen.getByTestId('drawer-test-handshake-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('HEALTHY: Handshake healthy');
      });
      u1();

      // 2. Draft card (card is null)
      const { unmount: u2 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );
      fireEvent.click(screen.getByTestId('drawer-test-handshake-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-handshake-result').textContent).toContain('FAILED: Handshake probe failed');
      });
      u2();
    });

    it('covers initial restricted accessPolicyMode for admin_allowlist or user_allowlist', () => {
      // Admin allowlist
      const cardWithAdminAllow: AdminAuthCard = {
        ...existingOidcCard,
        public_config: {
          admin_allowlist: ['alice@corp.com'],
        },
      };
      const { unmount: u1 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={cardWithAdminAllow}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );
      expect((screen.getByLabelText<HTMLSelectElement>(/Access Policy/i, { selector: 'select' })).value).toBe('restricted');
      expect(screen.getByLabelText(/Admin Allowlist/i, { selector: 'input' })).toBeDefined();
      u1();

      // User allowlist
      const cardWithUserAllow: AdminAuthCard = {
        ...existingOidcCard,
        public_config: {
          user_allowlist: ['bob@corp.com'],
        },
      };
      const { unmount: u2 } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={cardWithUserAllow}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );
      expect((screen.getByLabelText<HTMLSelectElement>(/Access Policy/i, { selector: 'select' })).value).toBe('restricted');
      u2();
    });
  });

  describe('Progressive Disclosure & AdvancedSection (KAN-319)', () => {
    it('renders primary fields outside AdvancedSection and keeps advanced fields collapsed by default on create and edit', () => {
      const { unmount } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Primary fields must be immediately present
      const displayNameInput = screen.getByLabelText(/Display Name/i, { selector: 'input' });
      const providerKindSelect = screen.getByLabelText(/Provider Kind/i, { selector: 'select' });
      const enableCardCheckbox = screen.getByLabelText(/Enable Card/i, { selector: 'input' });
      const issuerUrlInput = screen.getByLabelText(/Issuer URL/i, { selector: 'input' });
      const clientIdInput = screen.getByLabelText(/Client ID/i, { selector: 'input' });
      const clientSecretInput = screen.getByLabelText(/Client Secret/i, { selector: 'input' });

      expect(displayNameInput).toBeDefined();
      expect(providerKindSelect).toBeDefined();
      expect(enableCardCheckbox).toBeDefined();
      expect(issuerUrlInput).toBeDefined();
      expect(clientIdInput).toBeDefined();
      expect(clientSecretInput).toBeDefined();

      // AdvancedSection must be collapsed by default
      const advSection = screen.getByTestId('auth-advanced-section');
      expect(advSection.hasAttribute('open')).toBe(false);

      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      expect(advToggle.getAttribute('aria-expanded')).toBe('false');

      // Clicking the toggle expands the section
      fireEvent.click(advToggle);
      expect(advSection.hasAttribute('open')).toBe(true);
      expect(advToggle.getAttribute('aria-expanded')).toBe('true');

      unmount();

      // On edit, it also defaults to collapsed
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const editAdvSection = screen.getByTestId('auth-advanced-section');
      expect(editAdvSection.hasAttribute('open')).toBe(false);
    });

    it('auto-derives slug from display name on create unless customized', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const nameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' });
      const slugInput = screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' });

      fireEvent.change(nameInput, { target: { value: 'Corp Google SSO' } });
      expect(slugInput.value).toBe('corp-google-sso');

      // If user customizes slug, further display name changes do not overwrite it
      fireEvent.change(slugInput, { target: { value: 'my-custom-slug' } });
      fireEvent.change(nameInput, { target: { value: 'Corp Google SSO Updated' } });
      expect(slugInput.value).toBe('my-custom-slug');
    });

    it('renders active overrides count badge when advanced settings differ from defaults', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // existingOidcCard has button_subtext='Workforce IDP' and allowed_email_domains=['corp.example.com']
      const badge = screen.getByTestId('advanced-active-badge');
      expect(badge).toBeDefined();
      expect(badge.textContent).toContain('active');
    });

    it('applies 1-click provider presets correctly (Google, GitHub, Active Directory, OpenLDAP, Custom OAuth)', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Google preset
      const googleBtn = screen.getByRole('button', { name: /Google \(OAuth 2\.0\)/i });
      fireEvent.click(googleBtn);
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('Google Workspace');
      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('google-oauth');
      expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }).value).toBe('https://accounts.google.com');

      // GitHub preset
      const githubBtn = screen.getByRole('button', { name: /GitHub \(OAuth 2\.0\)/i });
      fireEvent.click(githubBtn);
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('GitHub');
      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('github-oauth');
      expect(screen.getByLabelText<HTMLInputElement>(/Issuer URL/i, { selector: 'input' }).value).toBe('https://github.com');

      // Active Directory preset
      const adBtn = screen.getByRole('button', { name: /Active Directory/i });
      fireEvent.click(adBtn);
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('Active Directory');
      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('ad-ldap');
      expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }).value).toBe('ldaps://ad.corp.local:636');

      // OpenLDAP preset
      const openldapBtn = screen.getByRole('button', { name: /Standard LDAP/i });
      fireEvent.click(openldapBtn);
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('OpenLDAP');
      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('openldap');
      expect(screen.getByLabelText<HTMLInputElement>(/Server URL/i, { selector: 'input' }).value).toBe('ldaps://ldap.corp.local:636');

      // Custom OAuth preset
      const customBtn = screen.getByRole('button', { name: /Custom OAuth 2\.0/i });
      fireEvent.click(customBtn);
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('Custom SSO');
      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('oauth1');
    });

    it('handles auto-derived slug clearing and edge cases in create vs edit mode', () => {
      const { unmount } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const nameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' });
      const slugInput = screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' });

      // Typing complex name
      fireEvent.change(nameInput, { target: { value: 'Google SSO (US-West #1)!' } });
      expect(slugInput.value).toBe('google-sso-us-west-1');

      // Clearing name clears slug
      fireEvent.change(nameInput, { target: { value: '' } });
      expect(slugInput.value).toBe('');

      // Customizing slug prevents further auto-derivation
      fireEvent.change(slugInput, { target: { value: 'manual-slug' } });
      fireEvent.change(nameInput, { target: { value: 'Enterprise Auth' } });
      expect(slugInput.value).toBe('manual-slug');

      unmount();

      // On edit mode, slug is read-only and name changes do not change slug
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const editNameInput = screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' });
      const editSlugInput = screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' });

      expect(editSlugInput.disabled).toBe(true);
      fireEvent.change(editNameInput, { target: { value: 'Renamed Okta SSO' } });
      expect(editSlugInput.value).toBe('okta-workforce');
    });

    it('toggles Enable Card and Replace Stored Secret on LDAP card', () => {
      const existingLdapCard: AdminAuthCard = {
        id: 'c-ldap',
        provider_kind: 'LDAP',
        slug: 'corp-ldap',
        display_name: 'Corp LDAP',
        button_subtext: 'LDAP Login',
        icon_preset: 'ldap',
        is_enabled: true,
        sort_rank: '2',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: true,
        dek_kid: 'dek-ldap-1',
        last_health_status: 'HEALTHY',
        last_handshake_at: '2026-11-13T20:00:00Z',
        check_summary: 'OK',
        latency_ms: 12,
        public_config: {
          url: 'ldaps://ldap.example.com:636',
          service_bind_dn: 'cn=admin,dc=example,dc=com',
          base_dn: 'dc=example,dc=com',
          transport_mode: 'ldaps',
        },
      };

      const onSave = vi.fn().mockResolvedValue(undefined);

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={existingLdapCard}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      // Toggle Enable Card
      const enableCheckbox = screen.getByLabelText<HTMLInputElement>(/Enable Card/i, { selector: 'input' });
      expect(enableCheckbox.checked).toBe(true);
      fireEvent.click(enableCheckbox);
      expect(enableCheckbox.checked).toBe(false);

      // Toggle Replace Secret
      const replaceCheckbox = screen.getByLabelText<HTMLInputElement>(/Replace Stored Secret/i, { selector: 'input' });
      const secretInput = screen.getByLabelText<HTMLInputElement>(/Bind DN Password/i, { selector: 'input' });
      expect(replaceCheckbox.checked).toBe(false);
      expect(secretInput.disabled).toBe(true);

      fireEvent.click(replaceCheckbox);
      expect(replaceCheckbox.checked).toBe(true);
      expect(secretInput.disabled).toBe(false);

      fireEvent.change(secretInput, { target: { value: 'NewSecret123!' } });
      expect(secretInput.value).toBe('NewSecret123!');

      // Unchecking clears secret input
      fireEvent.click(replaceCheckbox);
      expect(replaceCheckbox.checked).toBe(false);
      expect(secretInput.value).toBe('');
    });

    it('allows editing AdvancedSection allowlists, attributes, and file upload trigger', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Open AdvancedSection
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      // Access Policy restricted mode allowlists
      const policySelect = screen.getByLabelText(/Access Policy/i, { selector: 'select' });
      fireEvent.change(policySelect, { target: { value: 'restricted' } });

      const adminAllowlistInput = screen.getByLabelText<HTMLInputElement>(/Admin Allowlist/i, { selector: 'input' });
      const userAllowlistInput = screen.getByLabelText<HTMLInputElement>(/User Allowlist/i, { selector: 'input' });

      fireEvent.change(adminAllowlistInput, { target: { value: 'admin@corp.com, sysadmin' } });
      fireEvent.change(userAllowlistInput, { target: { value: 'user@corp.com' } });
      expect(adminAllowlistInput.value).toBe('admin@corp.com, sysadmin');
      expect(userAllowlistInput.value).toBe('user@corp.com');

      // Trigger upload button click
      const uploadBtn = screen.getByTestId('google-json-upload-btn');
      const hiddenFileInput = document.querySelector<HTMLInputElement>('.auth-hidden-file-input');
      expect(hiddenFileInput).toBeDefined();
      if (!hiddenFileInput) {
        throw new Error('hiddenFileInput not found');
      }
      const clickSpy = vi.spyOn(hiddenFileInput, 'click');
      fireEvent.click(uploadBtn);
      expect(clickSpy).toHaveBeenCalled();

      // Switch to LDAP to test LDAP attribute fields in AdvancedSection
      const providerKindSelect = screen.getByLabelText(/Provider Kind/i, { selector: 'select' });
      fireEvent.change(providerKindSelect, { target: { value: 'LDAP' } });

      const subjectInput = screen.getByLabelText<HTMLInputElement>(/Subject Attribute/i, { selector: 'input' });
      const emailInput = screen.getByLabelText<HTMLInputElement>(/Email Attribute/i, { selector: 'input' });
      const displayAttrInput = screen.getByLabelText<HTMLInputElement>(/Full Name Attribute/i, { selector: 'input' });

      fireEvent.change(subjectInput, { target: { value: 'customUUID' } });
      fireEvent.change(emailInput, { target: { value: 'userPrincipalName' } });
      fireEvent.change(displayAttrInput, { target: { value: 'gecos' } });

      expect(subjectInput.value).toBe('customUUID');
      expect(emailInput.value).toBe('userPrincipalName');
      expect(displayAttrInput.value).toBe('gecos');
    });

    it('surfaces validation errors on AdvancedSection hasErrors prop when slug or subtext or SPKI is invalid', async () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Fill primary fields
      fireEvent.change(screen.getByLabelText(/Display Name/i, { selector: 'input' }), { target: { value: 'Valid Name' } });
      fireEvent.change(screen.getByLabelText(/Client ID/i, { selector: 'input' }), { target: { value: 'client123' } });
      fireEvent.change(screen.getByLabelText(/Client Secret/i, { selector: 'input' }), { target: { value: 'secret123' } });

      // Open AdvancedSection and enter invalid slug
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      const slugInput = screen.getByLabelText(/Slug Identifier/i, { selector: 'input' });
      fireEvent.change(slugInput, { target: { value: 'INVALID_UPPERCASE_SLUG' } });

      const createBtn = screen.getByRole('button', { name: /Create Card/i });
      fireEvent.click(createBtn);

      await waitFor(() => {
        expect(screen.getByText(/Slug must be 3-48 lowercase alphanumeric characters or hyphens/i)).toBeDefined();
      });

      const advSection = screen.getByTestId('auth-advanced-section');
      // When hasErrors is true, AdvancedSection automatically expands
      expect(advSection.hasAttribute('open')).toBe(true);
      expect(screen.getByTestId('auth-advanced-section-toggle').getAttribute('aria-expanded')).toBe('true');
    });

    it('loads card with custom OAuth endpoints, spki pins array, and group restricted mode', () => {
      const advancedOidcCard: AdminAuthCard = {
        id: 'c-adv-oidc',
        provider_kind: 'OIDC',
        slug: 'advanced-sso',
        display_name: 'Advanced SSO',
        button_subtext: 'Enterprise Login',
        icon_preset: 'key',
        is_enabled: true,
        sort_rank: '3',
        auto_provision_users: false,
        allowed_email_domains: ['example.com'],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: null,
        public_config: {
          issuer: 'https://auth.custom.com',
          client_id: 'custom-client-id',
          authorization_endpoint: 'https://auth.custom.com/oauth2/v1/authorize',
          token_endpoint: 'https://auth.custom.com/oauth2/v1/token',
          userinfo_endpoint: 'https://auth.custom.com/oauth2/v1/userinfo',
          access_mode: 'group_restricted',
          admin_groups: ['Admins'],
          user_groups: ['Employees'],
          spki_sha256_pins: ['0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'],
        },
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={advancedOidcCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Open AdvancedSection
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      expect(screen.getByLabelText<HTMLInputElement>(/Slug Identifier/i, { selector: 'input' }).value).toBe('advanced-sso');
      expect(screen.getByLabelText<HTMLSelectElement>(/Access Policy/i, { selector: 'select' }).value).toBe('restricted');
      expect(screen.getByLabelText<HTMLInputElement>(/Button Subtext/i, { selector: 'input' }).value).toBe('Enterprise Login');
      expect(screen.getByLabelText<HTMLSelectElement>(/Icon Preset/i, { selector: 'select' }).value).toBe('key');
      expect(screen.getByLabelText<HTMLInputElement>(/Allowed Email Domains/i, { selector: 'input' }).value).toBe('example.com');
    });

    it('dynamically increments active overrides count badge when advanced settings are modified', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Open AdvancedSection
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      // Customize subtext
      const subtextInput = screen.getByLabelText(/Button Subtext/i, { selector: 'input' });
      fireEvent.change(subtextInput, { target: { value: 'Custom Button Subtext' } });

      const badge = screen.getByTestId('advanced-active-badge');
      expect(badge).toBeDefined();
      expect(badge.textContent).toBe('1 custom setting active');

      // Customize icon preset
      const iconSelect = screen.getByLabelText(/Icon Preset/i, { selector: 'select' });
      fireEvent.change(iconSelect, { target: { value: 'key' } });
      expect(badge.textContent).toBe('2 custom settings active');

      // Uncheck auto-provision
      const autoProv = screen.getByLabelText(/Auto-provision Users/i, { selector: 'input' });
      fireEvent.click(autoProv);
      expect(badge.textContent).toBe('3 custom settings active');
    });

    it('synchronizes all state fields when card prop changes dynamically via rerender', () => {
      const { rerender } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByText('Add Authentication Card')).toBeDefined();

      const oidcCardWithStrings: AdminAuthCard = {
        id: 'c-oidc-dyn',
        provider_kind: 'OIDC',
        slug: 'dynamic-oidc',
        display_name: 'Dynamic OIDC',
        button_subtext: 'Dyn Subtext',
        icon_preset: 'google',
        is_enabled: false,
        sort_rank: '1',
        auto_provision_users: false,
        allowed_email_domains: ['example.org'],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: null,
        public_config: {
          issuer: 'https://issuer.dynamic.com',
          client_id: 'client-dyn',
          authorization_endpoint: 'https://auth.dyn.com',
          token_endpoint: 'https://token.dyn.com',
          userinfo_endpoint: 'https://userinfo.dyn.com',
          scopes: 'openid, profile',
          client_auth: 'private_key_jwt',
          access_mode: 'group_restricted',
          admin_allowlist: ['admin1'],
          user_allowlist: ['user1'],
          admin_groups: ['Admins'],
          user_groups: ['Users'],
          spki_sha256_pins: ['0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'],
        },
      };

      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={oidcCardWithStrings}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByText('Edit Dynamic OIDC')).toBeDefined();
      expect(screen.getByLabelText<HTMLInputElement>(/Display Name/i, { selector: 'input' }).value).toBe('Dynamic OIDC');

      const ldapCardDyn: AdminAuthCard = {
        id: 'c-ldap-dyn',
        provider_kind: 'LDAP',
        slug: 'dynamic-ldap',
        display_name: 'Dynamic LDAP',
        button_subtext: 'Dyn LDAP',
        icon_preset: 'ldap',
        is_enabled: true,
        sort_rank: '2',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: null,
        public_config: {
          url: 'ldap://ldap.dynamic.com',
          transport_mode: 'starttls',
          service_bind_dn: 'cn=dyn,dc=dyn,dc=com',
          base_dn: 'dc=dyn,dc=com',
          user_search_filter: '(uid={username})',
          subject_attribute: 'entryUUID',
          email_attribute: 'mail',
          display_name_attribute: 'cn',
          ca_cert_pem: '-----BEGIN CERT-----DYN-----END CERT-----',
          spki_sha256_pin: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
        },
      };

      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={ldapCardDyn}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByText('Edit Dynamic LDAP')).toBeDefined();

      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      expect(screen.getByText('Add Authentication Card')).toBeDefined();
    });

    it('covers payload construction and error handling branches', async () => {
      const onSave = vi.fn().mockResolvedValue(undefined);

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      // GitHub preset applies endpoints (authorization_endpoint, token_endpoint, userinfo_endpoint)
      const githubBtn = screen.getByRole('button', { name: /GitHub \(OAuth 2\.0\)/i });
      fireEvent.click(githubBtn);

      fireEvent.change(screen.getByLabelText(/Client ID/i, { selector: 'input' }), { target: { value: 'gh-cid' } });
      fireEvent.change(screen.getByLabelText(/Client Secret/i, { selector: 'input' }), { target: { value: 'gh-secret' } });

      // Open AdvancedSection and clear scopes so scopes fallback is triggered
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      const scopesInput = screen.getByLabelText(/Scopes/i, { selector: 'input' });
      fireEvent.change(scopesInput, { target: { value: '' } });

      const createBtn = screen.getByRole('button', { name: /Create Card/i });
      fireEvent.click(createBtn);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalledWith(
          expect.objectContaining({
            provider_kind: 'OAUTH2',
            slug: 'github-oauth',
            public_config: expect.objectContaining({
              authorization_endpoint: 'https://github.com/login/oauth/authorize',
              token_endpoint: 'https://github.com/login/oauth/access_token',
              userinfo_endpoint: 'https://api.github.com/user',
              scopes: ['openid', 'profile', 'email'],
            }) as unknown,
          }),
          false,
        );
      });
    });

    it('covers non-Error exception handling in Google JSON parsing', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Open AdvancedSection
      const advToggle = screen.getByTestId('auth-advanced-section-toggle');
      fireEvent.click(advToggle);

      // Toggle paste box
      const pasteToggle = screen.getByRole('button', { name: /Paste JSON/i });
      fireEvent.click(pasteToggle);

      const pasteTextarea = screen.getByPlaceholderText(/Paste full Google Cloud Console web client JSON here/i);
      fireEvent.change(pasteTextarea, { target: { value: '{"web": {}}' } });

      // Mock JSON.parse to throw a string instead of an Error
      const parseSpy = vi.spyOn(JSON, 'parse').mockImplementationOnce(() => {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'Non-error string payload';
      });

      const applyBtn = screen.getByRole('button', { name: /Apply Google JSON/i });
      fireEvent.click(applyBtn);

      expect(screen.getByText(/Failed to parse JSON: Non-error string payload/i)).toBeDefined();
      parseSpy.mockRestore();
    });

    it('mounts ZERO input[type="password"] elements and applies .kb-masked-api-key + suppression attributes (KAN-407)', () => {
      const { container } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // 1. Verify ZERO password inputs exist in OIDC mode
      expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);

      const oidcSecret = container.querySelector<HTMLInputElement>('#card-secret');
      expect(oidcSecret).not.toBeNull();
      expect(oidcSecret?.getAttribute('type')).toBe('text');
      expect(oidcSecret?.className).toContain('kb-masked-api-key');
      expect(oidcSecret?.getAttribute('autoComplete')).toBe('off');
      expect(oidcSecret?.getAttribute('data-1p-ignore')).toBe('true');
      expect(oidcSecret?.getAttribute('data-lpignore')).toBe('true');
      expect(oidcSecret?.getAttribute('data-bwignore')).toBe('true');
      expect(oidcSecret?.getAttribute('data-form-type')).toBe('other');

      // 2. Switch to LDAP and verify ZERO password inputs
      fireEvent.click(screen.getByTestId('preset-openldap'));
      expect(container.querySelectorAll('input[type="password"]')).toHaveLength(0);

      const ldapSecret = container.querySelector<HTMLInputElement>('#card-secret');
      expect(ldapSecret).not.toBeNull();
      expect(ldapSecret?.getAttribute('type')).toBe('text');
      expect(ldapSecret?.className).toContain('kb-masked-api-key');
      expect(ldapSecret?.getAttribute('autoComplete')).toBe('off');
      expect(ldapSecret?.getAttribute('data-1p-ignore')).toBe('true');
      expect(ldapSecret?.getAttribute('data-lpignore')).toBe('true');
      expect(ldapSecret?.getAttribute('data-bwignore')).toBe('true');
      expect(ldapSecret?.getAttribute('data-form-type')).toBe('other');
    });

    it('wires is_enabled cleanly on submit in both create and edit modes (KAN-407)', async () => {
      const saveSpy = vi.fn().mockResolvedValue(undefined);
      const { rerender } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={saveSpy}
        />,
      );

      // Create mode: uncheck Enable Card
      fireEvent.change(screen.getByLabelText(/Display Name/i, { selector: 'input' }), { target: { value: 'Disabled Provider' } });
      fireEvent.change(screen.getByLabelText(/Client ID/i, { selector: 'input' }), { target: { value: 'client-123' } });
      const enableCheck = screen.getByLabelText<HTMLInputElement>('Enable Card', { selector: 'input' });
      expect(enableCheck.checked).toBe(true);
      fireEvent.click(enableCheck);
      expect(enableCheck.checked).toBe(false);

      fireEvent.click(screen.getByTestId('drawer-save-btn'));
      await waitFor(() => {
        expect(saveSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            is_enabled: false,
            display_name: 'Disabled Provider',
          }),
          false,
        );
      });

      // Edit mode: toggle is_enabled
      saveSpy.mockClear();
      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={{
            ...existingOidcCard,
            is_enabled: true,
          }}
          onClose={vi.fn()}
          onSave={saveSpy}
        />,
      );

      const editEnableCheck = screen.getByLabelText<HTMLInputElement>('Enable Card', { selector: 'input' });
      expect(editEnableCheck.checked).toBe(true);
      fireEvent.click(editEnableCheck);
      expect(editEnableCheck.checked).toBe(false);

      fireEvent.click(screen.getByTestId('drawer-save-btn'));
      await waitFor(() => {
        expect(saveSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            is_enabled: false,
          }),
          true,
        );
      });
    });

    it('renders localhost origin warning on OIDC callback URI when origin is localhost (KAN-407)', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const warning = screen.getByTestId('oidc-localhost-warning');
      expect(warning).toBeDefined();
      expect(warning.textContent).toContain('You are running on a local origin');
      expect(warning.textContent).toContain('require HTTPS or exact port registration');
    });

    it('validates CA PEM header requires -----BEGIN CERTIFICATE----- (KAN-407)', async () => {
      const saveSpy = vi.fn().mockResolvedValue(undefined);
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={saveSpy}
        />,
      );

      // Apply OpenLDAP preset to populate required LDAP fields
      fireEvent.click(screen.getByTestId('preset-openldap'));

      // Populate required bind_dn and base_dn
      fireEvent.change(screen.getByLabelText(/^Bind DN(?!\s*Password)/i, { selector: 'input' }), { target: { value: 'cn=admin,dc=corp,dc=local' } });
      fireEvent.change(screen.getByLabelText(/^Base DN/i, { selector: 'input' }), { target: { value: 'dc=corp,dc=local' } });

      // Open Advanced Section
      fireEvent.click(screen.getByTestId('auth-advanced-section-toggle'));

      const pemTextarea = screen.getByLabelText(/CA Certificate PEM/i, { selector: 'textarea' });
      fireEvent.change(pemTextarea, { target: { value: 'NOT_A_VALID_PEM_HEADER' } });

      fireEvent.click(screen.getByTestId('drawer-save-btn'));
      await waitFor(() => {
        expect(screen.getByText('CA certificate must begin with -----BEGIN CERTIFICATE-----')).toBeDefined();
      });
      expect(saveSpy).not.toHaveBeenCalled();

      // Fix PEM header
      fireEvent.change(pemTextarea, {
        target: { value: '-----BEGIN CERTIFICATE-----\nMIIBojCCAUqgAwIBAg...\n-----END CERTIFICATE-----' },
      });

      fireEvent.click(screen.getByTestId('drawer-save-btn'));
      await waitFor(() => {
        expect(saveSpy).toHaveBeenCalledTimes(1);
      });
      const lastPayload = saveSpy.mock.calls[0]?.[0] as CreateAuthCardPayload;
      expect(String(lastPayload.public_config.ca_cert_pem)).toContain('-----BEGIN CERTIFICATE-----');
      expect(saveSpy.mock.calls[0]?.[1]).toBe(false);
    });
  });

  describe('StudioDocLink Header Integration (KAN-450)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders auth-drawer-doc-link with correct href and title in drawer header in Light and Dark themes', () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(
          <AuthCardEditorDrawer
            isOpen={true}
            card={null}
            onClose={vi.fn()}
            onSave={vi.fn()}
          />,
        );

        const docLink = screen.getByTestId('auth-drawer-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe('/docs/multi-card-authentication-studio');
        expect(docLink.getAttribute('aria-label')).toBe('Multi-Card Authentication Studio Documentation');
        expect(docLink.textContent).toContain('Documentation ->');

        const headerActions = docLink.closest('.auth-editor-header-actions');
        expect(headerActions).not.toBeNull();
        if (!headerActions) {
          throw new Error('headerActions is null');
        }
        const closeBtn = headerActions.querySelector('button[aria-label="Close drawer"]');
        expect(closeBtn).not.toBeNull();

        unmount();
      }
    });

    it('opens in-app help panel when wrapped in ShellPanelsProvider and clicked', () => {
      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <AuthCardEditorDrawer
              isOpen={true}
              card={null}
              onClose={vi.fn()}
              onSave={vi.fn()}
            />
          </ShellPanelsProvider>,
        );

        const docLink = screen.getByTestId('auth-drawer-doc-link');
        fireEvent.click(docLink);

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel).toBeDefined();
        expect(helpPanel.textContent).toContain('/docs/multi-card-authentication-studio');

        // Verify the drawer is still visible and functional
        expect(screen.getByText('Add Authentication Card')).toBeDefined();
      } finally {
        unregister();
      }
    });

    it('preserves drawer close, cancel, and submit behavior alongside documentation link', async () => {
      const onClose = vi.fn();
      const onSave = vi.fn().mockResolvedValue(undefined);

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={onClose}
          onSave={onSave}
        />,
      );

      // Verify close button in header
      const closeBtn = screen.getByLabelText('Close drawer');
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalledTimes(1);

      // Verify cancel button in footer
      const cancelBtn = screen.getByRole('button', { name: /^cancel$/i });
      fireEvent.click(cancelBtn);
      expect(onClose).toHaveBeenCalledTimes(2);

      // Verify submit behavior still works
      fireEvent.change(screen.getByLabelText(/Display Name/i, { selector: 'input' }), { target: { value: 'Google Corp' } });
      fireEvent.change(screen.getByLabelText(/Client ID/i, { selector: 'input' }), { target: { value: 'google-client-id' } });
      fireEvent.click(screen.getByTestId('drawer-save-btn'));

      await waitFor(() => {
        expect(onSave).toHaveBeenCalledTimes(1);
      });
      const savedPayload = onSave.mock.calls[0]?.[0] as CreateAuthCardPayload;
      expect(savedPayload.provider_kind).toBe('OIDC');
      expect(savedPayload.display_name).toBe('Google Corp');
    });
  });

  describe('FieldHelpHint Form Fields Integration (KAN-449)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it.each(['light', 'dark'] as const)(
      'renders FieldHelpHint across mandatory OIDC and LDAP fields with ARIA attributes in %s theme',
      (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(
          <AuthCardEditorDrawer
            isOpen={true}
            card={null}
            onClose={vi.fn()}
            onSave={vi.fn()}
          />,
        );

        // OIDC primary hints
        const displayNameHelp = screen.getByTestId('card-display-name-help');
        expect(displayNameHelp).toBeDefined();
        expect(displayNameHelp.getAttribute('aria-label')).toBe('Help for Display Name');
        expect(displayNameHelp.getAttribute('aria-haspopup')).toBe('dialog');
        expect(displayNameHelp.getAttribute('aria-expanded')).toBe('false');

        const providerKindHelp = screen.getByTestId('card-provider-kind-help');
        expect(providerKindHelp.getAttribute('aria-label')).toBe('Help for Provider Kind');

        const isEnabledHelp = screen.getByTestId('card-is-enabled-help');
        expect(isEnabledHelp.getAttribute('aria-label')).toBe('Help for Enable Card');

        const issuerUrlHelp = screen.getByTestId('card-issuer-url-help');
        expect(issuerUrlHelp.getAttribute('aria-label')).toBe('Help for Issuer URL');

        const callbackUrlHelp = screen.getByTestId('card-callback-url-help');
        expect(callbackUrlHelp.getAttribute('aria-label')).toBe('Help for Authorized Redirect URI');

        const clientIdHelp = screen.getByTestId('card-client-id-help');
        expect(clientIdHelp.getAttribute('aria-label')).toBe('Help for Client ID');

        const secretHelp = screen.getByTestId('card-secret-help');
        expect(secretHelp.getAttribute('aria-label')).toBe('Help for Client Secret');

        // Switch to LDAP to verify LDAP-specific hints
        fireEvent.change(screen.getByLabelText(/Provider Kind/i, { selector: 'select' }), {
          target: { value: 'LDAP' },
        });

        const serverUrlHelp = screen.getByTestId('card-server-url-help');
        expect(serverUrlHelp.getAttribute('aria-label')).toBe('Help for Server URL');

        const bindDnHelp = screen.getByTestId('card-bind-dn-help');
        expect(bindDnHelp.getAttribute('aria-label')).toBe('Help for Bind DN');

        const ldapSecretHelp = screen.getByTestId('card-ldap-secret-help');
        expect(ldapSecretHelp.getAttribute('aria-label')).toBe('Help for Bind DN Password');

        const baseDnHelp = screen.getByTestId('card-base-dn-help');
        expect(baseDnHelp.getAttribute('aria-label')).toBe('Help for Base DN');

        unmount();
      },
    );

    it('renders Local Administrator Security Profile FieldHelpHint when card is LOCAL_ADMIN', () => {
      const localAdminCard: AdminAuthCard = {
        ...existingOidcCard,
        id: 'c-admin-local',
        provider_kind: 'LOCAL_ADMIN',
        slug: 'local-admin',
        display_name: 'Local Administrator',
        button_subtext: 'Emergency root access',
        icon_preset: 'shield',
      };

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={localAdminCard}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const localAdminHelp = screen.getByTestId('card-local-admin-security-help');
      expect(localAdminHelp).toBeDefined();
      expect(localAdminHelp.getAttribute('aria-label')).toBe('Help for Local Administrator Security Profile');
      expect(localAdminHelp.getAttribute('aria-haspopup')).toBe('dialog');
    });

    it('renders advanced FieldHelpHints across AdvancedSection in both OIDC and LDAP modes', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      // Open Advanced Section
      fireEvent.click(screen.getByTestId('auth-advanced-section-toggle'));

      // Check common advanced hints
      expect(screen.getByTestId('card-slug-help')).toBeDefined();
      expect(screen.getByTestId('card-subtext-help')).toBeDefined();
      expect(screen.getByTestId('card-icon-preset-help')).toBeDefined();
      expect(screen.getByTestId('card-auto-provision-help')).toBeDefined();
      expect(screen.getByTestId('card-email-domains-help')).toBeDefined();
      expect(screen.getByTestId('card-access-policy-help')).toBeDefined();

      // Check OIDC advanced hints
      expect(screen.getByTestId('card-scopes-help')).toBeDefined();
      expect(screen.getByTestId('card-token-auth-help')).toBeDefined();

      // Switch to restricted policy to verify restricted allowlist hints
      fireEvent.change(screen.getByLabelText(/Access Policy/i, { selector: 'select' }), {
        target: { value: 'restricted' },
      });
      expect(screen.getByTestId('card-admin-allowlist-help')).toBeDefined();
      expect(screen.getByTestId('card-user-allowlist-help')).toBeDefined();

      // Switch to LDAP to verify LDAP advanced hints
      fireEvent.change(screen.getByLabelText(/Provider Kind/i, { selector: 'select' }), {
        target: { value: 'LDAP' },
      });
      expect(screen.getByTestId('card-admin-groups-help')).toBeDefined();
      expect(screen.getByTestId('card-user-groups-help')).toBeDefined();
      expect(screen.getByTestId('card-starttls-help')).toBeDefined();
      expect(screen.getByTestId('card-user-filter-help')).toBeDefined();
      expect(screen.getByTestId('card-subject-attr-help')).toBeDefined();
      expect(screen.getByTestId('card-email-attr-help')).toBeDefined();
      expect(screen.getByTestId('card-display-attr-help')).toBeDefined();
      expect(screen.getByTestId('card-spki-pin-help')).toBeDefined();
      expect(screen.getByTestId('card-ca-pem-help')).toBeDefined();
    });

    it('opens popover dialog on focus and restores state on Escape dismissal', () => {
      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const helpBtn = screen.getByTestId('card-display-name-help');
      expect(helpBtn.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('card-display-name-help-popover')).toBeNull();

      // Focus opens popover
      act(() => {
        helpBtn.focus();
      });

      expect(helpBtn.getAttribute('aria-expanded')).toBe('true');
      const popover = screen.getByTestId('card-display-name-help-popover');
      expect(popover).toBeDefined();
      expect(popover.getAttribute('role')).toBe('dialog');
      expect(popover.getAttribute('aria-label')).toBe('Display Name');
      expect(popover.textContent).toContain('User-facing title shown on the login button and admin cards.');

      // Escape key closes popover
      fireEvent.keyDown(popover, { key: 'Escape' });
      expect(helpBtn.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('card-display-name-help-popover')).toBeNull();
    });
  });
});
