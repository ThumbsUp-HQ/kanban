import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { LoginPage } from './LoginPage';
import * as authApi from './authApi';
import { resolveSafeNext, parseRetryAfter, formatAuthError, type AuthCard } from './authApi';
import { ApiProblem } from '../../api/problem';

describe('LoginPage (KB-P3-35)', () => {
  const mock4Cards: AuthCard[] = [
    {
      id: 'c1',
      slug: 'okta-workforce',
      provider_kind: 'OIDC',
      display_name: 'Okta SSO',
      button_subtext: 'Primary identity provider',
      icon_preset: 'building',
    },
    {
      id: 'c2',
      slug: 'corp-ad',
      provider_kind: 'LDAP',
      display_name: 'Corporate Active Directory',
      button_subtext: 'Domain credentials',
      icon_preset: 'lock',
    },
    {
      id: 'c3',
      slug: 'github-org',
      provider_kind: 'OAUTH2',
      display_name: 'GitHub Enterprise',
      button_subtext: null,
      icon_preset: 'github',
    },
    {
      id: 'c4',
      slug: 'local-admin',
      provider_kind: 'LOCAL_ADMIN',
      display_name: 'Local Administrator',
      button_subtext: null,
      icon_preset: 'key',
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders 3 top buttons in API order, Primary badge only on first, and Local Admin only in disclosure (Mandatory Test Case 1)', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const cardList = screen.getByRole('list');
    const cardButtons = cardList.querySelectorAll('button.auth-card-button');
    // Exactly 3 top buttons (OIDC, LDAP, OAUTH2)
    expect(cardButtons.length).toBe(3);
    expect(cardButtons[0]?.textContent).toContain('Okta SSO');
    expect(cardButtons[1]?.textContent).toContain('Corporate Active Directory');
    expect(cardButtons[2]?.textContent).toContain('GitHub Enterprise');

    // Primary badge only on the first
    const primaryBadges = screen.getAllByText('Primary');
    expect(primaryBadges.length).toBe(1);

    // Local admin disclosure exists separately
    expect(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    ).toBeDefined();
  });

  it('open redirect security: resolves unsafe next targets to / while preserving safe relative paths (Mandatory Test Case 3)', () => {
    expect(resolveSafeNext('//evil.example')).toBe('/');
    expect(resolveSafeNext('https://evil.example')).toBe('/');
    expect(resolveSafeNext('/\\evil')).toBe('/');
    expect(resolveSafeNext('javascript:alert(1)')).toBe('/');
    expect(resolveSafeNext('')).toBe('/');
    expect(resolveSafeNext(null)).toBe('/');

    // Safe path is preserved
    expect(resolveSafeNext('/projects/KAN/issues')).toBe('/projects/KAN/issues');
    expect(resolveSafeNext('/projects/KAN/issues?layout=board')).toBe(
      '/projects/KAN/issues?layout=board',
    );
    const oauthAuthorizeNext =
      '/oauth/authorize?response_type=code&client_id=abc&redirect_uri=http%3A%2F%2F127.0.0.1%3A54321%2Fcallback&scope=agent:read+agent:write';
    expect(resolveSafeNext(oauthAuthorizeNext)).toBe(oauthAuthorizeNext);

    const longGeminiState = 'x'.repeat(1200);
    const geminiOauthNext = `/oauth/authorize?response_type=code&client_id=gemini_client&redirect_uri=https%3A%2F%2Fgemini.google.com%2Fcallback%3Ffoo%3Dbar&state=${longGeminiState}&scope=agent:read+agent:write`;
    expect(resolveSafeNext(geminiOauthNext)).toBe(geminiOauthNext);

    const subDelimsNext = '/oauth/authorize?state=abc@123;param=1!$()*';
    expect(resolveSafeNext(subDelimsNext)).toBe(subDelimsNext);

    expect(resolveSafeNext('/https://evil.example')).toBe('/');
  });

  it('initializes generic error banner when URL query contains error_description or error without leaking details', async () => {
    const origLocation = window.location;
    window.history.pushState({}, '', '/login?error=access_denied&error_description=User+not+in+allowlist');
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });

    render(<LoginPage />);

    await waitFor(() => {
      const alertText = screen.getByRole('alert').textContent;
      expect(alertText).toContain('Sign-in failed. Check your credentials and try again.');
      expect(alertText).not.toContain('User not in allowlist');
    });
    window.history.pushState({}, '', origLocation.pathname);
  });

  it('error copy and Retry-After parser clamp boundaries (Mandatory Test Case 5)', () => {
    // 1. INVALID_CREDENTIALS byte-identical message for unknown user and wrong password
    const errUnknownUser = new ApiProblem(401, {
      code: 'INVALID_CREDENTIALS',
      detail: 'User not found in realm',
    });
    const errWrongPass = new ApiProblem(401, {
      code: 'INVALID_CREDENTIALS',
      detail: 'Password mismatch for principal',
    });

    const formatted1 = formatAuthError(errUnknownUser);
    const formatted2 = formatAuthError(errWrongPass);

    expect(formatted1.message).toBe(
      'Sign-in failed. Check your credentials and try again.',
    );
    expect(formatted1.message).toBe(formatted2.message);

    // 2. Retry-After clamping
    expect(parseRetryAfter('abc')).toBe(60);
    expect(parseRetryAfter(0)).toBe(1);
    expect(parseRetryAfter('0')).toBe(1);
    expect(parseRetryAfter(-10)).toBe(1);
    expect(parseRetryAfter(99999)).toBe(3600);
    expect(parseRetryAfter('99999')).toBe(3600);
    expect(parseRetryAfter(45)).toBe(45);
  });

  it('renders exact emergency unlock command when cards list is empty (Mandatory Test Case 8)', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: [] });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('No sign-in methods are enabled.')).toBeDefined();
    });

    const codeBlock = screen.getByText('kanban-ctl auth emergency-unlock --enable-local-admin');
    expect(codeBlock).toBeDefined();
    expect(codeBlock.tagName.toLowerCase()).toBe('code');

    const copyBtn = screen.getByRole('button', { name: 'Copy' });
    expect(copyBtn).toBeDefined();
  });

  it('moves focus to error alert when error occurs (Mandatory Test Case 9)', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockRejectedValue(
      new ApiProblem(500, { code: 'SERVER_UNAVAILABLE' }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert).toBeDefined();
      expect(document.activeElement).toBe(alert);
    });
  });

  it('handles rate limited error with Retry-After and warning EmojiHint', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockRejectedValue(
      new ApiProblem(429, { code: 'RATE_LIMITED', retry_after: 45 }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(
        screen.getByText('Too many attempts. Try again in 45 seconds.'),
      ).toBeDefined();
    });
  });

  it('expands LDAP card on click, submits credentials, and transitions to MFA step', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    const ldapSpy = vi.spyOn(authApi, 'submitLdapLogin').mockResolvedValueOnce({
      status: 'mfa_required',
      challenge_id: 'chall-ldap-mfa',
      methods: ['totp'],
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    // Click on LDAP card to expand inline form
    const ldapBtn = screen.getByRole('button', { name: /Sign in with Corporate Active Directory/i });
    fireEvent.click(ldapBtn);

    expect(screen.getByLabelText(/Username/i)).toBeDefined();
    expect(screen.getByLabelText(/Password/i)).toBeDefined();

    // Toggle collapse
    fireEvent.click(ldapBtn);
    expect(screen.queryByLabelText(/Username/i)).toBeNull();

    // Re-expand and submit
    fireEvent.click(ldapBtn);
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'AliceSecret123!' } });

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in to Corporate Active Directory/i }),
    );

    await waitFor(() => {
      expect(ldapSpy).toHaveBeenCalledWith(
        'corp-ad',
        expect.objectContaining({
          username: 'alice',
          password: 'AliceSecret123!',
        }),
      );
      // Should now render SecondFactorStep
      expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    });

    // Test cancelling MFA step
    const cancelBtn = screen.getByRole('button', { name: /Cancel and return to sign-in/i });
    fireEvent.click(cancelBtn);

    expect(screen.getByText('Okta SSO')).toBeDefined();
  });

  it('handles direct authenticated response without MFA and navigates', async () => {
    const onNavigate = vi.fn();
    render(
      <LoginPage
        initialCards={mock4Cards}
        initialNext="/projects/KAN/issues"
        onNavigate={onNavigate}
      />,
    );

    expect(screen.getByText('Okta SSO')).toBeDefined();

    // Expand Local Admin
    const trigger = screen.getByRole('button', {
      name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
    });
    fireEvent.click(trigger);

    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValueOnce({
      status: 'authenticated',
    });

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'valid-password' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith('/projects/KAN/issues');
    });
  });

  it('allows dismissing error alert with close button', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockRejectedValue(
      new ApiProblem(500, { code: 'SERVER_ERR' }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    const closeBtn = screen.getByRole('button', { name: /Dismiss error/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('copies emergency unlock command to clipboard', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: [] });
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('No sign-in methods are enabled.')).toBeDefined();
    });

    const copyBtn = screen.getByRole('button', { name: 'Copy' });
    fireEvent.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith(
      'kanban-ctl auth emergency-unlock --enable-local-admin',
    );
  });

  it('navigates with window.location.assign when onNavigate is omitted', async () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock, search: '' },
    });

    render(<LoginPage initialCards={mock4Cards} />);

    // Expand Local Admin
    const trigger = screen.getByRole('button', {
      name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
    });
    fireEvent.click(trigger);

    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValueOnce({
      status: 'authenticated',
    });

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'valid-password' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith('/');
    });
  });

  it('handles CHALLENGE_EXPIRED inside SecondFactorStep and resets to provider list', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValueOnce({
      status: 'mfa_required',
      challenge_id: 'chall-expire-test',
      methods: ['totp'],
    });

    vi.spyOn(authApi, 'verifyTotp').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'CHALLENGE_EXPIRED' }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    fireEvent.click(
      screen.getByRole('button', {
        name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
      }),
    );

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'valid-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    });

    // Enter code to trigger CHALLENGE_EXPIRED
    const codeInput = screen.getByLabelText(/6-digit Authenticator Code/i);
    fireEvent.change(codeInput, { target: { value: '123456' } });

    await waitFor(() => {
      expect(
        screen.getByText('Your sign-in session expired. Start again.'),
      ).toBeDefined();
      // Returns to provider list
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });
  });

  it('sets error alert when LDAP login or Local Admin login fails inside LoginPage', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    vi.spyOn(authApi, 'submitLdapLogin').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'INVALID_CREDENTIALS' }),
    );
    vi.spyOn(authApi, 'submitLocalAdminLogin').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'INVALID_CREDENTIALS' }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    // 1. LDAP error
    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Corporate Active Directory/i }),
    );
    const ldapUser = document.getElementById('ldap-user-corp-ad');
    const ldapPwd = document.getElementById('ldap-pwd-corp-ad');
    expect(ldapUser).not.toBeNull();
    expect(ldapPwd).not.toBeNull();
    if (ldapUser && ldapPwd) {
      fireEvent.change(ldapUser, { target: { value: 'alice' } });
      fireEvent.change(ldapPwd, { target: { value: 'wrong-pass' } });
    }
    fireEvent.click(
      screen.getByRole('button', { name: /Sign in to Corporate Active Directory/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByText('Sign-in failed. Check your credentials and try again.'),
      ).toBeDefined();
    });

    // 2. Local Admin error
    fireEvent.click(
      screen.getByRole('button', {
        name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
      }),
    );
    const adminUser = document.getElementById('local-admin-username');
    const adminPwd = document.getElementById('local-admin-password');
    expect(adminUser).not.toBeNull();
    expect(adminPwd).not.toBeNull();
    if (adminUser && adminPwd) {
      fireEvent.change(adminUser, {
        target: { value: 'admin' },
      });
      fireEvent.change(adminPwd, { target: { value: 'wrong-pass' } });
    }
    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(
        screen.getAllByText('Sign-in failed. Check your credentials and try again.').length,
      ).toBeGreaterThanOrEqual(1);
    });
  });

  it('handles LDAP onCollapse when Escape is pressed inside LDAP form', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    const ldapCardBtn = screen.getByRole('button', {
      name: /Sign in with Corporate Active Directory/i,
    });
    fireEvent.click(ldapCardBtn);

    const ldapInput = screen.getByLabelText(/Username/i);
    expect(ldapInput).toBeDefined();

    // Trigger onCollapse via Escape
    fireEvent.keyDown(ldapInput, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByLabelText(/Username/i)).toBeNull();
    });
  });

  it('handles SecondFactorStep onError and default window.location.assign on success', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValue({
      status: 'mfa_required',
      challenge_id: 'chall-err-test',
      methods: ['totp'],
    });
    vi.spyOn(authApi, 'verifyTotp').mockRejectedValueOnce(
      new ApiProblem(400, { code: 'INVALID_CREDENTIALS', detail: 'Invalid TOTP code' }),
    );

    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock, search: '' },
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    );
    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'valid-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    });

    // Enter 6 digits, triggering verifyTotp which rejects
    const codeInput = screen.getByLabelText(/6-digit Authenticator Code/i);
    fireEvent.change(codeInput, { target: { value: '999999' } });

    await waitFor(() => {
      expect(
        screen.getByText('Sign-in failed. Check your credentials and try again.'),
      ).toBeDefined();
    });

    // Now test success path with window.location.assign
    vi.spyOn(authApi, 'verifyTotp').mockResolvedValueOnce({
      status: 'authenticated',
    });

    fireEvent.change(codeInput, { target: { value: '111111' } });
    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith('/');
    });
  });

  it('handles fetchAuthCards error gracefully', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockRejectedValueOnce(
      new ApiProblem(500, { code: 'INTERNAL_ERROR', detail: 'DB connection error' }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(
        screen.getByText('Server error. Please contact your administrator.'),
      ).toBeDefined();
    });
  });

  it('renders only Local Admin without divider when no top cards exist', async () => {
    const onlyAdminCard: AuthCard[] = [
      {
        id: 'c-admin',
        slug: 'local-admin',
        provider_kind: 'LOCAL_ADMIN',
        display_name: 'Local Administrator',
        button_subtext: null,
        icon_preset: 'key',
      },
    ];

    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: onlyAdminCard });

    render(<LoginPage />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
      ).toBeDefined();
    });

    // Zero top cards list
    expect(screen.queryByRole('list')).toBeNull();
    // Zero divider
    expect(screen.queryByText('or Local Administrator')).toBeNull();
  });

  it('renders without Local Admin disclosure when only OIDC cards exist', async () => {
    const onlyOidcCard: AuthCard[] = [
      {
        id: 'c-oidc',
        slug: 'google-sso',
        provider_kind: 'OIDC',
        display_name: 'Google Workspace',
        button_subtext: 'SSO',
        icon_preset: 'building',
      },
    ];

    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: onlyOidcCard });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Google Workspace')).toBeDefined();
    });

    expect(
      screen.queryByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    ).toBeNull();
  });

  it('renders rate limit EmojiHint when error code is RATE_LIMITED', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockRejectedValueOnce(
      new ApiProblem(429, {
        code: 'RATE_LIMITED',
        detail: 'Too many attempts',
        retry_after: 60,
      }),
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText(/Too many attempts/i)).toBeDefined();
      expect(screen.getByRole('button', { name: /About sign-in rate limits/i })).toBeDefined();
    });
  });

  it('cancels MFA challenge when user clicks Cancel and return to sign-in', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValue({
      status: 'mfa_required',
      challenge_id: 'chall-cancel',
      methods: ['totp'],
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    );
    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'valid-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    });

    // Click cancel button in SecondFactorStep
    const cancelBtn = screen.getByRole('button', { name: /Cancel and return to sign-in/i });
    fireEvent.click(cancelBtn);

    await waitFor(() => {
      // Returns to main card list
      expect(screen.getByText('Okta SSO')).toBeDefined();
      expect(screen.queryByRole('tab', { name: /Authenticator code/i })).toBeNull();
    });
  });

  it('handles clipboard write failure when copying emergency unlock command', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: [] });
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: {
        writeText: vi.fn().mockRejectedValue(new Error('Clipboard denied')),
      },
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('No sign-in methods are enabled.')).toBeDefined();
    });

    const copyBtn = screen.getByRole('button', { name: /Copy/i });
    fireEvent.click(copyBtn);

    // Does not throw, button still exists
    expect(copyBtn).toBeDefined();
  });

  it('copies emergency unlock command to clipboard and shows Copied! text', async () => {
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: [] });
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('No sign-in methods are enabled.')).toBeDefined();
    });

    const copyBtn = screen.getByRole('button', { name: 'Copy' });
    fireEvent.click(copyBtn);
    // Double click to cover clearTimeout
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledWith(
        'kanban-ctl auth emergency-unlock --enable-local-admin',
      );
      expect(screen.getByText('Copied!')).toBeDefined();
    });
  });

  it('handles direct authenticated response without MFA and invokes onNavigate', async () => {
    const onNavigate = vi.fn();
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });
    vi.spyOn(authApi, 'submitLdapLogin').mockResolvedValueOnce({
      status: 'authenticated',
    });

    render(<LoginPage initialNext="/custom/dashboard" onNavigate={onNavigate} />);

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Corporate Active Directory/i }),
    );
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'pwd' } });
    fireEvent.click(
      screen.getByRole('button', { name: /Sign in to Corporate Active Directory/i }),
    );

    await waitFor(() => {
      expect(onNavigate).toHaveBeenCalledWith('/custom/dashboard');
    });
  });

  it('handles unmounting while fetchAuthCards is pending', () => {
    let resolveCards: ((val: { cards: AuthCard[] }) => void) | undefined;
    vi.spyOn(authApi, 'fetchAuthCards').mockReturnValue(
      new Promise<{ cards: AuthCard[] }>((resolve) => {
        resolveCards = resolve;
      }),
    );

    const { unmount } = render(<LoginPage />);
    unmount();
    resolveCards?.({ cards: mock4Cards });
  });

  it('covers session mfa_pending bootstrap and remember-me toggle', async () => {
    vi.spyOn(authApi, 'fetchSessionInfo').mockResolvedValueOnce({
      authenticated: true,
      mfa_pending: true,
      session_id: 'sess-mfa-bootstrap',
    });
    vi.spyOn(authApi, 'fetchAuthCards').mockResolvedValue({ cards: mock4Cards });

    render(<LoginPage />);

    // Session mfa_pending boots directly into SecondFactorStep
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Authenticator code/i })).toBeDefined();
    });

    // Cancel back to login form
    fireEvent.click(screen.getByRole('button', { name: /Cancel and return to sign-in/i }));

    await waitFor(() => {
      expect(screen.getByText('Okta SSO')).toBeDefined();
    });

    // Toggle remember-me checkbox
    const rememberMeCheckbox = screen.getByTestId<HTMLInputElement>('login-remember-me-checkbox');
    expect(rememberMeCheckbox.checked).toBe(true);
    fireEvent.click(rememberMeCheckbox);
    expect(rememberMeCheckbox.checked).toBe(false);
    fireEvent.click(rememberMeCheckbox);
    expect(rememberMeCheckbox.checked).toBe(true);
  });
});
