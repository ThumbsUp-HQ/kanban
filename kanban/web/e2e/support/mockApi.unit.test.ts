import { describe, it, expect, vi } from 'vitest';
import { loadFixture, matchRoute, parseRouteKey, mockApi } from './mockApi';
import type { Page, Route, Request } from '@playwright/test';

describe('mockApi support module', () => {
  describe('loadFixture', () => {
    it('successfully loads existing json fixtures', () => {
      const me = loadFixture<{ user: string }>('me-adam');
      expect(me.user).toBe('@adam');

      const project = loadFixture<{ key: string }>('project-kan');
      expect(project.key).toBe('KAN');
    });

    it('throws on invalid or path-traversal names', () => {
      expect(() => loadFixture('../secrets')).toThrow('Invalid fixture name: ../secrets');
      expect(() => loadFixture('invalid/name')).toThrow('Invalid fixture name: invalid/name');
      expect(() => loadFixture('bad name')).toThrow('Invalid fixture name: bad name');
    });
  });

  describe('parseRouteKey', () => {
    it('correctly parses method and path pattern', () => {
      const { method, pathPattern } = parseRouteKey('GET /api/v1/issues/:issueKey');
      expect(method).toBe('GET');
      expect(pathPattern).toBe('/api/v1/issues/:issueKey');
    });

    it('handles key without space', () => {
      const { method, pathPattern } = parseRouteKey('GET');
      expect(method).toBe('GET');
      expect(pathPattern).toBe('');
    });
  });

  describe('matchRoute', () => {
    it('matches parameterized routes and extracts parameters', () => {
      const result = matchRoute('/api/v1/issues/:issueKey', '/api/v1/issues/KAN-142');
      expect(result.matched).toBe(true);
      expect(result.params).toEqual({ issueKey: 'KAN-142' });
    });

    it('does not match routes with different segment counts', () => {
      const result = matchRoute('/api/v1/issues/:issueKey', '/api/v1/issues/KAN-142/activity');
      expect(result.matched).toBe(false);
      expect(result.params).toEqual({});
    });

    it('does not match routes with differing static segments', () => {
      const result = matchRoute('/api/v1/issues/:issueKey', '/api/v1/projects/KAN-142');
      expect(result.matched).toBe(false);
      expect(result.params).toEqual({});
    });
  });

  describe('mockApi router', () => {
    it('routes matching requests and fulfills response', async () => {
      let registeredHandler: ((route: Route) => Promise<void>) | undefined;
      const routeMock = vi.fn().mockImplementation((pattern: string, handler: (route: Route) => Promise<void>) => {
        registeredHandler = handler;
        return Promise.resolve();
      });
      const fakePage = {
        route: routeMock,
      } as unknown as Page;

      const recorder = await mockApi(fakePage, {
        'POST /api/v1/other': { status: 204 },
        'GET /api/v1/issues/:issueKey': (req) => ({
          status: 200,
          json: { key: req.params.issueKey },
        }),
      });

      expect(routeMock).toHaveBeenCalledWith('**/api/v1/**', expect.any(Function));

      // Simulate a matching request
      const fulfillMock = vi.fn().mockResolvedValue(undefined);
      const fakeRequest = {
        url: () => 'http://127.0.0.1:4173/api/v1/issues/KAN-142',
        method: () => 'GET',
        postData: () => null,
        headers: () => ({ 'x-test': '1' }),
      } as unknown as Request;

      const fakeRoute = {
        request: () => fakeRequest,
        fulfill: fulfillMock,
      } as unknown as Route;

      if (registeredHandler) {
        await registeredHandler(fakeRoute);
      }

      expect(fulfillMock).toHaveBeenCalledWith({
        status: 200,
        contentType: 'application/json',
        headers: {},
        body: JSON.stringify({ key: 'KAN-142' }),
      });
      expect(recorder.calls.length).toBe(1);
      expect(recorder.calls[0]?.params).toEqual({ issueKey: 'KAN-142' });
      expect(recorder.unmatchedCalls.length).toBe(0);
    });

    it('returns 599 and records unmatched API routes', async () => {
      let registeredHandler: ((route: Route) => Promise<void>) | undefined;
      const fakePage = {
        route: vi.fn().mockImplementation((pattern: string, handler: (route: Route) => Promise<void>) => {
          registeredHandler = handler;
          return Promise.resolve();
        }),
      } as unknown as Page;

      const recorder = await mockApi(fakePage, {
        'GET /api/v1/issues': { status: 200, json: [] },
      });

      // Simulate an unmatched request with non-JSON postData to test fallback body parsing
      const fulfillMock = vi.fn().mockResolvedValue(undefined);
      const fakeRequest = {
        url: () => 'http://127.0.0.1:4173/api/v1/unknown-endpoint',
        method: () => 'POST',
        postData: () => 'plain text non-json',
        headers: () => ({}),
      } as unknown as Request;

      const fakeRoute = {
        request: () => fakeRequest,
        fulfill: fulfillMock,
      } as unknown as Route;

      if (registeredHandler) {
        await registeredHandler(fakeRoute);
      }

      expect(fulfillMock).toHaveBeenCalledWith({
        status: 599,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Unmatched API route: POST /api/v1/unknown-endpoint' }),
      });
      expect(recorder.unmatchedCalls.length).toBe(1);
      expect(recorder.unmatchedCalls[0]).toEqual({
        method: 'POST',
        path: '/api/v1/unknown-endpoint',
      });
    });

    it('supports response delayMs', async () => {
      let registeredHandler: ((route: Route) => Promise<void>) | undefined;
      const fakePage = {
        route: vi.fn().mockImplementation((pattern: string, handler: (route: Route) => Promise<void>) => {
          registeredHandler = handler;
          return Promise.resolve();
        }),
      } as unknown as Page;

      await mockApi(fakePage, {
        'GET /api/v1/delayed': {
          status: 200,
          json: { ok: true },
          delayMs: 10,
        },
      });

      const fulfillMock = vi.fn().mockResolvedValue(undefined);
      const fakeRequest = {
        url: () => 'http://127.0.0.1:4173/api/v1/delayed',
        method: () => 'GET',
        postData: () => null,
        headers: () => ({}),
      } as unknown as Request;

      const fakeRoute = {
        request: () => fakeRequest,
        fulfill: fulfillMock,
      } as unknown as Route;

      const start = Date.now();
      if (registeredHandler) {
        await registeredHandler(fakeRoute);
      }
      expect(Date.now() - start).toBeGreaterThanOrEqual(8);
      expect(fulfillMock).toHaveBeenCalledWith(
        expect.objectContaining({ status: 200 }),
      );
    });

    it('falls back to default status, empty headers, and empty body when omitted', async () => {
      let registeredHandler: ((route: Route) => Promise<void>) | undefined;
      const fakePage = {
        route: vi.fn().mockImplementation((pattern: string, handler: (route: Route) => Promise<void>) => {
          registeredHandler = handler;
          return Promise.resolve();
        }),
      } as unknown as Page;

      await mockApi(fakePage, {
        'GET /api/v1/first-path': {},
        'GET /api/v1/second-path': { status: 201, headers: { 'x-custom': 'abc' } },
      });

      // Call second-path to trigger match.matched === false on first-path
      const fulfillMock = vi.fn().mockResolvedValue(undefined);
      const fakeRequest = {
        url: () => 'http://127.0.0.1:4173/api/v1/second-path',
        method: () => 'GET',
        postData: () => null,
        headers: () => ({}),
      } as unknown as Request;

      const fakeRoute = {
        request: () => fakeRequest,
        fulfill: fulfillMock,
      } as unknown as Route;

      if (registeredHandler) {
        await registeredHandler(fakeRoute);
      }

      expect(fulfillMock).toHaveBeenCalledWith({
        status: 201,
        contentType: 'application/json',
        headers: { 'x-custom': 'abc' },
        body: JSON.stringify({}),
      });

      // Call first-path to verify status 200 and empty headers fallback
      const fulfillMock2 = vi.fn().mockResolvedValue(undefined);
      const fakeRequest2 = {
        url: () => 'http://127.0.0.1:4173/api/v1/first-path',
        method: () => 'GET',
        postData: () => null,
        headers: () => ({}),
      } as unknown as Request;

      const fakeRoute2 = {
        request: () => fakeRequest2,
        fulfill: fulfillMock2,
      } as unknown as Route;

      if (registeredHandler) {
        await registeredHandler(fakeRoute2);
      }

      expect(fulfillMock2).toHaveBeenCalledWith({
        status: 200,
        contentType: 'application/json',
        headers: {},
        body: JSON.stringify({}),
      });
    });
  });
});
