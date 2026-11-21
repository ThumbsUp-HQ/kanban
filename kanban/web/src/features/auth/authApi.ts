/**
 * Typed API client wrappers and validation helpers for Authentication & First-Boot Setup (KB-P3-35, S4.2, S4.3, S2.2).
 */

import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';

export type ProviderKind = 'OIDC' | 'OAUTH2' | 'LDAP' | 'LOCAL_ADMIN';

export interface AuthCard {
  id: string;
  slug: string;
  provider_kind: ProviderKind;
  display_name: string;
  button_subtext: string | null;
  icon_preset: string;
}

export interface AuthCardsResponse {
  cards: AuthCard[];
}

export type MfaMethod = 'webauthn' | 'totp' | 'recovery';

export type AuthLoginResponse =
  | { status: 'authenticated' }
  | {
      status: 'mfa_required';
      challenge_id: string;
      methods: MfaMethod[];
    };

export interface SetupClaimResponse {
  status: 'enrollment_required';
  enrollment_id: string;
}

export interface EnrollmentSuccessResponse {
  status: 'enrolled';
  recovery_codes: string[];
}

export interface TotpEnrollResponse {
  secret_base32: string;
  otpauth_uri: string;
}

/**
 * Validates and sanitizes the `next` redirect target parameter (Mandatory Test Case 3).
 * Must be a same-origin relative path matching `^/(?!/)[A-Za-z0-9/_\-?=&.%:+~]*$`
 * with no scheme/colon in the path segment before `?`.
 * Rejects protocol-relative //, backslash /\, or absolute schemes, returning '/' as fallback.
 */
export function resolveSafeNext(next: string | null | undefined): string {
  if (!next || typeof next !== 'string') {
    return '/';
  }
  const SAFE_NEXT_REGEX = /^\/(?!\/)[A-Za-z0-9/_\-?=&.%:+~]*$/;
  const [pathPart = ''] = next.split('?');
  if (!SAFE_NEXT_REGEX.test(next) || next.includes('\\') || pathPart.includes(':')) {
    return '/';
  }
  return next;
}

/**
 * Parses and clamps a Retry-After header or problem data value to 1..3600 seconds (Mandatory Test Case 5).
 * Non-numeric defaults to 60. Value < 1 clamps to 1; > 3600 clamps to 3600.
 */
export function parseRetryAfter(value: unknown): number {
  if (typeof value === 'number') {
    if (isNaN(value)) return 60;
    if (value < 1) return 1;
    if (value > 3600) return 3600;
    return Math.floor(value);
  }
  if (typeof value === 'string') {
    const parsed = parseInt(value.trim(), 10);
    if (isNaN(parsed)) return 60;
    if (parsed < 1) return 1;
    if (parsed > 3600) return 3600;
    return parsed;
  }
  return 60;
}

export interface FormattedError {
  message: string;
  code?: string;
  retryAfterSeconds?: number;
}

export interface SessionInfoResponse {
  authenticated: boolean;
  user?: {
    id: string;
    username: string;
    display_name?: string;
    role?: string;
    email?: string | null;
  } | null;
  mfa_pending?: boolean;
  session_id?: string | null;
  csrf_token?: string;
}

export async function fetchSessionInfo(): Promise<SessionInfoResponse> {
  const result = await apiFetch('GET', '/api/v1/auth/session' as never);
  return result as SessionInfoResponse;
}

/**
 * Maps API errors into uniform, safe error copy preventing principal enumeration (Action 8, Mandatory Test Case 5).
 */
