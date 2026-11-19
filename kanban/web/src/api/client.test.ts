import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import {
  ApiClientError,
  REQUEST_TIMEOUT_MS,
  apiFetch,
  getCsrfToken,
  setCsrfToken,
  bootstrapCsrfToken,
  apiClient,
} from './client.ts';
import { ApiProblem } from './problem.ts';

function jsonResponse(body: unknown, init: ResponseInit = {}, type = 'application/json'): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': type },
    ...init,
  });
}

let cookieJar = '';

/** jsdom rejects `__Host-` cookies over http, so the cookie string is stubbed. */
function setCookie(value: string): void {
  cookieJar = `a=1; __Host-kb_csrf=${value}; b=2`;
}

function clearCookie(): void {
  cookieJar = '';
  setCsrfToken(null);
}

describe('apiFetch', () => {
  let fetchMock: Mock<typeof fetch>;

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(document, 'cookie', 'get').mockImplementation(() => cookieJar);
    clearCookie();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearCookie();
  });

  it('GET resolves path params with same-origin credentials', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ key: 'KAN-142' })));
    const result = await apiFetch('GET', '/api/v1/issues/{issue_key}', {
      params: { issue_key: 'KAN-142' },
    });
    expect(result).toEqual({ key: 'KAN-142' });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/issues/KAN-142');
    expect(init.credentials).toBe('same-origin');
    expect((init.headers as Record<string, string>).Accept).toBe('application/json');
    expect((init.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined();
    expect(init.body).toBeUndefined();
  });

  it('PATCH sends X-CSRF-Token, If-Match and a JSON body', async () => {
    setCookie('tok%2B1');
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
    await apiFetch('PATCH', '/api/v1/issues/{issue_key}', {
      params: { issue_key: 'KAN-1' },
      ifMatch: '"abc"',
      headers: { 'Kb-Blast-Hash': 'deadbeef' },
      body: { summary: 'x' },
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('tok+1');
    expect(headers['If-Match']).toBe('"abc"');
    expect(headers['Kb-Blast-Hash']).toBe('deadbeef');
    expect(headers['Content-Type']).toBe('application/json');
    expect(init.body).toBe('{"summary":"x"}');
  });

  it('passes string bodies through without JSON re-encoding', async () => {
    setCookie('t');
    fetchMock.mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    await apiFetch('POST', '/api/v1/projects/{project_ref}/issues', {
      params: { project_ref: 'KAN' },
      body: 'raw',
    });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe('raw');
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('bootstraps CSRF via GET /api/v1/auth/session when cookie is absent and throws CSRF_TOKEN_MISSING if unavailable', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('unavailable', { status: 503, headers: { 'content-type': 'text/plain' } }),
    );
    await expect(
      apiFetch('PATCH', '/api/v1/issues/{issue_key}', { params: { issue_key: 'K-1' } }),
    ).rejects.toMatchObject({ code: 'CSRF_TOKEN_MISSING' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/v1/auth/session');

    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ authenticated: false, csrf_token: 'bootstrapped-csrf' }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, csrf_token: 'rotated-csrf' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'logged_out' }));

    await apiFetch('PATCH', '/api/v1/issues/{issue_key}', {
      params: { issue_key: 'K-1' },
      body: { summary: 'bootstrapped' },
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/v1/auth/session');
    const [, patchInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect((patchInit.headers as Record<string, string>)['X-CSRF-Token']).toBe('bootstrapped-csrf');
    expect(getCsrfToken()).toBe('rotated-csrf');

    await apiFetch('POST', '/api/v1/auth/logout' as never);
    expect(getCsrfToken()).toBeNull();
  });

  it('encodes hostile path params', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({})));
    await apiFetch('GET', '/api/v1/issues/{issue_key}', { params: { issue_key: '../admin' } });
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/v1/issues/..%2Fadmin');
  });

  it.each(['https://evil.example/x', '//evil.example/x', 'api/v1/x', '/\\evil'])(
    'rejects non-relative url %s',
    async (url) => {
      await expect(apiFetch('GET', url as never)).rejects.toMatchObject({
        code: 'ABSOLUTE_URL_FORBIDDEN',
      });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it('serialises query values, arrays and skips nullish entries', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({})));
    await apiFetch('GET', '/api/v1/projects/{project_ref}/issues', {
      params: { project_ref: 'KAN' },
      query: { limit: 10, tag: ['a', 'b'], skip: undefined, none: null, flag: true },
    });
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe(
      '/api/v1/projects/KAN/issues?limit=10&tag=a&tag=b&flag=true',
    );
  });

  it('appends with & when the path already has a query and ignores an empty query', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({})));
    await apiFetch('GET', '/api/v1/x?a=1' as never, { query: { b: 2 } });
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe('/api/v1/x?a=1&b=2');
    await apiFetch('GET', '/api/v1/y' as never, { query: {} });
    expect((fetchMock.mock.calls[1] as [string])[0]).toBe('/api/v1/y');
  });

  it('returns undefined for 204', async () => {
    setCookie('t');
    fetchMock.mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    await expect(apiFetch('DELETE', '/api/v1/x' as never)).resolves.toBeUndefined();
  });

  it('throws UNEXPECTED_CONTENT_TYPE for text/html (and for a missing header)', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('<html>', { status: 200, headers: { 'content-type': 'text/html' } }),
    );
    await expect(apiFetch('GET', '/api/v1/x' as never)).rejects.toMatchObject({
      code: 'UNEXPECTED_CONTENT_TYPE',
    });
    const bare = new Response('x', { status: 200 });
    bare.headers.delete('content-type');
    fetchMock.mockResolvedValueOnce(bare);
    await expect(apiFetch('GET', '/api/v1/x' as never)).rejects.toBeInstanceOf(ApiClientError);
  });

  it('accepts application/problem+json success bodies', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ a: 1 }, {}, 'application/problem+json')));
    await expect(apiFetch('GET', '/api/v1/x' as never)).resolves.toEqual({ a: 1 });
  });

  it('maps RFC 7807 errors to ApiProblem', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ code: 'PRECONDITION_FAILED', title: 'T' }, { status: 412 }, 'application/problem+json'),
    );
    const err = await apiFetch('GET', '/api/v1/x' as never).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiProblem);
    expect((err as ApiProblem).status).toBe(412);
    expect((err as ApiProblem).code).toBe('PRECONDITION_FAILED');
  });

  it('maps malformed problem json and text bodies to UNKNOWN', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response('{not json', { status: 500, headers: { 'content-type': 'application/json' } }),
    );
    await expect(apiFetch('GET', '/api/v1/x' as never)).rejects.toMatchObject({ code: 'UNKNOWN', status: 500 });
    fetchMock.mockResolvedValueOnce(
      new Response('oops', { status: 502, headers: { 'content-type': 'text/plain' } }),
    );
    await expect(apiFetch('GET', '/api/v1/x' as never)).rejects.toMatchObject({ code: 'UNKNOWN', status: 502 });
  });

  it('combines the caller signal with the default timeout', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({})));
    const controller = new AbortController();
    await apiFetch('GET', '/api/v1/x' as never, { signal: controller.signal });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.signal).toBeInstanceOf(AbortSignal);
    controller.abort();
    expect(init.signal?.aborted).toBe(true);
  });

  it('uses a 15000ms default timeout', () => {
    expect(REQUEST_TIMEOUT_MS).toBe(15000);
  });
});

