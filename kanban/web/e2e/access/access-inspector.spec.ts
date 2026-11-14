import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { loadFixture, mockApi, type MockRecorder } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const OBJECT_ID_142 = 'c0000000-0000-0000-0000-000000000142';
const OBJECT_ID_REDACTED = 'c0000000-0000-0000-0000-000000000143';

const issueKan142 = {
  key: 'KAN-142',
  object_id: OBJECT_ID_142,
  project_key: 'KAN',
  project_name: 'kanban',
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

async function setupMocks(page: Page): Promise<MockRecorder> {
  await page.unroute('**/api/v1/**');
  const kan142Access = loadFixture('access-inspector-kan-142');
  const redactedAccess = loadFixture('access-inspector-redacted');

  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/me': { json: loadFixture('me-adam') },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/issues/KAN-143': {
      json: {
        key: 'KAN-143',
        object_id: OBJECT_ID_REDACTED,
        project_key: 'KAN',
        summary: 'Redacted access check',
      },
    },
    'GET /api/v1/issues/KAN-999': {
      status: 404,
      json: { title: 'Not Found', status: 404 },
    },
    'GET /api/v1/issues/KAN-142/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/state': { json: { name: 'In Progress', group: 'started' } },
    'GET /api/v1/issues/KAN-142/subscription': { json: { subscribed: false } },
    'GET /api/v1/objects/KAN-142/canonical-url': { json: { url: '/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/projects/KAN/priorities': { json: { items: [] } },
    'GET /api/v1/projects/KAN/labels': { json: { items: [] } },
    'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
    'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
    'GET /api/v1/objects/KAN-142/access': { json: kan142Access },
    [`GET /api/v1/objects/${OBJECT_ID_142}/access`]: { json: kan142Access },
    [`GET /api/v1/objects/${OBJECT_ID_REDACTED}/access`]: { json: redactedAccess },
    [`POST /api/v1/objects/${OBJECT_ID_142}/access/agent-kill-switch`]: {
      json: {
        ...(kan142Access as Record<string, unknown>),
        agents: [],
      },
    },
  });
}

test.describe('Effective Access Inspector E2E & Design Proofs (KB-P3-49, S3.4)', () => {
  test('01: Opens from access pill, full sections, whitespace probe, and S3.4 proof', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/__dev/drawer');
    await page.click('[data-testid="link-kan-142"]');

    // Wait for drawer surface to be visible
    const surface = page.locator('.surface--drawer');
    await expect(surface).toBeVisible();

    // Access pill exists in drawer header
    const accessPill = page.locator('[data-testid="access-pill"]');
    await expect(accessPill).toBeVisible();

    // Open Access Inspector Popover via custom event on host
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, OBJECT_ID_142);

    const dialog = page.locator('div.access-inspector[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Verify Title & Manage Access button
    await expect(dialog.locator('.access-inspector__title')).toContainText(
      'EFFECTIVE ACCESS FOR ISSUE',
    );
    await expect(dialog.locator('.access-inspector__title .mono')).toHaveText('KAN-142');
    const manageBtn = dialog.locator('button.access-inspector__btn--secondary');
    await expect(manageBtn).toBeVisible();
    await expect(manageBtn).toHaveText('[Manage Access...]');

    // Verify Inherited Scope banner
    await expect(dialog.locator('.access-inspector__scope-banner')).toContainText(
      'Inherited Scope:',
    );
    await expect(dialog.locator('.access-inspector__scope-badge')).toContainText(
      'Project "kanban" (Workspace: Default)',
    );

    // Verify Users Section (2 Direct)
    await expect(dialog).toContainText('👤 USERS (2 Direct)');
    await expect(dialog).toContainText('Adam Outler');
    await expect(dialog).toContainText('@adam');
    await expect(dialog).toContainText('Maya Lin');
    await expect(dialog).toContainText('@maya');

    // Verify Groups Section (2)
    await expect(dialog).toContainText('👥 GROUPS (2)');
    await expect(dialog).toContainText('Core Backend');
    await expect(dialog).toContainText('(11 members, LDAPS synced)');
    await expect(dialog).toContainText('SecOps Reviewers');
    await expect(dialog).toContainText('(4 members, OIDC)');

    // Verify Agents & Workflow Runners Section (2 Active)
    await expect(dialog).toContainText('🤖 AGENTS & WORKFLOW RUNNERS (2 Active)');
    await expect(dialog).toContainText('Local Sparkle');
    await expect(dialog).toContainText('(ollama/qwen2.5-coder)');
    await expect(dialog).toContainText('Transition Gate');
    await expect(dialog).toContainText('(cli: agy -p, :ro repo)');
    const killSwitchBtn = dialog.locator('button.access-inspector__kill-switch-btn');
    await expect(killSwitchBtn).toBeVisible();

    // Verify Restricted Overrides (1)
    await expect(dialog).toContainText('🔒 RESTRICTED OVERRIDES (1)');
    await expect(dialog).toContainText('Contractors Group');
    const denyPill = dialog.locator('.access-inspector__deny-pill');
    await expect(denyPill).toBeVisible();
    await expect(denyPill).toHaveText('Explicit DENY');

    // Probe computed whitespace styles
    await probeStyles(page, testInfo, {
      name: 'access-inspector-styles',
      probes: [
        {
          selector: '.access-inspector',
          props: ['width', 'max-height', 'background-color', 'border-radius', 'z-index'],
        },
        {
          selector: '.access-inspector__row',
          props: ['min-height', 'padding-top', 'padding-bottom', 'box-sizing'],
        },
        {
          selector: '.access-inspector .emoji-hint',
          props: ['width', 'height'],
        },
        {
          selector: '.access-inspector__deny-pill',
          props: ['color', 'background-color'],
        },
      ],
    });

    // Capture Annotated Screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-inspector-full-s34',
      annotations: [
        {
          selector: '.access-inspector__header',
          label: 'header EFFECTIVE ACCESS FOR ISSUE KAN-142 + [Manage Access...]',
          note: 'Title with mono key and admin manage access action',
        },
        {
          selector: '.access-inspector__scope-banner',
          label: 'Inherited Scope banner',
          note: 'Transparent project inheritance without enumeration',
        },
        {
          selector: '.access-inspector__section:nth-of-type(1) .access-inspector__row',
          label: 'USERS (2 Direct) rows (38px)',
          note: 'Display name, mono handle, capability badge and source tag',
        },
        {
          selector: '.access-inspector__section:nth-of-type(2) .access-inspector__row',
          label: 'GROUPS (2) with LDAPS/OIDC counts',
          note: 'Directory synced group member count and capability badge',
        },
        {
          selector: '.access-inspector__section:nth-of-type(3)',
          label: 'AGENTS & WORKFLOW RUNNERS (2 Active) + [ Kill Switch ]',
          note: 'Autonomous runners, provider badges, and admin kill switch button',
        },
        {
          selector: '.access-inspector__deny-pill',
          label: 'RESTRICTED OVERRIDES (1) Explicit DENY',
          note: 'High-contrast explicit deny pill with danger palette',
        },
      ],
    });
  });

  test('02: Agent kill switch inline confirmation and Cancel focus ring', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/__dev/drawer');
    await page.click('[data-testid="link-kan-142"]');

    // Open Access Inspector Popover
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, OBJECT_ID_142);

    const dialog = page.locator('div.access-inspector[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Click [ Kill Switch ]
    const killSwitchBtn = dialog.locator('button.access-inspector__kill-switch-btn');
    await expect(killSwitchBtn).toBeVisible();
    await killSwitchBtn.click();

    // Verify inline confirmation banner
    const confirmStrip = dialog.locator('.access-inspector__kill-switch-confirm');
    await expect(confirmStrip).toBeVisible();
    await expect(confirmStrip).toContainText('Revoke all active agent grants on KAN-142?');

    const cancelBtn = dialog.locator('.access-inspector__btn--cancel');
    const confirmBtn = dialog.locator('.access-inspector__btn--danger');
    await expect(cancelBtn).toBeVisible();
    await expect(confirmBtn).toBeVisible();

    // Crucial security invariant: focus MUST default to Cancel to prevent accidental Enter confirmation
    await expect(cancelBtn).toBeFocused();

    // Capture Annotated Screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-agent-kill-switch-confirm',
      annotations: [
        {
          selector: '.access-inspector__kill-switch-confirm',
          label: 'inline confirmation banner',
          note: 'Two-step destructive action confirmation strip',
        },
        {
          selector: '.access-inspector__btn--cancel',
          label: '[Cancel] with initial focus ring',
          note: 'Default focus on cancel prevents accidental enter execution',
        },
        {
          selector: '.access-inspector__btn--danger',
          label: '[Confirm Kill Switch] button',
          note: 'Optimistic revocation hook with CSRF protection',
        },
      ],
    });
  });

  test('03: Non-admin caller with redacted external principals and zero data leakage', async ({
    page,
  }, testInfo) => {
    await setupMocks(page);

    await page.goto('/__dev/drawer');

    // Open Access Inspector Popover for redacted non-admin object
    await page.evaluate((objectId) => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId },
        }),
      );
    }, OBJECT_ID_REDACTED);

    const dialog = page.locator('div.access-inspector[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Redacted External Collaborator row is visible
    const redactedRow = dialog.locator('.access-inspector__row--redacted');
    await expect(redactedRow).toBeVisible();
    await expect(redactedRow).toContainText('1 External Collaborator - outside your visibility boundary');

    // Zero handle or email leakage anywhere on page
    const pageContent = await page.textContent('body');
    expect(pageContent).not.toContain('secret@vendor.io');

    // Literal XSS suppression
    await expect(dialog).toContainText('<img src=x onerror=alert(1)>');
    const imgElements = await dialog.locator('img').count();
    expect(imgElements).toBe(0);

    // Non-admin caller cannot see [Manage Access...] or [ Kill Switch ]
    const manageBtn = dialog.locator('button.access-inspector__btn--secondary');
    await expect(manageBtn).toHaveCount(0);
    const killSwitchBtn = dialog.locator('button.access-inspector__kill-switch-btn');
    await expect(killSwitchBtn).toHaveCount(0);

    // Capture Annotated Screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-redacted-external-collaborator',
      annotations: [
        {
          selector: '.access-inspector__row--redacted',
          label: '1 External Collaborator row with zero handle/email leakage',
          note: 'Anti-enumeration defense-in-depth sanitization',
        },
        {
          selector: '.access-inspector__header',
          label: '[Manage Access...] and [ Kill Switch ] absent for non-admin',
          note: 'Strict capability gating hiding privileged actions',
        },
      ],
    });
  });
});