export function formatAuthError(error: unknown): FormattedError {
  if (error instanceof ApiProblem) {
    const code = error.code;
    if (code === 'INVALID_CREDENTIALS') {
      return { message: 'Sign-in failed. Check your credentials and try again.', code };
    }
    if (code === 'CSRF_REJECTED' || (error.status === 403 && String(error.title).includes('CSRF'))) {
      return {
        message: 'Your browser session token is out of date - reload the page and try again.',
        code: 'CSRF_REJECTED',
      };
    }
    if (code === 'INTERNAL_ERROR' || error.status >= 500) {
      const rawReqId = error.data.request_id ?? error.data.requestId;
      const reqId = typeof rawReqId === 'string' ? rawReqId : undefined;
      const message = reqId
        ? `Server error (Request ID: ${reqId}). Please contact your administrator.`
        : 'Server error. Please contact your administrator.';
      return { message, code: code !== 'UNKNOWN' ? code : 'INTERNAL_ERROR' };
    }
    if (code === 'RATE_LIMITED') {
      const retryAfter = parseRetryAfter(
        error.data.retry_after ?? error.data.retryAfter ?? 60,
      );
      return {
        message: `Too many attempts. Try again in ${String(retryAfter)} seconds.`,
        code,
        retryAfterSeconds: retryAfter,
      };
    }
    if (code === 'WEBAUTHN_FAILED') {
      return {
        message: 'Passkey verification failed. Try again or use an authenticator code.',
        code,
      };
    }
    if (code === 'CHALLENGE_EXPIRED') {
      return { message: 'Your sign-in session expired. Start again.', code };
    }
    if (code === 'SETUP_TOKEN_INVALID') {
      return {
        message:
          'This setup link is invalid or has already been used. Check the container logs for the current setup URL.',
        code,
      };
    }
    return { message: 'Sign-in is unavailable right now.', code };
  }

  if (error instanceof Error && error.message) {
    if (error.message.includes('Rate limit') || error.message.includes('RATE_LIMITED')) {
      return { message: 'Too many attempts. Try again in 60 seconds.', code: 'RATE_LIMITED' };
    }
  }

  return { message: 'Sign-in is unavailable right now.' };
}

// ----------------------------------------------------------------------------
// API Endpoints (Action 3)
// ----------------------------------------------------------------------------

export async function fetchAuthCards(): Promise<AuthCardsResponse> {
  const result = await apiFetch('GET', '/api/v1/auth/cards' as never);
  return result as AuthCardsResponse;
}

export async function submitLdapLogin(
  slug: string,
  credentials: { username: string; password: string; remember_me?: boolean },
): Promise<AuthLoginResponse> {
  const path = `/api/v1/auth/cards/${encodeURIComponent(slug)}/ldap-login` as never;
  const result = await apiFetch('POST', path, { body: credentials });
  return result as AuthLoginResponse;
}

export async function submitLocalAdminLogin(credentials: {
  username: string;
  password: string;
  remember_me?: boolean;
}): Promise<AuthLoginResponse> {
  const result = (await apiFetch('POST', '/api/v1/auth/local/login' as never, {
    body: credentials,
  })) as {
    status?: 'authenticated' | 'mfa_required';
    mfa_pending?: boolean;
    session_id?: string;
    challenge_id?: string;
    methods?: MfaMethod[];
  };
  if (result.status === 'mfa_required') {
    return {
      status: 'mfa_required',
      challenge_id: result.challenge_id ?? result.session_id ?? '',
      methods: result.methods ?? ['webauthn', 'totp', 'recovery'],
    };
  }
  if (result.status === 'authenticated') {
    return { status: 'authenticated' };
  }
  if (result.mfa_pending) {
    return {
      status: 'mfa_required',
      challenge_id: result.challenge_id ?? result.session_id ?? '',
      methods: result.methods ?? ['webauthn', 'totp', 'recovery'],
    };
  }
  return { status: 'authenticated' };
}

export async function getWebauthnAssertionOptions(body: {
  challenge_id: string;
}): Promise<{ options: PublicKeyCredentialRequestOptionsJSON }> {
  const result = (await apiFetch('POST', '/api/v1/auth/webauthn/assertion/options' as never, {
    body,
  })) as
    | { options: PublicKeyCredentialRequestOptionsJSON }
    | PublicKeyCredentialRequestOptionsJSON;
  if ('options' in result) {
    return result;
  }
  return { options: result };
}

export async function verifyWebauthnAssertion(body: {
  challenge_id: string;
  credential: unknown;
}): Promise<{ status: 'authenticated' }> {
  const result = await apiFetch('POST', '/api/v1/auth/webauthn/assertion/verify' as never, { body });
  return result as { status: 'authenticated' };
}

