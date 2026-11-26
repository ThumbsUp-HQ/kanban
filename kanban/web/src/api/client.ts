/**
 * Typed OpenAPI fetch client for the Kanban frontend (KB-P3-33).
 *
 * Contract: relative `/api/v1/...` URLs only, same-origin credentials, CSRF header on unsafe
 * methods, optional `If-Match`, 15s default timeout, RFC 7807 problem mapping.
 */

import type { paths } from './schema.gen.ts';
import { ApiProblem, isAal2StepUpCode } from './problem.ts';

export class ApiClientError extends Error {
  readonly code: string;

  constructor(code: string, message?: string) {
    super(message ?? `API Client error: ${code}`);
    this.name = 'ApiClientError';
    this.code = code;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class Aal2StepUpCancelledError extends Error {
  constructor(message = 'AAL2 step-up challenge was cancelled') {
    super(message);
    this.name = 'Aal2StepUpCancelledError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export function isAal2StepUpCancelled(err: unknown): boolean {
  return (
    err instanceof Aal2StepUpCancelledError ||
    (err instanceof Error && err.name === 'Aal2StepUpCancelledError')
  );
}

export type Aal2StepUpHandler = (challenge: {
  challengeId?: string | undefined;
  methods?: string[] | undefined;
}) => Promise<boolean>;

let activeAal2StepUpHandler: Aal2StepUpHandler | null = null;
let pendingAal2StepUp: Promise<boolean> | null = null;

export function registerAal2StepUpHandler(handler: Aal2StepUpHandler | null): void {
  activeAal2StepUpHandler = handler;
  pendingAal2StepUp = null;
}

export function resetAal2StepUpCoordinator(): void {
  activeAal2StepUpHandler = null;
  pendingAal2StepUp = null;
}

export function getActiveAal2StepUpHandler(): Aal2StepUpHandler | null {
  return activeAal2StepUpHandler;
}

export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

type JsonOf<R> = R extends { content: { 'application/json': infer T } } ? T : unknown;

type SuccessBody<R> = R extends { 200: infer S }
  ? JsonOf<S>
  : R extends { 201: infer S }
    ? JsonOf<S>
    : R extends { 204: unknown }
      ? undefined
      : unknown;

export type ResponseBody<P extends keyof paths, M extends Method> =
  Lowercase<M> extends keyof paths[P]
    ? paths[P][Lowercase<M>] extends { responses: infer R }
      ? SuccessBody<R>
      : unknown
    : unknown;

type ParamValue = string | number | boolean;

export interface ApiFetchOptions {
  params?: Record<string, ParamValue> | undefined;
  query?: Record<string, ParamValue | readonly ParamValue[] | null | undefined> | undefined;
  body?: unknown;
  ifMatch?: string | undefined;
  headers?: Record<string, string> | undefined;
  signal?: AbortSignal | undefined;
}

export const REQUEST_TIMEOUT_MS = 15000;
const UNSAFE_METHODS: ReadonlySet<string> = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const CSRF_COOKIE_RE = /(?:^|;\s*)(__Host-kb_csrf|kb_csrf)=([^;]+)/g;
const SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

let cachedCsrfToken: string | null = null;

/** Updates the cached CSRF token and mirrors it into the plain-HTTP `kb_csrf` cookie. */
export function setCsrfToken(token: string | null): void {
  cachedCsrfToken = token;
  if (typeof document === 'undefined') {
    return;
  }
  try {
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
    if (token !== null && token.length > 0) {
      if (!isHttps) {
        document.cookie = `kb_csrf=${encodeURIComponent(token)}; Path=/; SameSite=Strict`;
      }
    } else {
      document.cookie = 'kb_csrf=; Path=/; SameSite=Strict; Max-Age=0';
    }
  } catch {
    // Ignore cookie write errors in restricted test environments
  }
}

/** Reads the `__Host-kb_csrf` or `kb_csrf` cookie value, or cached token fallback, or null when absent. */
export function getCsrfToken(): string | null {
  if (typeof document !== 'undefined') {
    const matches = [...document.cookie.matchAll(CSRF_COOKIE_RE)];
    if (matches.length > 0) {
      const hostMatch = matches.find((m) => m[1] === '__Host-kb_csrf');
      const fallbackMatch = matches.find((m) => m[1] === 'kb_csrf');
      const chosen = hostMatch ?? fallbackMatch ?? matches[0];
      const raw = chosen?.[2];
      if (raw !== undefined) {
        try {
          return decodeURIComponent(raw);
        } catch {
          return raw;
        }
      }
    }
  }
  if (cachedCsrfToken !== null && cachedCsrfToken.length > 0) {
    return cachedCsrfToken;
  }
  return null;
}

export async function bootstrapCsrfToken(
  signal?: AbortSignal,
  force = false,
): Promise<string | null> {
  if (!force && cachedCsrfToken !== null && cachedCsrfToken.length > 0) {
    return cachedCsrfToken;
  }
  try {
    const response = await fetch('/api/v1/auth/session', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
      signal: timeoutSignal(signal),
    });
    if (!response.ok) {
      return getCsrfToken();
    }
    const data = (await response.json()) as unknown;
    if (
      typeof data === 'object' &&
      data !== null &&
      'csrf_token' in data &&
      typeof (data as { csrf_token?: unknown }).csrf_token === 'string' &&
      (data as { csrf_token: string }).csrf_token.length > 0
    ) {
      const token = (data as { csrf_token: string }).csrf_token;
      setCsrfToken(token);
      return token;
    }
  } catch {
    // Fall back to cookie/cache state when session bootstrap is unreachable
  }
  return getCsrfToken();
}

function assertRelative(url: string): void {
  if (!url.startsWith('/') || url.startsWith('//') || SCHEME_RE.test(url) || url.includes('\\')) {
    throw new ApiClientError(
      'ABSOLUTE_URL_FORBIDDEN',
      'Only same-origin relative paths starting with a single / are allowed',
    );
  }
}

function buildQueryString(query: NonNullable<ApiFetchOptions['query']>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value === 'object') {
      for (const item of value) {
        search.append(key, String(item));
      }
    } else {
      search.append(key, String(value));
    }
  }
  return search.toString();
}

