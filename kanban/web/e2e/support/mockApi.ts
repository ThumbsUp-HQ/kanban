import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export interface MockRequest {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
  params: Record<string, string>;
}

export interface MockResponse {
  status?: number;
  json?: unknown;
  headers?: Record<string, string>;
  delayMs?: number;
  contentType?: string;
  body?: string | Buffer;
}

export type MockHandler = MockResponse | ((req: MockRequest) => MockResponse);

export type MockHandlers = Record<`${HttpMethod} /api/v1/${string}`, MockHandler>;

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
  params: Record<string, string>;
}

export interface UnmatchedCall {
  method: string;
  path: string;
}

export interface MockRecorder {
  calls: RecordedCall[];
  unmatchedCalls: UnmatchedCall[];
}

/**
 * Loads a JSON fixture by name from the e2e/fixtures directory.
 * Throws an error if the name contains invalid or path-traversal characters.
 */
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
export function loadFixture<T = unknown>(name: string): T {
  if (!/^[a-z0-9-]+$/.test(name)) {
    throw new Error(`Invalid fixture name: ${name}`);
  }
  const fixturePath = join(import.meta.dirname, '../fixtures', `${name}.json`);
  const content = readFileSync(fixturePath, 'utf-8');
  return JSON.parse(content) as T;
}

/**
 * Parses a handler key into method and pathname pattern.
 */
export function parseRouteKey(key: string): { method: string; pathPattern: string } {
  const spaceIdx = key.indexOf(' ');
  if (spaceIdx === -1) {
    return { method: key.trim(), pathPattern: '' };
  }
  return {
    method: key.slice(0, spaceIdx).trim(),
    pathPattern: key.slice(spaceIdx + 1).trim(),
  };
}

/**
 * Matches a URL pathname against a route pattern containing :param segments.
 */
export function matchRoute(
  patternPath: string,
  actualPath: string,
): { matched: boolean; params: Record<string, string> } {
  const patternSegments = patternPath.split('/').filter(Boolean);
  const actualSegments = actualPath.split('/').filter(Boolean);

  if (patternSegments.length !== actualSegments.length) {
    return { matched: false, params: {} };
  }

  const params: Record<string, string> = {};
  for (let i = 0; i < patternSegments.length; i++) {
    const p = String(patternSegments[i]);
    const a = String(actualSegments[i]);
    if (p.startsWith(':')) {
      params[p.slice(1)] = a;
    } else if (p !== a) {
      return { matched: false, params: {} };
    }
  }

  return { matched: true, params };
}

/**
 * Registers an interceptor for all /api/v1/ routes and matches configured handlers.
 * Unmatched calls receive a 599 status and are recorded.
 */
export async function mockApi(page: Page, handlers: MockHandlers): Promise<MockRecorder> {
  const recorder: MockRecorder = { calls: [], unmatchedCalls: [] };

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const pathname = url.pathname;
    let body: unknown = undefined;
    const postData = request.postData();
    if (postData) {
      try {
        body = JSON.parse(postData);
      } catch {
        body = postData;
      }
    }
    const headers = request.headers();

    let matched = false;
    for (const [key, handler] of Object.entries(handlers)) {
      const { method: handlerMethod, pathPattern } = parseRouteKey(key);
      if (handlerMethod !== method) {
        continue;
      }
      const match = matchRoute(pathPattern, pathname);
      if (match.matched) {
        matched = true;
        const reqObj: MockRequest = {
          method,
          path: pathname,
          body,
          headers,
          params: match.params,
        };
        recorder.calls.push(reqObj);
        const response = typeof handler === 'function' ? handler(reqObj) : handler;
        if (response.delayMs && response.delayMs > 0) {
          await new Promise((resolve) => setTimeout(resolve, response.delayMs));
        }
        const contentType =
          response.contentType ??
          response.headers?.['content-type'] ??
          'application/json';
        const isPlainObject =
          typeof response === 'object' &&
          !('json' in response) &&
          !('body' in response) &&
          !('status' in response);
        const resolvedBody =
          response.body ??
          JSON.stringify(
            response.json !== undefined
              ? response.json
              : isPlainObject
                ? response
                : {},
          );
        await route.fulfill({
          status: response.status ?? 200,
          contentType,
          headers: response.headers ?? {},
          body: resolvedBody,
        });
        break;
      }
    }

    if (!matched) {
      recorder.unmatchedCalls.push({ method, path: pathname });
      await route.fulfill({
        status: 599,
        contentType: 'application/json',
        body: JSON.stringify({ error: `Unmatched API route: ${method} ${pathname}` }),
      });
    }
  });

  return recorder;
}