export async function verifyTotp(body: {
  challenge_id: string;
  code: string;
}): Promise<{ status: 'authenticated' }> {
  const result = await apiFetch('POST', '/api/v1/auth/totp/verify' as never, { body });
  return result as { status: 'authenticated' };
}

export async function verifyRecoveryCode(body: {
  challenge_id: string;
  code: string;
}): Promise<{ status: 'authenticated' }> {
  const result = await apiFetch('POST', '/api/v1/auth/recovery/verify' as never, { body });
  return result as { status: 'authenticated' };
}

export async function submitSetupClaim(body: {
  token: string;
  username: string;
  display_name: string;
  password: string;
  email?: string;
  workspace_name?: string;
  workspace_slug?: string;
  project_name?: string;
  project_key?: string;
}): Promise<SetupClaimResponse> {
  const result = await apiFetch('POST', '/api/v1/setup/claim' as never, { body });
  return result as SetupClaimResponse;
}

export async function getWebauthnRegistrationOptions(body: {
  enrollment_id: string;
}): Promise<{ options: PublicKeyCredentialCreationOptionsJSON }> {
  const result = (await apiFetch('POST', '/api/v1/auth/webauthn/registration/options' as never, {
    body,
  })) as
    | { options: PublicKeyCredentialCreationOptionsJSON }
    | PublicKeyCredentialCreationOptionsJSON;
  if ('options' in result) {
    return result;
  }
  return { options: result };
}

export async function verifyWebauthnRegistration(body: {
  enrollment_id: string;
  credential: unknown;
}): Promise<EnrollmentSuccessResponse> {
  const result = (await apiFetch('POST', '/api/v1/auth/webauthn/registration/verify' as never, {
    body,
  })) as Partial<EnrollmentSuccessResponse>;
  if (Array.isArray(result.recovery_codes)) {
    return {
      status: 'enrolled',
      recovery_codes: result.recovery_codes,
    };
  }
  const generated = (await apiFetch(
    'POST',
    '/api/v1/auth/mfa/recovery-codes/generate' as never,
    { body: {} },
  )) as { recovery_codes: string[] };
  return {
    status: 'enrolled',
    recovery_codes: generated.recovery_codes,
  };
}

export async function enrollTotp(body: {
  enrollment_id: string;
}): Promise<TotpEnrollResponse> {
  const result = (await apiFetch('POST', '/api/v1/auth/mfa/totp/enroll' as never, {
    body,
  })) as { secret_base32?: string; secret?: string; otpauth_uri: string };
  return {
    secret_base32: result.secret_base32 ?? result.secret ?? '',
    otpauth_uri: result.otpauth_uri,
  };
}

export async function verifyTotpEnrollment(body: {
  enrollment_id: string;
  code: string;
}): Promise<EnrollmentSuccessResponse> {
  const result = (await apiFetch('POST', '/api/v1/auth/mfa/totp/confirm' as never, {
    body,
  })) as Partial<EnrollmentSuccessResponse>;
  if (Array.isArray(result.recovery_codes)) {
    return {
      status: 'enrolled',
      recovery_codes: result.recovery_codes,
    };
  }
  const generated = (await apiFetch(
    'POST',
    '/api/v1/auth/mfa/recovery-codes/generate' as never,
    { body: {} },
  )) as { recovery_codes: string[] };
  return {
    status: 'enrolled',
    recovery_codes: generated.recovery_codes,
  };
}

export interface PublicKeyCredentialRequestOptionsJSON {
  challenge: string;
  timeout?: number;
  rpId?: string;
  allowCredentials?: { id: string; type: string; transports?: string[] }[];
  userVerification?: UserVerificationRequirement;
}

export interface PublicKeyCredentialCreationOptionsJSON {
  rp: { name: string; id?: string };
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: { alg: number; type: string }[];
  timeout?: number;
  excludeCredentials?: { id: string; type: string; transports?: string[] }[];
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  attestation?: AttestationConveyancePreference;
}
