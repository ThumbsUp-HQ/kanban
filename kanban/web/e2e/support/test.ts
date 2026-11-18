import { test as baseTest, expect } from '@playwright/test';
import { mockApi, loadFixture, type MockRecorder } from './mockApi';
import type { Page } from '@playwright/test';

declare global {
  interface Window {
    __cspViolations?: { violatedDirective: string; blockedURI: string }[];
  }
}

export interface TestFixtures {
  mockRecorder: MockRecorder;
}

/**
 * Auto-fixture function that sets up CSP violation listeners,
 * error collectors, off-origin request blocking, and default API mocks.
 */
export async function testGuardFixture(
  { page }: { page: Page },
  use: (r: MockRecorder) => Promise<void>,
): Promise<void> {
  // 1. Register CSP violation listener before any scripts run
  await page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      window.__cspViolations?.push({
        violatedDirective: e.violatedDirective,
        blockedURI: e.blockedURI,
      });
    });
  });

  // 2. Track console errors and unhandled page errors
  const consoleErrors: string[] = [];
  const pageErrors: Error[] = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Ignore browser CSP parser warnings for S5.4 MIME-scoped data: sources
      if (text.startsWith('The source list for the Content Security Policy directive')) {
        return;
      }
      // Ignore expected 401, 403, 404, 409, 412, 429 resource errors from negative test fixtures
      if (
        text.includes('Failed to load resource: the server responded with a status of 401') ||
        text.includes('Failed to load resource: the server responded with a status of 403') ||
        text.includes('Failed to load resource: the server responded with a status of 404') ||
        text.includes('Failed to load resource: the server responded with a status of 409') ||
        text.includes('Failed to load resource: the server responded with a status of 412') ||
        text.includes('Failed to load resource: the server responded with a status of 429')
      ) {
        return;
      }
      consoleErrors.push(text);
    }
  });

  page.on('pageerror', (err) => {
    pageErrors.push(err);
  });

  // 3. Block all off-origin network requests
  const offOriginRequests: string[] = [];
  await page.route('**', (route) => {
    const urlStr = route.request().url();
    const port = process.env.E2E_PORT ?? '4173';
    if (
      urlStr.startsWith(`http://127.0.0.1:${port}`) ||
      urlStr.startsWith(`http://localhost:${port}`)
    ) {
      return route.continue();
    }
    offOriginRequests.push(urlStr);
    return route.abort();
  });

  // 4. Default API mock handlers
  const recorder = await mockApi(page, {
    'GET /api/v1/me': loadFixture('me-adam'),
    'GET /api/v1/system/status': loadFixture('system-status-prod'),
    'GET /api/v1/workspaces': {
      json: {
        items: [{ id: 'ws-default', slug: 'kanban', name: '👍kanban Workspace' }],
        active_workspace_id: 'ws-default',
      },
    },
    'GET /api/v1/media-proxy': {
      status: 200,
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
        'base64',
      ),
    },
  });

  // Run test
  // eslint-disable-next-line react-hooks/rules-of-hooks
  await use(recorder);

  // 5. Post-test assertions verifying zero violations
  let cspViolations: { violatedDirective: string; blockedURI: string }[] = [];
  try {
    cspViolations = await page.evaluate(() => window.__cspViolations ?? []);
  } catch {
    // Page was closed before evaluation
  }

  const issues: string[] = [];
  if (cspViolations.length > 0) {
    issues.push(
      `CSP violations detected (${String(cspViolations.length)}): ${cspViolations
        .map((v) => `${v.violatedDirective} (${v.blockedURI})`)
        .join(', ')}`,
    );
  }
  if (consoleErrors.length > 0) {
    issues.push(
      `Console errors detected (${String(consoleErrors.length)}): ${consoleErrors.join('; ')}`,
    );
  }
  if (pageErrors.length > 0) {
    issues.push(
      `Page errors detected (${String(pageErrors.length)}): ${pageErrors.map((e) => e.message).join('; ')}`,
    );
  }
  if (offOriginRequests.length > 0) {
    issues.push(
      `Off-origin requests blocked (${String(offOriginRequests.length)}): ${offOriginRequests.join(', ')}`,
    );
  }
  if (recorder.unmatchedCalls.length > 0) {
    issues.push(
      `Unmatched API calls detected (${String(recorder.unmatchedCalls.length)}): ${recorder.unmatchedCalls
        .map((c) => `${c.method} ${c.path}`)
        .join(', ')}`,
    );
  }

  if (issues.length > 0) {
    throw new Error(`Test guard verification failure:\n${issues.join('\n')}`);
  }
}

export const test = baseTest.extend<TestFixtures>({
  mockRecorder: [testGuardFixture, { auto: true }],
});

export { expect };
