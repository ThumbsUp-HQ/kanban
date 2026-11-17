import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as client from '../../api/client';
import {
  fetchAuthCards,
  submitLdapLogin,
  submitLocalAdminLogin,
  getWebauthnAssertionOptions,
  verifyWebauthnAssertion,
  verifyTotp,
  verifyRecoveryCode,
  submitSetupClaim,
  getWebauthnRegistrationOptions,
  verifyWebauthnRegistration,
  enrollTotp,
  verifyTotpEnrollment,
  parseRetryAfter,
  formatAuthError,
} from './authApi';
import { ApiProblem } from '../../api/problem';

describe('authApi wrappers and formatters (KB-P3-35)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls fetchAuthCards with GET /api/v1/auth/cards', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      cards: [],
    });

    const res = await fetchAuthCards();
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/auth/cards');
    expect(res.cards).toEqual([]);
  });

  it('calls submitLdapLogin with POST /api/v1/auth/cards/{slug}/ldap-login', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      status: 'authenticated',
    });

    const res = await submitLdapLogin('test-slug', {
      username: 'user',
      password: 'pwd',
    });
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/cards/test-slug/ldap-login', {
      body: { username: 'user', password: 'pwd' },
    });
    expect(res.status).toBe('authenticated');
  });

  it('calls submitLocalAdminLogin with POST /api/v1/auth/local/login', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      status: 'mfa_required',
      challenge_id: 'ch-1',
      methods: ['totp'],
    });

    const res = await submitLocalAdminLogin({
      username: 'admin',
      password: 'pwd',
    });
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/local/login', {
      body: { username: 'admin', password: 'pwd' },
    });
    expect(res.status).toBe('mfa_required');
  });

  it('calls WebAuthn assertion and verification endpoints', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      options: { challenge: 'ch' },
    });

    await getWebauthnAssertionOptions({ challenge_id: 'ch-1' });
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/assertion/options',
      { body: { challenge_id: 'ch-1' } },
    );

    fetchSpy.mockResolvedValueOnce({ status: 'authenticated' });
    await verifyWebauthnAssertion({ challenge_id: 'ch-1', credential: { id: 'x' } });
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/assertion/verify',
      { body: { challenge_id: 'ch-1', credential: { id: 'x' } } },
    );
  });

  it('calls verifyTotp and verifyRecoveryCode endpoints', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      status: 'authenticated',
    });

    await verifyTotp({ challenge_id: 'ch-totp', code: '123456' });
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/totp/verify', {
      body: { challenge_id: 'ch-totp', code: '123456' },
    });

    await verifyRecoveryCode({ challenge_id: 'ch-rec', code: 'rec-code' });
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/auth/recovery/verify', {
      body: { challenge_id: 'ch-rec', code: 'rec-code' },
    });
  });

  it('calls submitSetupClaim endpoint', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      status: 'enrollment_required',
      enrollment_id: 'enr-1',
    });

    const res = await submitSetupClaim({
      token: 'kb_setup_123',
      username: 'admin',
      display_name: 'Admin',
      password: 'password123456',
    });
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/setup/claim', {
      body: {
        token: 'kb_setup_123',
        username: 'admin',
        display_name: 'Admin',
        password: 'password123456',
      },
    });
    expect(res.enrollment_id).toBe('enr-1');
  });

  it('calls WebAuthn and TOTP enrollment endpoints', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({
      options: { challenge: 'c' },
    });

    await getWebauthnRegistrationOptions({ enrollment_id: 'enr-1' });
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/registration/options',
      { body: { enrollment_id: 'enr-1' } },
    );

    fetchSpy.mockResolvedValueOnce({
      status: 'enrolled',
      recovery_codes: ['c1'],
    });
    await verifyWebauthnRegistration({ enrollment_id: 'enr-1', credential: {} });
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/auth/webauthn/registration/verify',
      { body: { enrollment_id: 'enr-1', credential: {} } },
    );

    fetchSpy.mockResolvedValueOnce({
      secret_base32: 'ABC',
      otpauth_uri: 'otpauth://',
    });
    const totpRes = await enrollTotp({ enrollment_id: 'enr-1' });
    expect(totpRes.secret_base32).toBe('ABC');

    fetchSpy.mockResolvedValueOnce({
      status: 'enrolled',
      recovery_codes: ['c2'],
    });
    const verifyRes = await verifyTotpEnrollment({ enrollment_id: 'enr-1', code: '111111' });
    expect(verifyRes.recovery_codes).toEqual(['c2']);
  });

  it('covers formatAuthError for WEBAUTHN_FAILED, CHALLENGE_EXPIRED, SETUP_TOKEN_INVALID, and unknown codes', () => {
    expect(
      formatAuthError(new ApiProblem(400, { code: 'WEBAUTHN_FAILED' })).message,
    ).toBe('Passkey verification failed. Try again or use an authenticator code.');

    expect(
      formatAuthError(new ApiProblem(400, { code: 'CHALLENGE_EXPIRED' })).message,
    ).toBe('Your sign-in session expired. Start again.');

    expect(
      formatAuthError(new ApiProblem(400, { code: 'SETUP_TOKEN_INVALID' })).message,
    ).toBe(
      'This setup link is invalid or has already been used. Check the container logs for the current setup URL.',
    );

    expect(
      formatAuthError(
        new ApiProblem(403, {
          code: 'IDENTITY_NOT_PROVISIONED',
          detail: 'User is not in the authorized access list',
        }),
      ).message,
    ).toBe('User is not in the authorized access list');

    expect(
      formatAuthError(new ApiProblem(500, { code: 'CUSTOM_GATE_REJECTED' })).message,
    ).toBe('Sign-in is unavailable right now (code: CUSTOM_GATE_REJECTED).');

    expect(
      formatAuthError(new ApiProblem(500, { code: 'too_long_or_lowercase_code_not_matching_regex' }))
        .message,
    ).toBe('Sign-in is unavailable right now.');

    expect(formatAuthError(new Error('Rate limit exceeded')).message).toBe(
      'Too many attempts. Try again in 60 seconds.',
    );

    expect(formatAuthError('arbitrary non-error').message).toBe(
      'Sign-in is unavailable right now.',
    );

    expect(parseRetryAfter(NaN)).toBe(60);
    expect(parseRetryAfter({})).toBe(60);
    expect(parseRetryAfter('invalid-num')).toBe(60);
    expect(parseRetryAfter('120')).toBe(120);
    expect(parseRetryAfter('-5')).toBe(1);
    expect(parseRetryAfter('5000')).toBe(3600);
    expect(parseRetryAfter(0)).toBe(1);
    expect(parseRetryAfter(5000)).toBe(3600);
    expect(parseRetryAfter(45.6)).toBe(45);
  });
});