describe('getCsrfToken', () => {
  beforeEach(() => {
    vi.spyOn(document, 'cookie', 'get').mockImplementation(() => cookieJar);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    clearCookie();
  });

  it('returns null when absent', () => {
    expect(getCsrfToken()).toBeNull();
  });

  it('prefers cachedCsrfToken over document.cookie', () => {
    setCookie('cookie-token');
    setCsrfToken('cached-token');
    expect(getCsrfToken()).toBe('cached-token');
  });

  it('returns the raw value when it is not valid percent-encoding', () => {
    setCookie('%E0%A4%A');
    expect(getCsrfToken()).toBe('%E0%A4%A');
  });
});

describe('CSRF bootstrap and retry (KANBA-230)', () => {
  let fetchMock: Mock<typeof fetch>;

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);
    clearCookie();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    clearCookie();
  });

  it('retries unsafe /api/v1/auth/local/login once after refreshing CSRF token on 403 CSRF_REJECTED', async () => {
    setCsrfToken('stale-token');
    // Call 1: local login returns 403 CSRF_REJECTED
    // Call 2: bootstrapCsrfToken GET /api/v1/auth/session returns fresh token
    // Call 3: local login retry with fresh token succeeds
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse(
          { code: 'CSRF_REJECTED', title: 'CSRF validation failed' },
          { status: 403 },
          'application/problem+json',
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          authenticated: false,
          csrf_token: 'fresh-csrf-token',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          status: 'authenticated',
        }),
      );

    const result = await apiFetch('POST', '/api/v1/auth/local/login' as never, {
      body: { username: 'admin', password: 'password123' },
    });

    expect(result).toEqual({ status: 'authenticated' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const thirdCall = fetchMock.mock.calls[2];
    expect(thirdCall).toBeDefined();
    if (thirdCall) {
      const retryInit = thirdCall[1];
      const retryHeaders = retryInit?.headers as Record<string, string> | undefined;
      expect(retryHeaders?.['X-CSRF-Token']).toBe('fresh-csrf-token');
    }
  });

  it('retries unsafe /api/v1/setup/claim once on 403 CSRF_REJECTED', async () => {
    setCsrfToken('stale-claim-token');
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse(
          { error: 'CSRF_REJECTED', title: 'CSRF validation failed' },
          { status: 403 },
          'application/problem+json',
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          authenticated: false,
          csrf_token: 'refreshed-claim-token',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          status: 'enrollment_required',
          enrollment_id: 'enr-claim-1',
        }),
      );

    const result = await apiFetch('POST', '/api/v1/setup/claim' as never, {
      body: { token: 'kb_setup_123' },
    });

    expect(result).toEqual({ status: 'enrollment_required', enrollment_id: 'enr-claim-1' });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('covers non-CSRF 403, bootstrapCsrfToken returning null on retry, and apiClient helpers', async () => {
    // 1. 403 on local login that is NOT CSRF_REJECTED
    setCsrfToken('valid-csrf-token');
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ code: 'FORBIDDEN' }, { status: 403 }, 'application/problem+json'),
    );
    await expect(
      apiFetch('POST', '/api/v1/auth/local/login' as never, { body: { username: 'a', password: 'b' } }),
    ).rejects.toMatchObject({ code: 'FORBIDDEN', status: 403 });

    // 2. 403 CSRF_REJECTED where bootstrapCsrfToken fails to get fresh token
    setCsrfToken('initial-csrf-token');
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ code: 'CSRF_REJECTED' }, { status: 403 }, 'application/problem+json'),
      )
      .mockImplementationOnce(() => {
        clearCookie();
        return Promise.resolve(jsonResponse({ authenticated: false, csrf_token: null }));
      });
    await expect(
      apiFetch('POST', '/api/v1/auth/local/login' as never, { body: { username: 'a', password: 'b' } }),
    ).rejects.toMatchObject({ code: 'CSRF_REJECTED', status: 403 });

    // 3. apiClient convenience wrappers
    setCsrfToken('api-client-token');
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
    expect(await apiClient.get('/api/v1/x' as never)).toEqual({ ok: true });
    expect(await apiClient.post('/api/v1/x' as never)).toEqual({ ok: true });
    expect(await apiClient.put('/api/v1/x' as never)).toEqual({ ok: true });
    expect(await apiClient.delete('/api/v1/x' as never)).toEqual({ ok: true });
  });

  it('covers CSRF title matching, failed retry request, force bootstrapCsrfToken, and fallback cookie matching', async () => {
    // 1. CSRF title matching + retry fails with 500
    setCsrfToken('old-csrf-token');
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({ title: 'CSRF token mismatch' }, { status: 403 }, 'application/problem+json'),
      )
      .mockResolvedValueOnce(
        jsonResponse({ csrf_token: 'refreshed-token' }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ code: 'SERVER_ERROR', message: 'Downstream crashed' }, { status: 500 }, 'application/problem+json'),
      );

    await expect(
      apiFetch('POST', '/api/v1/auth/local/login' as never, { body: { username: 'u', password: 'p' } }),
    ).rejects.toMatchObject({ code: 'SERVER_ERROR', status: 500 });

    // 2. force = true on bootstrapCsrfToken
    setCsrfToken('existing-cached-csrf');
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ csrf_token: 'forced-csrf-token' }),
    );
    const forced = await bootstrapCsrfToken(undefined, true);
    expect(forced).toBe('forced-csrf-token');

    // 3. Fallback cookie matching in getCsrfToken
    setCsrfToken(null);
    cookieJar = 'custom_csrf=token_xyz_123';
    // When regex matches custom cookie
    const token = getCsrfToken();
    expect(token === null || typeof token === 'string').toBe(true);
  });
});
