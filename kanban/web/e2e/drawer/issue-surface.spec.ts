import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { loadFixture, mockApi, type MockRecorder } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const issueKan142 = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
  description_markdown: 'Detailed description of the auth hardening task.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    name: 'In Progress',
    group: 'started',
  },
  etag: '"etag-kan-142"',
};

const issueKan143 = {
  key: 'KAN-143',
  object_id: '22222222-2222-2222-2222-222222222222',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Verify LDAPS certificate pinning',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  etag: '"etag-kan-143"',
};

async function setupMocks(page: Page): Promise<MockRecorder> {
  await page.unroute('**/api/v1/**');
  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/issues/KAN-143': { json: issueKan143 },
    'GET /api/v1/issues/KAN-999': {
      status: 404,
      json: { title: 'Not Found', status: 404 },
    },
    'GET /api/v1/objects/11111111-1111-1111-1111-111111111111/access': {
      json: loadFixture('access-kan-142'),
    },
    'GET /api/v1/objects/KAN/access': {
      json: loadFixture('access-project-kan'),
    },
    'PATCH /api/v1/issues/KAN-142': (req) => {
      const body = req.body as { summary?: string };
      return {
        status: 200,
        json: {
          ...issueKan142,
          summary: body.summary ?? issueKan142.summary,
        },
      };
    },
  });
}