function isPlainBody(body: unknown): body is BodyInit {
  return (
    typeof body === 'string' ||
    body instanceof Blob ||
    body instanceof FormData ||
    body instanceof URLSearchParams
  );
}

function timeoutSignal(caller: AbortSignal | undefined): AbortSignal {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  return caller ? AbortSignal.any([caller, timeout]) : timeout;
}

async function readProblemBody(response: Response, contentType: string): Promise<unknown> {
  try {
    if (contentType.includes('json')) {
      return (await response.json()) as unknown;
    }
    return await response.text();
  } catch {
    return undefined;
  }
}

async function executeRequest(
  method: Method,
  path: string,
  opts: ApiFetchOptions = {},
  defaultAccept = 'application/json',
  isReplay = false,
): Promise<{ response: Response; resolved: string }> {
  let resolved: string = path;
  assertRelative(resolved);
  for (const [key, value] of Object.entries(opts.params ?? {})) {
    resolved = resolved.split(`{${key}}`).join(encodeURIComponent(String(value)));
  }
  assertRelative(resolved);
  if (opts.query) {
    const qs = buildQueryString(opts.query);
    if (qs) {
      resolved += (resolved.includes('?') ? '&' : '?') + qs;
    }
  }

  const headers: Record<string, string> = { Accept: defaultAccept, ...opts.headers };
  if (UNSAFE_METHODS.has(method)) {
    const csrf = getCsrfToken() ?? (await bootstrapCsrfToken(opts.signal));
    if (csrf === null) {
      throw new ApiClientError('CSRF_TOKEN_MISSING', 'Missing __Host-kb_csrf cookie');
    }
    headers['X-CSRF-Token'] = csrf;
  }
  if (opts.ifMatch !== undefined) {
    headers['If-Match'] = opts.ifMatch;
  }

  const init: RequestInit = {
    method,
    headers,
    credentials: 'same-origin',
    signal: timeoutSignal(opts.signal),
  };
  if (opts.body !== undefined) {
    if (isPlainBody(opts.body)) {
      init.body = opts.body;
    } else {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
  }

  let response = await fetch(resolved, init);
  const isAuthSession = path === '/api/v1/auth/session' || resolved.startsWith('/api/v1/auth/session');
  const initialExpiresAt = response.headers.get('x-kb-aal2-expires-at');
  if (initialExpiresAt && !isAuthSession && typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('kb:aal2-expires-at', { detail: { expiresAt: initialExpiresAt } })
    );
  }
  let contentType = response.headers.get('content-type') ?? '';

  if (!response.ok) {
    let problemBody = await readProblemBody(response, contentType);

    const problemCode =
      typeof problemBody === 'object' && problemBody !== null
        ? ((problemBody as { code?: unknown }).code ??
           (problemBody as { error?: unknown }).error)
        : undefined;

    const isAal2StepUp =
      response.status === 403 &&
      !isReplay &&
      isAal2StepUpCode(problemCode);

    if (isAal2StepUp) {
      if (!activeAal2StepUpHandler) {
        throw new ApiProblem(response.status, problemBody);
      }

      if (!pendingAal2StepUp) {
        const bodyObj = problemBody as Record<string, unknown>;
        const challengeId =
          typeof bodyObj.challenge_id === 'string' ? bodyObj.challenge_id : undefined;
        const methods = Array.isArray(bodyObj.methods)
          ? (bodyObj.methods as string[])
          : ['webauthn', 'totp'];

        pendingAal2StepUp = activeAal2StepUpHandler({ challengeId, methods }).finally(() => {
          pendingAal2StepUp = null;
        });
      }

      let elevationSuccess = false;
      try {
        elevationSuccess = await pendingAal2StepUp;
      } catch {
        elevationSuccess = false;
      }

      if (!elevationSuccess) {
        throw new Aal2StepUpCancelledError();
      }

      // Elevation succeeded: refresh CSRF token and timeout signal, then replay fetch once (max 1 replay)
      const freshCsrf = getCsrfToken() ?? (await bootstrapCsrfToken(opts.signal, true));
      if (freshCsrf) {
        headers['X-CSRF-Token'] = freshCsrf;
      }
      init.headers = headers;
      init.signal = timeoutSignal(opts.signal);

      response = await fetch(resolved, init);
      const replayExpiresAt = response.headers.get('x-kb-aal2-expires-at');
      if (replayExpiresAt && !isAuthSession && typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('kb:aal2-expires-at', { detail: { expiresAt: replayExpiresAt } })
        );
      }
      contentType = response.headers.get('content-type') ?? '';

      if (!response.ok) {
        problemBody = await readProblemBody(response, contentType);
        throw new ApiProblem(response.status, problemBody);
      }
    } else {
      const isCsrfRejected =
        typeof problemBody === 'object' &&
        problemBody !== null &&
        (('code' in problemBody && (problemBody as { code?: unknown }).code === 'CSRF_REJECTED') ||
          ('error' in problemBody && (problemBody as { error?: unknown }).error === 'CSRF_REJECTED') ||
          ('detail' in problemBody && String((problemBody as { detail?: unknown }).detail).toLowerCase().includes('csrf')) ||
          ('title' in problemBody && String((problemBody as { title?: unknown }).title).includes('CSRF')));

      const isCsrfRetryable =
        response.status === 403 &&
        !isReplay &&
        UNSAFE_METHODS.has(method) &&
        isCsrfRejected;

      if (isCsrfRetryable) {
        const freshCsrf = await bootstrapCsrfToken(opts.signal, true);
        if (freshCsrf) {
          headers['X-CSRF-Token'] = freshCsrf;
          init.headers = headers;
          response = await fetch(resolved, init);
          contentType = response.headers.get('content-type') ?? '';
          if (!response.ok) {
            problemBody = await readProblemBody(response, contentType);
            throw new ApiProblem(response.status, problemBody);
          }
        } else {
          throw new ApiProblem(response.status, problemBody);
        }
      } else {
        throw new ApiProblem(response.status, problemBody);
      }
    }
  }

  return { response, resolved };
}

