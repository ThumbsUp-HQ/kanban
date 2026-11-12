/**
 * Typed OpenAPI fetch client for the Kanban frontend (KB-P3-33).
 *
 * Contract: relative `/api/v1/...` URLs only, same-origin credentials, CSRF header on unsafe
 * methods, optional `If-Match`, 15s default timeout, RFC 7807 problem mapping.
 */

import type { paths } from './schema.gen.ts';
import { ApiProblem } from './problem.ts';

export class ApiClientError extends Error {
  readonly code: string;

  constructor(code: string, message?: string) {
    super(message ?? `API Client error: ${code}`);
    this.name = 'ApiClientError';
    this.code = code;
    Object.setPrototypeOf(this, new.target.prototype);
  }
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
  params?: Record<string, ParamValue>;
  query?: Record<string, ParamValue | readonly ParamValue[] | null | undefined>;
  body?: unknown;
  ifMatch?: string;
  signal?: AbortSignal;
}

export const REQUEST_TIMEOUT_MS = 15000;
const UNSAFE_METHODS: ReadonlySet<string> = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const CSRF_COOKIE_RE = /(?:^|;\s*)__Host-kb_csrf=([^;]+)/;
const SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

/** Reads the `__Host-kb_csrf` cookie value, or null when absent. */
export function getCsrfToken(): string | null {
  const raw = CSRF_COOKIE_RE.exec(document.cookie)?.[1];
  if (raw === undefined) {
    return null;
  }
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
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

/** Dispatches a typed request. Throws `ApiClientError` (client rules) or `ApiProblem` (non-2xx). */
export async function apiFetch<P extends keyof paths, M extends Method>(
  method: M,
  path: P,
  opts: ApiFetchOptions = {},
): Promise<ResponseBody<P, M>> {
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

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (UNSAFE_METHODS.has(method)) {
    const csrf = getCsrfToken();
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

  const response = await fetch(resolved, init);
  const contentType = response.headers.get('content-type') ?? '';

  if (!response.ok) {
    throw new ApiProblem(response.status, await readProblemBody(response, contentType));
  }
  if (response.status === 204) {
    return undefined as ResponseBody<P, M>;
  }
  if (!contentType.includes('application/json') && !contentType.includes('application/problem+json')) {
    throw new ApiClientError(
      'UNEXPECTED_CONTENT_TYPE',
      `Expected application/json but received ${contentType || 'none'}`,
    );
  }
  return (await response.json()) as ResponseBody<P, M>;
}