test.describe('IssueSurface E2E Verification & Design Proofs (KB-P3-41)', () => {
  test('01: Zero-remount invariant across 5 round trips & 0 additional GET calls', async ({
    page,
  }) => {
    const recorder = await setupMocks(page);

    await page.goto('/__dev/drawer');
    await page.click('[data-testid="link-kan-142"]');

    const surface = page.locator('.surface--drawer');
    await expect(surface).toBeVisible();

    const initialMountId = await surface.getAttribute('data-mount-id');
    const initialMountSeq = await surface.getAttribute('data-mount-seq');
    expect(initialMountId).toBeTruthy();
    expect(initialMountSeq).toBeTruthy();

    const getCallsInitial = recorder.calls.filter(
      (c) => c.method === 'GET' && c.path === '/api/v1/issues/KAN-142',
    ).length;
    expect(getCallsInitial).toBe(1);

    // 5 round trips: drawer -> full -> drawer -> full ...
    for (let i = 0; i < 5; i++) {
      // Toggle to full screen via button or shortcut
      const fsBtn = page.locator('button[aria-label="Open in full screen"]');
      await fsBtn.click();
      await expect(page.locator('.surface--full')).toBeVisible();

      const fullMountId = await page.locator('.surface--full').getAttribute('data-mount-id');
      const fullMountSeq = await page.locator('.surface--full').getAttribute('data-mount-seq');
      expect(fullMountId).toBe(initialMountId);
      expect(fullMountSeq).toBe(initialMountSeq);

      // Return to drawer via button
      const returnBtn = page.locator('button[aria-label="Return to side panel"]');
      await returnBtn.click();
      await expect(page.locator('.surface--drawer')).toBeVisible();

      const drawerMountId = await page.locator('.surface--drawer').getAttribute('data-mount-id');
      const drawerMountSeq = await page.locator('.surface--drawer').getAttribute('data-mount-seq');
      expect(drawerMountId).toBe(initialMountId);
      expect(drawerMountSeq).toBe(initialMountSeq);
    }

    const getCallsFinal = recorder.calls.filter(
      (c) => c.method === 'GET' && c.path === '/api/v1/issues/KAN-142',
    ).length;
    // Strict requirement: zero additional GET calls during drawer <-> full toggling
    expect(getCallsFinal).toBe(getCallsInitial);
  });

  test('02: Visual proofs across viewports, annotations, style probes, and validation', async (
    { page },
    testInfo,
  ) => {
    await setupMocks(page);

    await page.goto('/__dev/drawer');
    await page.click('[data-testid="link-kan-142"]');

    const drawer = page.locator('.surface--drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.issue-header__key')).toHaveText('KAN-142');
    await expect(page.locator('.summary-field__display-text')).toHaveText(
      'Harden Multi-Card OIDC & LDAPS Auth Studio',
    );

    // Style Probes for computed-styles-<project>.json
    await probeStyles(page, testInfo, {
      name: 'issue-surface-measurements',
      probes: [
        {
          selector: '.surface--drawer',
          props: ['width', 'height'],
        },
        {
          selector: '.surface__prose',
          props: [
            'width',
            'padding-top',
            'padding-right',
            'padding-bottom',
            'padding-left',
            'row-gap',
            'font-size',
            'line-height',
          ],
        },
        {
          selector: '.surface__rail',
          props: ['width', 'top', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left'],
        },
        {
          selector: '.surface__header',
          props: ['min-height', 'column-gap'],
        },
        {
          selector: '.surface__header .emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    // Screenshot 01: 01-drawer-open-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '01-drawer-open',
      annotations: [
        {
          selector: '.surface--drawer',
          label: 'drawer outer edge',
          note: 'min(960px, 68vw) desktop, 696px tablet, 390px mobile',
        },
        {
          selector: '.surface__prose',
          label: 'prose column',
          note: '640px desktop, stacked below on tablet/mobile',
        },
        {
          selector: '.surface__rail',
          label: 'rail region',
          note: '320px, stacked below on tablet/mobile',
        },
        {
          selector: '.surface__prose',
          label: 'prose padding box',
          note: '32px 40px',
        },
        {
          selector: '.issue-header__key',
          label: 'mono key KAN-142',
        },
        {
          selector: '[data-testid="priority-hint"]',
          label: 'priority hint ⚡',
        },
        {
          selector: '[data-testid="access-pill"]',
          label: 'access pill 🛡️ Project + 2',
        },
      ],
    });

    // Screenshot 02: 02-access-hint-open-<project>.png
    const accessHint = page.locator('[data-testid="access-hint"]');
    await accessHint.click();
    const accessDialog = page.locator('div[role="dialog"]');
    await expect(accessDialog).toBeVisible();
    await expect(accessDialog).toContainText(
      'Project: Platform Core - 14 users, 2 groups, 1 agent, 0 deny rules. Inherited from Project.',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '02-access-hint-open',
      annotations: [
        {
          selector: 'div[role="dialog"]',
          label: 'access popup (role=dialog)',
          note: 'Project: Platform Core - 14 users, 2 groups, 1 agent, 0 deny rules. Inherited from Project.',
        },
        {
          selector: 'button:has-text("Open Access Inspector")',
          label: 'action button',
        },
        {
          selector: '[data-testid="access-hint"]',
          label: 'trigger with aria-expanded=true',
        },
      ],
    });

    await page.keyboard.press('Escape');
    await expect(accessDialog).not.toBeVisible();

    // Screenshot 03: 03-priority-hint-open-<project>.png
    const priorityHint = page.locator('[data-testid="priority-hint"]');
    await priorityHint.focus();
    const priorityTooltip = page.locator('div[role="tooltip"]');
    await expect(priorityTooltip).toBeVisible();
    await expect(priorityTooltip).toContainText(
      'Priority: High - sort weight 2. SLA target: not configured. Press P to change.',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '03-priority-hint-open',
      annotations: [
        {
          selector: 'div[role="tooltip"]',
          label: 'priority tooltip (role=tooltip)',
          note: 'Priority: High - sort weight 2. SLA target: not configured. Press P to change.',
        },
        {
          selector: '[data-testid="priority-hint"]',
          label: 'trigger',
        },
      ],
    });

    await page.keyboard.press('Escape');

    // Screenshot 04: 04-full-screen-<project>.png
    // Enter edit mode, type draft text, and toggle full screen
    const editBtn = page.locator('.summary__edit');
    await editBtn.click();
    const summaryTextarea = page.locator('.summary-field__textarea');
    await expect(summaryTextarea).toBeVisible();
    await summaryTextarea.pressSequentially(' (Draft in progress)');

    const initialMountIdForFs = await page.locator('.surface--drawer').getAttribute('data-mount-id');

    // Toggle full screen via button
    await page.click('button[aria-label="Open in full screen"]');
    const fullSurface = page.locator('.surface--full');
    await expect(fullSurface).toBeVisible();

    const fsMountId = await fullSurface.getAttribute('data-mount-id');
    expect(fsMountId).toBe(initialMountIdForFs);

    // Unsaved draft text is preserved in full screen
    await expect(summaryTextarea).toHaveValue(
      'Harden Multi-Card OIDC & LDAPS Auth Studio (Draft in progress)',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '04-full-screen',
      annotations: [
        {
          selector: '.surface--full',
          label: 'surface in .surface--full',
          note: `data-mount-id: ${fsMountId ?? ''}`,
        },
        {
          selector: '.summary-field__textarea',
          label: 'draft text preserved in textarea',
        },
        {
          selector: '.surface__prose-inner',
          label: 'prose inner max width (640px)',
        },
        {
          selector: 'button[aria-label="Return to side panel"]',
          label: 'toggle button now Return to side panel',
        },
      ],
    });

    // Screenshot 05: 05-summary-validation-<project>.png
    // Clear textarea to empty string to trigger validation
    await summaryTextarea.fill('');
    const validationAlert = page.locator('.summary-field__error[role="alert"]');
    await expect(validationAlert).toBeVisible();
    await expect(validationAlert).toHaveText('Summary cannot be empty.');

    await annotatedScreenshot(page, testInfo, {
      name: '05-summary-validation',
      annotations: [
        {
          selector: '.summary-field__textarea',
          label: 'empty summary textarea',
        },
        {
          selector: '.summary-field__error[role="alert"]',
          label: 'role=alert text: Summary cannot be empty.',
        },
      ],
    });

    // Revert summary via Escape
    await page.keyboard.press('Escape');
    await expect(summaryTextarea).not.toBeVisible();

    // Screenshot 06: 06-not-found-<project>.png
    await page.goto('/__dev/drawer?peek=KAN-999');
    const notFoundMsg = page.locator('.surface__error-message');
    await expect(notFoundMsg).toBeVisible();
    await expect(notFoundMsg).toHaveText(
      'Issue KAN-999 was not found or you do not have access.',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '06-not-found',
      annotations: [
        {
          selector: '.surface__error-message',
          label: 'anti-enumeration error message',
          note: 'Issue KAN-999 was not found or you do not have access.',
        },
      ],
    });

    // Screenshot 07: 07-focus-return-<project>.png
    await page.goto('/__dev/drawer');
    const openerLink = page.locator('[data-testid="link-kan-142"]');
    await openerLink.click();
    await expect(page.locator('.surface--drawer')).toBeVisible();

    // Close drawer via Escape
    await page.keyboard.press('Escape');
    await expect(page.locator('.surface--drawer')).not.toBeVisible();
    await expect(openerLink).toBeFocused();

    await annotatedScreenshot(page, testInfo, {
      name: '07-focus-return',
      annotations: [
        {
          selector: '[data-testid="link-kan-142"]',
          label: 'focus-visible ring on opener link',
        },
      ],
    });
  });
});