/** Dispatches a typed request. Throws `ApiClientError` (client rules) or `ApiProblem` (non-2xx). */
export async function apiFetch<P extends keyof paths, M extends Method>(
  method: M,
  path: P,
  opts: ApiFetchOptions = {},
  isReplay = false,
): Promise<ResponseBody<P, M>> {
  const { response, resolved } = await executeRequest(
    method,
    path,
    opts,
    'application/json',
    isReplay,
  );
  if (response.status === 204) {
    return undefined as ResponseBody<P, M>;
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json') && !contentType.includes('application/problem+json')) {
    throw new ApiClientError(
      'UNEXPECTED_CONTENT_TYPE',
      `Expected application/json but received ${contentType || 'none'}`,
    );
  }
  const parsed = (await response.json()) as ResponseBody<P, M>;
  if (resolved === '/api/v1/auth/logout') {
    setCsrfToken(null);
  } else if (
    typeof parsed === 'object' &&
    parsed !== null &&
    'csrf_token' in parsed &&
    typeof (parsed as { csrf_token?: unknown }).csrf_token === 'string' &&
    (parsed as { csrf_token: string }).csrf_token.length > 0
  ) {
    setCsrfToken((parsed as { csrf_token: string }).csrf_token);
  }
  return parsed;
}

export interface ApiBlobResponse {
  blob: Blob;
  filename?: string | undefined;
  contentType: string;
  headers: Headers;
}

