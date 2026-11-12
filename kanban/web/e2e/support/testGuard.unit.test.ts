import { describe, it, expect, vi } from 'vitest';
import { testGuardFixture } from './test';
import type { Page, Route, Request, ConsoleMessage } from '@playwright/test';

describe('testGuardFixture', () => {
  it('passes cleanly when zero violations occur', async () => {
    const addInitScriptMock = vi.fn().mockImplementation((fn: () => void) => {
      fn();
      // Dispatch synthetic securitypolicyviolation event to verify handler
      const event = new Event('securitypolicyviolation');
      Object.assign(event, { violatedDirective: 'none', blockedURI: '' });
      document.dispatchEvent(event);
      window.__cspViolations = []; // clear so it passes cleanly
      return Promise.resolve();
    });

    const fakePage = {
      addInitScript: addInitScriptMock,
      on: vi.fn(),
      route: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockImplementation((fn: () => unknown) => {
        return Promise.resolve(typeof fn === 'function' ? fn() : fn);
      }),
    } as unknown as Page;

    let useCalled = false;
    await testGuardFixture({ page: fakePage }, async (recorder) => {
      useCalled = true;
      expect(recorder).toBeDefined();
      await Promise.resolve();
    });

    expect(useCalled).toBe(true);
    expect(addInitScriptMock).toHaveBeenCalled();
  });

  it('fails when CSP violations are recorded', async () => {
    window.__cspViolations = [
      { violatedDirective: "style-src 'self'", blockedURI: '' },
    ];
    const fakePage = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      on: vi.fn(),
      route: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockImplementation((fn: () => unknown) => {
        return Promise.resolve(typeof fn === 'function' ? fn() : fn);
      }),
    } as unknown as Page;

    try {
      await expect(
        testGuardFixture({ page: fakePage }, async () => {
          // do nothing
        }),
      ).rejects.toThrow('CSP violations detected');
    } finally {
      delete window.__cspViolations;
    }
  });

  it('fails when console errors or page errors occur', async () => {
    delete window.__cspViolations;
    const listeners: Record<string, (arg: unknown) => void> = {};
    const fakePage = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      on: vi.fn().mockImplementation((event: string, cb: (arg: unknown) => void) => {
        listeners[event] = cb;
      }),
      route: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockImplementation((fn: () => unknown) => {
        return Promise.resolve(typeof fn === 'function' ? fn() : fn);
      }),
    } as unknown as Page;

    await expect(
      testGuardFixture({ page: fakePage }, async () => {
        const fakeMsg = {
          type: () => 'error',
          text: () => 'Simulated console error',
        } as unknown as ConsoleMessage;
        listeners.console?.(fakeMsg);
        listeners.pageerror?.(new Error('Simulated page crash'));
        await Promise.resolve();
      }),
    ).rejects.toThrow('Console errors detected');
  });

  it('blocks and fails on off-origin requests', async () => {
    let globalRouteHandler: ((route: Route) => Promise<void>) | undefined;
    const fakePage = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      on: vi.fn(),
      route: vi.fn().mockImplementation((pattern: string, handler: (route: Route) => Promise<void>) => {
        if (pattern === '**') {
          globalRouteHandler = handler;
        }
        return Promise.resolve();
      }),
      evaluate: vi.fn().mockResolvedValue([]),
    } as unknown as Page;

    await expect(
      testGuardFixture({ page: fakePage }, async () => {
        const abortMock = vi.fn().mockResolvedValue(undefined);
        const continueMock = vi.fn().mockResolvedValue(undefined);

        const localReq = {
          url: () => 'http://127.0.0.1:4173/assets/test.js',
        } as unknown as Request;
        const localRoute = {
          request: () => localReq,
          continue: continueMock,
          abort: abortMock,
        } as unknown as Route;
        if (globalRouteHandler) {
          await globalRouteHandler(localRoute);
        }
        expect(continueMock).toHaveBeenCalled();

        const evilReq = {
          url: () => 'http://evil.com/tracker.js',
        } as unknown as Request;
        const evilRoute = {
          request: () => evilReq,
          continue: continueMock,
          abort: abortMock,
        } as unknown as Route;
        if (globalRouteHandler) {
          await globalRouteHandler(evilRoute);
        }
        expect(abortMock).toHaveBeenCalled();
      }),
    ).rejects.toThrow('Off-origin requests blocked');
  });

  it('ignores non-error console messages and handles page closed during teardown', async () => {
    const listeners: Record<string, (arg: unknown) => void> = {};
    const fakePage = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      on: vi.fn().mockImplementation((event: string, cb: (arg: unknown) => void) => {
        listeners[event] = cb;
      }),
      route: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockRejectedValue(new Error('Target page, context or browser has been closed')),
    } as unknown as Page;

    await testGuardFixture({ page: fakePage }, async () => {
      listeners.console?.({
        type: () => 'info',
        text: () => 'non-error info',
      });
      listeners.console?.({
        type: () => 'error',
        text: () => 'The source list for the Content Security Policy directive ...',
      });
      await Promise.resolve();
    });
  });

  it('fails when unmatched API calls are recorded', async () => {
    const fakePage = {
      addInitScript: vi.fn().mockResolvedValue(undefined),
      on: vi.fn(),
      route: vi.fn().mockResolvedValue(undefined),
      evaluate: vi.fn().mockResolvedValue([]),
    } as unknown as Page;

    await expect(
      testGuardFixture({ page: fakePage }, async (recorder) => {
        recorder.unmatchedCalls.push({ method: 'GET', path: '/api/v1/unknown' });
        await Promise.resolve();
      }),
    ).rejects.toThrow('Unmatched API calls detected');
  });
});