export function parseContentDispositionFilename(disposition: string | null): string | undefined {
  if (!disposition) return undefined;
  const rfc5987Match = /filename\*=UTF-8''([^";\r\n]+)/i.exec(disposition);
  if (rfc5987Match?.[1]) {
    try {
      return decodeURIComponent(rfc5987Match[1]);
    } catch {
      return rfc5987Match[1];
    }
  }
  const standardMatch = /filename=["']?([^"';\r\n]+)["']?/i.exec(disposition);
  if (standardMatch?.[1]) {
    return standardMatch[1].trim();
  }
  return undefined;
}

/** Dispatches a request for binary data (blob). Throws `ApiClientError` (client rules) or `ApiProblem` (non-2xx). */
export async function apiFetchBlob(
  method: Method,
  path: string,
  opts: ApiFetchOptions = {},
  isReplay = false,
): Promise<ApiBlobResponse> {
  const defaultAccept = opts.headers?.Accept ?? 'application/octet-stream, application/gzip, application/json';
  const { response } = await executeRequest(method, path, opts, defaultAccept, isReplay);
  const contentType = response.headers.get('content-type') ?? 'application/octet-stream';
  const disposition = response.headers.get('content-disposition');
  const filename = parseContentDispositionFilename(disposition);
  const blob = await response.blob();
  return {
    blob,
    filename,
    contentType,
    headers: response.headers,
  };
}

export const apiClient = {
  get: <P extends keyof paths>(path: P, opts?: ApiFetchOptions) => apiFetch('GET', path, opts),
  post: <P extends keyof paths>(path: P, opts?: ApiFetchOptions) => apiFetch('POST', path, opts),
  put: <P extends keyof paths>(path: P, opts?: ApiFetchOptions) => apiFetch('PUT', path, opts),
  patch: <P extends keyof paths>(path: P, opts?: ApiFetchOptions) => apiFetch('PATCH', path, opts),
  delete: <P extends keyof paths>(path: P, opts?: ApiFetchOptions) => apiFetch('DELETE', path, opts),
  blob: (method: Method, path: string, opts?: ApiFetchOptions) => apiFetchBlob(method, path, opts),
};
